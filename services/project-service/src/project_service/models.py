"""SQLAlchemy ORM models.

These models are the source of truth for the database schema.
Alembic generates migration scripts from the diff between these models
and the current database state.

Column rules (CLAUDE.md):
  - snake_case names
  - UUID primary keys
  - created_at + updated_at on all tables
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Roles: ADMIN  SV_TEAM  PROJECT_OWNER  VIEWER
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="VIEWER")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    projects: Mapped[list[Project]] = relationship("Project", back_populates="creator", lazy="select")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    team: Mapped[str] = mapped_column(String(255), nullable=False)
    # Environments: TEST  STAGING  PROD
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="TEST")
    expected_tps: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Lifecycle states: DRAFT  READY  DEPLOYING  LIVE  SUSPENDED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    stub_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    creator: Mapped[User] = relationship("User", back_populates="projects")
    stubs: Mapped[list[Stub]] = relationship("Stub", back_populates="project", cascade="all, delete-orphan")
    deployments: Mapped[list[Deployment]] = relationship("Deployment", back_populates="project")


class Stub(Base):
    __tablename__ = "stubs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Input format detected: level-1-txt  level-2-txt  soap-txt  stateful-txt  postman  openapi
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    # S3 object key for the uploaded source file
    source_file_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    wiremock_mapping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    project: Mapped[Project] = relationship("Project", back_populates="stubs")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    # Target: AWS  CROSS_ACCOUNT  ON_PREM
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, default="AWS")
    ec2_instance_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ec2_ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    gitlab_pipeline_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # States: PENDING  BUILDING  DEPLOYING  LIVE  TERMINATED  FAILED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    project: Mapped[Project] = relationship("Project", back_populates="deployments")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Job types: PARSE  GENERATE  DEPLOY  REPORT
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Job states: QUEUED  RUNNING  DONE  FAILED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    stub_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("stubs.id"), nullable=True)
    sqs_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # SQS message contract: {job_id, type, payload, created_at, project_id}
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
