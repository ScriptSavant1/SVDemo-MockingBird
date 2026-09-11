"""TLS server certificate + private key (and optional CA bundle) upload,
validation, and S3 storage — for updating an EXISTING stub's cert after
creation (swapping an expiring cert, turning HTTPS on for a stub that
predates this feature, etc).

A stub's initial protocol/cert choice happens at upload time instead — see
routers/upload.py's /stubs/upload, which accepts the same cert fields
inline so the stub doesn't need to exist yet before a cert can be attached
to it.

POST /api/v1/projects/{project_id}/stubs/{stub_id}/tls-cert
  — accepts multipart/form-data: server_cert, server_key, optional ca_bundle
  — validates with the `cryptography` library (see ../tls_cert.py)
  — on success: uploads to S3/local storage AND updates the stub's TLS
    columns directly (this service already owns Stub row writes), returns
    200 + TlsCertUploadResult
  — on any validation failure: returns 422 with a specific detail string
    naming exactly which check failed; nothing is partially stored
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import CurrentUser, require_sv_team_or_admin
from ..models import Stub
from ..schemas import TlsCertUploadResult
from ..tls_cert import (
    TlsCertValidationError,
    read_limited,
    store_tls_files,
    validate_ca_bundle,
    validate_cert_key_pair,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/api/v1/projects/{project_id}/stubs/{stub_id}/tls-cert",
    response_model=TlsCertUploadResult,
    status_code=status.HTTP_200_OK,
    summary="Upload and validate a TLS server certificate + private key (optionally with a CA bundle for mTLS) for an existing stub",
)
def upload_stub_tls_cert(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    server_cert: UploadFile = File(..., description="PEM-encoded X.509 server certificate"),
    server_key: UploadFile = File(..., description="PEM-encoded, unencrypted private key matching server_cert"),
    ca_bundle: UploadFile | None = File(
        None, description="Optional PEM CA bundle (one or more concatenated certs) for mutual-TLS verification"
    ),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_sv_team_or_admin),
) -> TlsCertUploadResult:
    stub = db.query(Stub).filter(Stub.id == stub_id, Stub.project_id == project_id).first()
    if stub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stub {stub_id} not found in project {project_id}",
        )

    cert_bytes = read_limited(server_cert, "server_cert")
    key_bytes = read_limited(server_key, "server_key")
    bundle_bytes = read_limited(ca_bundle, "ca_bundle") if ca_bundle is not None else None

    try:
        _cert, warnings = validate_cert_key_pair(cert_bytes, key_bytes)
        if bundle_bytes is not None:
            validate_ca_bundle(bundle_bytes)
    except TlsCertValidationError as exc:
        logger.info("TLS cert upload rejected for stub %s: %s", stub_id, exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    cert_key, key_key, bundle_key = store_tls_files(
        f"stubs/{project_id}/{stub_id}/tls", cert_bytes, key_bytes, bundle_bytes,
    )

    stub.tls_cert_source = "UPLOADED"
    stub.tls_cert_s3_key = cert_key
    stub.tls_key_s3_key = key_key
    if bundle_key is not None:
        stub.tls_ca_bundle_s3_key = bundle_key
    db.commit()

    logger.info(
        "TLS cert stored for stub %s (server_cert=%d bytes, server_key=%d bytes, ca_bundle=%s)",
        stub_id, len(cert_bytes), len(key_bytes),
        f"{len(bundle_bytes)} bytes" if bundle_bytes is not None else "not provided",
    )

    return TlsCertUploadResult(
        tls_cert_s3_key=cert_key,
        tls_key_s3_key=key_key,
        tls_ca_bundle_s3_key=bundle_key,
        warnings=warnings,
    )
