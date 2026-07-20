# Agent Behavior & Standards for Agent Dashboard

This document establishes the baseline behavior and technical standards for AI agents collaborating on the Agent Dashboard project.

## Inspiration

This project is inspired by the following blog post:
- [Building an AI Coding Agent Dashboard with React and FastAPI](https://blog.marcnuri.com/ai-coding-agent-dashboard)

## Core Technical Stack

- **Backend**: Python 3.9+ with FastAPI and `python-socketio`.
- **Frontend**: React (TypeScript) via Vite, `xterm.js`, and `socket.io-client`.
- **Database**: SQLite with SQLAlchemy ORM.
- **Authentication**: OIDC/OAuth for UI users; Static API Keys (Machine Tokens) for agents.
- **Deployment**: OCI containers (Podman/Docker) using `compose`.
- **Integration**: Python wrapper script using `pty` or `pexpect`.

## Coding Standards

### Python
- **Formatting**: Use `black` for formatting.
- **Linting**: Adhere to `flake8` and `pylint` standards.
- **Documentation**: Use Google-style docstrings. Be verbose with documentation for new functions.
- **Error Handling**: Implement robust error handling and logging in all new functions.
- **Style**: Max line length of 88 characters.

### Frontend (React/TypeScript)
- **Formatting**: Use `prettier`.
- **Linting**: Use `eslint` with project-specific configurations.
- **Language**: Use TypeScript for all new components and logic.
- **Styling**: Use Tailwind CSS v4 utility classes. Custom CSS should only be used for overrides that Tailwind cannot express (e.g., third-party component styling).

## Task Delegation

When a `task` tool is available, use it proactively to
delegate work to specialist sub-agents:

- **explore** — use when you need to map unfamiliar
  parts of the codebase, find symbols across modules,
  or gather `path:line` evidence before making changes.
- **scout** — use when the answer requires official
  documentation, web research, API behavior, or
  knowledge not found in the repository.
- **general** — use for parallel units of work,
  multi-step implementation tasks, or research that
  may require edits to validate.
- **reviewer** — use after non-trivial edits to get an
  independent code review before presenting results.

Delegate when:
- The task involves multiple independent subtasks that
  can run in parallel.
- You need to research while simultaneously editing.
- The work benefits from isolated context (e.g.,
  exploring a subdirectory while the parent works on
  another).
- A code review would add confidence before committing.

Do NOT delegate trivial tasks (1–3 tool calls, 1–2
  files) — handle those directly.

## Workflow & Safety

### Research & Strategy
- **Research Phase**: Systematically map the codebase and validate assumptions. Prioritize empirical reproduction of issues.
- **Strategy Phase**: Share a concise summary of the strategy before execution.
- **Plan Mode**: Use `enter_plan_mode` for architectural changes, new features, or complex refactoring.

### Execution & Validation
- **Atomic Changes**: Keep changes surgical and focused on the sub-task.
- **Testing**: Every change must include verification logic (e.g., unit tests, integration tests, or reproduction scripts).
- **Validation**: Run project-specific build, lint, and test commands before finalizing.

### Automated Checks
- **Pre-commit**: Run `./scripts/check.sh precommit` before committing (or install the git hook via `./scripts/install-hooks.sh`).
- **CI**: GitHub Actions runs format, lint, typecheck, build, test, and security checks on all PRs. All checks must pass.
- **Coverage**: Unit test coverage reports are generated at `coverage/backend/index.html`.

### Security
- **Secrets**: Never log, print, or commit secrets, API keys, or sensitive credentials.
- **OIDC**: Ensure all UI-facing endpoints are protected by OIDC.
- **Agent Auth**: Ensure all agent-facing Socket.IO namespaces require a valid `MACHINE_TOKEN`.

## Git & Documentation
- **Commits**: Git commit messages should be thorough and verbose. Always include the tag `Co-authored-by: <model name> <email>`.
- **Commit Strategy**: Do not amend commits unless explicitly asked. Always create new commits.
- **Documentation**: Always add documentation for new features and keep existing documentation updated with changes. Documentation must be user-friendly for both beginner users and developers alike. Never remove existing code documentation unless the code itself is removed.

## Agent Tool Awareness
- This project integrates with Claude Code, Gemini CLI, and their OpenTelemetry telemetry. Proactively flag when you know of new model releases, CLI features, telemetry schema changes, or pricing updates that affect the dashboard's integration points. Suggest filing an issue if the change isn't part of the current task.

## Critical Mandates
- **User Approval**: Agents MUST request and receive explicit approval from the user before starting any new phase of the implementation plan.
- **Persistence**: Ensure the SQLite database is persisted via host mounts in the Podman configuration.
- **Python Imports**: Avoid dependency imports outside of the top level. If warranted, justify and comment appropriately.
