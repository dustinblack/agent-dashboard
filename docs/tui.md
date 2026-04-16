# TUI Frontend

The TUI (Terminal User Interface) provides a keyboard-driven
alternative to the web dashboard. It connects to the same
backend and supports spawning, monitoring, attaching to, and
stopping agent sessions — all from a terminal.

Built with [Python Textual](https://github.com/Textualize/textual)
and designed to work with tmux for multi-pane agent terminal
access.

## Quick Start

The TUI is bundled in the backend container. To launch it:

```bash
# Interactive shell into the backend container
podman exec -it <backend-container> python3 -m tui

# Or with tmux for session persistence
podman exec -it <backend-container> tmux new "python3 -m tui"
```

The TUI connects to `http://localhost:8000` by default (the
backend running in the same container). To connect to a
remote backend:

```bash
python3 -m tui --url http://your-hub-ip:8000
```

You can also install and run the TUI locally:

```bash
pip install -r tui/requirements.txt
python3 -m tui --url http://your-hub-ip:8000
```

## Keybindings

| Key | Action |
|-----|--------|
| `j` / `↓` | Move selection down |
| `k` / `↑` | Move selection up |
| `a` | Attach to selected agent (opens tmux window or foreground) |
| `x` | Stop selected agent |
| `s` | Open spawn screen |
| `r` | Refresh agent list |
| `q` | Quit |

### When attached to an agent session

| Key | Action |
|-----|--------|
| `Ctrl+C` | Disconnect from session |
| `Enter`, `~`, `.` | SSH-style detach sequence |

## Layout

The dashboard uses a two-tier display:

**Compact list** — One line per agent showing tool type,
project, branch, worktree indicator, status, and cost.
Task description on a second line.

**Detail pane** — Full telemetry for the selected agent:
model, context bar, token breakdown, cost, activity,
MCP servers, task description, worktree path, and runtime.

The detail pane updates as you navigate the list.

## tmux Integration

When running inside tmux, pressing `a` to attach opens
a new tmux window with the terminal client connected to
the selected agent. The window is named
`tool:project:branch` (e.g. `claude:agent-dashboard:main`).

Switch between the dashboard and agent terminals using
standard tmux window navigation (`Ctrl+B` then window
number or `n`/`p`).

When not in tmux, pressing `a` exits the TUI and runs the
terminal client in the foreground. The TUI can be relaunched
after disconnecting.

## Spawn Screen

Press `s` to open the spawn screen. Select:

1. **Host** — online hosts only
2. **Tool** — Claude, Gemini, or Bash
3. **Project** — populated from the selected host's scanned
   repositories
4. **Resume Session** — toggle to continue the latest session
   or start fresh
5. **Worktree Isolation** — toggle to create an isolated git
   worktree (smart default: ON when another agent is active
   on the same project)
6. **Task Description** — optional text

Press `Escape` to cancel.

## Standalone Terminal Client

The terminal client can be used independently to attach to
a specific agent session by UUID:

```bash
python3 -m tui attach <agent-uuid> --url http://your-hub-ip:8000
```

This provides raw PTY passthrough with history replay,
resize propagation, and DA response filtering. If the
session is stale (daemon was restarted), the client
automatically attempts to reconnect by spawning a
replacement agent with resume mode.

## Architecture

The TUI consists of two components:

1. **Dashboard app** (`tui/app.py`) — Textual application
   showing hosts, agents, and telemetry. Fetches data via
   REST API and receives live updates via Socket.IO.

2. **Terminal client** (`tui/terminal_client.py`) — Standalone
   asyncio script that provides raw terminal passthrough to
   a remote agent session via Socket.IO.

Both use `tui/client.py`, an async client library that wraps
the REST API and Socket.IO protocol.

## Requirements

- Python 3.9+
- tmux (recommended, for multi-pane support)
- Dependencies: `textual`, `python-socketio[asyncio_client]`,
  `httpx`, `aiohttp`

All dependencies are pre-installed in the backend container.
