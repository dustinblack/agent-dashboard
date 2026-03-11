# Implementation Plan: Gemini AI Coding Agent Dashboard

## Background & Motivation
The goal is to implement an "AI Coding Agent Dashboard" specifically designed for the Gemini CLI. This dashboard will provide centralized orchestration, allowing the user to view all active agent sessions across multiple machines, inspect token usage/context, and remotely interact with the agents' terminal sessions directly from any modern web browser.

## Tech Stack & Architecture
Based on your preferences, the system will be built using the following stack:
- **Backend Server**: **Python / FastAPI** for the core API, integrated with **Socket.IO** (`python-socketio`) for robust real-time communication.
- **Database**: **SQLite** (easy to persist in a single volume on the host).
- **Frontend Dashboard**: **React** (via Vite), leveraging `xterm.js` for the browser terminal emulator and Socket.IO-client.
- **User Authentication (UI)**: **OIDC / OAuth** (e.g., GitHub, Google, or Auth0) to secure access to the dashboard.
- **Agent Authentication**: **Static API Keys** (Machine Tokens) configured locally on each development workstation via environment variables.
- **Agent Integration Strategy**: A lightweight **Python Wrapper Script** (using the `pty` or `pexpect` modules). This runs the original Gemini CLI as a subprocess, intercepts stdout/stdin, and pipes the data to the central hub via Socket.IO, minimizing intrusive changes to the core CLI.
- **Deployment Engine**: **Podman** on your local x86_64 RHEL 9 server (using rootless containers and `podman-compose`).

---

## Architecture Overview

1. **The Wrapper (`gemini-telemetry-wrapper.py`)**:
   - Executes `gemini <args>` via pseudo-terminal (`pty`).
   - Connects to the central backend via Socket.IO, authenticating with a pre-shared `MACHINE_TOKEN`.
   - Emits terminal output in real-time and listens for remote input from the backend to pipe back into the local `gemini` process.
2. **The Central Hub (FastAPI + Socket.IO)**:
   - Validates OIDC login for browser users.
   - Validates API Keys for agent connections.
   - Maintains an SQLite database of active sessions, metadata, and basic historical logs.
   - Relays Socket.IO messages (keystrokes and terminal text) between the React UI and the specific Agent Wrapper.
3. **The Web UI (React)**:
   - Dashboard page showing active agents and their statuses.
   - "Attach" button that opens an embedded `xterm.js` terminal window over a Socket.IO connection.

---

## Agent Instructions
- **CRITICAL**: The agent MUST request and receive explicit approval from the user before starting any new phase of the implementation plan. Do not proceed to the next phase without confirmation.
- **TESTING**: Always develop automated tests (unit or integration) alongside any new code implementation.
- **DOCUMENTATION**: Always add documentation for new features and keep existing documentation updated with changes. Documentation must be user-friendly for both beginner users and developers alike.

## Phased Implementation Plan

### Phase 1: Core API & Database Setup
1. Scaffold a FastAPI project using Python 3.9+.
2. Implement SQLAlchemy ORM models for SQLite (e.g., `Machine`, `Session`, `Log`).
3. Create basic CRUD endpoints for managing registered machines and viewing active sessions.

### Phase 2: Authentication
1. **Frontend/Backend OIDC:** Integrate an OAuth client library (like `Authlib` for FastAPI or `next-auth`/`react-oidc` for React) to enforce login before the dashboard UI or its API routes can be accessed.
2. **Agent Auth:** Implement FastAPI middleware/dependency injection to reject any Agent Socket.IO connections that do not provide a valid API key (Machine Token).

### Phase 3: The Agent Wrapper & Socket.IO Relay
1. Integrate `python-socketio` into the FastAPI backend to handle namespaces (e.g., `/terminal`).
2. Write the client-side `gemini-telemetry-wrapper.py`. This script will spawn the Gemini CLI, read its stdout asynchronously, and emit `terminal_output` events to the backend.
3. Implement the reverse flow: the wrapper listens for `terminal_input` events from the backend and writes those bytes directly into the `pty`'s stdin.

### Phase 4: Frontend UI & Remote Terminal
1. Scaffold a React app using Vite.
2. Build the Dashboard Grid view (fetching active sessions from the API).
3. Create the Terminal Component using `xterm.js` and the `xterm-addon-fit`. Connect this component to the Socket.IO `/terminal` namespace to render the remote shell and send keystrokes.

### Phase 5: Containerization for RHEL 9 (Podman)
1. Write a `Dockerfile` for the Python backend.
2. Write a `Dockerfile` for the React frontend (multi-stage build that serves the static assets via an NGINX container).
3. Author a `compose.yml` specifically tailored for Podman:
   - Mounts a local host directory into the Backend container for the SQLite `.db` file to ensure persistence across container restarts.
   - Exposes port `80`/`443` for the web UI and backend API.
4. Document the `podman-compose` run commands and systemd unit generation (`podman generate systemd`) to ensure the service runs on RHEL 9 boot.

---

## Verification & Testing
- **Local Testing**: Run the FastAPI backend and Vite dev server locally. Start the wrapper script pointing to `localhost` and ensure terminal output appears flawlessly in the browser `xterm.js` instance.
- **Podman Verification**: Deploy the stack using `podman-compose up -d`. Verify the containers start without root privileges on the RHEL 9 box and that the SQLite database file persists properly after a `podman-compose down`.
- **Security Audit**: Ensure that unauthenticated WebSocket connections are strictly dropped and that OIDC token flows work end-to-end.

## Migration & Maintenance Strategy
- **Upgrades**: Changes to the agent wrapper can be distributed by updating a single Python script on the workstations. Backend/Frontend updates require simple `podman-compose pull && podman-compose up -d` cycles on the RHEL 9 server.
- **Rollbacks**: If a container image update introduces a bug, Podman makes it trivial to rollback to the previous image tag. The SQLite database schema changes will be managed by Alembic (Python migration tool) to allow safe database downgrades if necessary.