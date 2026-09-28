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
import zipfile

import openpyxl
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


def _xlsx_zip_bytes() -> bytes:
    """Build a minimal, real Mockingbird xlsx stub template zip in memory —
    one static stub, one data-driven stub with a real (non-placeholder)
    match condition and a Default row, mirroring xlsx_parser's own test
    fixtures. Used here specifically to prove upload.py's stub-name-override
    fix: these two names ("SimpleStub", "ComplexStub") must survive into the
    generated WireMock mappings untouched by whatever stub_name the form
    submits.
    """
    wb = openpyxl.Workbook()
    stubs_ws = wb.active
    stubs_ws.title = "Stubs"
    stubs_ws.append(["STUBS"])
    stubs_ws.append([
        "Stub Name", "Model", "Protocol", "Method", "URL Path", "Templated URL?",
        "Request Body", "Response Status", "Response Content-Type",
        "Response Body  (inline, file:<name>, or SEE Rules)", "Data-driven?", "Notes",
    ])
    stubs_ws.append(["SimpleStub", "Demo", "REST", "GET", "/v1/simple", "No", None, "200",
                      "application/json", '{"ok":true}', "No", ""])
    stubs_ws.append(["ComplexStub", "Demo", "REST", "POST", "/v1/complex", "No", None, "200",
                      "application/json", "SEE Rules tab", "Yes", ""])

    rules_ws = wb.create_sheet("Rules")
    rules_ws.append(["RULES"])
    rules_ws.append([
        "Stub Name", "Order", "Scenario", "Extract Field", "Extract From",
        "Path / Expression", "Lookup File", "Match On", "Response Status",
        "Response Body (file:<name>)",
    ])
    rules_ws.append(["ComplexStub", 1, "Success 1", "action", "body-json-path", "$.action",
                      None, "action == 'create'", 200, '{"status":"created"}'])
    rules_ws.append(["ComplexStub", 2, "Default", "action", "body-json-path", "$.action",
                      None, "always", 200, '{"status":"unknown"}'])

    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mockingbird-stub-template.xlsx", xlsx_buf.getvalue())
    return zip_buf.getvalue()


