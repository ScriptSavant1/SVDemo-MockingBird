"""Tests for POST /api/v1/projects/{project_id}/stubs/{stub_id}/tls-cert —
validates and stores an uploaded TLS server certificate + private key (and
optional CA bundle for mutual-TLS) for an EXISTING stub's generated stub
engine.

A stub's initial protocol/cert is normally set at upload time instead (see
test_upload.py's TLS-related tests) — this endpoint covers the "update it
later" case (swap an expiring cert, turn HTTPS on after the fact).

Certs/keys are generated fresh at test time with the `cryptography` library
itself rather than hardcoded PEM fixtures — a hardcoded cert would eventually
expire and silently break these tests years from now; generating fresh on
every run avoids that entirely.
"""
from __future__ import annotations

import datetime
import io
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ingestion_service.models import Stub

# Mirror the UUIDs defined in conftest — must start with a letter (SQLite NUMERIC affinity guard)
PROJECT_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
UNKNOWN_PROJECT_ID = uuid.UUID("99000000-0000-0000-0000-000000000099")


def _seed_stub(db_session, project_id=PROJECT_ID) -> str:
    """Insert a Stub row directly via the DB session, rather than through
    an authenticated client — conftest's client fixtures share a single
    `app.dependency_overrides` dict, so mixing two client fixtures (e.g. an
    sv_client to set up a stub, then unauth_client to test against it) in
    one test leaves whichever fixture ran its setup last "winning" for
    BOTH clients. Tests that need a pre-existing stub but exercise a
    different/no auth client use this instead of a second client fixture."""
    stub_id = uuid.uuid4()
    stub = Stub(id=stub_id, project_id=project_id, name="TLS Test Stub", format="level-1-txt", protocol="HTTPS")
    db_session.add(stub)
    db_session.commit()
    return str(stub_id)

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


