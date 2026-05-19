# Agent Dashboard Host Daemon

The Host Daemon runs on remote development machines and manages AI agent sessions for the Agent Dashboard. It listens for spawn commands from the Hub, multiplexes agent I/O through pseudo-terminals, and relays output to the frontend via Socket.IO.

## Prerequisites
- Python 3.9+
- A running instance of the central Dashboard Backend (Hub).

## Agent Profiles

The daemon uses YAML/JSON profile files to define how each
agent tool is spawned, detected, and monitored. Bundled
profiles for Claude, Gemini, and Bash are in `agent/profiles/`.
Custom profiles can be added by dropping a YAML file into the
same directory. See [Agent Profiles](../docs/agent-profiles.md)
for the full schema and examples.

## Included Tools

The container image bundles the following tools so spawned agents have everything they need:

| Tool | Purpose |
|------|---------|
| **Gemini CLI** (`@google/gemini-cli`) | Google Gemini AI coding agent |
| **Claude Code** (`@anthropic-ai/claude-code`) | Anthropic Claude AI coding agent |
| **Google Cloud CLI** (`gcloud`) | GCP authentication for Claude Code via Vertex AI |
| **GitHub CLI** (`gh`) | GitHub interaction (PRs, issues, etc.) |
| **GitLab CLI** (`glab`) | GitLab interaction (MRs, issues, etc.) |
| **Git** | Version control |
| **Podman** | Container builds and runtimes (podman-in-podman) |
| **Go** (`golang`) | Go builds and tests |
| **Rust / Cargo** | Rust builds and tests |
| **SSH client** | Remote repository access |

## Configuration

The daemon relies on the following environment variables:
- `HOST_TOKEN`: (Required) The pre-shared token for this host, registered with the Hub.
- `DASHBOARD_URL`: (Optional) The URL of the central Dashboard Backend. Defaults to `http://localhost:8000`.
- `PROJECTS_ROOT`: (Optional) Root directory (or colon-separated list of directories) to scan for project repositories. Defaults to `/git`. Example: `PROJECTS_ROOT=/git:/workspace:/data/repos`.
- `OTLP_PORT`: (Optional) Port for the local OTLP HTTP telemetry receiver. Defaults to `4318`. Set to a different value when running multiple daemons on the same host with `Network=host`.
- `PROJECTS_DEPTH`: (Optional) Maximum directory depth to scan for git repositories below each `PROJECTS_ROOT` entry. Defaults to `6`.

### Tool-Specific Configuration

Credentials and configuration for individual tools are passed into the container via volume mounts. See the main project [README](../README.md) for complete examples including:
- `~/.gemini` — Gemini CLI configuration
- `~/.claude` — Claude Code configuration
- `~/.config/gcloud` — GCP credentials (for Claude Code via Vertex AI)
- `~/.config/gh` — GitHub CLI configuration (see note below about token access)
- `~/.config/glab-cli` — GitLab CLI configuration (see note below about token access)
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

### GitLab CLI Authentication in Containers

Similar to the GitHub CLI, `glab` may store tokens in the system keyring, making them inaccessible from inside the container.

**Solution:** Pass your GitLab token via the `GITLAB_TOKEN` environment variable:
```bash
# Pass it to the container
-e GITLAB_TOKEN="glpat_your-token-here"       # podman run
Environment=GITLAB_TOKEN=glpat_your-token-here # systemd quadlet
```

`glab` recognizes `GITLAB_TOKEN` automatically and uses it for all API calls.

## Containerized Usage (Podman / Docker)

1. Build the container image:
   ```bash
   cd agent/
   # Regenerate Containerfile from template + profiles
   # (only needed after adding/modifying profiles)
   python3 generate_containerfile.py
   podman build -t agent-dashboard-daemon -f Containerfile .
   ```

2. See the main project [README](../README.md) for full run commands with all required environment variables and volume mounts.

### Systemd Restart Policy

When running the daemon as a systemd service (e.g., via a
Podman Quadlet), add a restart policy so the daemon
recovers automatically from unexpected exits:

