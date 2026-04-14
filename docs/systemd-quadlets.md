# Running as a System Service (Systemd Quadlets)

For production deployments, use systemd quadlets so that
containers start automatically on boot without relying on the
source directory or `compose.yml`.

## Hub Services

Create the following files in `/etc/containers/systemd/`:

**`/etc/containers/systemd/agent-dashboard-data.volume`**
```ini
[Volume]
VolumeName=dashboard_data
```

**`/etc/containers/systemd/agent-dashboard-backend.container`**
```ini
[Unit]
Description=Agent Dashboard Backend
After=network-online.target

[Container]
Image=localhost/agent-dashboard_backend:latest
PublishPort=8000:8000
Volume=agent-dashboard-data.volume:/app/data
Environment=DATABASE_URL=sqlite:////app/data/agent_dashboard.db
Environment=BYPASS_AUTH=true

[Install]
WantedBy=multi-user.target
```

**`/etc/containers/systemd/agent-dashboard-frontend.container`**
```ini
[Unit]
Description=Agent Dashboard Frontend
After=network-online.target agent-dashboard-backend.service

[Container]
Image=localhost/agent-dashboard_frontend:latest
PublishPort=8080:80

[Install]
WantedBy=multi-user.target
```

Reload and start:
```bash
sudo systemctl daemon-reload
sudo systemctl start agent-dashboard-backend.service
sudo systemctl start agent-dashboard-frontend.service
```

## Host Daemon (Rootless Quadlet)

For the host daemon, use a **rootless** quadlet so agents run
as your user and file permissions are preserved. Create
`~/.config/containers/systemd/agent-dashboard-daemon.container`:

```ini
[Unit]
Description=Agent Dashboard Host Daemon
After=network-online.target

[Container]
Image=localhost/agent-dashboard-daemon:latest
Network=host
PodmanArgs=--privileged

# Environment Variables
Environment=DASHBOARD_URL=http://your-server-ip:8000
Environment=HOST_TOKEN=secret-token-123
Environment=PROJECTS_ROOT=/git
# OTLP telemetry receiver port (default 4318; change when
# running multiple daemons on the same host)
Environment=OTLP_PORT=4318
Environment=GEMINI_API_KEY=your-key-here
Environment=GH_TOKEN=ghp_your-token-here
Environment=GITLAB_TOKEN=glpat_your-token-here
Environment=CLAUDE_CODE_USE_VERTEX=1
Environment=CLOUD_ML_REGION=us-east5
Environment=ANTHROPIC_VERTEX_PROJECT_ID=your-gcp-project-id

# Volume Mounts (using %h for your home directory)
Volume=%h/path/to/your/git:/git
Volume=%h/.ssh:/root/.ssh:ro
Volume=%h/.gitconfig:/root/.gitconfig:ro
Volume=%h/.gemini/:/root/.gemini
Volume=%h/.claude/:/root/.claude
Volume=%h/.config/gcloud:/root/.config/gcloud:ro
Volume=%h/.config/gh:/root/.config/gh:ro
Volume=%h/.config/glab-cli:/root/.config/glab-cli:ro

[Install]
WantedBy=default.target
```

Reload and start:
```bash
systemctl --user daemon-reload
systemctl --user start agent-dashboard-daemon.service
```

> [!IMPORTANT]
> **Lingering:** By default, most Linux distributions kill user
> processes on logout. For rootless services to start at boot
> and persist after logout, enable lingering:
> ```bash
> sudo loginctl enable-linger $USER
> ```