def _create_stub(client, project_id=PROJECT_ID) -> str:
    resp = client.post(
        f"/api/v1/projects/{project_id}/stubs/upload",
        data={"stub_name": "TLS Test Stub", "protocol": "HTTPS"},
        files={"file": ("payment.txt", io.BytesIO(LEVEL1_TXT), "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["stub_id"]


# ── Cert/key generation helpers ────────────────────────────────────────────

def _generate_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_cert(
    private_key: rsa.RSAPrivateKey,
    *,
    not_valid_after: datetime.datetime,
    not_valid_before: datetime.datetime | None = None,
    common_name: str = "stub.example.com",
) -> x509.Certificate:
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    if not_valid_before is None:
        not_valid_before = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
    )
    return builder.sign(private_key, hashes.SHA256())


def _pem_cert(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _pem_key(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _fresh_cert_and_key(days_valid: int = 365) -> tuple[bytes, bytes]:
    """Generate a self-signed cert + matching private key, both PEM-encoded."""
    key = _generate_private_key()
    not_valid_after = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days_valid)
    cert = _build_cert(key, not_valid_after=not_valid_after)
    return _pem_cert(cert), _pem_key(key)


# ── Successful upload ───────────────────────────────────────────────────────


def test_upload_tls_cert_valid_pair_succeeds(sv_client, db_session):
    stub_id = _create_stub(sv_client)
    cert_pem, key_pem = _fresh_cert_and_key()

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tls_cert_s3_key"] == f"stubs/{PROJECT_ID}/{stub_id}/tls/server.crt.pem"
    assert body["tls_key_s3_key"] == f"stubs/{PROJECT_ID}/{stub_id}/tls/server.key.pem"
    assert body["tls_ca_bundle_s3_key"] is None
    assert body["warnings"] == []

    # Confirm the stub ROW itself was updated (not just S3) — query via a
    # fresh session against the same db_engine the client fixtures use.
    db_session.expire_all()
    stub = db_session.get(Stub, uuid.UUID(stub_id))
    assert stub.tls_cert_source == "UPLOADED"
    assert stub.tls_cert_s3_key == f"stubs/{PROJECT_ID}/{stub_id}/tls/server.crt.pem"


def test_upload_tls_cert_by_admin_succeeds(admin_client, db_session):
    stub_id = _seed_stub(db_session)
    cert_pem, key_pem = _fresh_cert_and_key()

    resp = admin_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 200


# ── Validation failures ──────────────────────────────────────────────────────


def test_upload_tls_cert_mismatched_key_returns_422(sv_client):
    stub_id = _create_stub(sv_client)
    cert_pem, _unused_key_pem = _fresh_cert_and_key()
    _unused_cert_pem, other_key_pem = _fresh_cert_and_key()

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(other_key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 422
    assert "does not match" in resp.json()["detail"]


def test_upload_tls_cert_expired_cert_returns_422(sv_client):
    stub_id = _create_stub(sv_client)
    key = _generate_private_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = _build_cert(
        key,
        not_valid_before=now - datetime.timedelta(days=30),
        not_valid_after=now - datetime.timedelta(days=1),
    )
    cert_pem = _pem_cert(cert)
    key_pem = _pem_key(key)

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 422
    assert "expired" in resp.json()["detail"]


def test_upload_tls_cert_malformed_pem_returns_422(sv_client):
    stub_id = _create_stub(sv_client)
    _cert_pem, key_pem = _fresh_cert_and_key()

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(b"this is not a certificate"), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 422
    assert "not a valid PEM-encoded X.509 certificate" in resp.json()["detail"]


def test_upload_tls_cert_malformed_key_returns_422(sv_client):
    stub_id = _create_stub(sv_client)
    cert_pem, _key_pem = _fresh_cert_and_key()

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(b"not a key either"), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 422
    assert "not a valid unencrypted PEM-encoded private key" in resp.json()["detail"]


def test_upload_tls_cert_oversized_file_returns_413(sv_client):
    stub_id = _create_stub(sv_client)
    cert_pem, key_pem = _fresh_cert_and_key()
    oversized = cert_pem + b"\n" + b"x" * (65 * 1024)

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(oversized), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 413


# ── CA bundle ─────────────────────────────────────────────────────────────────


def test_upload_tls_cert_with_ca_bundle_succeeds(sv_client):
    stub_id = _create_stub(sv_client)
    cert_pem, key_pem = _fresh_cert_and_key()

    ca1_key = _generate_private_key()
    ca1_cert = _build_cert(ca1_key, not_valid_after=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=730), common_name="Test CA One")
    ca2_key = _generate_private_key()
    ca2_cert = _build_cert(ca2_key, not_valid_after=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=730), common_name="Test CA Two")
    bundle_pem = _pem_cert(ca1_cert) + _pem_cert(ca2_cert)

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
            "ca_bundle": ("ca-bundle.pem", io.BytesIO(bundle_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tls_ca_bundle_s3_key"] == f"stubs/{PROJECT_ID}/{stub_id}/tls/ca-bundle.pem"


def test_upload_tls_cert_with_invalid_ca_bundle_returns_422(sv_client):
    stub_id = _create_stub(sv_client)
    cert_pem, key_pem = _fresh_cert_and_key()

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
            "ca_bundle": ("ca-bundle.pem", io.BytesIO(b"garbage, not a cert"), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 422
    assert "ca_bundle" in resp.json()["detail"]


# ── 404 — stub not found ───────────────────────────────────────────────────────


def test_upload_tls_cert_unknown_stub_returns_404(sv_client):
    cert_pem, key_pem = _fresh_cert_and_key()

    resp = sv_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{uuid.uuid4()}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 404


def test_upload_tls_cert_unknown_project_returns_404(sv_client):
    stub_id = _create_stub(sv_client)
    cert_pem, key_pem = _fresh_cert_and_key()

    resp = sv_client.post(
        f"/api/v1/projects/{UNKNOWN_PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 404


# ── Auth / RBAC ───────────────────────────────────────────────────────────────


def test_upload_tls_cert_without_token_returns_401(unauth_client, db_session):
    stub_id = _seed_stub(db_session)
    cert_pem, key_pem = _fresh_cert_and_key()

    resp = unauth_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 401


def test_upload_tls_cert_viewer_role_returns_403(viewer_client, db_session):
    stub_id = _seed_stub(db_session)
    cert_pem, key_pem = _fresh_cert_and_key()

    resp = viewer_client.post(
        f"/api/v1/projects/{PROJECT_ID}/stubs/{stub_id}/tls-cert",
        files={
            "server_cert": ("server.crt.pem", io.BytesIO(cert_pem), "application/x-pem-file"),
            "server_key": ("server.key.pem", io.BytesIO(key_pem), "application/x-pem-file"),
        },
    )
    assert resp.status_code == 403
