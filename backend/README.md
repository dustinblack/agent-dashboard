# Agent Dashboard Backend

This is the FastAPI backend for the Gemini AI Coding Agent Dashboard.

## Features
- Machine registration and management.
- Session tracking.
- Terminal log storage (initial implementation).
- Health check endpoint.

## Tech Stack
- **FastAPI**: Web framework.
- **SQLAlchemy**: ORM for database interaction.
- **SQLite**: Database (local persistence).
- **Pydantic**: Data validation and serialization.
- **Authlib**: OIDC authentication for dashboard users.

## Authentication
The backend supports two distinct authentication strategies:
1. **OIDC (OpenID Connect) for Users**: Web UI users are authenticated via an external OIDC provider (e.g., Google, GitHub, Keycloak). The `/login` endpoint redirects to the provider, and `/auth` handles the callback. Protected UI routes require an active session.
   - Configure OIDC via environment variables: `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL`.
2. **Machine Tokens for Agents**: Gemini CLI agents authenticate their connections using a static API key configured locally on the agent machine. This token is passed in the `X-Machine-Token` header for API routes or Socket.IO connections.

## Getting Started

### Prerequisites
- Python 3.9+

### Setup
1. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

### Running the Server
```bash
PYTHONPATH=. uvicorn backend.app.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.
You can access the interactive API documentation at `http://127.0.0.1:8000/docs`.

### Running Tests
```bash
PYTHONPATH=. pytest backend/tests/test_main.py
```

## API Endpoints
- `GET /health`: Health check.
- `GET /machines`: List all registered machines.
- `POST /machines`: Register a new machine.
- `GET /sessions`: List all active and historical sessions.
