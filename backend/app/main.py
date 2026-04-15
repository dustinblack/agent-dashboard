"""FastAPI application and REST API endpoints for Agent Dashboard.

Defines Pydantic schemas, authentication endpoints, and CRUD
operations for hosts, agents, and telemetry.
"""

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
import socketio
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import models, database, auth, socket

# Initialize the database
models.Base.metadata.create_all(bind=database.engine)

# --- Version tracking ---
# Read embedded version from /app/VERSION (written at build
# time). Falls back to "dev" if the file doesn't exist.
_CURRENT_VERSION = "dev"
try:
    with open("/app/VERSION", "r", encoding="utf-8") as _vf:
        _CURRENT_VERSION = _vf.read().strip() or "dev"
except FileNotFoundError:
    pass

# Regex to detect clean semver tags (e.g. v0.4.0) vs
# development builds (e.g. v0.4.0-3-g20799ff or just a hash)
_SEMVER_TAG = re.compile(r"^v?\d+\.\d+\.\d+$")

# Cached latest release info from GitHub
_latest_release: Dict[str, Optional[str]] = {
    "tag": None,
    "url": None,
}

# GitHub repo for release checks
_GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "dustinblack/agent-dashboard",
)
# Interval between GitHub release checks (seconds)
_VERSION_CHECK_INTERVAL = 1800  # 30 minutes


def _parse_semver(version: str) -> Optional[tuple]:
    """Parses a version string into a (major, minor, patch)
    tuple. Returns None if the version is not a clean semver
    tag.
    """
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", version)
    if match:
        return tuple(int(x) for x in match.groups())
    return None


def _is_dev_build(version: str) -> bool:
    """Returns True if the version is a development build
    (not a clean semver tag).
    """
    return not _SEMVER_TAG.match(version)


fastapi_app = FastAPI(title="AI Coding Agent Dashboard API")

# Add Session Middleware for OIDC
fastapi_app.add_middleware(
    SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "super-secret-default-key")
)

# Add CORS Middleware
# In lab environments (BYPASS_AUTH=true), we allow any HTTP/HTTPS origin.
# In production, specify comma-separated origins via the ALLOWED_ORIGINS env var.
allowed_origins_env = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
)
allowed_origins = [
    origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()
]

if os.getenv("BYPASS_AUTH", "false").lower() == "true":
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex="https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount Socket.IO
app = socketio.ASGIApp(socket.sio, fastapi_app)


# Pydantic Schemas
class HostBase(BaseModel):
    """Base schema for host data."""

    name: str


class HostCreate(HostBase):
    """Schema for creating a new host registration."""

    host_token: str


class HostSchema(HostBase):
    """Schema for host responses including status and metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    projects: Optional[dict] = None
    created_at: datetime


class AgentBase(BaseModel):
    """Base schema for agent session data."""

    agent_id: str
    tool_name: Optional[str] = None
    pid: Optional[int] = None
    telemetry: dict = {}


class AgentCreate(AgentBase):
    """Schema for creating a new agent session."""

    host_id: int


class AgentSchema(AgentBase):
    """Schema for agent responses with status and timestamps."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    host_id: int
    status: str
    tool_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None


class AgentDetailSchema(AgentSchema):
    """Extended agent schema that includes the host name."""

    host_name: str


class SpawnRequest(BaseModel):
    """Schema for requesting an agent spawn on a host."""

    host_id: int
    tool_name: str
    project_dir: Optional[str] = None
    task_description: Optional[str] = None
    session_mode: Optional[str] = "resume"
    use_worktree: Optional[bool] = False
    cols: Optional[int] = 120
    rows: Optional[int] = 40


# Authentication Endpoints
@fastapi_app.get("/login")
async def login(request: Request):
    """Redirects the user to the OIDC provider for login."""
    redirect_uri = request.url_for("auth_route")
    return await auth.oauth.oidc.authorize_redirect(request, redirect_uri)


