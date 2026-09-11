"""Phase 3 Sprint 10 — ingestion-service tests.

18 tests covering:
  - Health check
  - Valid file upload (Level 1 TXT, Level 2 TXT, Postman JSON)
  - Invalid file content
  - Auth and RBAC enforcement
  - File size limits
  - Presigned URL generation

Tests use moto for S3 and SQLite in-memory for the database (see conftest.py).
To run: pip install -e ../parser-worker && pip install -e ".[dev]" && pytest
"""
from __future__ import annotations

import io
import uuid

import pytest

# Mirror the UUIDs defined in conftest — must start with a letter (SQLite NUMERIC affinity guard)
PROJECT_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
OTHER_PROJECT_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

# ── Fixture file content ──────────────────────────────────────────────────────

LEVEL1_TXT = b"""--- MOCKINGBIRD v1.0 ---
Stub-Name: Payment API
Team: PaymentsTeam
Method: POST
URL: /payments/domestic

--- REQUEST ---
Content-Type: application/json

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"transactionId": "TXN-001", "status": "ACCEPTED"}
"""

LEVEL2_TXT = b"""--- MOCKINGBIRD v1.0 ---
Stub-Name: Payment API
Team: PaymentsTeam
Method: POST
URL: /payments/domestic

--- REQUEST HEADERS ---
Content-Type: application/json

--- SCENARIO: success ---
Match-Type: body-json-path
Match-Field: $.currency
Match-Value: GBP
--- RESPONSE ---
Status: 200
{"status": "ACCEPTED"}

--- SCENARIO DEFAULT ---
--- RESPONSE ---
Status: 422
{"error": "Only GBP supported"}
"""

# body value uses a plain string (no nested JSON) to avoid escaped-quote issues
# in Python triple-quoted b-strings.
POSTMAN_JSON = b"""{
  "info": {
    "name": "Customer API",
    "_postman_id": "abc-123",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Get customer",
      "request": {
        "method": "GET",
        "url": { "raw": "{{baseUrl}}/customers/12345" },
        "header": [{"key": "Accept", "value": "application/json"}]
      },
      "response": [
        {
          "name": "200 OK",
          "status": "OK",
          "code": 200,
          "originalRequest": {
            "method": "GET",
            "url": { "raw": "{{baseUrl}}/customers/12345" }
          },
          "header": [{"key": "Content-Type", "value": "application/json"}],
          "body": "found"
        }
      ]
    }
  ]
}
"""

INVALID_CONTENT = b"this is not any recognised Mockingbird format"

UNKNOWN_PROJECT_ID = uuid.UUID("99000000-0000-0000-0000-000000000099")

# ── Health ────────────────────────────────────────────────────────────────────


def test_health(sv_client):
    resp = sv_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["service"] == "ingestion-service"


# ── Successful uploads ────────────────────────────────────────────────────────


