import os
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime

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
    started_at: datetime
    ended_at: Optional[datetime] = None

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

@fastapi_app.get("/health")
def health_check():
    """
    Simple public health check endpoint.
    """
    return {"status": "healthy"}
