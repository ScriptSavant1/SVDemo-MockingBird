"""Project CRUD router — /api/v1/projects."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import CurrentUser, get_current_user, require_admin, require_sv_team_or_admin
from ..models import AuditLog, Project
from ..schemas import (
    ProblemDetail, ProjectCreate, ProjectOut, ProjectPage, ProjectUpdate,
    VALID_ENVIRONMENTS, VALID_STATUSES,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

_PROBLEM_NOT_FOUND = "https://mockingbird.internal/errors/project-not-found"
_PROBLEM_VALIDATION = "https://mockingbird.internal/errors/validation"


def _get_or_404(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ProblemDetail(
                type=_PROBLEM_NOT_FOUND,
                title="Project Not Found",
                status=404,
                detail=f"Project {project_id} does not exist",
            ).model_dump(),
        )
    return project


def _audit(db: Session, user: CurrentUser, project_id: uuid.UUID, action: str, detail: dict | None = None) -> None:
    log = AuditLog(project_id=project_id, user_id=user.id, action=action, detail=detail or {})
    db.add(log)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_sv_team_or_admin),
) -> Project:
    if body.environment not in VALID_ENVIRONMENTS:
        raise HTTPException(
            status_code=422,
            detail=ProblemDetail(
                type=_PROBLEM_VALIDATION,
                title="Invalid environment",
                status=422,
                detail=f"environment must be one of {sorted(VALID_ENVIRONMENTS)}",
            ).model_dump(),
        )
    project = Project(
        name=body.name,
        team=body.team,
        environment=body.environment,
        expected_tps=body.expected_tps,
        description=body.description,
        created_by=user.id,
    )
    db.add(project)
    db.flush()
    _audit(db, user, project.id, "project.created", {"name": project.name})
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=ProjectPage)
def list_projects(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> ProjectPage:
    total = db.query(Project).count()
    items = db.query(Project).order_by(Project.created_at.desc()).offset(offset).limit(limit).all()
    return ProjectPage(
        items=[ProjectOut.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> Project:
    return _get_or_404(db, project_id)


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_sv_team_or_admin),
) -> Project:
    project = _get_or_404(db, project_id)
    changes: dict = {}
    if body.name is not None:
        project.name = body.name
        changes["name"] = body.name
    if body.team is not None:
        project.team = body.team
        changes["team"] = body.team
    if body.environment is not None:
        if body.environment not in VALID_ENVIRONMENTS:
            raise HTTPException(
                status_code=422,
                detail=ProblemDetail(
                    type=_PROBLEM_VALIDATION,
                    title="Invalid environment",
                    status=422,
                    detail=f"environment must be one of {sorted(VALID_ENVIRONMENTS)}",
                ).model_dump(),
            )
        project.environment = body.environment
        changes["environment"] = body.environment
    if body.expected_tps is not None:
        project.expected_tps = body.expected_tps
        changes["expected_tps"] = body.expected_tps
    if body.description is not None:
        project.description = body.description
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=ProblemDetail(
                    type=_PROBLEM_VALIDATION,
                    title="Invalid status",
                    status=422,
                    detail=f"status must be one of {sorted(VALID_STATUSES)}",
                ).model_dump(),
            )
        project.status = body.status
        changes["status"] = body.status
    _audit(db, user, project.id, "project.updated", changes)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_admin),
) -> None:
    project = _get_or_404(db, project_id)
    db.delete(project)
    db.commit()
