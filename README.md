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
1. Build and start the containers (Always use `--no-cache` after code changes to ensure the latest version is built):
   ```bash
   podman-compose build --no-cache && podman-compose up -d
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

It is recommended to mount your local development directory and Gemini configuration folder so the spawned agents can access your code and maintain persistent settings.

```bash
cd agent/
podman build -t agent-dashboard-daemon -f Containerfile .

podman run -it --rm --network=host \
  --security-opt label=disable \
  -e DASHBOARD_URL="http://127.0.0.1:8000" \
  -e HOST_TOKEN="secret-token-123" \
  -e GEMINI_API_KEY="your-key-here" \
  -e PROJECTS_ROOT="/git" \
  -v /path/to/your/git:/git \
  -v $HOME/.gemini/:/root/.gemini \
  agent-dashboard-daemon
```
*(Note: We use `--security-opt label=disable` instead of the `:Z` mount flag to safely grant the container access to your local files without recursively changing their SELinux labels, which can cause permission errors on large directories.)*

### 3. Spawn Agents
Go to the Web UI (`http://localhost:8080`). You will see your workstation listed. Click **"Spawn Gemini"** or **"Spawn Claude"** to start a remote AI session. 

**Note on Console UX:**
- **Detached Windows:** Attaching to a terminal now opens a standalone browser popup window with minimal interface, allowing for side-by-side multi-tasking across different agents.
- **History Replay:** If you close a terminal window and re-attach later, the dashboard automatically replays the recent session history so you can pick up exactly where you left off.
- **Color Support:** Terminals are configured with `xterm-256color` support for rich CLI output.

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
