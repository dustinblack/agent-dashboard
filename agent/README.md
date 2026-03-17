# Agent Dashboard Host Daemon

The Host Daemon runs on remote development machines and manages AI agent sessions for the Agent Dashboard. It listens for spawn commands from the Hub, multiplexes agent I/O through pseudo-terminals, and relays output to the frontend via Socket.IO.

## Prerequisites
- Python 3.9+
- A running instance of the central Dashboard Backend (Hub).

## Included Tools

The container image bundles the following tools so spawned agents have everything they need:

| Tool | Purpose |
|------|---------|
| **Gemini CLI** (`@google/gemini-cli`) | Google Gemini AI coding agent |
| **Claude Code** (`@anthropic-ai/claude-code`) | Anthropic Claude AI coding agent |
| **Google Cloud CLI** (`gcloud`) | GCP authentication for Claude Code via Vertex AI |
| **GitHub CLI** (`gh`) | GitHub interaction (PRs, issues, etc.) |
| **Git** | Version control |
| **SSH client** | Remote repository access |

## Configuration

The daemon relies on the following environment variables:
- `HOST_TOKEN`: (Required) The pre-shared token for this host, registered with the Hub.
- `DASHBOARD_URL`: (Optional) The URL of the central Dashboard Backend. Defaults to `http://localhost:8000`.
- `PROJECTS_ROOT`: (Optional) Root directory to scan for project repositories. Defaults to `/git`.

### Tool-Specific Configuration

Credentials and configuration for individual tools are passed into the container via volume mounts. See the main project [README](../README.md) for complete examples including:
- `~/.gemini` — Gemini CLI configuration
- `~/.claude` — Claude Code configuration
- `~/.config/gcloud` — GCP credentials (for Claude Code via Vertex AI)
- `~/.config/gh` — GitHub CLI configuration (see note below about token access)
- `~/.ssh` and `~/.gitconfig` — Git/SSH configuration

### GitHub CLI Authentication in Containers

Mounting `~/.config/gh` into the container is necessary but may not be sufficient for authentication. By default, `gh auth login` stores tokens in the host's system keyring (GNOME Keyring, KDE Wallet, etc.), which is not accessible from inside the container. The mounted `hosts.yml` will reference the token but won't contain it.

**Solution:** Pass your GitHub token via the `GH_TOKEN` environment variable:
```bash
# Retrieve your token from the host keyring
gh auth token

# Pass it to the container
-e GH_TOKEN="ghp_your-token-here"           # podman run
Environment=GH_TOKEN=ghp_your-token-here    # systemd quadlet
```

`gh` recognizes `GH_TOKEN` automatically and uses it for all API calls.

## Containerized Usage (Podman / Docker)

1. Build the container image:
   ```bash
   cd agent/
   podman build -t agent-dashboard-daemon -f Containerfile .
   ```

2. See the main project [README](../README.md) for full run commands with all required environment variables and volume mounts.

## Telemetry

The daemon runs a local OTLP HTTP receiver on port 4318 that captures telemetry (model names, token usage) from spawned agents. Both OTLP logs (`/v1/logs`, used by Gemini) and traces (`/v1/traces`, used by Claude Code) are supported.
