# Pi Default Configurations

This directory contains default configuration files for
Pi coding agent sessions running in the dashboard.

## Agent Overrides (`agents/`)

These are agent definition overrides for the
[pi-task](https://github.com/heyhuynhgiabuu/pi-task)
sub-agent extension. They are based on pi-task's
bundled agent definitions with one critical change:
**the `model:` line is removed** so that sub-agents
inherit the parent session's provider and model from
`~/.pi/agent/settings.json`.

Without these overrides, pi-task's bundled agents
default to `opencode-go/deepseek-v4-flash`, which
fails if that provider isn't configured.

### Installation

Copy the agent overrides to your Pi user config
directory (persisted via the `~/.pi` volume mount):

```bash
cp -r agent/pi-defaults/agents/ ~/.pi/agents/
```

Or for project-level overrides (applies only to a
specific project):

```bash
cp -r agent/pi-defaults/agents/ /path/to/project/.pi/agents/
```

Pi-task's precedence: project agents > user agents >
bundled agents.
