import os
from fastapi import Security, HTTPException, status, Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from . import models, database
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

# API Key Authentication for Agents
API_KEY_NAME = "X-Machine-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_current_machine(
    api_key_header: str = Security(api_key_header),
    db: Session = Depends(database.get_db)
) -> models.Machine:
    """
    Validates the machine token passed in the header and returns the corresponding Machine model.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing machine token",
        )
    
    machine = db.query(models.Machine).filter(models.Machine.machine_token == api_key_header).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid machine token",
        )
    
    return machine

# OIDC Authentication for Dashboard UI
# Using dummy defaults for local development. In production, these should be set via environment variables.
config = Config(environ={
    "OIDC_CLIENT_ID": os.getenv("OIDC_CLIENT_ID", "dummy-client-id"),
    "OIDC_CLIENT_SECRET": os.getenv("OIDC_CLIENT_SECRET", "dummy-client-secret"),
    "OIDC_DISCOVERY_URL": os.getenv("OIDC_DISCOVERY_URL", "https://dummy-oidc-provider/.well-known/openid-configuration")
})
oauth = OAuth(config)

oauth.register(
    name='oidc',
    server_metadata_url=config.get('OIDC_DISCOVERY_URL'),
    client_id=config.get('OIDC_CLIENT_ID'),
    client_secret=config.get('OIDC_CLIENT_SECRET'),
    client_kwargs={
        'scope': 'openid email profile'
    }
)

def get_current_user(request: Request):
    """
    Dependency to check if a user is logged in via OIDC session.
    """
    user = request.session.get('user')
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
