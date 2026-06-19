"""Admin router — user management and audit log (ADMIN role only)."""
from __future__ import annotations

import uuid
from typing import Annotated, Optional

import bcrypt as _bcrypt_lib
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import CurrentUser, require_admin
from ..models import AuditLog, User
from ..schemas import (
    AuditLogOut, AuditLogPage,
    ProblemDetail,
    ResetPasswordIn,
    UserCreate, UserOut, UserPage, UserPatch,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _hash_password(plain: str) -> str:
    return _bcrypt_lib.hashpw(plain.encode("utf-8"), _bcrypt_lib.gensalt()).decode("utf-8")

_PROBLEM_NOT_FOUND = "https://mockingbird.internal/errors/user-not-found"


def _get_user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ProblemDetail(
                type=_PROBLEM_NOT_FOUND,
                title="User Not Found",
                status=404,
                detail=f"User {user_id} does not exist",
            ).model_dump(),
        )
    return user


@router.get("/users", response_model=UserPage)
def list_users(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_admin),
) -> UserPage:
    total = db.query(User).count()
    items = db.query(User).order_by(User.created_at.asc()).offset(offset).limit(limit).all()
    return UserPage(
        items=[UserOut.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_admin),
) -> User:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ProblemDetail(
                type="https://mockingbird.internal/errors/duplicate-username",
                title="Username Already Exists",
                status=409,
                detail=f"Username '{body.username}' is already taken",
            ).model_dump(),
        )
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ProblemDetail(
                type="https://mockingbird.internal/errors/duplicate-email",
                title="Email Already Registered",
                status=409,
                detail=f"Email '{body.email}' is already registered",
            ).model_dump(),
        )
    user = User(
        username=body.username,
        email=body.email,
        password_hash=_hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(
    user_id: uuid.UUID,
    body: UserPatch,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_admin),
) -> User:
    user = _get_user_or_404(db, user_id)
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordIn,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_admin),
) -> None:
    user = _get_user_or_404(db, user_id)
    user.password_hash = _hash_password(body.new_password)
    db.commit()


@router.get("/audit", response_model=AuditLogPage)
def list_audit(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    _admin: CurrentUser = Depends(require_admin),
) -> AuditLogPage:
    q = db.query(AuditLog, User.username).outerjoin(User, AuditLog.user_id == User.id)
    if project_id is not None:
        q = q.filter(AuditLog.project_id == project_id)
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return AuditLogPage(
        items=[
            AuditLogOut(
                id=log.id,
                project_id=log.project_id,
                user_id=log.user_id,
                username=username,
                action=log.action,
                detail=log.detail,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log, username in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
