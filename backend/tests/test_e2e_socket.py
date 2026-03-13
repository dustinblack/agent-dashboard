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
    """Spawns the real FastAPI application in a subprocess for E2E testing."""
    port = get_free_port()
    
    # We use a test database specifically for this e2e test
    test_db_url = "sqlite:///./e2e_test.db"
    
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db_url
    env["BYPASS_AUTH"] = "true"  # Ensure we bypass OIDC for API testing
    
    # Start the server
    process = subprocess.Popen(
        [".venv/bin/uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=None,
        stderr=None
    )
    
    # Wait for the server to start
    url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            r = httpx.get(f"{url}/health")
            if r.status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(0.5)
    else:
        process.terminate()
        raise RuntimeError(f"Server did not start in time. Port: {port}")

    yield url

    # Cleanup
    process.terminate()
    process.wait(timeout=5)
    if os.path.exists("./e2e_test.db"):
        os.remove("./e2e_test.db")


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
        json={"name": "spawn-host", "host_token": "spawn-token"}
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
        headers={"x-host-token": "spawn-token"}
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


def test_socketio_relay_multiplex_e2e(live_server):
    """Test I/O relay multiplexed by agent_id."""
    
    # 1. Register and connect host
    httpx.post(
        f"{live_server}/hosts", 
        json={"name": "relay-host", "host_token": "relay-token"}
    )
    
    host_sio = socketio.Client()
    host_received_input = []
    host_received_events = []
    
    @host_sio.on("terminal_input", namespace="/terminal")
    def on_input(data):
        host_received_input.append(data)

    @host_sio.on("request_history", namespace="/terminal")
    def on_history(data):
        host_received_events.append(("request_history", data))

    host_sio.connect(
        live_server, 
        namespaces=["/terminal"], 
        headers={"x-host-token": "relay-token"}
    )
    
    # We'll use a dummy agent_id
    agent_id = "test-agent-123"
    
    # 2. UI connects
    ui_sio = socketio.Client()
    ui_received_output = []
    
    @ui_sio.on("terminal_output", namespace="/terminal")
    def on_output(data):
        ui_received_output.append(data)
        
    ui_sio.connect(live_server, namespaces=["/terminal"])
    
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
    
    host_sio.disconnect()
    ui_sio.disconnect()
