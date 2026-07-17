# Agent Profiles

Agent profiles define how the host daemon spawns, detects,
and monitors each AI coding agent tool. Instead of hardcoded
logic for specific tools, the daemon reads YAML or JSON
profile files from the `agent/profiles/` directory at
startup.

## Bundled Profiles

Four profiles are included out of the box:

| Profile | File | Description |
|---------|------|-------------|
| Claude | `agent/profiles/claude.yaml` | Claude Code CLI with OTLP telemetry and MCP detection |
| Antigravity | `agent/profiles/agy.yaml` | Antigravity CLI (`agy`) — Google's replacement for Gemini CLI |
| Pi | `agent/profiles/pi.yaml` | Pi coding agent — provider-agnostic, supports Claude/GPT/Gemini/local models |
| Gemini | `agent/profiles/gemini.yaml` | Gemini CLI (sunset June 18, 2026 — replaced by Antigravity) |
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

## Local Overrides

Profile files in `agent/profiles/` are tracked by Git.
To customize a profile for your environment without
modifying tracked files, create a companion
`.local.yaml` file:

```
agent/profiles/pi.local.yaml
```

The `.local` suffix is already in `.gitignore`, so
these files won't be committed or cause dirty working
trees.

### Example

To allow Pi to connect to MCP servers with self-signed
TLS certificates:

```yaml
# agent/profiles/pi.local.yaml
name: pi
env:
  NODE_TLS_REJECT_UNAUTHORIZED: "0"
```

To add a custom model flag and extra provider key:

```yaml
# agent/profiles/claude.local.yaml
name: claude
commands:
  new: ["claude", "--model", "opus"]
  resume: ["bash", "-c", "claude --continue --model opus || claude --model opus"]
env:
  MY_CUSTOM_VAR: "value"
```

### Merge behavior

Local overrides are merged into the base profile
before parsing. The merge semantics depend on the
field type:

| Field type | Behavior | Example |
|-----------|----------|--------|
| **Scalars** (`binary`, `color`, etc.) | Local replaces base | `color: green` overrides `color: blue` |
| **`env`** (dict) | Dict merge — local keys override, base keys preserved | Local `{B: 2}` + base `{A: 1}` → `{A: 1, B: 2}` |
| **`commands`** (dict) | Dict merge — local keys override per-command | Local `{new: [...]}` overrides `new`, preserves `resume` |
| **`permission_patterns`** (list) | Extend — local items appended, duplicates removed | |
| **`telemetry.*_metrics`** (lists) | Extend | `token_metrics`, `activity_metrics`, `excluded_metrics` |
| **`mcp.user_files`** (list) | Extend | |
| **`provisioning.passthrough_env`** (list) | Extend | |
| **`sidecar.fields`** (dict) | Dict merge | |
| **`name`** | Never overridden | Used for matching only |

### Supported file extensions

The daemon checks for companions in this order:
1. `{name}.local.yaml`
2. `{name}.local.yml`
3. `{name}.local.json`

Only the first match is used.

### Error handling

If a `.local` file is malformed (invalid YAML/JSON),
the base profile loads without the override and the
error is logged. A `.local` file without a matching
base profile is silently ignored.

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

## Migrating from Gemini CLI to Antigravity CLI

Google's Antigravity CLI (`agy`) replaces Gemini CLI,
which sunset **June 18, 2026** for free and personal
users. Enterprise API key users can continue using
Gemini CLI.

The Antigravity profile requires **agy >= 1.0.12**,
which added `--add-dir` (workspace directory targeting)
and `--continue` (session resume from the command line).

### Automatic migration

On first launch, `agy` auto-migrates Gemini CLI config
(MCP servers, permissions, keybindings). Since both
tools share the `~/.gemini` volume mount, migration
finds existing config automatically. You can also run
`agy plugin import gemini` manually inside a session.

### Workspace targeting

The profile uses `--new-project --add-dir .` to create
a fresh project context and add the daemon's working
directory to agy's workspace. `--new-project` prevents
agy's implicit memory (learned from previous host-side
sessions) from bleeding stale paths into the container
workspace. Without it, agy may try to navigate to
host paths like `/home/user/...` that don't exist
inside the container.

