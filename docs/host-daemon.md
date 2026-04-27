# Host Daemon Reference

The host daemon runs on each development machine as a
containerized service. It connects to the hub, spawns AI agent
sessions in pseudo-terminals, relays I/O, and collects
OpenTelemetry telemetry.

For basic setup, see the [Getting Started](../README.md#4-deploy-the-host-daemon)
section of the main README.

## Container Run Command (Full)

```bash
podman run -d --name host-daemon --network=host \
  --privileged \
  -e DASHBOARD_URL="http://your-server-ip:8000" \
  -e HOST_TOKEN="secret-token-123" \
  -e PROJECTS_ROOT="/git" \
  -e OTLP_PORT="4318" \
  -e GEMINI_API_KEY="your-key-here" \
  -e CLAUDE_CODE_USE_VERTEX=1 \
  -e CLOUD_ML_REGION="us-east5" \
  -e ANTHROPIC_VERTEX_PROJECT_ID="your-gcp-project-id" \
  -v /path/to/your/git:/git \
  -v $HOME/.ssh:/root/.ssh:ro \
  -v $HOME/.gitconfig:/root/.gitconfig:ro \
  -v $HOME/.gemini/:/root/.gemini \
  -v $HOME/.claude/:/root/.claude \
  -v $HOME/.config/gcloud:/root/.config/gcloud:ro \
  -v $HOME/.config/gh:/root/.config/gh:ro \
  -v $HOME/.config/glab-cli:/root/.config/glab-cli:ro \
  localhost/agent-dashboard-daemon:latest
```

> [!WARNING]
> `--privileged` is required for container-in-container support
> (e.g., agents building and running containers during
> development sessions). This also implicitly disables SELinux
> label confinement.

> [!TIP]
> **Missing config directories:** Volume mounts for
> `~/.claude/` and `~/.gemini/` will fail if the directories
> don't exist on the host. If you haven't used one of these
> tools locally, create them first: `mkdir -p ~/.claude
> ~/.gemini`

> [!TIP]
> **Reconfiguring the daemon:** Environment variables and
> volume mounts are fixed at container creation time. To
> change them, stop and remove the existing container, then
> re-run with the new parameters:
> ```bash
> podman stop host-daemon && podman rm host-daemon
> # Re-run the podman run command with updated settings
> ```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DASHBOARD_URL` | URL of the hub backend | *(required)* |
| `HOST_TOKEN` | Token from the host registration step | *(required)* |
| `PROJECTS_ROOT` | Root directory for project scanning | *(required)* |
| `OTLP_PORT` | OTLP telemetry receiver port | `4318` |
| `PROJECTS_DEPTH` | Max scan depth below `PROJECTS_ROOT` | `6` |
| `GEMINI_API_KEY` | API key for Gemini CLI | — |
| `CLAUDE_CODE_USE_VERTEX` | Set to `1` to use Vertex AI for Claude | — |
| `CLOUD_ML_REGION` | GCP region (e.g., `us-east5`) | — |
| `ANTHROPIC_VERTEX_PROJECT_ID` | GCP project ID for Vertex AI | — |
| `GH_TOKEN` | GitHub CLI personal access token | — |
| `GITLAB_TOKEN` | GitLab CLI personal access token | — |

## Volume Mounts

| Host Path | Container Path | Mode | Purpose |
|-----------|---------------|------|---------|
| `/path/to/your/git` | `/git` | rw | Project source code |
| `~/.ssh` | `/root/.ssh` | ro | SSH keys for git operations |
| `~/.gitconfig` | `/root/.gitconfig` | ro | Git configuration |
| `~/.gemini/` | `/root/.gemini` | rw | Gemini CLI settings |
| `~/.claude/` | `/root/.claude` | rw | Claude Code settings |
| `~/.config/gcloud` | `/root/.config/gcloud` | ro | GCP credentials |
| `~/.config/gh` | `/root/.config/gh` | ro | GitHub CLI config |
| `~/.config/glab-cli` | `/root/.config/glab-cli` | ro | GitLab CLI config |

## Authentication

<details>
<summary><strong>GitHub CLI</strong></summary>

The container includes the GitHub CLI (`gh`). Mounting
`~/.config/gh` alone is usually not sufficient because `gh auth
login` stores tokens in your system keyring (GNOME Keyring, KDE
Wallet, etc.), which is not accessible from inside the container.

Export your token and pass it as an environment variable instead:

```bash
# Get your current token from the host keyring
gh auth token

# Pass it to the container
-e GH_TOKEN="ghp_your-token-here"           # podman/docker run
Environment=GH_TOKEN=ghp_your-token-here    # quadlet
```

The `GH_TOKEN` environment variable is recognized by `gh`
automatically and takes precedence over stored credentials.
</details>

<details>
<summary><strong>GitLab CLI</strong></summary>

The container includes the GitLab CLI (`glab`). Similar to `gh`,
mounting `~/.config/glab-cli` alone may not be sufficient if your
token is stored in the system keyring.

Pass your token as an environment variable instead:

```bash
-e GITLAB_TOKEN="glpat_your-token-here"       # podman/docker run
Environment=GITLAB_TOKEN=glpat_your-token-here # quadlet
```

The `GITLAB_TOKEN` environment variable is recognized by `glab`
automatically and takes precedence over stored credentials.
</details>

<details>
<summary><strong>Claude Code via Vertex AI</strong></summary>

If you use Claude Code via Google Cloud Vertex AI, the daemon
container includes the `gcloud` CLI and supports passing GCP
credentials through. Configure GCP authentication on the **host
machine** before starting the daemon — the `~/.config/gcloud`
volume mount passes your credentials into the container.

Required environment variables for Vertex AI:
- `CLAUDE_CODE_USE_VERTEX=1`
- `CLOUD_ML_REGION` — your GCP region (e.g., `us-east5`)
- `ANTHROPIC_VERTEX_PROJECT_ID` — your GCP project ID
</details>

## Compose File Reference

The `compose.yml` in the project root starts the hub services:

```yaml
services:
  backend:
    # FastAPI + Socket.IO hub on port 8000
    # Build context is repo root (for git version detection)
    # Persists SQLite DB in dashboard_data volume
    # BYPASS_AUTH=true skips OIDC for private networks

  frontend:
    # React UI served by Nginx on port 8080
    # Build context is repo root (for git version detection)
    # VITE_API_URL build arg configures backend connection
```

| Setting | Description |
|---------|-------------|
| `VITE_API_URL` | Backend URL for remote access (build arg via `.env`) |
| `BYPASS_AUTH` | Set to `true` to skip OIDC auth (default in compose) |
| `DATABASE_URL` | SQLite path inside the backend container |
| `dashboard_data` | Named volume for database persistence |

> [!NOTE]
> Both services use the **repo root** as their build context
> so they can detect the application version from git tags
> automatically. The version is displayed in the dashboard
> header and used for upgrade notifications.

## Included Tools

The daemon container bundles the following tools:

| Tool | Purpose |
|------|---------|
| **Gemini CLI** (`@google/gemini-cli`) | Google Gemini AI coding agent |
| **Claude Code** (`@anthropic-ai/claude-code`) | Anthropic Claude AI coding agent |
| **Google Cloud CLI** (`gcloud`) | GCP authentication for Claude via Vertex AI |
| **GitHub CLI** (`gh`) | GitHub interaction (PRs, issues, etc.) |
| **GitLab CLI** (`glab`) | GitLab interaction (MRs, issues, etc.) |
| **Git** | Version control |
| **Podman** | Container builds and runtimes (podman-in-podman) |
| **Go** (`golang`) | Go builds and tests |
| **Rust / Cargo** | Rust builds and tests |
| **SSH client** | Remote repository access |
