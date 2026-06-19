from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3

from .config import settings


# ── Local file storage (no S3) ──────────────────────────────────────────────

def is_local_storage() -> bool:
    return bool(settings.local_storage_path)


def upload_local(s3_key: str, data: bytes) -> str:
    """Write bytes to LOCAL_STORAGE_PATH/<s3_key>. Used when S3 is unavailable."""
    dest = Path(settings.local_storage_path or "./uploads") / s3_key  # type: ignore[arg-type]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return s3_key


def local_file_url(s3_key: str) -> str:
    """Return a file:// URL so the frontend can show a path (local dev only)."""
    dest = Path(settings.local_storage_path or "./uploads") / s3_key  # type: ignore[arg-type]
    return dest.as_uri()


# ── S3 storage ───────────────────────────────────────────────────────────────

def get_s3_client() -> Any:
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client("s3", **kwargs)


def upload_bytes(client: Any, s3_key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=data,
        ContentType=content_type,
    )
    return s3_key


def generate_presigned_url(client: Any, s3_key: str, expires_in: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )
