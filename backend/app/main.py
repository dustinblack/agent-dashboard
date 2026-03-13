import os
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone

from . import models, database, auth, socket
import socketio

from fastapi.middleware.cors import CORSMiddleware

# Initialize the database
models.Base.metadata.create_all(bind=database.engine)

fastapi_app = FastAPI(title="AI Coding Agent Dashboard API")

# Add Session Middleware for OIDC
fastapi_app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "super-secret-default-key"))

# Add CORS Middleware
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Socket.IO
app = socketio.ASGIApp(socket.sio, fastapi_app)

# Pydantic Schemas
class HostBase(BaseModel):
    name: str

class HostCreate(HostBase):
    host_token: str

class HostSchema(HostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    created_at: datetime

class AgentBase(BaseModel):
    agent_id: str
    tool_name: Optional[str] = None
    pid: Optional[int] = None

class AgentCreate(AgentBase):
    host_id: int

class AgentSchema(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    host_id: int
    status: str
    tool_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None

class SpawnRequest(BaseModel):
    host_id: int
    tool_name: str

# Authentication Endpoints
@fastapi_app.get("/login")
async def login(request: Request):
    """Redirects the user to the OIDC provider for login."""
    redirect_uri = request.url_for('auth_route')
    return await auth.oauth.oidc.authorize_redirect(request, redirect_uri)

@fastapi_app.get("/auth", name="auth_route")
async def auth_route(request: Request):
    """Handles the OIDC callback, validating the token and setting the user session."""
    try:
        token = await auth.oauth.oidc.authorize_access_token(request)
        user = token.get('userinfo')
        if user:
            request.session['user'] = dict(user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")
    return RedirectResponse(url='/')

@fastapi_app.get("/logout")
async def logout(request: Request):
    """Clears the current user's session."""
    request.session.pop('user', None)
    return RedirectResponse(url='/')

@fastapi_app.get("/me")
async def me(user: dict = Depends(auth.get_current_user)):
    """Returns the currently logged-in user's profile information."""
    return user

# Protected API Endpoints
@fastapi_app.get("/hosts", response_model=List[HostSchema])
def read_hosts(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    List all registered hosts. Requires UI login.
    """
    hosts = db.query(models.Host).offset(skip).limit(limit).all()
    return hosts

@fastapi_app.post("/hosts", response_model=HostSchema)
def create_host(host: HostCreate, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    Register a new host. Requires UI login.
    """
    db_host = models.Host(name=host.name, host_token=host.host_token)
    db.add(db_host)
    try:
        db.commit()
        db.refresh(db_host)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Host registration failed. Name or token might already exist.")
    return db_host

@fastapi_app.get("/agents", response_model=List[AgentSchema])
def read_agents(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    List all active and historical agent sessions. Requires UI login.
    """
    agents = db.query(models.Agent).offset(skip).limit(limit).all()
    return agents

@fastapi_app.post("/agents/spawn", response_model=AgentSchema)
async def spawn_agent(request: SpawnRequest, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    Commands a remote host to spawn a new AI agent session.
    """
    # 0. Check if host is online
    host = db.query(models.Host).filter(models.Host.id == request.host_id).first()
    if not host or host.status != "online":
        raise HTTPException(status_code=400, detail="Cannot spawn agent: Host is offline or does not exist.")

    import uuid
    agent_uuid = str(uuid.uuid4())
    
    # 1. Create database record
    db_agent = models.Agent(
        host_id=request.host_id,
        agent_id=agent_uuid,
        tool_name=request.tool_name,
        status="active"
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)

    # 2. Relay command to the specific host daemon via Socket.IO
    # The host daemon should be in a room named "host_{id}"
    await socket.sio.emit(
        'spawn_agent', 
        {'agent_id': agent_uuid, 'tool': request.tool_name}, 
        room=f"host_{request.host_id}", 
        namespace='/terminal'
    )
    
    return db_agent

@fastapi_app.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    Commands a remote host to stop an active AI agent session.
    """
    db_agent = db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    
    if db_agent.status == "closed":
        return {"status": "already closed"}

    # 1. Update database immediately so the UI removes the card on next refresh
    db_agent.status = "closed"
    db_agent.ended_at = datetime.now(timezone.utc)
    db.commit()

    # 2. Relay command to the specific host daemon to kill the actual process
    await socket.sio.emit(
        'stop_agent', 
        {'agent_id': agent_id}, 
        room=f"host_{db_agent.host_id}", 
        namespace='/terminal'
    )
    
    # 3. Notify all UI clients via Socket.IO for real-time removal
    await socket.sio.emit(
        'agent_status_update', 
        {'agent_id': agent_id, 'status': 'closed'}, 
        namespace='/terminal'
    )
    
    return {"status": "stop command issued"}

@fastapi_app.get("/health")
def health_check():
    """
    Simple public health check endpoint.
    """
    return {"status": "healthy"}
