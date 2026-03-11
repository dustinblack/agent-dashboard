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

# Initialize the database
models.Base.metadata.create_all(bind=database.engine)

fastapi_app = FastAPI(title="Gemini AI Coding Agent Dashboard API")

# Add Session Middleware for OIDC
fastapi_app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "super-secret-default-key"))

# Mount Socket.IO
app = socketio.ASGIApp(socket.sio, fastapi_app)

# Pydantic Schemas
class MachineBase(BaseModel):
    name: str

class MachineCreate(MachineBase):
    machine_token: str

class Machine(MachineBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime

class SessionBase(BaseModel):
    session_id: str

class SessionCreate(SessionBase):
    machine_id: int

class SessionSchema(SessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    machine_id: int
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
@fastapi_app.get("/machines", response_model=List[Machine])
def read_machines(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    List all registered machines. Requires UI login.
    """
    machines = db.query(models.Machine).offset(skip).limit(limit).all()
    return machines

@fastapi_app.post("/machines", response_model=Machine)
def create_machine(machine: MachineCreate, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    Register a new machine. Requires UI login.
    """
    db_machine = models.Machine(name=machine.name, machine_token=machine.machine_token)
    db.add(db_machine)
    try:
        db.commit()
        db.refresh(db_machine)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Machine registration failed. Name or token might already exist.")
    return db_machine

@fastapi_app.get("/sessions", response_model=List[SessionSchema])
def read_sessions(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db), user: dict = Depends(auth.get_current_user)):
    """
    List all active and historical sessions. Requires UI login.
    """
    sessions = db.query(models.Session).offset(skip).limit(limit).all()
    return sessions

@fastapi_app.get("/health")
def health_check():
    """
    Simple public health check endpoint.
    """
    return {"status": "healthy"}
