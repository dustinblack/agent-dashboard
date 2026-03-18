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
- **Deployment**: Podman (rootless) on RHEL 9 using `podman-compose`.
- **Integration**: Python wrapper script using `pty` or `pexpect`.

## Coding Standards

### Python
- **Formating**: Use `black` for formatting.
- **Linting**: Adhere to `flake8` and `pylint` standards.
- **Documentation**: Use Google-style docstrings. Be verbose with documentation for new functions.
- **Error Handling**: Implement robust error handling and logging in all new functions.
- **Style**: Max line length of 88 characters.

### Frontend (React/TypeScript)
- **Formatting**: Use `prettier`.
- **Linting**: Use `eslint` with project-specific configurations.
- **Language**: Use TypeScript for all new components and logic.
- **Styling**: Use Tailwind CSS v4 utility classes. Custom CSS should only be used for overrides that Tailwind cannot express (e.g., third-party component styling).

## Workflow & Safety

### Research & Strategy
- **Research Phase**: Systematically map the codebase and validate assumptions. Prioritize empirical reproduction of issues.
- **Strategy Phase**: Share a concise summary of the strategy before execution.
- **Plan Mode**: Use `enter_plan_mode` for architectural changes, new features, or complex refactoring.

### Execution & Validation
- **Atomic Changes**: Keep changes surgical and focused on the sub-task.
- **Testing**: Every change must include verification logic (e.g., unit tests, integration tests, or reproduction scripts).
- **Validation**: Run project-specific build, lint, and test commands before finalizing.

### Security
- **Secrets**: Never log, print, or commit secrets, API keys, or sensitive credentials.
- **OIDC**: Ensure all UI-facing endpoints are protected by OIDC.
- **Agent Auth**: Ensure all agent-facing Socket.IO namespaces require a valid `MACHINE_TOKEN`.

## Git & Documentation
- **Commits**: Git commit messages should be thorough and verbose. Always include the tag `AI-assisted-by: <model name and version>`.
- **Commit Strategy**: Do not amend commits unless explicitly asked. Always create new commits.
- **Documentation**: Always add documentation for new features and keep existing documentation updated with changes. Documentation must be user-friendly for both beginner users and developers alike. Never remove existing code documentation unless the code itself is removed.

## Critical Mandates
- **User Approval**: Agents MUST request and receive explicit approval from the user before starting any new phase of the implementation plan.
- **Persistence**: Ensure the SQLite database is persisted via host mounts in the Podman configuration.
- **Python Imports**: Avoid dependency imports outside of the top level. If warranted, justify and comment appropriately.
