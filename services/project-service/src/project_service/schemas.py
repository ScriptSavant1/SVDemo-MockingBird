"""Pydantic v2 request/response schemas for the project-service API.

Error responses follow RFC 7807 Problem JSON:
  {"type": "...", "title": "...", "status": 404, "detail": "..."}
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Problem JSON (RFC 7807) ────────────────────────────────────────────────────

class ProblemDetail(BaseModel):
    type: str = "https://mockingbird.internal/errors/generic"
    title: str
    status: int
    detail: str


# ── Users ──────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Projects ───────────────────────────────────────────────────────────────────

VALID_ENVIRONMENTS = {"TEST", "STAGING", "PROD"}
VALID_STATUSES = {"DRAFT", "READY", "DEPLOYING", "LIVE", "SUSPENDED"}


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


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthOut(BaseModel):
    status: str
    service: str
    version: str = "0.1.0"
