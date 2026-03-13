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


def test_socketio_relay_e2e(live_server):
    """Test end-to-end Socket.IO relay between an Agent and the UI."""
    
    # 1. First register the host token via API
    httpx.post(
        f"{live_server}/hosts", 
        json={"name": "socket-host", "host_token": "socket-token"}
    )
    
    # 2. Agent Daemon connects
    agent_sio = socketio.Client()
    agent_connected = False
    
    @agent_sio.event(namespace="/terminal")
    def connect():
        nonlocal agent_connected
        agent_connected = True

    agent_received_input = []
    
    @agent_sio.on("terminal_input", namespace="/terminal")
    def on_terminal_input(data):
        agent_received_input.append(data)
        
    # Agent Daemon authenticates via header
    agent_sio.connect(
        live_server, 
        namespaces=["/terminal"], 
        headers={"x-host-token": "socket-token"}
    )
    
    # Wait for connection
    for _ in range(10):
        if agent_connected:
            break
        time.sleep(0.1)
    
    assert agent_connected, "Agent failed to connect via Socket.IO"
    
    # The agent's SID is its identifier
    agent_sid = agent_sio.get_sid(namespace="/terminal")
    
    # 3. UI connects
    ui_sio = socketio.Client()
    ui_connected = False
    
    @ui_sio.event(namespace="/terminal")
    def connect():
        nonlocal ui_connected
        ui_connected = True
        
    ui_received_output = []
    
    @ui_sio.on("terminal_output", namespace="/terminal")
    def on_terminal_output(data):
        ui_received_output.append(data)
        
    ui_sio.connect(live_server, namespaces=["/terminal"])
    
    for _ in range(10):
        if ui_connected:
            break
        time.sleep(0.1)
        
    assert ui_connected, "UI failed to connect via Socket.IO"
    
    # UI joins the specific agent's room to receive its output
    ui_sio.emit("join_room", {"room": agent_sid}, namespace="/terminal")
    time.sleep(0.2) # Allow time for join
    
    # The server should have immediately sent a carriage return (\r) to the agent upon join
    # Wait for Agent to receive it
    for _ in range(10):
        if agent_received_input:
            break
        time.sleep(0.1)
        
    assert len(agent_received_input) >= 1
    assert agent_received_input[0]["input"] == "\r"
    
    # 4. Agent sends output
    test_output = "Hello from agent!"
    agent_sio.emit("terminal_output", {"output": test_output}, namespace="/terminal")
    
    # Wait for UI to receive it
    for _ in range(10):
        if ui_received_output:
            break
        time.sleep(0.1)
        
    assert len(ui_received_output) == 1
    assert ui_received_output[0]["output"] == test_output
    assert ui_received_output[0]["sid"] == agent_sid
    
    # 5. UI sends input back to the agent
    test_input = "ls -la\n"
    ui_sio.emit("terminal_input", {"target_sid": agent_sid, "input": test_input}, namespace="/terminal")
    
    # Wait for Agent to receive it
    for _ in range(10):
        if len(agent_received_input) > 1:
            break
        time.sleep(0.1)
        
    assert len(agent_received_input) == 2
    assert agent_received_input[1]["input"] == test_input
    
    # Cleanup
    agent_sio.disconnect()
    ui_sio.disconnect()
