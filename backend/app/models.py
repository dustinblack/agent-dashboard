from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

class Host(Base):
    """
    Represents a developer workstation or server where the host daemon is running.
    """
    __tablename__ = "hosts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    host_token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    agents = relationship("Agent", back_populates="host")

class Agent(Base):
    """
    Represents an active or historical AI agent session (e.g. Gemini, Claude).
    """
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=False)
    agent_id = Column(String, unique=True, index=True, nullable=False)
    tool_name = Column(String, nullable=True) # gemini, claude, etc.
    pid = Column(Integer, nullable=True)     # Process ID on the host
    status = Column(String, default="active") # active, closed
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    host = relationship("Host", back_populates="agents")
    logs = relationship("Log", back_populates="agent")

class Log(Base):
    """
    Stores terminal logs or metadata for a given agent session.
    """
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    agent = relationship("Agent", back_populates="logs")
