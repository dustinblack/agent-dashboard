# Agent Dashboard

An AI Coding Agent Dashboard designed for the Gemini CLI and Claude Code, allowing centralized orchestration and remote interaction with multiple AI agent sessions across different machines.

## Architecture
- **Backend (Hub)**: Python 3.9+ with FastAPI and `python-socketio`. Manages the database and relays commands.
- **Frontend**: React (TypeScript) via Vite, `xterm.js`, and `socket.io-client`. Central command UI.
- **Host Daemon**: Background service running on remote development machines. Listens for `spawn` commands from the hub and multiplexes Agent I/O.
- **Agent**: A specific AI CLI session (Gemini, Claude, or Bash) running inside a pseudo-terminal on a Host.

## Deployment on RHEL 9 with Podman (The Hub)

The Hub (Backend + Frontend) is configured to run as rootless containers using `podman-compose`.

### Prerequisites
```bash
sudo dnf install podman podman-compose
```

### Running the Hub (Local Test Configuration)
1. Build and start the containers:
   ```bash
   podman-compose up -d --build
   ```
2. Hub UI: `http://localhost:8080`
3. Hub API: `http://localhost:8000`

---

## Remote Host Setup

Each machine you want to orchestrate needs to run the `Host Daemon`.

### 1. Register the Host
First, register your machine with the Hub to get a `HOST_TOKEN`:
```bash
curl -X POST http://localhost:8000/hosts \
  -H "Content-Type: application/json" \
  -d '{"name": "my-dev-workstation", "host_token": "secret-token-123"}'
```

### 2. Run the Host Daemon (Containerized)
```bash
cd agent/
podman build -t agent-dashboard-daemon -f Containerfile .
podman run -it --rm --network=host \
  -e DASHBOARD_URL="http://127.0.0.1:8000" \
  -e HOST_TOKEN="secret-token-123" \
  agent-dashboard-daemon
```
*(Note: Use the Hub's IP address for `DASHBOARD_URL` if the daemon is on a different machine.)*

### 3. Spawn Agents
Go to the Web UI (`http://localhost:8080`). You will see your workstation listed. Click **"Spawn Gemini"** or **"Spawn Claude"** to start a remote AI session. The UI will automatically attach you to the terminal.

---

### Running in Production
1. Remove `BYPASS_AUTH=true` from `compose.yml`.
2. Configure real OIDC environment variables in the backend.
3. Setup a reverse proxy (NGINX) with TLS for WebSocket support.

### Persistence
The SQLite database is stored in the `dashboard_data` Podman volume.

### Running on Boot (Systemd)
Generate user-level systemd units:
```bash
mkdir -p ~/.config/systemd/user/
# Create agent-dashboard.service (see README for details)
systemctl --user enable --now agent-dashboard.service
loginctl enable-linger $USER
```
