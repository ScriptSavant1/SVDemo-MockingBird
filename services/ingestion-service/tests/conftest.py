"""Shared pytest fixtures for ingestion-service tests.

Database: SQLite file per test (tmp_path) — guarantees true isolation.
  In-memory SQLite with StaticPool can share connections unexpectedly
  across tests; file-based SQLite with a unique tmp_path avoids this.
S3: moto mock_aws activated per test via autouse fixture.
Auth: FastAPI dependency_overrides on the shared app instance.
"""
from __future__ import annotations

import os
import uuid

import boto3
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Tell boto3 to use fake credentials so it never reaches AWS
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

import ingestion_service.config as _cfg

_cfg.settings.s3_bucket = "mockingbird-test-bucket"
_cfg.settings.aws_region = "eu-west-2"
_cfg.settings.jwt_secret = "test-jwt-secret"

from ingestion_service.database import Base, get_db
from ingestion_service.dependencies import CurrentUser, get_current_user, require_sv_team_or_admin
from ingestion_service.main import app
from ingestion_service.models import Project, User

TEST_S3_BUCKET = "mockingbird-test-bucket"

# UUIDs must start with a hex letter (a-f) so SQLite does not apply NUMERIC
# affinity and round them to floats (which would cause spurious UNIQUE collisions).
OWNER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
OTHER_PROJECT_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


# ── Database fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_engine(tmp_path):
    """Unique SQLite file per test — no shared state between tests."""
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Session:
    TestSession = sessionmaker(bind=db_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def owner_user(db_session: Session) -> User:
    user = User(
        id=OWNER_ID,
        username="sv.engineer",
        email="sv@company.com",
        password_hash="$2b$12$placeholder",
        role="SV_TEAM",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def test_projects(db_session: Session, owner_user: User):
    """Create primary and secondary test projects in the test DB."""
    project = Project(
        id=PROJECT_ID,
        name="Payments Integration",
        team="PaymentsTeam",
        created_by=OWNER_ID,
    )
    other = Project(
        id=OTHER_PROJECT_ID,
        name="Other Project",
        team="OtherTeam",
        created_by=OWNER_ID,
    )
    db_session.add_all([project, other])
    db_session.commit()
    return project, other


# ── S3 mock ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_s3_bucket():
    """Activate moto S3 mock and create the test bucket before every test."""
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(
            Bucket=TEST_S3_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
        )
        yield client


# ── FastAPI test client helpers ───────────────────────────────────────────────

def _make_client(db_engine, role: str) -> TestClient:
    """Build a TestClient with get_db, get_current_user, require_sv_team_or_admin overridden."""
    TestSession = sessionmaker(bind=db_engine)

    def override_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    def override_get_current_user() -> CurrentUser:
        return CurrentUser(id=OWNER_ID, username="sv.engineer", role=role)

    def override_require_sv_team_or_admin() -> CurrentUser:
        if role not in ("ADMIN", "SV_TEAM"):
            raise HTTPException(
                status_code=403,
                detail="SV_TEAM or ADMIN role required to upload stubs",
            )
        return CurrentUser(id=OWNER_ID, username="sv.engineer", role=role)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_sv_team_or_admin] = override_require_sv_team_or_admin

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def sv_client(db_engine, test_projects):
    client = _make_client(db_engine, role="SV_TEAM")
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(db_engine, test_projects):
    client = _make_client(db_engine, role="ADMIN")
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def viewer_client(db_engine, test_projects):
    client = _make_client(db_engine, role="VIEWER")
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def owner_client(db_engine, test_projects):
    client = _make_client(db_engine, role="PROJECT_OWNER")
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def unauth_client(db_engine, test_projects):
    """Client with no auth override — real JWT validation runs (401 on missing token)."""
    TestSession = sessionmaker(bind=db_engine)

    def override_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    # Intentionally NOT overriding get_current_user or require_sv_team_or_admin

    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()