```ini
[Service]
Restart=on-failure
RestartSec=5
```

## Telemetry

The daemon runs a local OTLP HTTP receiver (default port 4318, configurable via `OTLP_PORT`) that captures telemetry (model names, token usage) from spawned agents. All three OTLP signals are supported:

| Signal | Endpoint | Used By |
|--------|----------|---------|
| Logs | `/v1/logs` | Gemini CLI |
| Traces | `/v1/traces` | Gemini CLI, Claude Code |
| Metrics | `/v1/metrics` | Claude Code (`claude_code.token.usage` counters) |

The daemon automatically configures the required OpenTelemetry environment variables for each spawned agent, including `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`, and `OTEL_EXPORTER_OTLP_PROTOCOL` for Claude Code compatibility.

### Telemetry Fields

The daemon maintains the following telemetry fields for each agent, broadcast to the dashboard via Socket.IO:

| Field | Source | Description |
|-------|--------|-------------|
| `model` | OTLP logs/traces/metrics | The AI model name (e.g., `claude-opus-4-6`, `gemini-2.0-flash`) |
| `context_tokens` | OTLP logs/traces | Current context window usage (latest `input_tokens` per API call). Decreases after compression. |
| `tokens` | OTLP metrics | Cumulative token total across all API calls |
| `input_tokens` | OTLP metrics | Cumulative input tokens, split by `type` attribute on token.usage metrics |
| `output_tokens` | OTLP metrics | Cumulative output tokens |
| `cache_read_tokens` | OTLP metrics | Cumulative cache read tokens |
| `cache_creation_tokens` | OTLP metrics | Cumulative cache creation tokens |
| `cost_usd` | OTLP metrics (Claude only) | Session cost in USD from `claude_code.cost.usage` metric. For Gemini, cost is estimated on the frontend from pricing tables. |
| `run_time_seconds` | OTLP metrics | Active session time — Claude: `claude_code.active_time.total` (periodic), Gemini: `gemini_cli.agent.duration` (end-of-session only) |
| `current_activity` | OTLP logs/traces/metrics, PROMPT_COMMAND | Latest tool or function name being executed. For bash sessions, shows the current working directory via PROMPT_COMMAND sidecar. |
| `task_description` | User-provided | Editable task description, synced from the dashboard UI via `update_task_description` socket event |
| `agent_status` | Derived | `working`, `idle`, or `waiting_permission` — derived from OTLP activity and terminal output patterns |
| `mcp_servers` | Config files | MCP server names detected from `.mcp.json`, `~/.claude.json`, or `~/.gemini/settings.json` |
| `last_cmd` | PROMPT_COMMAND (bash only) | Last executed command text, extracted from bash history |
| `last_exit_code` | PROMPT_COMMAND (bash only) | Exit code of the last command. Non-zero values trigger an error badge on the card. |
| `worktree_path` | Daemon (spawn) | Absolute path to the git worktree directory, if the agent was spawned with worktree isolation. Null otherwise. |
| `git_branch` | Git | Current branch of the agent's working directory |
| `git_project` | Git | Repository name extracted from the git remote URL |

### Git Worktree Isolation

When spawning an agent, the user can enable "Worktree Isolation" to create a separate git worktree for the session. This prevents concurrent agents from conflicting on the same working tree.

**Lifecycle:**
1. **Creation**: The daemon creates a worktree at `{PROJECTS_ROOT}/.agent-worktrees/{project}/agent-{id[:8]}` with a new branch `agent/{tool}-{id[:8]}` based on the current HEAD.
2. **Working directory**: The agent process runs in the worktree directory instead of the original project.
3. **Cleanup**: When the agent is stopped or closed, the daemon removes the worktree (`git worktree remove --force`) and deletes the branch (`git branch -D`).

**Companion sessions** inherit the parent agent's working directory (worktree or original) and do not create additional worktrees. This ensures companion chains (e.g. Claude → Bash → Gemini) all share the same working context.

**Smart default**: The spawn modal defaults the worktree toggle to ON when another agent is already active on the same project and host.
