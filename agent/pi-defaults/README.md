# Pi Default Configurations

This directory contains default configuration files for
Pi coding agent sessions running in the dashboard.

## Setup

Run the setup script to install all Pi defaults:

```bash
./agent/pi-defaults/setup.sh
```

This copies agent overrides to `~/.pi/agents/`, installs
the global `AGENTS.md`, and renames pi-task's tool from
`task` to `Agent` for proactive delegation.

## What's included

### Agent Overrides (`agents/`)

Agent definition overrides for the
[pi-task](https://github.com/heyhuynhgiabuu/pi-task)
sub-agent extension. Based on pi-task's bundled agent
definitions with the `model:` line removed so that
sub-agents inherit the parent session's provider and
model from `~/.pi/agent/settings.json`.

Without these overrides, pi-task's bundled agents
default to `opencode-go/deepseek-v4-flash`, which
fails if that provider isn't configured.

Pi-task's precedence: project agents > user agents >
bundled agents.

### Global AGENTS.md

Installs `~/.pi/agent/AGENTS.md` with task delegation
guidance that tells the model when and how to use
sub-agents proactively.

### pi-task Tool Name (`task` → `Agent`)

Claude (the model) is trained to proactively delegate
to a tool called `Agent` (Claude Code's built-in
sub-agent tool name). pi-task defaults to `task`,
which the model treats as a generic tool and only uses
when explicitly asked.

The Pi profile sets `PI_TASK_TOOL_NAME=Agent` in its
env vars, which pi-task (>= 0.3.5) reads at startup.
This causes the model to delegate autonomously,
matching Claude Code's native sub-agent behavior.

No manual patching is needed — the env var is injected
automatically by the daemon at spawn time.
