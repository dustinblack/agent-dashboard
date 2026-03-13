import os
from fastapi import Security, HTTPException, status, Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from . import models, database
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

# API Key Authentication for Host Daemons
API_KEY_NAME = "X-Host-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_current_host(
    api_key_header: str = Security(api_key_header),
    db: Session = Depends(database.get_db)
) -> models.Host:
    """
    Validates the host token passed in the header and returns the corresponding Host model.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing host token",
        )
    
    host = db.query(models.Host).filter(models.Host.host_token == api_key_header).first()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid host token",
        )
    
    return host

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
    if os.getenv("BYPASS_AUTH", "false").lower() == "true":
        return {"email": "dev@example.com", "name": "Developer"}

    user = request.session.get('user')
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
