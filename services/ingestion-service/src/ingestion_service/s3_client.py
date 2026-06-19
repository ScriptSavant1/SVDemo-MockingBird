from __future__ import annotations

from typing import Any

import boto3

from .config import settings


def get_s3_client() -> Any:
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client("s3", **kwargs)


def upload_bytes(client: Any, s3_key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to S3 and return the key."""
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
