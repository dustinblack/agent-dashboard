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

### Running the Application

1. Build and start the containers in the background:
   ```bash
   podman-compose up -d --build
   ```

2. The application will be accessible at:
   - Frontend: `http://localhost:80` (or the IP of your RHEL server)
   - Backend API: `http://localhost:8000`

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
