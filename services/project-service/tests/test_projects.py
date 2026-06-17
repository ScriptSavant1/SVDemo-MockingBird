"""Phase 3 Sprint 9 — project-service project CRUD tests."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


# ── health ─────────────────────────────────────────────────────────────────────

class TestHealth:

    def test_health_returns_ok(self, admin_client: TestClient):
        r = admin_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["service"] == "project-service"


# ── create project ─────────────────────────────────────────────────────────────

class TestCreateProject:

    def test_sv_team_can_create_project(self, sv_client: TestClient):
        r = sv_client.post("/api/v1/projects", json={
            "name": "Payment API Stub",
            "team": "Payments Team",
            "environment": "TEST",
            "expected_tps": 10000,
        })
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "Payment API Stub"
        assert body["team"] == "Payments Team"
        assert body["status"] == "DRAFT"
        assert "id" in body

    def test_admin_can_create_project(self, admin_client: TestClient):
        r = admin_client.post("/api/v1/projects", json={
            "name": "Admin Project",
            "team": "SV Team",
        })
        assert r.status_code == 201

    def test_create_project_defaults(self, sv_client: TestClient):
        r = sv_client.post("/api/v1/projects", json={
            "name": "Defaults Test",
            "team": "Team A",
        })
        assert r.status_code == 201
        body = r.json()
        assert body["environment"] == "TEST"
        assert body["expected_tps"] == 1000
        assert body["status"] == "DRAFT"
        assert body["stub_url"] is None
        assert body["api_key"] is None

    def test_create_project_with_description(self, sv_client: TestClient):
        r = sv_client.post("/api/v1/projects", json={
            "name": "With Desc",
            "team": "Team B",
            "description": "For integration testing of payments flow",
        })
        assert r.status_code == 201
        assert r.json()["description"] == "For integration testing of payments flow"

    def test_create_project_invalid_environment(self, sv_client: TestClient):
        r = sv_client.post("/api/v1/projects", json={
            "name": "Bad Env",
            "team": "Team C",
            "environment": "DEVELOPMENT",
        })
        assert r.status_code == 422

    def test_create_project_missing_name(self, sv_client: TestClient):
        r = sv_client.post("/api/v1/projects", json={"team": "Team D"})
        assert r.status_code == 422

    def test_create_project_missing_team(self, sv_client: TestClient):
        r = sv_client.post("/api/v1/projects", json={"name": "No Team"})
        assert r.status_code == 422

    def test_viewer_cannot_create_project(self, viewer_client: TestClient):
        r = viewer_client.post("/api/v1/projects", json={
            "name": "Viewer Project",
            "team": "Viewer Team",
        })
        assert r.status_code == 403

    def test_expected_tps_out_of_range(self, sv_client: TestClient):
        r = sv_client.post("/api/v1/projects", json={
            "name": "TPS Test",
            "team": "Team",
            "expected_tps": 0,
        })
        assert r.status_code == 422


# ── list projects ──────────────────────────────────────────────────────────────

class TestListProjects:

    def test_empty_list(self, sv_client: TestClient):
        r = sv_client.get("/api/v1/projects")
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["limit"] == 20
        assert body["offset"] == 0

    def test_list_returns_created_project(self, sv_client: TestClient):
        sv_client.post("/api/v1/projects", json={"name": "P1", "team": "T1"})
        r = sv_client.get("/api/v1/projects")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["name"] == "P1"

    def test_pagination_limit(self, sv_client: TestClient):
        for i in range(5):
            sv_client.post("/api/v1/projects", json={"name": f"P{i}", "team": "T"})
        r = sv_client.get("/api/v1/projects?limit=3")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 3
        assert body["total"] == 5
        assert body["limit"] == 3

    def test_pagination_offset(self, sv_client: TestClient):
        for i in range(3):
            sv_client.post("/api/v1/projects", json={"name": f"Q{i}", "team": "T"})
        r = sv_client.get("/api/v1/projects?limit=2&offset=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 1
        assert body["offset"] == 2

    def test_viewer_can_list_projects(self, viewer_client: TestClient):
        r = viewer_client.get("/api/v1/projects")
        assert r.status_code == 200


# ── get project ────────────────────────────────────────────────────────────────

class TestGetProject:

    def test_get_existing_project(self, sv_client: TestClient):
        create_r = sv_client.post("/api/v1/projects", json={"name": "Get Test", "team": "T"})
        project_id = create_r.json()["id"]
        r = sv_client.get(f"/api/v1/projects/{project_id}")
        assert r.status_code == 200
        assert r.json()["id"] == project_id
        assert r.json()["name"] == "Get Test"

    def test_get_nonexistent_project_returns_404(self, sv_client: TestClient):
        r = sv_client.get(f"/api/v1/projects/{uuid.uuid4()}")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["status"] == 404
        assert "not-found" in detail["type"]

    def test_viewer_can_get_project(self, sv_client: TestClient, viewer_client: TestClient):
        create_r = sv_client.post("/api/v1/projects", json={"name": "Viewer Get", "team": "T"})
        project_id = create_r.json()["id"]
        r = viewer_client.get(f"/api/v1/projects/{project_id}")
        assert r.status_code == 200


# ── update project ─────────────────────────────────────────────────────────────

class TestUpdateProject:

    def test_update_name(self, sv_client: TestClient):
        create_r = sv_client.post("/api/v1/projects", json={"name": "Old Name", "team": "T"})
        project_id = create_r.json()["id"]
        r = sv_client.put(f"/api/v1/projects/{project_id}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_status(self, sv_client: TestClient):
        create_r = sv_client.post("/api/v1/projects", json={"name": "Status Test", "team": "T"})
        project_id = create_r.json()["id"]
        r = sv_client.put(f"/api/v1/projects/{project_id}", json={"status": "READY"})
        assert r.status_code == 200
        assert r.json()["status"] == "READY"

    def test_update_invalid_status(self, sv_client: TestClient):
        create_r = sv_client.post("/api/v1/projects", json={"name": "Status Test 2", "team": "T"})
        project_id = create_r.json()["id"]
        r = sv_client.put(f"/api/v1/projects/{project_id}", json={"status": "BROKEN"})
        assert r.status_code == 422

    def test_update_nonexistent_project(self, sv_client: TestClient):
        r = sv_client.put(f"/api/v1/projects/{uuid.uuid4()}", json={"name": "Ghost"})
        assert r.status_code == 404

    def test_viewer_cannot_update_project(self, sv_client: TestClient, viewer_client: TestClient):
        create_r = sv_client.post("/api/v1/projects", json={"name": "RBAC Test", "team": "T"})
        project_id = create_r.json()["id"]
        r = viewer_client.put(f"/api/v1/projects/{project_id}", json={"name": "Hacked"})
        assert r.status_code == 403


# ── delete project ─────────────────────────────────────────────────────────────

class TestDeleteProject:

    def test_admin_can_delete_project(self, admin_client: TestClient):
        create_r = admin_client.post("/api/v1/projects", json={"name": "To Delete", "team": "T"})
        project_id = create_r.json()["id"]
        r = admin_client.delete(f"/api/v1/projects/{project_id}")
        assert r.status_code == 204

    def test_deleted_project_not_found(self, admin_client: TestClient):
        create_r = admin_client.post("/api/v1/projects", json={"name": "To Delete 2", "team": "T"})
        project_id = create_r.json()["id"]
        admin_client.delete(f"/api/v1/projects/{project_id}")
        r = admin_client.get(f"/api/v1/projects/{project_id}")
        assert r.status_code == 404

    def test_sv_team_cannot_delete_project(self, sv_client: TestClient):
        create_r = sv_client.post("/api/v1/projects", json={"name": "Cannot Delete", "team": "T"})
        project_id = create_r.json()["id"]
        r = sv_client.delete(f"/api/v1/projects/{project_id}")
        assert r.status_code == 403

    def test_delete_nonexistent_project(self, admin_client: TestClient):
        r = admin_client.delete(f"/api/v1/projects/{uuid.uuid4()}")
        assert r.status_code == 404
