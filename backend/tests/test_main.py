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


def test_spawn_agent_host_offline():
    """Spawning on an offline host returns 400."""
    r_host = client.post(
        "/hosts",
        json={"name": "offline-host", "host_token": "off-token"},
    )
    host_id = r_host.json()["id"]
    # Host defaults to 'offline' status
    r = client.post(
        "/agents/spawn",
        json={"host_id": host_id, "tool_name": "bash"},
    )
    assert r.status_code == 400


def test_spawn_agent_host_not_found():
    """Spawning on a nonexistent host returns 400."""
    r = client.post(
        "/agents/spawn",
        json={"host_id": 99999, "tool_name": "bash"},
    )
    assert r.status_code == 400


def test_spawn_agent_with_task():
    """Verify telemetry_json persists project_dir and task."""
    from backend.app import models

    r_host = client.post(
        "/hosts",
        json={"name": "task-host", "host_token": "task-token"},
    )
    host_id = r_host.json()["id"]
    db = next(override_get_db())
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    host.status = "online"
    db.commit()
    db.close()

    r = client.post(
        "/agents/spawn",
        json={
            "host_id": host_id,
            "tool_name": "claude",
            "project_dir": "/git/myproject",
            "task_description": "Fix the bug",
        },
    )
    assert r.status_code == 200
    agent_id = r.json()["agent_id"]

    r_detail = client.get(f"/agents/{agent_id}/details")
    tel = r_detail.json()["telemetry"]
    assert tel["project_dir"] == "/git/myproject"
    assert tel["task_description"] == "Fix the bug"


def test_stop_agent():
    """Spawn then stop an agent, verify status=closed."""
    from backend.app import models

    r_host = client.post(
        "/hosts",
        json={"name": "stop-host", "host_token": "stop-token"},
    )
    host_id = r_host.json()["id"]
    db = next(override_get_db())
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    host.status = "online"
    db.commit()
    db.close()

    r_spawn = client.post(
        "/agents/spawn",
        json={"host_id": host_id, "tool_name": "bash"},
    )
    agent_id = r_spawn.json()["agent_id"]

    r_stop = client.post(f"/agents/{agent_id}/stop")
    assert r_stop.status_code == 200


def test_stop_agent_not_found():
    """Stopping a nonexistent agent returns 404."""
    r = client.post("/agents/nonexistent-id/stop")
    assert r.status_code == 404


def test_stop_agent_already_closed():
    """Stopping an already-closed agent is idempotent."""
    from backend.app import models

    r_host = client.post(
        "/hosts",
        json={
            "name": "idempotent-host",
            "host_token": "idem-token",
        },
    )
    host_id = r_host.json()["id"]
    db = next(override_get_db())
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    host.status = "online"
    db.commit()
    db.close()

    r_spawn = client.post(
        "/agents/spawn",
        json={"host_id": host_id, "tool_name": "bash"},
    )
    agent_id = r_spawn.json()["agent_id"]
    client.post(f"/agents/{agent_id}/stop")

    # Stop again — should be idempotent
    r2 = client.post(f"/agents/{agent_id}/stop")
    assert r2.status_code == 200
    assert r2.json()["status"] == "already stopped"


def test_get_agent_details_not_found():
    """Getting details for a nonexistent agent returns 404."""
    r = client.get("/agents/nonexistent-id/details")
    assert r.status_code == 404


def test_get_companions_with_match():
    """Two active agents on same host+project are companions."""
    from backend.app import models

    r_host = client.post(
        "/hosts",
        json={
            "name": "companion-host",
            "host_token": "comp-token",
        },
    )
    host_id = r_host.json()["id"]
    db = next(override_get_db())
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    host.status = "online"
    db.commit()
    db.close()

    r1 = client.post(
        "/agents/spawn",
        json={
            "host_id": host_id,
            "tool_name": "claude",
            "project_dir": "/git/shared",
        },
    )
    r2 = client.post(
        "/agents/spawn",
        json={
            "host_id": host_id,
            "tool_name": "gemini",
            "project_dir": "/git/shared",
        },
    )
    aid1 = r1.json()["agent_id"]
    aid2 = r2.json()["agent_id"]

    companions = client.get(f"/agents/{aid1}/companions")
    assert companions.status_code == 200
    companion_ids = [a["agent_id"] for a in companions.json()]
    assert aid2 in companion_ids


def test_get_companions_no_match():
    """Agents on different projects are not companions."""
    from backend.app import models

    r_host = client.post(
        "/hosts",
        json={
            "name": "nocomp-host",
            "host_token": "nocomp-token",
        },
    )
    host_id = r_host.json()["id"]
    db = next(override_get_db())
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    host.status = "online"
    db.commit()
    db.close()

    r1 = client.post(
        "/agents/spawn",
        json={
            "host_id": host_id,
            "tool_name": "claude",
            "project_dir": "/git/project-a",
        },
    )
    client.post(
        "/agents/spawn",
        json={
            "host_id": host_id,
            "tool_name": "gemini",
            "project_dir": "/git/project-b",
        },
    )
    aid1 = r1.json()["agent_id"]

    companions = client.get(f"/agents/{aid1}/companions")
    assert companions.status_code == 200
    assert len(companions.json()) == 0


def test_get_companions_not_found():
    """Getting companions for a nonexistent agent returns 404."""
    r = client.get("/agents/nonexistent-id/companions")
    assert r.status_code == 404


def test_read_agents_status_filter():
    """Filtering agents by status=active works."""
    r = client.get("/agents?status=active")
    assert r.status_code == 200
    for agent in r.json():
        assert agent["status"] == "active"


def test_delete_host_not_found():
    """Deleting a nonexistent host returns 404."""
    r = client.delete("/hosts/99999")
    assert r.status_code == 404


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
