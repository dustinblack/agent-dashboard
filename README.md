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
Go to the Web UI (`http://localhost:8080`). You will see your workstation listed. Click **"Spawn Gemini"**, **"Spawn Claude"**, or **"Spawn Bash"** to start a remote session.

**Note on Host Management:**
- **Host Deletion:** You can dynamically remove offline or retired hosts from the dashboard by clicking the "Delete" trash can icon. This will safely cascade and clean up all historical agent sessions and logs associated with that host.

**Note on Agent Spawning:**
- **Project Selection:** The daemon automatically scans the `PROJECTS_ROOT` directory in the background every 60 seconds. You can select a project directory for the agent to start in via the dropdown menu. You can also force a refresh of this list if you've recently added a new project.

**Note on Console UX:**
- **Detached Windows:** Attaching to a terminal now opens a standalone browser popup window with minimal interface, allowing for side-by-side multi-tasking across different agents.
- **Dynamic Resizing:** Terminals perfectly scale to match the window viewport size in real-time, instantly relaying geometry changes back to the underlying remote PTY.
- **History Replay:** If you close a terminal window and re-attach later, the dashboard automatically replays the recent session history so you can pick up exactly where you left off.
- **Color Support:** Terminals are configured with `xterm-256color` support for rich CLI output.
- **Live Telemetry (OTel):** The dashboard now uses standardized OpenTelemetry (OTLP) to capture model names and token usage. The Host Daemon runs a local OTLP receiver (port 4318) that child agents (Gemini, Claude) report to, ensuring 100% accurate stats without screen-scraping or interfering with terminal performance. Bash agents omit these stat boxes dynamically.

---

### Running in Production (Internal Lab)
If you are deploying this strictly for an internal, private lab network, you can simplify the deployment by continuing to bypass OIDC authentication and avoiding reverse proxies.

1. Ensure the `BYPASS_AUTH=true` flag remains in your `compose.yml`.
2. To allow machines on your network to access the UI and the Backend API, you must explicitly set the `VITE_API_URL` environment variable for the frontend.

Create a `.env` file in the root directory (or inject it directly into `compose.yml`):
```bash
# Replace 'your-server-ip' with the actual IP address or local DNS name of the host
VITE_API_URL=http://your-server-ip:8000
```

Then, update your `compose.yml` to pass this to the frontend build:

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Containerfile
      args:
        VITE_API_URL: ${VITE_API_URL}
    ports:
      - "8080:80"
```

*(Note: You will also need to update `frontend/Containerfile` to accept `ARG VITE_API_URL` and pass it during the `npm run build` step.)*

### Persistence
The SQLite database is stored in the `dashboard_data` Podman volume.

### Running on Boot (Systemd for RHEL 9)
To ensure the Hub containers start automatically on boot as a system-wide service:

1. **Generate the podman-compose systemd template:**
   Run this command with `sudo` to install the generic template into the system directory (`/etc/systemd/system/`):
   ```bash
   sudo podman-compose systemd -a create-unit
   sudo systemctl daemon-reload
   ```
2. **Enable and start the service for this project:**
   Ensure you are in the directory containing the `compose.yml` file (e.g., `agent-dashboard`), then run:
   ```bash
   sudo systemctl enable --now podman-compose@agent-dashboard.service
   ```