@fastapi_app.get("/auth", name="auth_route")
async def auth_route(request: Request):
    """Handles the OIDC callback, validating the token and setting the user session."""
    try:
        token = await auth.oauth.oidc.authorize_access_token(request)
        user = token.get("userinfo")
        if user:
            request.session["user"] = dict(user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")
    return RedirectResponse(url="/")


@fastapi_app.get("/logout")
async def logout(request: Request):
    """Clears the current user's session."""
    request.session.pop("user", None)
    return RedirectResponse(url="/")


@fastapi_app.get("/me")
async def me(user: dict = Depends(auth.get_current_user)):
    """Returns the currently logged-in user's profile information."""
    return user


# Protected API Endpoints
@fastapi_app.get("/hosts", response_model=List[HostSchema])
def read_hosts(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    List all registered hosts. Requires UI login.
    """
    hosts = db.query(models.Host).offset(skip).limit(limit).all()
    print(
        f"DEBUG: read_hosts returning {len(hosts)} hosts."
        f" Sample projects:"
        f" {[h.last_projects_json for h in hosts]}"
    )
    return hosts


@fastapi_app.post("/hosts", response_model=HostSchema)
def create_host(
    host: HostCreate,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    Register a new host. Requires UI login.
    """
    db_host = models.Host(name=host.name, host_token=host.host_token)
    db.add(db_host)
    try:
        db.commit()
        db.refresh(db_host)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Host registration failed." " Name or token might already exist.",
        )
    return db_host


@fastapi_app.delete("/hosts/{host_id}")
def delete_host(
    host_id: int,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    Deletes a registered host and cascades to all its
    agents and logs. Requires UI login.
    """
    db_host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not db_host:
        raise HTTPException(status_code=404, detail="Host not found.")

    try:
        db.delete(db_host)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete host: {e}")
    return {"detail": "Host deleted successfully."}


@fastapi_app.get("/agents", response_model=List[AgentSchema])
def read_agents(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    List agent sessions, optionally filtered by status. Requires UI login.
    """
    query = db.query(models.Agent)
    if status:
        query = query.filter(models.Agent.status == status)
    agents = query.offset(skip).limit(limit).all()
    return agents


@fastapi_app.get(
    "/agents/{agent_id}/details",
    response_model=AgentDetailSchema,
)
def get_agent_details(
    agent_id: str,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    Returns a single agent's data along with the host name.
    Requires UI login.
    """
    db_agent = db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    host = db.query(models.Host).filter(models.Host.id == db_agent.host_id).first()
    host_name = host.name if host else "unknown"

    return AgentDetailSchema(
        id=db_agent.id,
        host_id=db_agent.host_id,
        agent_id=db_agent.agent_id,
        tool_name=db_agent.tool_name,
        pid=db_agent.pid,
        status=db_agent.status,
        telemetry=db_agent.telemetry,
        started_at=db_agent.started_at,
        ended_at=db_agent.ended_at,
        host_name=host_name,
    )


@fastapi_app.get(
    "/agents/{agent_id}/companions",
    response_model=List[AgentSchema],
)
def get_agent_companions(
    agent_id: str,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    Returns active companion agents on the same host sharing
    the same effective working directory. Companions are matched
    by worktree_path when present (agents sharing the same
    worktree), or by project_dir when neither agent has a
    worktree (agents sharing the original repo). This prevents
    worktree-isolated agents from being matched as companions
    to non-worktree agents on the same project.
    Requires UI login.
    """
    db_agent = db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    tel = db_agent.telemetry_json or {}
    worktree_path = tel.get("worktree_path")
    project_dir = tel.get("project_dir")
    if not project_dir:
        return []

    # Match companions by effective working directory:
    # if this agent is in a worktree, find others in the
    # same worktree. If not, find others also without a
    # worktree on the same project.
    base_filter = [
        models.Agent.host_id == db_agent.host_id,
        models.Agent.status == "active",
        models.Agent.agent_id != agent_id,
    ]
    if worktree_path:
        base_filter.append(
            func.json_extract(models.Agent.telemetry_json, "$.worktree_path")
            == worktree_path
        )
    else:
        base_filter.append(
            func.json_extract(models.Agent.telemetry_json, "$.project_dir")
            == project_dir
        )
        # Exclude agents that have a worktree_path set
        base_filter.append(
            func.json_extract(models.Agent.telemetry_json, "$.worktree_path").is_(None)
        )

    companions = db.query(models.Agent).filter(*base_filter).all()
    return companions


@fastapi_app.post("/agents/spawn", response_model=AgentSchema)
async def spawn_agent(
    request: SpawnRequest,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    Commands a remote host to spawn a new AI agent session.
    """
    # 0. Check if host is online
    host = db.query(models.Host).filter(models.Host.id == request.host_id).first()
    if not host or host.status != "online":
        raise HTTPException(
            status_code=400,
            detail="Cannot spawn agent: Host is offline or does not exist.",
        )

    import uuid

    agent_uuid = str(uuid.uuid4())

    # 1. Create database record
    db_agent = models.Agent(
        host_id=request.host_id,
        agent_id=agent_uuid,
        tool_name=request.tool_name,
        status="active",
        telemetry_json={
            "project_dir": request.project_dir,
            "task_description": request.task_description,
            "use_worktree": request.use_worktree or False,
        },
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)

    # 2. Relay command to the specific host daemon via Socket.IO
    # The host daemon should be in a room named "host_{id}"
    await socket.sio.emit(
        "spawn_agent",
        {
            "agent_id": agent_uuid,
            "tool": request.tool_name,
            "project_dir": request.project_dir,
            "task_description": request.task_description,
            "session_mode": request.session_mode or "resume",
            "use_worktree": request.use_worktree or False,
            "cols": request.cols or 120,
            "rows": request.rows or 40,
        },
        room=f"host_{request.host_id}",
        namespace="/terminal",
    )

    return db_agent


@fastapi_app.post("/agents/{agent_id}/stop")
async def stop_agent(
    agent_id: str,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """
    Commands a remote host to stop an active AI agent session.
    """
    db_agent = db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    if db_agent.status in ("closed", "stopped"):
        return {"status": "already stopped"}

    # 1. Update database with "stopped" status to distinguish
    # user-initiated stops from daemon-side disconnects
    # ("closed"). This prevents the terminal auto-reconnect
    # from respawning the agent.
    db_agent.status = "stopped"
    db_agent.ended_at = datetime.now(timezone.utc)
    db.commit()

    # 2. Relay command to the specific host daemon to kill the actual process
    await socket.sio.emit(
        "stop_agent",
        {"agent_id": agent_id},
        room=f"host_{db_agent.host_id}",
        namespace="/terminal",
    )

    # 3. Notify all UI clients via Socket.IO for real-time removal.
    # Use "stopped" so terminal windows know this was user-initiated
    # and should not auto-reconnect.
    await socket.sio.emit(
        "agent_status_update",
        {"agent_id": agent_id, "status": "stopped"},
        namespace="/terminal",
    )

    return {"status": "stop command issued"}


class TaskDescriptionUpdate(BaseModel):
    """Request body for updating an agent's task description."""

    task_description: str


@fastapi_app.patch(
    "/agents/{agent_id}/task-description",
)
async def update_task_description(
    agent_id: str,
    body: TaskDescriptionUpdate,
    db: Session = Depends(database.get_db),
    user: dict = Depends(auth.get_current_user),
):
    """Updates the user-provided task description for an
    active agent. Persists to DB and syncs to the host
    daemon so its telemetry dict stays current.
    """
    db_agent = db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    # Update telemetry_json in the database
    tel = dict(db_agent.telemetry_json or {})
    tel["task_description"] = body.task_description
    db_agent.telemetry_json = tel
    db.commit()

    # Relay to daemon so its local telemetry stays in sync
    await socket.sio.emit(
        "update_task_description",
        {
            "agent_id": agent_id,
            "task_description": body.task_description,
        },
        room=f"host_{db_agent.host_id}",
        namespace="/terminal",
    )

    # Broadcast updated telemetry to all UI clients
    await socket.sio.emit(
        "agent_telemetry_update",
        {"agent_id": agent_id, "telemetry": tel},
        namespace="/terminal",
    )

    return {"status": "updated"}


@fastapi_app.get("/health")
def health_check():
    """
    Simple public health check endpoint.
    """
    return {"status": "healthy"}


@fastapi_app.get("/version")
def get_version():
    """Returns current version and latest available release.

    The current version is embedded at build time. The latest
    release is fetched from GitHub periodically in the
    background. For tagged builds, update_available is true
    when a newer semver release exists. For development builds,
    update_available is always false but the latest release
    info is still returned for informational display.
    """
    current = _CURRENT_VERSION
    latest = _latest_release["tag"]
    latest_url = _latest_release["url"]
    is_dev = _is_dev_build(current)

    update_available = False
    if not is_dev and latest:
        current_ver = _parse_semver(current)
        latest_ver = _parse_semver(latest)
        if current_ver and latest_ver:
            update_available = latest_ver > current_ver

    return {
        "current": current,
        "is_dev": is_dev,
        "latest": latest,
        "latest_url": latest_url,
        "update_available": update_available,
    }


async def _check_latest_release():
    """Background task that periodically fetches the latest
    GitHub release and caches the result. Runs every 30 minutes.
    Errors are logged but do not affect application operation.
    """
    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{_GITHUB_REPO}" "/releases/latest",
                    headers={"Accept": "application/vnd.github.v3+json"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    _latest_release["tag"] = data.get("tag_name")
                    _latest_release["url"] = data.get("html_url")
                    print(
                        f"Version check: current={_CURRENT_VERSION}"
                        f" latest={_latest_release['tag']}"
                    )
                else:
                    print(f"Version check failed: " f"HTTP {resp.status_code}")
        except Exception as e:
            print(f"Version check error: {e}")
        await asyncio.sleep(_VERSION_CHECK_INTERVAL)


@fastapi_app.on_event("startup")
async def start_version_checker():
    """Launches the background GitHub release checker."""
    asyncio.create_task(_check_latest_release())
