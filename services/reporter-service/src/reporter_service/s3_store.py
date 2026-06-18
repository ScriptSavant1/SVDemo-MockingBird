"""Upload rendered report files to S3.

S3 key structure:
  reports/{project_id}/{stub_id}/{deployment_id}/{timestamp}/report.pdf
  reports/{project_id}/{stub_id}/{deployment_id}/{timestamp}/report.xlsx
  reports/{project_id}/{stub_id}/{deployment_id}/{timestamp}/report.pptx
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any


def _timestamp_prefix(deployment_id: str, dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    ts = dt.strftime("%Y%m%d_%H%M%S")
    return f"reports/{deployment_id}/{ts}"


def upload_pdf(client: Any, bucket: str, deployment_id: str, data: bytes, dt: datetime | None = None) -> str:
    key = f"{_timestamp_prefix(deployment_id, dt)}/report.pdf"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType="application/pdf",
        ContentDisposition=f'attachment; filename="report.pdf"',
    )
    return key


def upload_excel(client: Any, bucket: str, deployment_id: str, data: bytes, dt: datetime | None = None) -> str:
    key = f"{_timestamp_prefix(deployment_id, dt)}/report.xlsx"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ContentDisposition=f'attachment; filename="report.xlsx"',
    )
    return key


def upload_ppt(client: Any, bucket: str, deployment_id: str, data: bytes, dt: datetime | None = None) -> str:
    key = f"{_timestamp_prefix(deployment_id, dt)}/report.pptx"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ContentDisposition=f'attachment; filename="report.pptx"',
    )
    return key


def presigned_url(client: Any, bucket: str, key: str, expires: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )
