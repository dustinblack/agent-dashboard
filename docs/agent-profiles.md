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

### Field Reference

#### Top-Level Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | **yes** | — | Unique identifier used in spawn requests and internal lookups. Must match the filename (e.g., `claude` for `claude.yaml`). |
| `display_name` | string | no | `""` | Human-readable name shown in UI buttons, badges, and logs. |
| `color` | string | no | `"slate"` | UI theme color keyword for spawn buttons and badges. Supported: `purple`, `blue`, `slate`, `green`, `red`, `amber`, `cyan`. |
| `binary` | string | no | `""` | CLI binary name. Used for availability detection via `<binary> --version`. |
| `always_available` | bool | no | `false` | If true, skip binary and auth checks — always show as available (e.g., `bash`). |
| `env` | map | no | `{}` | Environment variables injected at agent spawn time. Values support `{otlp_port}` and `{agent_id}` placeholders. |
| `permission_patterns` | list | no | `[]` | Regex patterns (case-insensitive) for detecting permission prompts in terminal output. Merged with built-in defaults (`Y/n`, `yes/no`, `Continue?`, etc.). |

#### `commands`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `commands.new` | list | no | `[]` | Command and arguments for starting a new session. Supports custom CLI flags: `["claude", "--model", "opus"]`. |
| `commands.resume` | list | no | `[]` | Command and arguments for resuming a previous session. If identical to `new`, the UI won't show a resume toggle. Can use bash fallback chains: `["bash", "-c", "tool --resume --model opus \|\| tool --model opus"]`. Include the same custom flags in both the resume and fallback commands. |

#### `auth`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `auth.env_vars` | list | no | `[]` | Environment variable names to check for authentication. If empty, the tool is available whenever the binary exists. |
| `auth.require` | string | no | `"any"` | `"any"` = at least one env var must be set. `"all"` = all must be set. |

#### `mcp`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mcp.project_file` | string | no | `null` | Project-level MCP config filename (relative to project dir, e.g., `.mcp.json`). |
| `mcp.user_files` | list | no | `[]` | User-level MCP config file paths (`~` is expanded). |

#### `telemetry`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `telemetry.token_metrics` | list | no | `[]` | OTLP metric names for token usage tracking (cumulative counters). |
| `telemetry.cost_metric` | string | no | `null` | OTLP metric name for cost tracking (USD). |
| `telemetry.activity_metrics` | list | no | `[]` | OTLP metric names for tool/function activity (sets `current_activity`). |
| `telemetry.runtime_metric.name` | string | no | `""` | OTLP metric name for runtime duration. |
| `telemetry.runtime_metric.unit` | string | no | `"seconds"` | Unit of the runtime metric: `"seconds"` or `"milliseconds"`. |
| `telemetry.excluded_metrics` | list | no | `[]` | OTLP metric names to explicitly ignore (avoid double-counting). |

#### `sidecar`

For tools without OTLP support (e.g., bash). The daemon
injects a `PROMPT_COMMAND` that writes telemetry to a JSON
file, which the daemon reads periodically.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `sidecar.prompt_command` | string | no | `null` | Shell command injected as `PROMPT_COMMAND`. Should output JSON to stdout. |
| `sidecar.file_pattern` | string | no | `"{tmpdir}/.agent-telemetry-{agent_id}"` | Path template for the sidecar JSON file. `{tmpdir}` and `{agent_id}` are replaced at runtime. |
| `sidecar.fields` | map | no | `{}` | Maps sidecar JSON keys to telemetry field names (e.g., `current_activity: cwd`). |

#### `provisioning`

Optional build-time metadata used by
`generate_containerfile.py` to produce the Containerfile,
and as documentation for manual container setup.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `provisioning.install.npm` | list | no | `[]` | npm packages to install globally (`npm install -g`). |
| `provisioning.install.pip` | list | no | `[]` | pip packages to install (`pip3 install`). |
| `provisioning.install.system` | list | no | `[]` | System packages to install via the package manager (`dnf install`). |
| `provisioning.config_files` | list | no | `[]` | Config files to seed in the container image. Each entry has `path` (string), `mkdir` (bool), and optionally `content` (string). |
| `provisioning.verify` | string | no | `null` | Command to verify the installation succeeded (e.g., `"claude --version"`). Run as a `RUN` step in the Containerfile. |
| `provisioning.mounts` | list | no | `[]` | Host volume mounts. Each entry has `host` (string, `~` expanded), `container` (string), and `mode` (`"rw"` or `"ro"`). |
| `provisioning.passthrough_env` | list | no | `[]` | Environment variables to pass from the host to the container at runtime (via `podman run -e` or quadlet `Environment=`). Distinct from `env` which the daemon injects at agent spawn time. |

### Full Example

```yaml
name: myagent
display_name: My Agent
color: green
binary: myagent-cli
always_available: false

commands:
  new: ["myagent-cli"]
  resume: ["bash", "-c", "myagent-cli --resume || myagent-cli"]

env:
  MY_AGENT_TELEMETRY: "true"
  MY_AGENT_OTLP_ENDPOINT: "http://127.0.0.1:{otlp_port}"

auth:
  env_vars:
    - MY_AGENT_API_KEY
  require: any

mcp:
  project_file: .mcp.json
  user_files:
    - ~/.myagent/config.json

telemetry:
  token_metrics:
    - myagent.token.usage
  cost_metric: myagent.cost.usage
  activity_metrics:
    - myagent.tool.execution
  runtime_metric:
    name: myagent.active_time
    unit: seconds
  excluded_metrics:
    - gen_ai.client.token.usage

sidecar:
  prompt_command: >-
    printf '{"cwd":"%s"}\n' "$PWD"
  file_pattern: "{tmpdir}/.agent-telemetry-{agent_id}"
  fields:
    current_activity: cwd

permission_patterns:
  - "Do you want to proceed"
  - "Allow .+ to run"

provisioning:
  install:
    npm:
      - "@example/my-agent-cli"
  config_files:
    - path: "/root/.myagent"
      mkdir: true
    - path: "/root/.myagent/config.json"
      content: '{"key": "value"}'
  verify: "myagent --version"
  mounts:
    - host: "~/.myagent"
      container: "/root/.myagent"
      mode: rw
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
