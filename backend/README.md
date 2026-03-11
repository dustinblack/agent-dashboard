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
