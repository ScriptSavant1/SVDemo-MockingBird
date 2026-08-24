"""FastAPI dependency injection — JWT auth for REST and WebSocket routes.

Tokens are issued by auth-service; this service only verifies the signature
using the shared JWT_SECRET (same pattern as project-service/ingestion-service).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import settings

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: uuid.UUID
    username: str
    role: str


def _decode(token: str) -> CurrentUser:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    user_id = payload.get("sub")
    if user_id is None:
        raise JWTError("missing sub claim")
    return CurrentUser(
        id=uuid.UUID(str(user_id)),
        username=payload.get("username", ""),
        role=payload.get("role", "VIEWER"),
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    """Verify the JWT Bearer token for REST routes. Raises 401 if missing/invalid."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return _decode(credentials.credentials)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user_ws(token: Optional[str]) -> Optional[CurrentUser]:
    """Verify a JWT passed as a WebSocket query param (browsers can't set
    Authorization headers on WebSocket handshakes). Returns None on failure —
    callers close the socket rather than raise, since WS auth errors aren't HTTP.
    """
    if not token:
        return None
    try:
        return _decode(token)
    except (JWTError, ValueError):
        return None