### Workspace isolation

The following settings in
`~/.gemini/antigravity-cli/settings.json` are
recommended for dashboard use:

```json
{
  "allowNonWorkspaceAccess": false,
  "enableTelemetry": true
}
```

- **`allowNonWorkspaceAccess: false`** — prevents agy
  from reading or writing files outside the workspace.
  If you explicitly ask agy to access an external
  path, it will prompt for permission instead of
  silently exploring.
- **`enableTelemetry: true`** — required for OTLP
  telemetry export. Without this, `settings.json`
  overrides the profile’s `GEMINI_CLI_TELEMETRY_ENABLED`
  env var and telemetry is silently disabled.

The profile provisions these as defaults for fresh
installs, but the host `~/.gemini` volume mount
overlays them at runtime — set them on your host
machine to ensure they take effect.

### Session resume

The resume command uses `--continue` to pick up the
most recent conversation. If no prior session exists,
it falls back to starting a new conversation. The
`--conversation <id>` flag is also available for
resuming a specific conversation, but the profile
defaults to the simpler `--continue` behavior.

### Coexistence

Both profiles can be active simultaneously during the
transition period — Gemini and Antigravity appear as
separate spawn buttons in the dashboard. This allows
testing `agy` while keeping Gemini sessions running.

### Post-sunset cleanup

After June 18, 2026, free/personal users can remove
`agent/profiles/gemini.yaml` and regenerate the
Containerfile to drop Gemini CLI from the container
image.

## Recommended Pi Extensions

Pi uses community extensions for telemetry and MCP
connectivity. Extensions are installed per-user inside
a Pi session and persist via the `~/.pi` volume mount.
They cannot be pre-installed in the container image
because the host volume mount overlays the container's
`/root/.pi` directory at runtime.

Install the following inside a Pi session on first use:

