from __future__ import annotations

from pydantic import BaseModel


class IngestionResult(BaseModel):
    """Returned by the upload endpoint regardless of whether the file was valid."""

    valid: bool
    format_detected: str | None = None
    summary: str = ""
    stub_count: int = 0
    scenario_count: int = 0
    warnings: list[str] = []
    errors: list[str] = []
    # Set only when valid=True — the stub record created and its S3 key
    s3_key: str | None = None
    stub_id: str | None = None


class DownloadUrlResponse(BaseModel):
    stub_id: str
    filename: str
    presigned_url: str
    expires_in_seconds: int = 3600


class TlsCertUploadResult(BaseModel):
    """Returned by the TLS cert upload endpoint on success (422 is raised, not returned, on failure)."""

    tls_cert_s3_key: str
    tls_key_s3_key: str
    tls_ca_bundle_s3_key: str | None = None
    warnings: list[str] = []
