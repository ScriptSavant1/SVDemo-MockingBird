"""Shared pytest fixtures for project-service tests.

Uses SQLite in-memory with StaticPool so all connections share the same
underlying connection — this makes create_all() and session queries see
the same database state.

The get_db dependency is overridden with a test session bound to the
test engine — this is a real database engine, not a mock.
"""
from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from project_service.database import Base, get_db
from project_service.dependencies import get_current_user, CurrentUser
from project_service.main import create_app
from project_service.models import User

TEST_JWT_SECRET = "test-secret"
TEST_JWT_ALGORITHM = "HS256"

import project_service.config as _cfg
_cfg.settings.jwt_secret = TEST_JWT_SECRET
_cfg.settings.jwt_algorithm = TEST_JWT_ALGORITHM


@pytest.fixture(scope="function")
def db_engine():
    """One isolated in-memory SQLite database per test function."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # All connections share the same SQLite connection
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    TestSession = sessionmaker(bind=db_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def admin_user(db_session: Session) -> User:
    user = User(username="admin", email="admin@company.com", password_hash="hashed", role="ADMIN")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def sv_user(db_session: Session) -> User:
    user = User(username="sv.engineer", email="sv@company.com", password_hash="hashed", role="SV_TEAM")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def viewer_user(db_session: Session) -> User:
    user = User(username="viewer", email="viewer@company.com", password_hash="hashed", role="VIEWER")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_client(db_engine, current_user: CurrentUser) -> TestClient:
    """Build a TestClient with get_db and get_current_user both overridden."""
    app = create_app()
    TestSession = sessionmaker(bind=db_engine)

    def override_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        return current_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app)


@pytest.fixture(scope="function")
def admin_client(db_engine, admin_user: User) -> TestClient:
    return _make_client(db_engine, CurrentUser(id=admin_user.id, username=admin_user.username, role="ADMIN"))


@pytest.fixture(scope="function")
def sv_client(db_engine, sv_user: User) -> TestClient:
    return _make_client(db_engine, CurrentUser(id=sv_user.id, username=sv_user.username, role="SV_TEAM"))


@pytest.fixture(scope="function")
def viewer_client(db_engine, viewer_user: User) -> TestClient:
    return _make_client(db_engine, CurrentUser(id=viewer_user.id, username=viewer_user.username, role="VIEWER"))
