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


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        username = payload.get("username", "")
        role = payload.get("role", "VIEWER")
        if user_id is None:
            raise JWTError("missing sub claim")
        return CurrentUser(id=uuid.UUID(str(user_id)), username=username, role=role)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_sv_team_or_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in ("ADMIN", "SV_TEAM"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SV_TEAM or ADMIN role required")
    return user
