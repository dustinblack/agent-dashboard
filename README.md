# Agent Dashboard

An AI Coding Agent Dashboard designed for the Gemini CLI, allowing centralized orchestration and remote interaction with active agent sessions.

## Architecture
- **Backend**: Python 3.9+ with FastAPI and `python-socketio`.
- **Frontend**: React (TypeScript) via Vite, `xterm.js`, and `socket.io-client`.
- **Database**: SQLite with SQLAlchemy ORM.
- **Agent Wrapper**: Python script using `pty` to intercept and stream terminal I/O over Socket.IO.

## Deployment on RHEL 9 with Podman

This project is configured to run rootless containers using `podman` and `podman-compose`.

### Prerequisites

Ensure you have `podman` and `podman-compose` installed:
```bash
sudo dnf install podman podman-compose
```

### Running the Application (Local Test Configuration)

For local development and testing, you can bypass the OIDC authentication requirement by passing the `BYPASS_AUTH=true` environment variable to the backend. This is already configured in the default `compose.yml`.

1. Build and start the containers in the background:
   ```bash
   podman-compose up -d --build
   ```

2. The application will be accessible at:
   - Frontend: `http://localhost:8080` (or the IP of your RHEL server)
   - Backend API: `http://localhost:8000`

### Simulating a Connected Agent

To see the dashboard in action locally, you can run the agent wrapper script as a container, pointing it at your local backend.

First, register a dummy token with your backend:
```bash
curl -X POST http://localhost:8000/machines \
  -H "Content-Type: application/json" \
  -d '{"name": "test-agent", "machine_token": "test-token-123"}'
```

Then, run the agent container:
```bash
cd agent/
podman build -t agent-dashboard-agent -f Containerfile .
podman run -it --rm --network=host \
  -e DASHBOARD_URL="http://127.0.0.1:8000" \
  -e MACHINE_TOKEN="test-token-123" \
  -e MACHINE_NAME="containerized-agent" \
  agent-dashboard-agent bash
```
Navigate to `http://localhost:8080` to attach to the terminal!

### Running in Production

To run the application securely in production:
1. Edit `compose.yml` and **remove** the `BYPASS_AUTH=true` environment variable.
2. Provide real OIDC provider credentials as environment variables to the backend container (e.g., `CLIENT_ID`, `CLIENT_SECRET`, `OIDC_DISCOVERY_URL`).
3. Set up a reverse proxy (like NGINX or Traefik) to handle HTTPS termination for both the frontend (`:8080`) and the WebSocket connections to the backend (`:8000/socket.io`).

### Persistence

The SQLite database is stored in a named Podman volume (`dashboard_data`). This ensures that your data persists even if the containers are recreated.

### Running on Boot (Systemd)

To ensure the Agent Dashboard starts automatically on system boot, you can generate systemd unit files from the Podman containers.

1. Ensure the containers are running.
2. Generate the systemd unit file for the podman-compose project:
   ```bash
   # You might need to generate units for each container or use a pod.
   # For a podman-compose setup, you can generate a systemd unit for the whole setup,
   # or manage it via systemd directly invoking podman-compose:
   
   mkdir -p ~/.config/systemd/user/
   ```

3. Create `~/.config/systemd/user/agent-dashboard.service`:
   ```ini
   [Unit]
   Description=Agent Dashboard Podman Compose Service
   After=network-online.target
   
   [Service]
   Type=exec
   WorkingDirectory=%h/git/dustinblack/agent-dashboard
   ExecStart=/usr/bin/podman-compose up
   ExecStop=/usr/bin/podman-compose down
   Restart=always
   
   [Install]
   WantedBy=default.target
   ```

4. Enable and start the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now agent-dashboard.service
   ```

5. Enable lingering so the service starts on boot even without you logging in:
   ```bash
   loginctl enable-linger $USER
   ```
