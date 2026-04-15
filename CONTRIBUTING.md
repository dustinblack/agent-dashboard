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

### 4. Code Standards & Quality Checks
We maintain high standards for code quality. Before submitting a pull request, please run the following checks:

```bash
# To run all fast checks (format, lint, typecheck, secrets)
./scripts/check.sh precommit

# To run the full CI suite (includes tests and builds)
./scripts/check.sh ci
```

| Check | Tool |
| ----- | ---- |
| **Python Formatting** | `black` |
| **Python Linting** | `flake8` + `pylint` |
| **Frontend Formatting** | `prettier` |
| **Frontend Linting** | `eslint` |
| **Frontend Types** | `tsc` (TypeScript) |
| **Secrets Detection** | `gitleaks` |

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
