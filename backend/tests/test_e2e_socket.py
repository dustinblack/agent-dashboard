import pytest
import subprocess
import time
import httpx
import socketio
import socket
import os

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def live_server():
    port = get_free_port()
    # Find project root to point to .venv/bin/uvicorn
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    uvicorn_path = os.path.join(project_root, ".venv/bin/uvicorn")
    
    # Ensure we are in the backend directory or point to it
    cmd = [uvicorn_path, "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    
    # We need to set up the environment so it doesn't try to use real OIDC
    env = os.environ.copy()
    env["BYPASS_AUTH"] = "true"
    env["DATABASE_URL"] = "sqlite:///./test.db"
    
    # Find backend dir relative to current project root
    # This test file is in backend/tests/test_e2e_socket.py
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_path = os.path.join(backend_dir, "test.db")
    
    # Remove old test DB
    if os.path.exists(db_path):
        os.remove(db_path)
        
    proc = subprocess.Popen(cmd, env=env, cwd=backend_dir)
    url = f"http://127.0.0.1:{port}"
    
    # Wait for server to be ready
    for _ in range(50):
        try:
            httpx.get(url)
            break
        except httpx.RequestError:
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError("Server failed to start")
        
    yield url
    proc.terminate()
    proc.wait()
    if os.path.exists(db_path):
        os.remove(db_path)

def test_api_and_cors_e2e(live_server):
    """Test standard API and CORS headers on a live server."""
    headers = {"Origin": "http://localhost:8080"}
    
    # Create a host via API (simulating UI interaction)
    r_post = httpx.post(
        f"{live_server}/hosts", 
        json={"name": "e2e-host", "host_token": "e2e-token"},
        headers=headers
    )
    assert r_post.status_code == 200
    assert r_post.headers.get("access-control-allow-origin") == "http://localhost:8080"
    
    host_data = r_post.json()
    assert host_data["name"] == "e2e-host"


def test_agent_spawning_e2e(live_server):
    """Test the full agent spawning flow from UI -> Backend -> Host Daemon."""
    
    # 1. Register host
    r_host = httpx.post(
        f"{live_server}/hosts", 
        json={"name": "spawn-host-2", "host_token": "spawn-token-2"}
    )
    host_id = r_host.json()["id"]

    # 2. Host Daemon connects
    host_sio = socketio.Client()
    spawn_events = []
    
    @host_sio.on("spawn_agent", namespace="/terminal")
    def on_spawn(data):
        spawn_events.append(data)

    host_sio.connect(
        live_server, 
        namespaces=["/terminal"], 
        headers={"x-host-token": "spawn-token-2"}
    )

    # 3. UI triggers spawn via REST API
    r_spawn = httpx.post(
        f"{live_server}/agents/spawn",
        json={"host_id": host_id, "tool_name": "gemini"}
    )
    assert r_spawn.status_code == 200
    agent_data = r_spawn.json()
    agent_uuid = agent_data["agent_id"]

    # 4. Verify Host Daemon received the spawn event
    for _ in range(20):
        if spawn_events:
            break
        time.sleep(0.1)

    assert len(spawn_events) == 1
    assert spawn_events[0]["agent_id"] == agent_uuid
    assert spawn_events[0]["tool"] == "gemini"

    host_sio.disconnect()


def test_http_endpoints(live_server):
    """Simple test of REST endpoints."""
    # List hosts
    r = httpx.get(f"{live_server}/hosts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # Register a host
    r = httpx.post(f"{live_server}/hosts", json={"name": "test-host", "host_token": "secret"})
    assert r.status_code == 200
    host_id = r.json()["id"]

    # List agents
    r = httpx.get(f"{live_server}/agents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_socketio_connection(live_server):
    """Test Socket.IO connection and registration."""
    sio = socketio.Client()
    connected = []
    
    @sio.on("connect", namespace="/terminal")
    def on_connect():
        connected.append(True)
        
    # Connect with a valid host token
    # First register the host
    httpx.post(f"{live_server}/hosts", json={"name": "spawn-host", "host_token": "spawn-token"})
    
    sio.connect(live_server, namespaces=["/terminal"], headers={"x-host-token": "spawn-token"})
    time.sleep(0.5)
    
    assert len(connected) > 0
    sio.disconnect()

def test_socketio_relay_multiplex_e2e(live_server):
    """Test I/O relay multiplexed by agent_id."""
    
    # 1. Register and connect host
    r_host = httpx.post(
        f"{live_server}/hosts", 
        json={"name": "relay-host", "host_token": "relay-token"}
    )
    relay_host_id = r_host.json()["id"]
    
    host_sio = socketio.Client()
    host_received_input = []
    host_received_events = []
    
    @host_sio.on("terminal_input", namespace="/terminal")
    def on_input(data):
        host_received_input.append(data)

    @host_sio.on("request_history", namespace="/terminal")
    def on_history(data):
        host_received_events.append(("request_history", data))

    @host_sio.on("request_projects", namespace="/terminal")
    def on_request_projects(data):
        host_received_events.append(("request_projects", data))

    host_sio.connect(
        live_server, 
        namespaces=["/terminal"], 
        headers={"x-host-token": "relay-token"}
    )
    
    # We'll use a REAL agent_id from the DB
    r_spawn = httpx.post(
        f"{live_server}/agents/spawn",
        json={"host_id": relay_host_id, "tool_name": "bash"}
    )
    agent_id = r_spawn.json()["agent_id"]
    
    # 2. UI connects
    ui_sio = socketio.Client()
    ui_received_output = []
    ui_received_host_telemetry = []
    ui_received_tel_updates = []
    
    @ui_sio.on("terminal_output", namespace="/terminal")
    def on_output(data):
        ui_received_output.append(data)
        
    @ui_sio.on("host_telemetry_update", namespace="/terminal")
    def on_host_telemetry(data):
        ui_received_host_telemetry.append(data)

    @ui_sio.on("agent_telemetry_update", namespace="/terminal")
    def on_tel_update(data):
        ui_received_tel_updates.append(data)

    ui_sio.connect(live_server, namespaces=["/terminal"])

    # 2.1 Verify UI can request projects and host receives it
    ui_sio.emit("request_projects", {}, namespace="/terminal")
    for _ in range(20):
        if any(e[0] == "request_projects" for e in host_received_events):
            break
        time.sleep(0.1)
    assert any(e[0] == "request_projects" for e in host_received_events)

    # 2.2 Verify Host can emit telemetry and UI receives it
    test_telemetry = {"projects_root": "/test", "available_projects": ["proj1", "proj2"]}
    host_sio.emit("host_telemetry", test_telemetry, namespace="/terminal")
    for _ in range(20):
        if ui_received_host_telemetry:
            break
        time.sleep(0.1)
    assert len(ui_received_host_telemetry) >= 1
    assert ui_received_host_telemetry[-1]["telemetry"] == test_telemetry
    
    # UI joins the specific agent's room
    ui_sio.emit("join_room", {"room": agent_id}, namespace="/terminal")
    
    # 2.5 Verify host received request_history and initial \r
    for _ in range(20):
        if any(e[0] == "request_history" for e in host_received_events) and \
           any(d.get("input") == "\r" for d in host_received_input):
            break
        time.sleep(0.1)
    
    assert any(e[0] == "request_history" for e in host_received_events)
    assert any(d.get("input") == "\r" for d in host_received_input)

    # 3. Host Daemon sends output for that agent_id
    test_output = "Multi-agent output"
    host_sio.emit("terminal_output", {"sid": agent_id, "output": test_output}, namespace="/terminal")
    
    # Wait for UI to receive it
    for _ in range(10):
        if ui_received_output:
            break
        time.sleep(0.1)
        
    assert len(ui_received_output) == 1
    assert ui_received_output[0]["output"] == test_output
    assert ui_received_output[0]["sid"] == agent_id
    
    # 4. UI sends input back to that agent_id
    test_input = "whoami"
    ui_sio.emit("terminal_input", {"target_sid": agent_id, "input": test_input}, namespace="/terminal")
    
    # Wait for Host Daemon to receive it
    for _ in range(10):
        if any(d.get("target_sid") == agent_id and d.get("input") == test_input for d in host_received_input):
            break
        time.sleep(0.1)
        
    assert any(d.get("target_sid") == agent_id and d.get("input") == test_input for d in host_received_input)

    # 5. Test OTLP Telemetry relay
    new_tel = {"model": "gpt-otlp", "tokens": 500}
    host_sio.emit("agent_telemetry", {"agent_id": agent_id, "telemetry": new_tel}, namespace="/terminal")
    
    for _ in range(20):
        if any(d.get("agent_id") == agent_id for d in ui_received_tel_updates):
            break
        time.sleep(0.1)
        
    assert any(d.get("agent_id") == agent_id for d in ui_received_tel_updates)
    matching_update = next(d for d in ui_received_tel_updates if d.get("agent_id") == agent_id)
    assert matching_update["telemetry"]["model"] == "gpt-otlp"
    
    host_sio.disconnect()
    ui_sio.disconnect()
