from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from . import models, database

# Initialize the database
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Gemini AI Coding Agent Dashboard API")

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

# Endpoints
@app.get("/machines", response_model=List[Machine])
def read_machines(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    """
    List all registered machines.
    """
    machines = db.query(models.Machine).offset(skip).limit(limit).all()
    return machines

@app.post("/machines", response_model=Machine)
def create_machine(machine: MachineCreate, db: Session = Depends(database.get_db)):
    """
    Register a new machine.
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

@app.get("/sessions", response_model=List[SessionSchema])
def read_sessions(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    """
    List all active and historical sessions.
    """
    sessions = db.query(models.Session).offset(skip).limit(limit).all()
    return sessions

@app.get("/health")
def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "healthy"}
