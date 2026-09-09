"""Tests for routers/nft.py — on-demand NFT script generation.
Phase 1 (see docs/progress/PHASE1_JMETER_NFT_GENERATION.md): nft-jmeter.zip.
Phase 2 (see docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md): nft-scripts.zip
(combined jmeter/ + devweb/ folders).

Uses the same sv_client/PROJECT_ID fixtures as test_upload.py. Does not
touch or duplicate anything about the upload flow itself — these tests
only exercise the nft.py endpoints.
"""
from __future__ import annotations

import io
import uuid
import zipfile

PROJECT_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
UNKNOWN_PROJECT_ID = uuid.UUID("99000000-0000-0000-0000-000000000099")

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


def _upload_and_get_stub_id(sv_client) -> str:
    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/upload",
        data={"stub_name": "Payment API"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"], body
    return body["stub_id"]


def test_nft_jmeter_zip_returns_valid_zip_with_expected_files(sv_client):
    stub_id = _upload_and_get_stub_id(sv_client)

    resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/nft-jmeter.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "test-plan.jmx" in names
        assert "README.md" in names
        assert any(n.startswith("data/") and n.endswith(".csv") for n in names)

        jmx = zf.read("test-plan.jmx").decode("utf-8")
        assert "${requestPath}" in jmx
        assert "POST" in jmx

        [csv_name] = [n for n in names if n.startswith("data/")]
        csv_text = zf.read(csv_name).decode("utf-8")
        assert "requestPath,requestBody,expectedStatus" in csv_text
        assert "/payments/domestic" in csv_text
        assert "200" in csv_text


def test_nft_jmeter_zip_unknown_stub_returns_404(sv_client):
    resp = sv_client.get(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{uuid.uuid4()}/nft-jmeter.zip"
    )
    assert resp.status_code == 404


def test_nft_jmeter_zip_unknown_project_returns_404(sv_client):
    stub_id = _upload_and_get_stub_id(sv_client)
    resp = sv_client.get(f"/api/v1/projects/{UNKNOWN_PROJECT_ID}/stubs/{stub_id}/nft-jmeter.zip")
    assert resp.status_code == 404


def test_nft_jmeter_zip_does_not_require_stub_engine_pre_generation(sv_client):
    """The NFT zip is generated purely from the stored source file, on
    demand — it must work immediately after upload, before/without ever
    calling the separate generate/deploy steps."""
    stub_id = _upload_and_get_stub_id(sv_client)
    resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/nft-jmeter.zip")
    assert resp.status_code == 200


def test_nft_scripts_zip_contains_both_jmeter_and_devweb_folders(sv_client):
    stub_id = _upload_and_get_stub_id(sv_client)

    resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/nft-scripts.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "README.md" in names
        assert "jmeter/test-plan.jmx" in names
        assert any(n.startswith("jmeter/data/") and n.endswith(".csv") for n in names)
        assert "devweb/main.js" in names
        assert "devweb/rts.yml" in names
        assert "devweb/parameters.yml" in names
        assert any(n.endswith(".usr") and n.startswith("devweb/") for n in names)
        assert any(n.startswith("devweb/data/") and n.endswith(".csv") for n in names)
        # DevWeb's proprietary vendor SDK file is deliberately not bundled
        assert not any(n.endswith("DevWebSdk.d.ts") for n in names)

        main_js = zf.read("devweb/main.js").decode("utf-8")
        assert "load.action(" in main_js
        assert "load.Transaction(" in main_js
        assert "load.params" in main_js and "requestPath" in main_js  # path is parameterized

        params_yml = zf.read("devweb/parameters.yml").decode("utf-8")
        assert "requestPath" in params_yml
        assert "same as" in params_yml


def test_nft_scripts_zip_unknown_stub_returns_404(sv_client):
    resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{uuid.uuid4()}/nft-scripts.zip")
    assert resp.status_code == 404


def test_nft_scripts_zip_unknown_project_returns_404(sv_client):
    stub_id = _upload_and_get_stub_id(sv_client)
    resp = sv_client.get(f"/api/v1/projects/{UNKNOWN_PROJECT_ID}/stubs/{stub_id}/nft-scripts.zip")
    assert resp.status_code == 404


def test_nft_scripts_zip_does_not_require_stub_engine_pre_generation(sv_client):
    stub_id = _upload_and_get_stub_id(sv_client)
    resp = sv_client.get(f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/nft-scripts.zip")
    assert resp.status_code == 200
