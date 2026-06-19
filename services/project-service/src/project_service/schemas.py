"""Pydantic v2 request/response schemas for the project-service API.

Error responses follow RFC 7807 Problem JSON:
  {"type": "...", "title": "...", "status": 404, "detail": "..."}
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Problem JSON (RFC 7807) ────────────────────────────────────────────────────

class ProblemDetail(BaseModel):
    type: str = "https://mockingbird.internal/errors/generic"
    title: str
    status: int
    detail: str


# ── Users ──────────────────────────────────────────────────────────────────────

VALID_ROLES = {"ADMIN", "SV_TEAM", "PROJECT_OWNER", "VIEWER"}


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="VIEWER")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v


class UserPatch(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v


class ResetPasswordIn(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int


# ── Audit Log ──────────────────────────────────────────────────────────────────

class AuditLogOut(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID]
    user_id: Optional[uuid.UUID]
    username: Optional[str]
    action: str
    detail: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int


# ── Projects ───────────────────────────────────────────────────────────────────

VALID_ENVIRONMENTS = {"TEST", "STAGING", "PROD"}
VALID_STATUSES = {"DRAFT", "READY", "DEPLOYING", "LIVE", "SUSPENDED", "ARCHIVED"}


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    team: str = Field(..., min_length=1, max_length=255)
    environment: str = Field(default="TEST")
    expected_tps: int = Field(default=1000, ge=1, le=100000)
    description: Optional[str] = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    team: Optional[str] = Field(default=None, min_length=1, max_length=255)
    environment: Optional[str] = None
    expected_tps: Optional[int] = Field(default=None, ge=1, le=100000)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[str] = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    team: str
    environment: str
    expected_tps: int
    description: Optional[str]
    status: str
    stub_url: Optional[str]
    api_key: Optional[str]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    total: int
    limit: int
    offset: int


# ── Stubs ──────────────────────────────────────────────────────────────────────

VALID_FORMATS = {
    "level-1-txt", "level-2-txt", "level-3-json",
    "soap-txt", "stateful-txt", "postman", "openapi",
}


class StubCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    format: str
    source_file_key: Optional[str] = Field(default=None, max_length=500)
    wiremock_mapping_count: int = Field(default=0, ge=0)


class StubOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    format: str
    source_file_key: Optional[str]
    wiremock_mapping_count: int
    generated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Jobs ───────────────────────────────────────────────────────────────────────

VALID_JOB_TYPES = {"PARSE", "GENERATE", "DEPLOY", "REPORT"}
VALID_JOB_STATUSES = {"QUEUED", "RUNNING", "DONE", "FAILED"}


class JobOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    project_id: Optional[uuid.UUID]
    stub_id: Optional[uuid.UUID]
    sqs_message_id: Optional[str]
    payload: dict
    result: Optional[dict]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerateTriggerOut(BaseModel):
    job_id: uuid.UUID
    status: str = "QUEUED"
    type: str = "PARSE"
    message: str = "Parse job queued. Poll /api/v1/jobs/{job_id} for status updates."


# ── Deployments ────────────────────────────────────────────────────────────────

VALID_TARGET_TYPES = {"AWS", "CROSS_ACCOUNT", "ON_PREM"}
VALID_DEPLOYMENT_STATUSES = {"PENDING", "BUILDING", "PROVISIONING", "LIVE", "SUSPENDED", "FAILED"}


class DeploymentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    stub_id: Optional[uuid.UUID]
    job_id: Optional[uuid.UUID]
    target_type: str
    status: str
    ec2_instance_id: Optional[str]
    ec2_ip_address: Optional[str]
    ec2_instance_type: Optional[str]
    gitlab_pipeline_id: Optional[str]
    docker_image_tag: Optional[str]
    stub_url: Optional[str]
    api_key: Optional[str]
    error_message: Optional[str]
    deployed_at: Optional[datetime]
    terminated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeployTriggerOut(BaseModel):
    deployment_id: uuid.UUID
    job_id: uuid.UUID
    status: str = "PENDING"
    message: str = "Deploy job queued. Poll /api/v1/jobs/{job_id} for status updates."


class SuspendTriggerOut(BaseModel):
    deployment_id: uuid.UUID
    status: str = "SUSPENDED"
    message: str = "Suspend job queued. EC2 will be terminated; stubs are preserved."


class ReportTriggerOut(BaseModel):
    deployment_id: uuid.UUID
    job_id: uuid.UUID
    status: str = "QUEUED"
    message: str = "Report job queued. Poll /api/v1/jobs/{job_id} for status updates."


# ── Reports ────────────────────────────────────────────────────────────────────

class ReportJobOut(BaseModel):
    id: uuid.UUID
    status: str
    result: Optional[dict]
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DownloadUrlOut(BaseModel):
    url: str
    format: str
    expires_in_seconds: int = 900


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthOut(BaseModel):
    status: str
    service: str
    version: str = "0.1.0"
