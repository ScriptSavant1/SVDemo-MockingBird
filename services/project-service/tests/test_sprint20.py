"""Sprint 20 — Admin panel: user management + audit log."""
from __future__ import annotations

import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ADMIN_TOKEN = "test-admin-token"
ADMIN_USER_ID = str(uuid.uuid4())

SVTEAM_TOKEN = "test-svteam-token"
SVTEAM_USER_ID = str(uuid.uuid4())


@pytest.fixture()
def client(monkeypatch) -> Generator[TestClient, None, None]:
    from project_service.main import app
    from project_service.database import Base, get_db
    from project_service.dependencies import CurrentUser, get_current_user, require_admin

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def _override_auth():
        return CurrentUser(id=uuid.UUID(SVTEAM_USER_ID), username="svteam", role="SV_TEAM")

    def _override_admin():
        return CurrentUser(id=uuid.UUID(ADMIN_USER_ID), username="adminuser", role="ADMIN")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_auth
    app.dependency_overrides[require_admin] = _override_admin

    yield TestClient(app, raise_server_exceptions=True)

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)


def _seed_user(db: Session, *, username: str = "alice", role: str = "SV_TEAM") -> dict:
    import bcrypt as _bcrypt_lib
    from project_service.models import User
    pw_hash = _bcrypt_lib.hashpw(b"password123", _bcrypt_lib.gensalt()).decode("utf-8")
    u = User(username=username, email=f"{username}@test.com",
             password_hash=pw_hash, role=role, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": str(u.id), "username": u.username, "role": u.role}


# ── List users ─────────────────────────────────────────────────────────────────

def test_list_users_empty(client):
    r = client.get("/api/v1/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_users_returns_seeded_user(client):
    from project_service.database import get_db
    db: Session = next(client.app.dependency_overrides[get_db]())
    _seed_user(db, username="bob")

    r = client.get("/api/v1/admin/users")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["username"] == "bob"


# ── Create user ────────────────────────────────────────────────────────────────

def test_create_user_returns_201(client):
    r = client.post("/api/v1/admin/users", json={
        "username": "charlie",
        "email": "charlie@test.com",
        "password": "password123",
        "role": "SV_TEAM",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "charlie"
    assert body["role"] == "SV_TEAM"
    assert body["is_active"] is True
    assert "password_hash" not in body


def test_create_user_duplicate_username_returns_409(client):
    payload = {"username": "dup", "email": "dup@test.com", "password": "password123", "role": "VIEWER"}
    client.post("/api/v1/admin/users", json=payload)
    r = client.post("/api/v1/admin/users", json={**payload, "email": "other@test.com"})
    assert r.status_code == 409


def test_create_user_duplicate_email_returns_409(client):
    payload = {"username": "user_one", "email": "shared@test.com", "password": "password123", "role": "VIEWER"}
    client.post("/api/v1/admin/users", json=payload)
    r = client.post("/api/v1/admin/users", json={**payload, "username": "user_two"})
    assert r.status_code == 409


def test_create_user_invalid_role_returns_422(client):
    r = client.post("/api/v1/admin/users", json={
        "username": "x", "email": "x@test.com", "password": "password123", "role": "SUPERUSER"
    })
    assert r.status_code == 422


def test_create_user_short_password_returns_422(client):
    r = client.post("/api/v1/admin/users", json={
        "username": "x", "email": "x@test.com", "password": "short", "role": "VIEWER"
    })
    assert r.status_code == 422


# ── Patch user ─────────────────────────────────────────────────────────────────

def test_patch_user_role(client):
    create_r = client.post("/api/v1/admin/users", json={
        "username": "dave", "email": "dave@test.com", "password": "password123", "role": "VIEWER"
    })
    user_id = create_r.json()["id"]
    r = client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "SV_TEAM"})
    assert r.status_code == 200
    assert r.json()["role"] == "SV_TEAM"


def test_patch_user_suspend(client):
    create_r = client.post("/api/v1/admin/users", json={
        "username": "eve", "email": "eve@test.com", "password": "password123", "role": "VIEWER"
    })
    user_id = create_r.json()["id"]
    r = client.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_patch_user_not_found_returns_404(client):
    r = client.patch(f"/api/v1/admin/users/{uuid.uuid4()}", json={"role": "VIEWER"})
    assert r.status_code == 404


# ── Reset password ─────────────────────────────────────────────────────────────

def test_reset_password_returns_204(client):
    create_r = client.post("/api/v1/admin/users", json={
        "username": "frank", "email": "frank@test.com", "password": "password123", "role": "VIEWER"
    })
    user_id = create_r.json()["id"]
    r = client.post(f"/api/v1/admin/users/{user_id}/reset-password",
                    json={"new_password": "newpassword456"})
    assert r.status_code == 204


# ── Audit log ──────────────────────────────────────────────────────────────────

def test_list_audit_returns_entries(client):
    from project_service.database import get_db
    from project_service.models import AuditLog
    db: Session = next(client.app.dependency_overrides[get_db]())
    log = AuditLog(action="project.created", detail={"name": "Test"})
    db.add(log)
    db.commit()

    r = client.get("/api/v1/admin/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "project.created"


def test_list_audit_includes_username_via_join(client):
    import bcrypt as _bcrypt_lib
    from project_service.database import get_db
    from project_service.models import AuditLog, User
    db: Session = next(client.app.dependency_overrides[get_db]())

    pw_hash = _bcrypt_lib.hashpw(b"password123", _bcrypt_lib.gensalt()).decode("utf-8")
    user = User(username="grace", email="grace@test.com",
                password_hash=pw_hash, role="SV_TEAM")
    db.add(user)
    db.flush()
    log = AuditLog(user_id=user.id, action="stub.deployed", detail={})
    db.add(log)
    db.commit()

    r = client.get("/api/v1/admin/audit")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["username"] == "grace"


def test_list_audit_filters_by_project_id(client):
    from project_service.database import get_db
    from project_service.models import AuditLog
    db: Session = next(client.app.dependency_overrides[get_db]())
    proj_id = uuid.uuid4()
    db.add(AuditLog(project_id=proj_id, action="project.created", detail={}))
    db.add(AuditLog(action="stub.deployed", detail={}))  # different project
    db.commit()

    r = client.get(f"/api/v1/admin/audit?project_id={proj_id}")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["action"] == "project.created"