def test_upload_xlsx_zip_generates_all_stubs_and_preserves_real_names(sv_client):
    """Regression test for the stub-name-override bug: uploading an xlsx zip
    with a generic package-level stub_name must NOT overwrite the sheet's own
    per-operation stub names ("SimpleStub", "ComplexStub") with "My Package 1"
    / "My Package 2" the way CA LISA/Postman uploads intentionally do.
    """
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "My Package"},
        files={"file": ("xlsx-mini.zip", io.BytesIO(_xlsx_zip_bytes()), "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True, body.get("errors")
    assert "xlsx" in body["format_detected"]
    assert body["stub_count"] == 2
    assert body["scenario_count"] == 3  # SimpleStub: 1, ComplexStub: 2

    stub_id = body["stub_id"]
    zip_resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/wiremock.zip")
    assert zip_resp.status_code == 200

    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        names = zf.namelist()

    # The real per-operation names must appear in the generated mapping
    # filenames; the generic package-level "stub_name" must NOT have replaced
    # them (that would collapse both operations into indistinguishable
    # "my_package_1_*"/"my_package_2_*" files).
    assert any("simplestub" in n.lower() for n in names), names
    assert any("complexstub" in n.lower() for n in names), names
    assert not any("my_package" in n.lower() for n in names), names


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
    body = resp.json()
    assert body["error_code"] == "MB-UPL-001"
    assert body["error_summary"] == "'empty.txt' is empty"


# ── 404 – project not found ───────────────────────────────────────────────────


def test_upload_to_unknown_project_returns_404(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{UNKNOWN_PROJECT_ID}/stubs/upload",
        data={"stub_name": "Orphan Stub"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "MB-REQ-404"
    assert body["detail"] == f"Project {UNKNOWN_PROJECT_ID} not found"


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
    body = resp.json()
    assert body["code"] == "MB-UPL-002"
    assert body["detail"] == "Upload is 11.0 MB — the limit is 10 MB"


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


# ── Error codes: xlsx template with a missing referenced file ─────────────────


def _xlsx_template_zip(referenced: list[str], included: list[str]) -> bytes:
    """A minimal Mockingbird xlsx stub template zip: one static stub per
    `referenced` file (Response Body = file:<name>), plus only the `included`
    data files — so any referenced-but-not-included file is missing."""
    import openpyxl
    import zipfile

    wb = openpyxl.Workbook()
    stubs = wb.active
    stubs.title = "Stubs"
    stubs.append(["Mockingbird stub template"])
    stubs.append(["Stub Name", "Protocol", "Method", "URL Path", "Response Status",
                  "Response Content-Type", "Response Body", "Data-driven?"])
    for i, name in enumerate(referenced):
        stubs.append([f"Stub{i}", "REST", "GET", f"/api/s{i}", "200", "application/json", f"file:{name}", "No"])
    rules = wb.create_sheet("Rules")
    rules.append(["Rules"])
    rules.append(["Stub Name", "Order", "Scenario", "Extract Field", "Extract From",
                  "Path / Expression", "Lookup File", "Match On", "Response Status", "Response Body"])
    xlsx = io.BytesIO()
    wb.save(xlsx)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("template.xlsx", xlsx.getvalue())
        for name in included:
            zf.writestr(f"data/{name}", b'{"ok": true}')
    return buf.getvalue()


def test_xlsx_missing_referenced_files_get_one_line_summary(sv_client):
    zip_bytes = _xlsx_template_zip(
        referenced=["a_response.json", "b_response.json", "c_response.json"],
        included=["a_response.json"],
    )
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Xlsx Package"},
        files={"file": ("pkg.zip", io.BytesIO(zip_bytes), "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["error_code"] == "MB-UPL-004"
    assert body["error_summary"] == "Referenced 2 files are missing from the upload: b_response.json, c_response.json"
    assert len(body["errors"]) == 2  # full detail still there underneath


def test_xlsx_complete_upload_is_valid(sv_client):
    zip_bytes = _xlsx_template_zip(referenced=["a_response.json"], included=["a_response.json"])
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Xlsx Package"},
        files={"file": ("pkg.zip", io.BytesIO(zip_bytes), "application/zip")},
    )
    body = resp.json()
    assert body["valid"] is True, body
    assert body["error_code"] is None


def test_unrecognised_format_gets_upl_003(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Junk"},
        files={"file": ("junk.txt", io.BytesIO(b"this is not any spec format at all"), "text/plain")},
    )
    body = resp.json()
    assert body["valid"] is False
    assert body["error_code"] == "MB-UPL-003"
    assert body["error_summary"].startswith("File format not recognised.")


def test_invalid_protocol_gets_upl_006(sv_client):
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "P", "protocol": "FTP"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    body = resp.json()
    assert body["error_code"] == "MB-UPL-006"
    assert body["error_summary"] == "Protocol must be one of BOTH, HTTP, HTTPS (got 'FTP')"


def test_unexpected_parser_crash_returns_coded_500_without_internals(sv_client, monkeypatch):
    import parser_worker.detector as detector

    def boom(_path):
        raise RuntimeError("secret internal path C:/very/internal/thing")

    monkeypatch.setattr(detector, "detect_and_parse", boom)
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Crash"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "MB-SYS-001"
    assert body["ref"] and body["ref"] in body["detail"]
    assert "secret" not in resp.text and "internal/thing" not in resp.text


def test_missing_dependency_returns_sys_002_naming_the_component(sv_client, monkeypatch):
    import parser_worker.detector as detector

    def missing(_path):
        raise ModuleNotFoundError("No module named 'openpyxl'", name="openpyxl")

    monkeypatch.setattr(detector, "detect_and_parse", missing)
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Dep"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "MB-SYS-002"
    assert "'openpyxl'" in body["detail"]


def test_stub_project_generation_failure_is_a_visible_warning(sv_client, monkeypatch, tmp_path):
    import parser_worker.generator.springboot as springboot
    from ingestion_service import config as _cfg

    # Stub-project pre-generation only runs in local-storage mode — pin it
    # here rather than depend on the developer's .env.
    monkeypatch.setattr(_cfg.settings, "local_storage_path", str(tmp_path))

    def boom(*_a, **_k):
        raise RuntimeError("template missing")

    monkeypatch.setattr(springboot, "generate_springboot_project_zip", boom)
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "GenFail"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    body = resp.json()
    assert body["valid"] is True
    gen = [w for w in body["warnings"] if w.startswith("MB-GEN-001 · ")]
    assert len(gen) == 1 and "(ref " in gen[0]
    assert "template missing" not in gen[0]
