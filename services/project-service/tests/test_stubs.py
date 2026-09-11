"""Phase 3 Sprint 9 — project-service stub CRUD tests."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


# ── helpers ────────────────────────────────────────────────────────────────────

def _create_project(client: TestClient, name: str = "Test Project") -> str:
    r = client.post("/api/v1/projects", json={"name": name, "team": "Test Team"})
    assert r.status_code == 201
    return r.json()["id"]


# ── create stub ────────────────────────────────────────────────────────────────

class TestCreateStub:

    def test_create_stub_in_project(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Payment Stub",
            "format": "level-2-txt",
            "wiremock_mapping_count": 3,
        })
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "Payment Stub"
        assert body["format"] == "level-2-txt"
        assert body["project_id"] == project_id
        assert body["wiremock_mapping_count"] == 3

    def test_create_stub_all_formats(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        valid_formats = [
            "level-1-txt", "level-2-txt", "level-3-json",
            "soap-txt", "stateful-txt", "postman", "openapi",
        ]
        for fmt in valid_formats:
            r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
                "name": f"Stub {fmt}",
                "format": fmt,
            })
            assert r.status_code == 201, f"Expected 201 for format {fmt}, got {r.status_code}"

    def test_create_stub_invalid_format(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Bad Format",
            "format": "csv",
        })
        assert r.status_code == 422

    def test_create_stub_with_s3_key(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "S3 Stub",
            "format": "postman",
            "source_file_key": "uploads/project-abc/payment-collection.json",
        })
        assert r.status_code == 201
        assert r.json()["source_file_key"] == "uploads/project-abc/payment-collection.json"

    def test_create_stub_project_not_found(self, sv_client: TestClient):
        r = sv_client.post(f"/api/v1/projects/{uuid.uuid4()}/stubs", json={
            "name": "Ghost Stub",
            "format": "level-1-txt",
        })
        assert r.status_code == 404

    def test_viewer_cannot_create_stub(self, sv_client: TestClient, viewer_client: TestClient):
        project_id = _create_project(sv_client)
        r = viewer_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Viewer Stub",
            "format": "level-1-txt",
        })
        assert r.status_code == 403

    def test_create_stub_missing_name(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={"format": "level-1-txt"})
        assert r.status_code == 422


# ── list stubs ─────────────────────────────────────────────────────────────────

class TestListStubs:

    def test_empty_stub_list(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.get(f"/api/v1/projects/{project_id}/stubs")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_returns_all_stubs(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        for i in range(3):
            sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
                "name": f"Stub {i}",
                "format": "level-1-txt",
            })
        r = sv_client.get(f"/api/v1/projects/{project_id}/stubs")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_stubs_isolated_by_project(self, sv_client: TestClient):
        pid1 = _create_project(sv_client, "Project Alpha")
        pid2 = _create_project(sv_client, "Project Beta")
        sv_client.post(f"/api/v1/projects/{pid1}/stubs", json={"name": "Alpha Stub", "format": "level-1-txt"})
        sv_client.post(f"/api/v1/projects/{pid1}/stubs", json={"name": "Alpha Stub 2", "format": "level-2-txt"})
        sv_client.post(f"/api/v1/projects/{pid2}/stubs", json={"name": "Beta Stub", "format": "soap-txt"})
        r1 = sv_client.get(f"/api/v1/projects/{pid1}/stubs")
        r2 = sv_client.get(f"/api/v1/projects/{pid2}/stubs")
        assert len(r1.json()) == 2
        assert len(r2.json()) == 1

    def test_list_stubs_project_not_found(self, sv_client: TestClient):
        r = sv_client.get(f"/api/v1/projects/{uuid.uuid4()}/stubs")
        assert r.status_code == 404


# ── get stub ───────────────────────────────────────────────────────────────────

class TestGetStub:

    def test_get_existing_stub(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        create_r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Get Me",
            "format": "openapi",
        })
        stub_id = create_r.json()["id"]
        r = sv_client.get(f"/api/v1/projects/{project_id}/stubs/{stub_id}")
        assert r.status_code == 200
        assert r.json()["id"] == stub_id
        assert r.json()["name"] == "Get Me"

    def test_get_stub_not_found(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.get(f"/api/v1/projects/{project_id}/stubs/{uuid.uuid4()}")
        assert r.status_code == 404
        assert "stub-not-found" in r.json()["detail"]["type"]

    def test_get_stub_wrong_project(self, sv_client: TestClient):
        pid1 = _create_project(sv_client, "Project X")
        pid2 = _create_project(sv_client, "Project Y")
        create_r = sv_client.post(f"/api/v1/projects/{pid1}/stubs", json={
            "name": "Belongs to X",
            "format": "level-1-txt",
        })
        stub_id = create_r.json()["id"]
        # Asking for it under project Y should 404
        r = sv_client.get(f"/api/v1/projects/{pid2}/stubs/{stub_id}")
        assert r.status_code == 404


# ── delete stub ────────────────────────────────────────────────────────────────

class TestDeleteStub:

    def test_delete_stub(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        create_r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Delete Me",
            "format": "level-1-txt",
        })
        stub_id = create_r.json()["id"]
        r = sv_client.delete(f"/api/v1/projects/{project_id}/stubs/{stub_id}")
        assert r.status_code == 204

    def test_deleted_stub_not_found(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        create_r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Delete Me 2",
            "format": "level-1-txt",
        })
        stub_id = create_r.json()["id"]
        sv_client.delete(f"/api/v1/projects/{project_id}/stubs/{stub_id}")
        r = sv_client.get(f"/api/v1/projects/{project_id}/stubs/{stub_id}")
        assert r.status_code == 404

    def test_delete_project_cascades_to_stubs(self, admin_client: TestClient, sv_client: TestClient):
        project_id = _create_project(sv_client)
        sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Cascade Stub",
            "format": "level-1-txt",
        })
        admin_client.delete(f"/api/v1/projects/{project_id}")
        # Project gone → stubs gone → list returns 404 (project not found)
        r = sv_client.get(f"/api/v1/projects/{project_id}/stubs")
        assert r.status_code == 404


# ── TLS / mTLS protocol config (per-stub — see migration 006) ───────────────────

class TestStubTlsConfig:

    def test_create_with_https_protocol(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "HTTPS Stub", "format": "level-1-txt", "protocol": "HTTPS",
        })
        assert r.status_code == 201
        assert r.json()["protocol"] == "HTTPS"

    def test_create_with_invalid_protocol(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Bad Protocol", "format": "level-1-txt", "protocol": "FTP",
        })
        assert r.status_code == 422

    def test_create_default_protocol_is_http(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "Default Protocol", "format": "level-1-txt",
        })
        assert r.json()["protocol"] == "HTTP"

    def test_tls_config_never_exposes_raw_s3_keys(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        create_r = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "No Leak", "format": "level-1-txt", "protocol": "HTTPS",
            "tls_cert_s3_key": "stubs/p/s/tls/server.crt.pem",
            "tls_key_s3_key": "stubs/p/s/tls/server.key.pem",
        })
        for key in ("tls_cert_s3_key", "tls_key_s3_key", "tls_ca_bundle_s3_key"):
            assert key not in create_r.text
        assert create_r.json()["has_uploaded_cert"] is True
        assert create_r.json()["has_ca_bundle"] is False

    def test_update_tls_config_enable_mtls_without_ca_bundle_returns_422(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        stub_id = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "S", "format": "level-1-txt", "protocol": "HTTPS",
        }).json()["id"]
        r = sv_client.put(f"/api/v1/projects/{project_id}/stubs/{stub_id}/tls-config", json={
            "mtls_enabled": True,
        })
        assert r.status_code == 422

    def test_update_tls_config_set_ca_bundle_then_enable_mtls_same_call_succeeds(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        stub_id = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "S", "format": "level-1-txt", "protocol": "HTTPS",
        }).json()["id"]
        r = sv_client.put(f"/api/v1/projects/{project_id}/stubs/{stub_id}/tls-config", json={
            "tls_ca_bundle_s3_key": "stubs/p/s/tls/ca-bundle.pem",
            "mtls_enabled": True,
        })
        assert r.status_code == 200
        assert r.json()["mtls_enabled"] is True
        assert r.json()["has_ca_bundle"] is True

    def test_update_tls_config_switching_to_http_clears_tls_state(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        stub_id = sv_client.post(f"/api/v1/projects/{project_id}/stubs", json={
            "name": "S", "format": "level-1-txt", "protocol": "HTTPS",
            "tls_cert_s3_key": "c", "tls_key_s3_key": "k",
            "tls_ca_bundle_s3_key": "ca", "mtls_enabled": True,
        }).json()["id"]
        r = sv_client.put(f"/api/v1/projects/{project_id}/stubs/{stub_id}/tls-config", json={
            "protocol": "HTTP",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["protocol"] == "HTTP"
        assert body["mtls_enabled"] is False
        assert body["has_uploaded_cert"] is False
        assert body["has_ca_bundle"] is False

    def test_update_tls_config_unknown_stub_returns_404(self, sv_client: TestClient):
        project_id = _create_project(sv_client)
        r = sv_client.put(
            f"/api/v1/projects/{project_id}/stubs/{uuid.uuid4()}/tls-config",
            json={"protocol": "HTTPS"},
        )
        assert r.status_code == 404
