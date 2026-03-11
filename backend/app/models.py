from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class Machine(Base):
    """
    Represents a developer workstation or server where the Gemini CLI agent is running.
    """
    __tablename__ = "machines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    machine_token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sessions = relationship("Session", back_populates="machine")

class Session(Base):
    """
    Represents an active or historical Gemini CLI agent session.
    """
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    session_id = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="active") # active, closed
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    machine = relationship("Machine", back_populates="sessions")
    logs = relationship("Log", back_populates="session")

class Log(Base):
    """
    Stores terminal logs or metadata for a given session.
    """
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("Session", back_populates="logs")
