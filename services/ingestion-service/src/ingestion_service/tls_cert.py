"""Shared TLS server-certificate validation + storage helpers.

Used by both routers/tls.py (standalone "update a stub's cert later"
endpoint) and routers/upload.py (cert can ride along with the initial spec
upload, since a stub's protocol/cert are set at upload time — see
project-service migration 006).

Validates with the `cryptography` library directly (no openssl subprocess —
avoids any command-injection surface). Security discipline: raw file bytes
(especially the private key) are never logged — only filenames/sizes/
outcomes — and no exception message or response ever includes key
material, only structural descriptions of what failed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException, UploadFile, status

from .s3_client import get_s3_client, is_local_storage, upload_bytes, upload_local

logger = logging.getLogger(__name__)

# PEM certs/keys/bundles are KB-sized text files — 64 KB is generous headroom
# for even a multi-cert CA bundle, while still catching anything wildly wrong.
MAX_TLS_FILE_BYTES = 64 * 1024
_EXPIRY_WARNING_WINDOW_DAYS = 30
_PEM_CERT_MARKER = "-----BEGIN CERTIFICATE-----"


class TlsCertValidationError(Exception):
    """Raised with a 422-appropriate detail string — callers translate this
    to HTTPException themselves, since upload.py's existing convention for
    the surrounding request differs slightly from tls.py's."""


def read_limited(file: UploadFile, field_name: str) -> bytes:
    content = file.file.read()
    if len(content) > MAX_TLS_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{field_name} exceeds {MAX_TLS_FILE_BYTES // 1024} KB limit",
        )
    return content


def _not_valid_after_utc(cert: x509.Certificate) -> datetime:
    """cryptography >=42 exposes not_valid_after_utc directly; fall back to
    the deprecated naive not_valid_after (already UTC per RFC 5280, just
    without tzinfo) for older installed versions."""
    utc_value = getattr(cert, "not_valid_after_utc", None)
    if utc_value is not None:
        return utc_value
    return cert.not_valid_after.replace(tzinfo=timezone.utc)  # pragma: no cover — only hit on cryptography <42


def validate_cert_key_pair(cert_bytes: bytes, key_bytes: bytes) -> tuple[x509.Certificate, list[str]]:
    """Validate a server cert + private key pair. Returns (cert, warnings).
    Raises TlsCertValidationError with a specific message on any failure."""
    try:
        cert = x509.load_pem_x509_certificate(cert_bytes)
    except Exception as exc:
        raise TlsCertValidationError("server_cert is not a valid PEM-encoded X.509 certificate") from exc

    try:
        key = serialization.load_pem_private_key(key_bytes, password=None)
    except Exception as exc:
        # Covers malformed keys as well as password-protected ones — the
        # latter raises TypeError asking for a password, also treated as a
        # validation failure since only unencrypted keys are accepted here.
        raise TlsCertValidationError("server_key is not a valid unencrypted PEM-encoded private key") from exc

    if cert.public_key().public_numbers() != key.public_key().public_numbers():
        raise TlsCertValidationError("server_key does not match server_cert")

    warnings: list[str] = []
    not_valid_after = _not_valid_after_utc(cert)
    now = datetime.now(timezone.utc)
    if not_valid_after <= now:
        raise TlsCertValidationError(f"server_cert has expired (was valid until {not_valid_after.isoformat()})")
    if (not_valid_after - now).days < _EXPIRY_WARNING_WINDOW_DAYS:
        warnings.append(f"server_cert expires soon: {not_valid_after.isoformat()}")

    return cert, warnings


def validate_ca_bundle(bundle_bytes: bytes) -> None:
    """A bundle may contain multiple concatenated PEM certs. Split on the
    BEGIN CERTIFICATE marker, re-prepending it to each non-empty chunk, and
    parse each one independently — lenient about whitespace/ordering,
    strict about actually-malformed cert data."""
    text = bundle_bytes.decode("utf-8", errors="replace")
    chunks = [_PEM_CERT_MARKER + part for part in text.split(_PEM_CERT_MARKER) if part.strip()]
    if not chunks:
        raise TlsCertValidationError("ca_bundle contains no valid certificates")
    for chunk in chunks:
        try:
            x509.load_pem_x509_certificate(chunk.encode("utf-8"))
        except Exception as exc:
            raise TlsCertValidationError("ca_bundle contains an invalid certificate") from exc


def store_tls_files(
    key_prefix: str,
    cert_bytes: bytes,
    key_bytes: bytes,
    bundle_bytes: Optional[bytes],
) -> tuple[str, str, Optional[str]]:
    """Store validated cert/key/bundle under stubs/{project_id}/{stub_id}/tls/
    (key_prefix), local disk or S3 matching the branch already used
    elsewhere in this service. Returns (cert_key, key_key, bundle_key)."""
    cert_key = f"{key_prefix}/server.crt.pem"
    key_key = f"{key_prefix}/server.key.pem"
    bundle_key = f"{key_prefix}/ca-bundle.pem" if bundle_bytes is not None else None

    if is_local_storage():
        upload_local(cert_key, cert_bytes)
        upload_local(key_key, key_bytes)
        if bundle_key is not None:
            upload_local(bundle_key, bundle_bytes)  # type: ignore[arg-type]
    else:
        s3: Any = get_s3_client()
        upload_bytes(s3, cert_key, cert_bytes, "application/x-pem-file")
        upload_bytes(s3, key_key, key_bytes, "application/x-pem-file")
        if bundle_key is not None:
            upload_bytes(s3, bundle_key, bundle_bytes, "application/x-pem-file")  # type: ignore[arg-type]

    return cert_key, key_key, bundle_key