def test_upload_sanitizes_path_traversal_filename(sv_client):
    """A malicious multipart filename must never survive into the storage key."""
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Payment API"},
        files={"file": ("../../../../etc/evil.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    s3_key = resp.json()["s3_key"]
    assert ".." not in s3_key
    assert s3_key.endswith("/evil.txt")


def test_upload_level1_txt_valid(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Payment API"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["stub_id"] is not None
    assert body["s3_key"] is not None
    assert body["stub_count"] == 1
    assert body["scenario_count"] == 1


def test_upload_level2_txt_returns_correct_scenario_count(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Multi-scenario Payment"},
        files={"file": ("payment_l2.txt", io.BytesIO(LEVEL2_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["scenario_count"] == 2
    assert "level-2" in body["format_detected"]


def test_upload_postman_json_detected(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Customer API (Postman)"},
        files={"file": ("customer.postman_collection.json", io.BytesIO(POSTMAN_JSON), "application/json")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert "postman" in body["format_detected"].lower()


def test_upload_by_admin_succeeds(admin_client):
    resp = admin_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Admin uploaded stub"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


# ── Validation failures ───────────────────────────────────────────────────────


def test_upload_invalid_format_returns_errors(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Bad Stub"},
        files={"file": ("bad.txt", io.BytesIO(INVALID_CONTENT), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0
    assert body["stub_id"] is None
    assert body["s3_key"] is None


def test_upload_empty_file_returns_error(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Empty"},
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
    assert resp.json()["errors"][0] == "Uploaded file is empty"


# ── 404 – project not found ───────────────────────────────────────────────────


def test_upload_to_unknown_project_returns_404(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{UNKNOWN_PROJECT_ID}/stubs/upload",
        data={"stub_name": "Orphan Stub"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 404


# ── Auth / RBAC ───────────────────────────────────────────────────────────────


def test_upload_without_token_returns_401(unauth_client):
    resp = unauth_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Unauth"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 401


def test_upload_viewer_role_returns_403(viewer_client):
    resp = viewer_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Viewer upload"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 403


def test_upload_project_owner_role_returns_403(owner_client):
    resp = owner_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Owner upload"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 403


# ── File size ─────────────────────────────────────────────────────────────────


def test_upload_oversized_file_returns_413(sv_client):
    big_content = b"x" * (11 * 1024 * 1024)  # 11 MB > 10 MB limit
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Big File"},
        files={"file": ("big.txt", io.BytesIO(big_content), "text/plain")},
    )
    assert resp.status_code == 413


# ── S3 key and stub record ────────────────────────────────────────────────────


def test_upload_creates_stub_record_in_db(sv_client, db_engine):
    from sqlalchemy.orm import sessionmaker
    from ingestion_service.models import Stub

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "DB Record Check"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    stub_id = uuid.UUID(resp.json()["stub_id"])

    # Open a separate session to verify the committed stub record
    VerifySession = sessionmaker(bind=db_engine)
    verify = VerifySession()
    try:
        stub = verify.get(Stub, stub_id)
        assert stub is not None
        assert stub.name == "DB Record Check"
        assert stub.source_file_key == resp.json()["s3_key"]
        assert stub.project_id == PROJECT_ID
    finally:
        verify.close()


def test_s3_key_contains_project_and_filename(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Key Check"},
        files={"file": ("myspec.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    s3_key = resp.json()["s3_key"]
    assert str(PROJECT_ID) in s3_key
    assert "myspec.txt" in s3_key


# ── Protocol / TLS cert at upload time ────────────────────────────────────────
# A stub's protocol/cert are set here, per-stub, at upload time — not on the
# project (see project-service migration 006). Cert is optional even for
# HTTPS: omitting it means "auto-generate a self-signed one at deploy time".


def test_upload_default_protocol_is_http(sv_client, db_engine):
    from sqlalchemy.orm import sessionmaker
    from ingestion_service.models import Stub

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Default Protocol"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    stub_id = uuid.UUID(resp.json()["stub_id"])

    VerifySession = sessionmaker(bind=db_engine)
    verify = VerifySession()
    try:
        stub = verify.get(Stub, stub_id)
        assert stub.protocol == "HTTP"
        assert stub.tls_cert_source is None
    finally:
        verify.close()


def test_upload_https_without_cert_defaults_to_auto_generated(sv_client, db_engine):
    from sqlalchemy.orm import sessionmaker
    from ingestion_service.models import Stub

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "HTTPS No Cert", "protocol": "HTTPS"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    stub_id = uuid.UUID(resp.json()["stub_id"])

    VerifySession = sessionmaker(bind=db_engine)
    verify = VerifySession()
    try:
        stub = verify.get(Stub, stub_id)
        assert stub.protocol == "HTTPS"
        assert stub.tls_cert_source == "AUTO_GENERATED"
        assert stub.tls_cert_s3_key is None
    finally:
        verify.close()


def test_upload_https_with_valid_cert_stores_it(sv_client, db_engine):
    from sqlalchemy.orm import sessionmaker
    from ingestion_service.models import Stub
    from tests.test_tls import _fresh_cert_and_key

    cert_pem, key_pem = _fresh_cert_and_key()
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "HTTPS With Cert", "protocol": "HTTPS"},
        files={
            "file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain"),
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 200
    stub_id = uuid.UUID(resp.json()["stub_id"])

    VerifySession = sessionmaker(bind=db_engine)
    verify = VerifySession()
    try:
        stub = verify.get(Stub, stub_id)
        assert stub.tls_cert_source == "UPLOADED"
        assert stub.tls_cert_s3_key == f"stubs/{PROJECT_ID}/{stub_id}/tls/server.crt.pem"
    finally:
        verify.close()


def test_upload_with_mismatched_cert_key_returns_validation_error(sv_client):
    from tests.test_tls import _fresh_cert_and_key

    cert_pem, _unused = _fresh_cert_and_key()
    _unused2, other_key_pem = _fresh_cert_and_key()
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Bad Pair", "protocol": "HTTPS"},
        files={
            "file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain"),
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(other_key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 200  # IngestionResult(valid=False, ...), not a 4xx
    body = resp.json()
    assert body["valid"] is False
    assert "does not match" in body["errors"][0]


def test_upload_invalid_protocol_returns_validation_error(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Bad Protocol", "protocol": "FTP"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_upload_mtls_without_ca_bundle_returns_validation_error(sv_client):
    from tests.test_tls import _fresh_cert_and_key

    cert_pem, key_pem = _fresh_cert_and_key()
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "mTLS No Bundle", "protocol": "HTTPS", "mtls_enabled": "true"},
        files={
            "file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain"),
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "CA bundle" in body["errors"][0]


# ── Presigned URL ─────────────────────────────────────────────────────────────


def test_get_presigned_url_for_uploaded_stub(sv_client):
    upload_resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Presigned Test"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    stub_id = upload_resp.json()["stub_id"]

    resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/source")
    assert resp.status_code == 200
    body = resp.json()
    assert "presigned_url" in body
    assert body["expires_in_seconds"] == 3600
    assert body["stub_id"] == stub_id


def test_get_presigned_url_unknown_stub_returns_404(sv_client):
    fake_id = uuid.uuid4()
    resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{fake_id}/source")
    assert resp.status_code == 404


def test_get_presigned_url_wrong_project_returns_404(sv_client):
    upload_resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Wrong Project Test"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    stub_id = upload_resp.json()["stub_id"]

    # Request the stub but under the OTHER project's ID — should be 404
    resp = sv_client.get(f"/api/v1/projects/{OTHER_PROJECT_ID}/stubs/{stub_id}/source")
    assert resp.status_code == 404


def test_get_presigned_url_without_auth_returns_401(unauth_client):
    fake_id = uuid.uuid4()
    resp = unauth_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{fake_id}/source")
    assert resp.status_code == 401
