"""Database engine and session configuration for Agent Dashboard.

Uses SQLite via SQLAlchemy with WAL mode for concurrent read/write
performance. The database URL is configured through the
DATABASE_URL environment variable.
"""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite:///./agent_dashboard.db"
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and tuning pragmas on each new connection.

    WAL (Write-Ahead Logging) allows concurrent reads during
    writes, preventing the full-database locks that block the
    async event loop when telemetry updates and terminal I/O
    relay compete for the same connection.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(  # pylint: disable=invalid-name
    autocommit=False, autoflush=False, bind=engine
)

Base = declarative_base()


def get_db():
    """
    Dependency to provide a database session for FastAPI requests.
    Ensures the session is closed after the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