| Extension | Install Command | Purpose |
|-----------|----------------|---------|
| [pi-otel](https://www.npmjs.com/package/pi-otel) | `pi install npm:pi-otel` | OTLP telemetry for dashboard cards (model, tokens, cost, activity). |
| [pi-mcp](https://github.com/0xKobold/pi-mcp) | `pi install npm:@0xkobold/pi-mcp` | MCP server connectivity. Supports stdio, SSE, HTTP, and WebSocket transports. |
| [pi-task](https://github.com/heyhuynhgiabuu/pi-task) | `pi install npm:@heyhuynhgiabuu/pi-task` | Sub-agent delegation with tmux pane visibility. Proactive agents explore, research, and review in parallel. |

Install all at once:

```
pi install npm:pi-otel npm:@0xkobold/pi-mcp npm:@heyhuynhgiabuu/pi-task
```

> **Note:** Extensions persist via the `~/.pi` volume
> mount. Install once per host — they survive container
> restarts.

### Extension configuration

- **pi-otel**: The Pi profile injects the essential
  OTLP environment variables at spawn time:
  - `OTEL_EXPORTER_OTLP_ENDPOINT` — set by the daemon
    to `http://127.0.0.1:{otlp_port}` for all tools.
  - `OTEL_EXPORTER_OTLP_PROTOCOL` — set to `http/json`
    so pi-otel uses the daemon's HTTP/JSON receiver.
  - `OTEL_SERVICE_NAME` — set to the agent's unique ID
    so the daemon can match OTLP data to the correct
    session. **This is required for multi-instance
    tracking.** Pi-otel reads `OTEL_SERVICE_NAME` with
    higher priority than `OTEL_RESOURCE_ATTRIBUTES` —
    without it, all Pi sessions report
    `service.name="pi"` (the default) and the daemon
    cannot distinguish between them.
  - `PI_OTEL_METRICS` — set to `1` to enable the
    `PeriodicExportingMetricReader` in the OTel SDK.
    **Metrics are disabled by default in pi-otel.** Without
    this, the token usage histogram, tool call counter,
    and operation duration histogram defined in the Pi
    profile's `telemetry` section are never emitted.
    Token tracking partially falls back to span
    attributes, but the activity counter and runtime
    histogram are lost.

  You can optionally configure additional settings in
  `~/.pi/agent/settings.json`:
  ```json
  {
    "otel": {
      "enabled": true,
      "protocol": "http/json",
      "signals": {
        "traces": true,
        "metrics": true,
        "logs": true
      }
    }
  }
  ```
  The profile's env vars take precedence over
  settings.json for the values they set. The `logs`
  signal can be enabled via `PI_OTEL_LOGS=1` env var
  or in settings.json — it forwards OTel internal
  diagnostics to the OTLP endpoint.

  > **Note (pi-otel v0.1.0):** HTTP exporters may
  > send to `POST /` instead of `/v1/{signal}` paths
  > ([details](https://github.com/NikiforovAll/pi-otel/issues/4)).
  > The daemon includes a permanent root-path
  > compatibility route that auto-detects the signal
  > type from the payload, so this is handled
  > transparently.
- **pi-mcp**: Reads server configs from
  `~/.pi/agent/mcp.json`. Can import configs from
  Claude Code, Cursor, and VS Code.
- **pi-task**: Spawns sub-agents in tmux panes
  (visible in the dashboard terminal) or falls back
  to the Pi SDK when tmux is unavailable. Includes
  four built-in agent types:
  - **explore** (proactive) — read-only codebase
    mapping with `path:line` evidence.
  - **scout** (proactive) — web/docs research for
    answers not found in the repo.
  - **general** (proactive) — multi-step tasks:
    research, implementation, or mixed.
  - **reviewer** (proactive) — code review after
    non-trivial edits.

  **Important:** pi-task's bundled agents default to
  `opencode-go/deepseek-v4-flash`, which fails if
  that provider isn't configured. Copy the dashboard's
  agent overrides (which remove the hardcoded model so
  sub-agents inherit from `settings.json`) to your Pi
  user config:

  ```bash
  cp -r agent/pi-defaults/agents/ ~/.pi/agents/
  ```

  Set `PI_TASK_CHILD_NO_EXTENSIONS=1` in the Pi
  profile's env if sub-agents crash on startup due to
  extension load errors (e.g. pi-vertex `baseUrl`
  bug, see [#94](https://github.com/dustinblack/agent-dashboard/issues/94)).

  When running inside the dashboard's tmux-wrapped
  sessions (#83), pi-task automatically detects tmux
  and creates split panes for sub-agents. The parent
  and sub-agent panes are both visible in the
  dashboard terminal.

### Alternative: pi-subagents

[pi-subagents](https://www.npmjs.com/package/@tintinweb/pi-subagents)
(by tintinweb) is a popular alternative sub-agent
extension that uses Pi's in-process SDK instead of
tmux. It provides Claude Code-style tool names
(`Agent`, `get_subagent_result`, `steer_subagent`),
a live widget UI, FleetView, and scheduled agents.

Install as a replacement or alongside pi-task:

```
pi install npm:@tintinweb/pi-subagents
```

| Feature | pi-task | pi-subagents |
|---------|---------|-------------|
| Execution | tmux panes (visible) | In-process (invisible) |
| tmux required | No (SDK fallback) | No |
| Proactive delegation | Yes | Yes |
| Steering mid-run | No | Yes |
| Session resume | Yes (tmux) | Yes |
| Dashboard visibility | Sub-agent panes visible | No — runs inside parent |

pi-task is recommended for dashboard use because
sub-agent activity is visible in the terminal. Both
extensions can coexist but will register competing
`task`/`Agent` tools — install only one at a time.

### Using Pi with Vertex AI

Pi supports Claude and Gemini models via Google Cloud
Vertex AI through the `@ssweens/pi-vertex` extension.

**1. Install the extension** inside a Pi session:

```
pi install npm:@ssweens/pi-vertex
```

**2. Set the default provider** in
`~/.pi/agent/settings.json`:

```json
{
  "defaultProvider": "vertex",
  "defaultModel": "claude-sonnet-4-6"
}
```

This avoids needing `--provider vertex` on the command
line — Pi will use Vertex AI by default for all
sessions. You can also set `defaultModel` to your
preferred model.

**3. Add Vertex env vars** to your daemon quadlet or
`podman run` command. Pi-vertex uses different env var
names than Claude Code:

```ini
# If you already have ANTHROPIC_VERTEX_PROJECT_ID and
# CLOUD_ML_REGION for Claude Code, add these with the
# same values:
Environment=GOOGLE_CLOUD_PROJECT=your-gcp-project-id
Environment=GOOGLE_CLOUD_LOCATION=us-east5
```

| Claude Code env var | Pi-vertex equivalent |
|---|---|
| `ANTHROPIC_VERTEX_PROJECT_ID` | `GOOGLE_CLOUD_PROJECT` |
| `CLOUD_ML_REGION` | `GOOGLE_CLOUD_LOCATION` |
| `CLAUDE_CODE_USE_VERTEX` | (not used by Pi) |

The gcloud ADC credentials (`~/.config/gcloud` mount)
handle authentication for both Claude Code and Pi — no
additional credential setup needed.

> **Note:** A built-in Vertex AI provider for Pi is
> [proposed upstream](https://github.com/earendil-works/pi/issues/5082),
> which would eliminate the need for this extension.

### Replacing an extension

These are community-maintained packages. If a better
alternative emerges or one becomes unmaintained, swap
it with `pi uninstall <old>` and `pi install <new>`.
Update this documentation when replacing a recommended
extension.

## Known Limitations

### Self-signed TLS certificates

Pi (and other Node.js-based agents like Claude Code and
Gemini CLI) will reject connections to MCP servers or
other services that use self-signed TLS certificates.
If you need to connect to such services, set
`NODE_TLS_REJECT_UNAUTHORIZED=0` in the agent's
environment.

The recommended approach is a [local override](#local-overrides)
so you don't modify the tracked profile:

```yaml
# agent/profiles/pi.local.yaml
name: pi
env:
  NODE_TLS_REJECT_UNAUTHORIZED: "0"
```

Alternatively, pass it through to the container at
runtime:

```bash
-e NODE_TLS_REJECT_UNAUTHORIZED=0    # podman run
Environment=NODE_TLS_REJECT_UNAUTHORIZED=0  # quadlet
```

> **Security note:** This disables TLS certificate
> verification for all outbound HTTPS connections in
> that agent process, not just the MCP server. Only
> use this in environments where you trust the network
> (e.g., internal development networks with a private
> CA). The preferred solution is to install your CA
> certificate in the container's trust store.

### Session resume path mismatch

Claude Code keys project history by **absolute CWD path**.
Host sessions use paths like `/home/user/workspace/project`,
but inside the daemon container the same project is mounted
at a different path (e.g., `/git/project`). This creates
separate project directories in `~/.claude/projects/` —
`/resume` inside a daemon session won't find conversations
from host-side sessions, and vice versa.

**Workaround:** Start and resume sessions consistently from
the same environment (always via the dashboard, or always
on the host). Alternatively, mount volumes at paths matching
the host (e.g., `-v /home/user/workspace:/home/user/workspace`)
so the CWD is identical in both environments.

## Notes

- The standard OTLP endpoint and resource attributes
  (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_RESOURCE_ATTRIBUTES`)
  are always injected by the daemon regardless of profile.
- Some OTel SDKs (notably pi-otel) read `OTEL_SERVICE_NAME`
  with higher priority than the `service.name` key in
  `OTEL_RESOURCE_ATTRIBUTES`. Profiles for such tools
  should set `OTEL_SERVICE_NAME: "{agent_id}"` in their
  `env` section to ensure correct multi-instance tracking.
- Generic permission patterns (Y/n, yes/no, Continue?, etc.)
  are always active. Profile patterns are merged in addition.
- Profile changes require a daemon restart to take effect.
- The daemon logs which profiles were loaded at startup.
- Supported color keywords: `purple`, `blue`, `slate`,
  `green`, `red`, `amber`, `cyan`. Unknown keywords fall
  back to `slate`.
