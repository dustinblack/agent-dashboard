# Contributing to the Agent Dashboard

Thank you for your interest in contributing to the Agent Dashboard! We welcome contributions from everyone.

## Getting Started

### 1. Prerequisites
Before you begin, ensure you have the following installed on your development machine:
- Python 3.9+
- Node.js 22+
- `pip` and `npm`
- A container runtime (Podman or Docker)

### 2. Set Up Your Local Environment
Fork the repository and clone it to your local machine:
```bash
git clone https://github.com/your-username/agent-dashboard.git
cd agent-dashboard
```

Install the project dependencies and the pre-commit hook:
```bash
# Install Python dev dependencies
pip install -r backend/requirements.txt \
            -r agent/requirements.txt \
            -r requirements-dev.txt

# Install frontend dependencies
cd frontend && npm install && cd ..

# Install the pre-commit hook
./scripts/install-hooks.sh
```

### 3. Development Workflow
Always work on a new branch for each contribution:
```bash
git checkout -b your-feature-name
```

#### Working with AI Development Agents
This project is built with AI-first development in mind. We encourage the use of AI development agents (e.g., Gemini CLI) to assist with implementation, refactoring, and testing.

If you are using an AI development agent, please ensure that it is aware of and adheres to the standards defined in **[AGENTS.md](AGENTS.md)**. These standards are designed to ensure that agent-generated code remains consistent, high-quality, and easy to maintain.

**Mandatory Pre-commit Hooks:** When using an AI agent, it is critically important to ensure you have installed the pre-commit hooks (`./scripts/install-hooks.sh`). AI agents can introduce formatting, linting, or type errors that might slip past manual review. The hooks ensure that the project's shared quality check scripts run automatically during every commit, providing an essential layer of automated verification that remains outside the direct purview of the AI agent.

### 4. Code Standards & Quality Checks
We maintain high standards for code quality.

If you followed the instructions in step 2 to install the pre-commit hook (`./scripts/install-hooks.sh`), the quality checks will run automatically whenever you `git commit`.

You can also run them manually at any time to verify your work before committing:

```bash
# To run all fast checks (format, lint, typecheck, secrets)
./scripts/check.sh precommit

# To run the full CI suite (includes tests and builds)
./scripts/check.sh ci
```

| Command | What it runs |
|---------|-------------|
| `./scripts/check.sh format` | `black` (Python), `prettier` (frontend) |
| `./scripts/check.sh lint` | `flake8` + `pylint` (Python), `eslint` (frontend) |
| `./scripts/check.sh typecheck` | TypeScript type checking (`tsc`) |
| `./scripts/check.sh test` | Backend unit tests with coverage |
| `./scripts/check.sh security` | `bandit` (Python), `npm audit` (frontend) |
| `./scripts/check.sh secrets` | Secret detection (`gitleaks`) |
| `./scripts/check.sh precommit` | format + lint + typecheck + secrets (fast) |
| `./scripts/check.sh ci` | format + lint + typecheck + build + test + security + secrets |

### 5. Submitting a Pull Request
Once your changes are complete and all checks pass:
1.  Push your changes to your fork on GitHub.
2.  Open a Pull Request (PR) from your branch to the `main` branch of the original repository.
3.  Provide a clear and concise description of your changes in the PR.
4.  Reference any related issues using their ID (e.g., `Fixes #123`).

## Code of Conduct
By participating in this project, you agree to abide by our **[Code of Conduct](CODE_OF_CONDUCT.md)**.

## Questions?
If you have any questions or need help, please open an issue on GitHub.
