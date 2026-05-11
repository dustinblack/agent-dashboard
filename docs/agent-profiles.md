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
color: green
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

# UI theme color for spawn buttons and badges.
# Supported keywords: purple, blue, slate, green,
# red, amber, cyan. Defaults to slate if omitted.
color: green

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
  # File path pattern ({tmpdir} and {agent_id} replaced at runtime)
  file_pattern: "{tmpdir}/.agent-telemetry-{agent_id}"
  # Map sidecar JSON keys to telemetry field names
  fields:
    current_activity: cwd

# Permission prompt patterns (regex, case-insensitive)
# These are merged with generic defaults (Y/n, yes/no, etc.)
permission_patterns:
  - "Do you want to proceed"
  - "Allow .+ to run"

# Build-time provisioning metadata (optional).
# Used by generate_containerfile.py and as
# documentation for manual container setup.
provisioning:
  # Packages to install in the container image
  install:
    npm:
      - "@example/my-agent-cli"
    # pip:
    #   - "my-agent-package"
    # system:
    #   - "some-dnf-package"

  # Config files to seed in the container image
  config_files:
    # Create a directory
    - path: "/root/.myagent"
      mkdir: true
    # Create a file with specific content
    - path: "/root/.myagent/config.json"
      content: '{"key": "value"}'

  # Command to verify the installation succeeded
  verify: "myagent --version"

  # Host directories to mount into the container
  mounts:
    - host: "~/.myagent"
      container: "/root/.myagent"
      mode: rw

  # Container-level env vars to pass through from the
  # host. Distinct from profile.env which the daemon
  # injects at agent spawn time — these are set on the
  # container itself (podman run -e / quadlet Environment=).
  passthrough_env:
    - MY_AGENT_API_KEY
```

## How Profiles Are Used

| Feature | Profile Field | Used By |
|---------|--------------|---------|
| Spawn commands | `commands.new`, `commands.resume` | `spawn_agent()` |
| Environment vars | `env` | `spawn_agent()` (child process) |
| Tool detection | `binary`, `auth`, `always_available` | `_detect_available_tools()` |
| Spawn button label | `display_name` | HostCard, SpawnModal, Terminal header |
| Spawn button color | `color` | HostCard buttons, Terminal badge |
| Resume mode toggle | `commands.resume` vs `commands.new` | SpawnModal (derived) |
| MCP detection | `mcp.project_file`, `mcp.user_files` | `_detect_mcp_servers()` |
| Token tracking | `telemetry.token_metrics` | `handle_otlp()` |
| Cost tracking | `telemetry.cost_metric` | `handle_otlp()` |
| Activity tracking | `telemetry.activity_metrics` | `handle_otlp()` |
| Runtime tracking | `telemetry.runtime_metric` | `handle_otlp()` |
| Permission prompts | `permission_patterns` | Terminal output matching |
| Sidecar telemetry | `sidecar.*` | `update_agents_git_info()` |
| Companion buttons | `name`, `display_name` | Terminal companion bar |
| Container install | `provisioning.install.*` | `generate_containerfile.py` |
| Config seeding | `provisioning.config_files` | `generate_containerfile.py` |
| Install verification | `provisioning.verify` | `generate_containerfile.py` |
| Volume mounts | `provisioning.mounts` | Documentation / setup scripts |
| Container env vars | `provisioning.passthrough_env` | Documentation / setup scripts |

## Resume Mode

The SpawnModal shows a "Resume Session" toggle when a tool
supports resuming previous sessions. This is **derived
automatically** from the `commands` configuration — no
separate flag is needed:

- **Supports resume**: `commands.resume` is defined AND
  differs from `commands.new` (e.g. Claude, Gemini).
- **No resume**: `commands.resume` is empty, undefined, or
  identical to `commands.new` (e.g. Bash where both are
  `["bash"]`).

## Adding a New Agent Tool

To add support for a completely new agent tool (e.g.
Aider, Codex, Cursor), follow these steps:

### 1. Create the Profile

Create a YAML file in `agent/profiles/` with both runtime
configuration and provisioning metadata:

```yaml
# agent/profiles/aider.yaml
name: aider
display_name: Aider
color: green
binary: aider

commands:
  new: ["aider"]
  resume: ["aider"]

auth:
  env_vars:
    - OPENAI_API_KEY
  require: any

provisioning:
  install:
    pip:
      - "aider-chat"
  verify: "aider --version"
  mounts:
    - host: "~/.aider"
      container: "/root/.aider"
      mode: rw
  passthrough_env:
    - OPENAI_API_KEY
```

### 2. Regenerate the Containerfile

The Containerfile is generated from a Jinja2 template
plus profile provisioning metadata. Regenerate it to
include the new tool's packages:

```bash
cd agent/
python3 generate_containerfile.py
```

This reads all profiles and produces a Containerfile
with the correct `npm install`, `pip install`, config
seeding, and verification steps. If your tool needs
custom installation beyond what the provisioning schema
supports (e.g., a tarball download with arch detection),
add those steps directly to `Containerfile.template`.

### 3. Mount Credentials (if needed)

The profile's `provisioning.mounts` documents what host
directories need to be mounted. Add them to your
container run command or quadlet:

```bash
-v ~/.aider:/root/.aider          # podman run
Volume=%h/.aider:/root/.aider     # systemd quadlet
```

### 4. Set Auth Environment Variables

The profile's `provisioning.passthrough_env` documents
what environment variables the container needs. Pass them
through:

```bash
-e OPENAI_API_KEY="sk-..."               # podman run
Environment=OPENAI_API_KEY=sk-...        # systemd quadlet
```

### 5. Rebuild and Deploy

```bash
cd agent/
podman build -t agent-dashboard-daemon -f Containerfile .
```

Restart the daemon. The new tool will automatically:
- Appear as a spawn button with the configured color
- Show in the TUI tool selector
- Be available as a companion in terminal views
- Have its resume toggle derived from the commands config

No frontend or backend code changes are required.

## Notes

- The standard OTLP endpoint and resource attributes
  (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_RESOURCE_ATTRIBUTES`)
  are always injected by the daemon regardless of profile.
- Generic permission patterns (Y/n, yes/no, Continue?, etc.)
  are always active. Profile patterns are merged in addition.
- Profile changes require a daemon restart to take effect.
- The daemon logs which profiles were loaded at startup.
- Supported color keywords: `purple`, `blue`, `slate`,
  `green`, `red`, `amber`, `cyan`. Unknown keywords fall
  back to `slate`.
