# Pi Default Configurations

This directory contains default configuration files for
Pi coding agent sessions running in the dashboard.

## Setup

Run the setup script to install all Pi defaults:

```bash
./agent/pi-defaults/setup.sh
```

This copies agent overrides to `~/.pi/agent/agents/`,
installs the global `AGENTS.md`, and patches pi-task
if needed.

## What's included

### Agent Overrides (`agents/`)

Agent definition overrides for the
[pi-task](https://github.com/heyhuynhgiabuu/pi-task)
sub-agent extension. Based on pi-task's bundled agent
definitions with the `model:` line removed so that
sub-agents inherit the parent session's default model
from `~/.pi/agent/settings.json`.

Without these overrides, pi-task's bundled agents
default to `opencode-go/deepseek-v4-flash`, which
fails if that provider isn't configured.

#### Precedence

Pi-task loads agent definitions from three locations
and merges by name, with later sources winning:

1. **Bundled** — shipped with pi-task
2. **User** — `~/.pi/agent/agents/*.md`
3. **Project** — `.pi/agents/*.md` in the repo

Project-level agents override user-level agents of the
same name. This is important for `model:` overrides —
if a project agent definition omits `model:`, it
shadows any user-level definition that sets one.

#### Model and Thinking Overrides

Each agent `.md` file supports `model:` and `thinking:`
in its YAML frontmatter:

```yaml
---
description: >-
  Agent description here.
model: vertex/claude-sonnet-4-6
thinking: medium
readonly: true
proactive: true
---
```

**`model:`** — Sets the model for this sub-agent.
Format is `provider/model-id` (e.g.,
`vertex/claude-sonnet-4-6`) or just `model-id` if your
default provider is correct. When omitted, the
sub-agent inherits `defaultModel` from
`~/.pi/agent/settings.json` — **not** the parent
session's runtime model. This is because the tmux
backend spawns an independent `pi` CLI process that
reads its own config.

To see available models:
```bash
pi --list-models
```

**`thinking:`** — Sets the thinking/reasoning level.
Valid values: `off`, `minimal`, `low`, `medium`,
`high`, `xhigh`, `max`. Not all models support
extended thinking — notably, Haiku 4.5 only accepts
`disabled` or `enabled` and will crash with `high` or
above. Match the thinking level to the model's
capabilities.

#### Recommended Model Assignments

Assign models based on each agent's role and the
cost/quality tradeoff:

| Agent | Role | Recommended Tier | Thinking |
|-------|------|-----------------|----------|
| **explore** | Read-only codebase mapping | Fast/cheap (e.g., Haiku) | `off` |
| **scout** | External research & docs | Mid-tier (e.g., Sonnet) | `off`–`medium` |
| **general** | Code implementation | Strong (e.g., Opus, Sonnet) | `medium`+ |
| **reviewer** | Code review & audit | Strong (e.g., Sonnet, Gemini Pro) | `high`–`xhigh` |

Using a different model family for the reviewer (e.g.,
Gemini for review when Claude writes the code) avoids
blind spots where the same model overlooks its own
patterns.

#### Example: Custom Model Configuration

Copy the defaults and add your model preferences:

```bash
# Install defaults
./agent/pi-defaults/setup.sh

# Edit your user-level agents
vim ~/.pi/agent/agents/explore.md   # add: model: vertex/claude-haiku-4-5
vim ~/.pi/agent/agents/general.md   # add: model: vertex/claude-sonnet-4-6
vim ~/.pi/agent/agents/reviewer.md  # add: model: google/gemini-3.1-pro-preview
vim ~/.pi/agent/agents/scout.md     # add: model: vertex/claude-sonnet-4-6
```

> **Note:** Do not add project-level `.pi/agents/`
> files that omit `model:` — they will shadow your
> user-level overrides and all sub-agents will fall
> back to `defaultModel` from settings.json.

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
