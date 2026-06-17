"""Stub CRUD router — /api/v1/projects/{project_id}/stubs."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import CurrentUser, get_current_user, require_sv_team_or_admin
from ..models import Project, Stub
from ..schemas import ProblemDetail, StubCreate, StubOut, VALID_FORMATS

router = APIRouter(prefix="/api/v1/projects/{project_id}/stubs", tags=["stubs"])

_PROBLEM_PROJECT_NOT_FOUND = "https://mockingbird.internal/errors/project-not-found"
_PROBLEM_STUB_NOT_FOUND = "https://mockingbird.internal/errors/stub-not-found"
_PROBLEM_VALIDATION = "https://mockingbird.internal/errors/validation"


def _project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ProblemDetail(
                type=_PROBLEM_PROJECT_NOT_FOUND,
                title="Project Not Found",
                status=404,
                detail=f"Project {project_id} does not exist",
            ).model_dump(),
        )
    return project


def _stub_or_404(db: Session, project_id: uuid.UUID, stub_id: uuid.UUID) -> Stub:
    stub = db.query(Stub).filter(Stub.id == stub_id, Stub.project_id == project_id).first()
    if stub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ProblemDetail(
                type=_PROBLEM_STUB_NOT_FOUND,
                title="Stub Not Found",
                status=404,
                detail=f"Stub {stub_id} does not exist in project {project_id}",
            ).model_dump(),
        )
    return stub


@router.post("", response_model=StubOut, status_code=status.HTTP_201_CREATED)
def create_stub(
    project_id: uuid.UUID,
    body: StubCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_sv_team_or_admin),
) -> Stub:
    _project_or_404(db, project_id)
    if body.format not in VALID_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=ProblemDetail(
                type=_PROBLEM_VALIDATION,
                title="Invalid stub format",
                status=422,
                detail=f"format must be one of {sorted(VALID_FORMATS)}",
            ).model_dump(),
        )
    stub = Stub(
        project_id=project_id,
        name=body.name,
        format=body.format,
        source_file_key=body.source_file_key,
        wiremock_mapping_count=body.wiremock_mapping_count,
    )
    db.add(stub)
    db.commit()
    db.refresh(stub)
    return stub


@router.get("", response_model=list[StubOut])
def list_stubs(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> list[Stub]:
    _project_or_404(db, project_id)
    return db.query(Stub).filter(Stub.project_id == project_id).order_by(Stub.created_at).all()


@router.get("/{stub_id}", response_model=StubOut)
def get_stub(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> Stub:
    return _stub_or_404(db, project_id, stub_id)


@router.delete("/{stub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stub(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_sv_team_or_admin),
) -> None:
    stub = _stub_or_404(db, project_id, stub_id)
    db.delete(stub)
    db.commit()
