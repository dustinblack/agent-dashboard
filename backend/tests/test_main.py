import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.main import fastapi_app, app
from backend.app.database import Base, get_db
from backend.app.auth import get_current_user

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = override_get_db


def override_get_current_user():
    return {"email": "test@example.com", "name": "Test User"}


fastapi_app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_host():
    response = client.post(
        "/hosts", json={"name": "test-host", "host_token": "test-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-host"
    assert "id" in data


def test_read_hosts():
    response = client.get("/hosts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == "test-host"


def test_delete_host():
    r = client.post("/hosts", json={"name": "to-delete", "host_token": "del-token"})
    assert r.status_code == 200
    h_id = r.json()["id"]

    r_del = client.delete(f"/hosts/{h_id}")
    assert r_del.status_code == 200

    r_list = client.get("/hosts")
    assert not any(h["id"] == h_id for h in r_list.json())


def test_read_agents():
    response = client.get("/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_update_task_description():
    """Test updating an agent's task description via
    PATCH endpoint.
    """
    # Create a host and spawn an agent to get a valid
    # agent record
    r_host = client.post(
        "/hosts",
        json={
            "name": "desc-host",
            "host_token": "desc-token",
        },
    )
    host_id = r_host.json()["id"]
    # Mark host online so spawn succeeds
    from backend.app import models

    db = next(override_get_db())
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    host.status = "online"
    db.commit()
    db.close()

    r_spawn = client.post(
        "/agents/spawn",
        json={
            "host_id": host_id,
            "tool_name": "bash",
        },
    )
    assert r_spawn.status_code == 200
    agent_id = r_spawn.json()["agent_id"]

    # Update task description
    r_patch = client.patch(
        f"/agents/{agent_id}/task-description",
        json={"task_description": "Fix the login bug"},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["status"] == "updated"

    # Verify it persisted
    r_detail = client.get(f"/agents/{agent_id}/details")
    assert r_detail.status_code == 200
    tel = r_detail.json()["telemetry"]
    assert tel["task_description"] == "Fix the login bug"

    # Update again to verify overwrite
    r_patch2 = client.patch(
        f"/agents/{agent_id}/task-description",
        json={"task_description": "Refactor auth module"},
    )
    assert r_patch2.status_code == 200
    r_detail2 = client.get(f"/agents/{agent_id}/details")
    tel2 = r_detail2.json()["telemetry"]
    assert tel2["task_description"] == "Refactor auth module"

    # 404 for non-existent agent
    r_missing = client.patch(
        "/agents/nonexistent/task-description",
        json={"task_description": "nope"},
    )
    assert r_missing.status_code == 404


def test_cors_preflight():
    """Test that the OPTIONS preflight request is properly handled by CORSMiddleware."""
    headers = {
        "Origin": "http://localhost:8080",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    }
    response = client.options("/hosts", headers=headers)
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:8080"
    )
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_get_request():
    """Test that a GET request returns the proper CORS headers."""
    headers = {
        "Origin": "http://localhost:8080",
    }
    response = client.get("/hosts", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:8080"
    )
    assert response.headers.get("access-control-allow-credentials") == "true"
