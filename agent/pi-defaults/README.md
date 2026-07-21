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

### pi-task Tool Rename (`task` → `Agent`)

Claude (the model) is trained to proactively delegate
to a tool called `Agent` (Claude Code's built-in
sub-agent tool name). pi-task registers its tool as
`task`, which the model treats as a generic tool and
only uses when explicitly asked.

The setup script renames the tool from `task` to
`Agent` via a sed patch, causing the model to delegate
autonomously. This is a workaround pending an upstream
configuration option
([heyhuynhgiabuu/pi-task#11](https://github.com/heyhuynhgiabuu/pi-task/issues/11)).

> **Note:** The patch must be reapplied after upgrading
> pi-task (`pi install npm:@heyhuynhgiabuu/pi-task`).
> Run `setup.sh` again after upgrades.
