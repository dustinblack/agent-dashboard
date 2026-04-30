# Agent Profiles

Agent profiles define how the host daemon spawns, detects,
and monitors each AI coding agent tool. Instead of hardcoded
logic for specific tools, the daemon reads YAML or JSON
profile files from the `agent/profiles/` directory at
startup.

## Bundled Profiles

Three profiles are included out of the box:

| Profile | File | Description |
|---------|------|-------------|
| Claude | `agent/profiles/claude.yaml` | Claude Code CLI with OTLP telemetry and MCP detection |
| Gemini | `agent/profiles/gemini.yaml` | Gemini CLI with custom telemetry endpoints |
| Bash | `agent/profiles/bash.yaml` | Bash shell with PROMPT_COMMAND sidecar telemetry |

## Creating a Custom Profile

To add support for a new agent tool, create a YAML or JSON
file in `agent/profiles/`. The daemon loads all `.yaml`,
`.yml`, and `.json` files from this directory on startup.

### Minimal Profile

```yaml
name: myagent
display_name: My Agent
binary: myagent-cli

commands:
  new: ["myagent-cli"]
  resume: ["myagent-cli", "--resume"]
```

### Full Schema

```yaml
# Required: unique identifier used in spawn requests
name: myagent

# Display name shown in logs and UI
display_name: My Agent

# Binary to check for availability
binary: myagent-cli

# If true, always listed as available (e.g. bash)
always_available: false

# Spawn commands
commands:
  # Command for new sessions
  new: ["myagent-cli"]
  # Command for resume mode (can include fallback chains)
  resume: ["bash", "-c", "myagent-cli --resume || myagent-cli"]

# Environment variables injected at spawn time.
# Supports {otlp_port} and {agent_id} placeholders.
env:
  MY_AGENT_TELEMETRY: "true"
  MY_AGENT_OTLP_ENDPOINT: "http://127.0.0.1:{otlp_port}"

# Auth detection for the Spawn button visibility
auth:
  # Environment variables to check
  env_vars:
    - MY_AGENT_API_KEY
  # "any" = at least one must be set
  # "all" = all must be set
  require: any

# MCP server config file locations
mcp:
  # Project-level config (relative to project dir)
  project_file: .mcp.json
  # User-level config files (~ expanded)
  user_files:
    - ~/.myagent/config.json

# OTLP telemetry metric mappings
telemetry:
  # Metric names for token usage tracking
  token_metrics:
    - myagent.token.usage
  # Metric name for cost tracking (USD)
  cost_metric: myagent.cost.usage
  # Metric names for tool/function activity
  activity_metrics:
    - myagent.tool.execution
  # Runtime duration metric
  runtime_metric:
    name: myagent.active_time
    unit: seconds  # or "milliseconds"
  # Metrics to explicitly ignore (avoid double-counting)
  excluded_metrics:
    - gen_ai.client.token.usage

# Sidecar telemetry (for tools without OTLP support)
sidecar:
  # Shell command injected as PROMPT_COMMAND
  prompt_command: >-
    printf '{"cwd":"%s"}\n' "$PWD"
  # File path pattern ({agent_id} is replaced at runtime)
  file_pattern: "/tmp/.agent-telemetry-{agent_id}"
  # Map sidecar JSON keys to telemetry field names
  fields:
    current_activity: cwd

# Permission prompt patterns (regex, case-insensitive)
# These are merged with generic defaults (Y/n, yes/no, etc.)
permission_patterns:
  - "Do you want to proceed"
  - "Allow .+ to run"
```

## How Profiles Are Used

| Feature | Profile Field | Daemon Method |
|---------|--------------|---------------|
| Spawn commands | `commands.new`, `commands.resume` | `spawn_agent()` |
| Environment vars | `env` | `spawn_agent()` (child process) |
| Tool detection | `binary`, `auth`, `always_available` | `_detect_available_tools()` |
| MCP detection | `mcp.project_file`, `mcp.user_files` | `_detect_mcp_servers()` |
| Token tracking | `telemetry.token_metrics` | `handle_otlp()` |
| Cost tracking | `telemetry.cost_metric` | `handle_otlp()` |
| Activity tracking | `telemetry.activity_metrics` | `handle_otlp()` |
| Runtime tracking | `telemetry.runtime_metric` | `handle_otlp()` |
| Permission prompts | `permission_patterns` | Terminal output matching |
| Sidecar telemetry | `sidecar.*` | `update_agents_git_info()` |

## Notes

- The standard OTLP endpoint and resource attributes
  (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_RESOURCE_ATTRIBUTES`)
  are always injected by the daemon regardless of profile.
- Generic permission patterns (Y/n, yes/no, Continue?, etc.)
  are always active. Profile patterns are merged in addition.
- Profile changes require a daemon restart to take effect.
- The daemon logs which profiles were loaded at startup.
