"""Thin wrapper around boto3 SQS for sending job messages.

SQS message contract (CLAUDE.md):
  { "job_id": str, "type": str, "payload": dict, "created_at": ISO-8601, "project_id": str }
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from .config import settings


def get_sqs_client() -> Any:
    return boto3.client("sqs", region_name=settings.aws_region)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_deploy_job(
    client: Any,
    job_id: uuid.UUID,
    stub_id: uuid.UUID,
    project_id: uuid.UUID,
    deployment_id: uuid.UUID,
    generated_s3_key: str,
    target_type: str = "AWS",
) -> str:
    """Send a DEPLOY job message to the deploy queue. Returns the SQS MessageId."""
    body = {
        "job_id": str(job_id),
        "type": "DEPLOY",
        "payload": {
            "generated_s3_key": generated_s3_key,
            "stub_id": str(stub_id),
            "project_id": str(project_id),
            "deployment_id": str(deployment_id),
            "target_type": target_type,
        },
        "created_at": _now_iso(),
        "project_id": str(project_id),
    }
    response = client.send_message(
        QueueUrl=settings.sqs_deploy_queue_url,
        MessageBody=json.dumps(body),
    )
    return response["MessageId"]


def enqueue_report_job(
    client: Any,
    job_id: uuid.UUID,
    deployment_id: uuid.UUID,
    project_id: uuid.UUID,
    report_period_hours: int = 24,
) -> str:
    """Send a REPORT job message to the report queue. Returns the SQS MessageId."""
    body = {
        "job_id": str(job_id),
        "type": "REPORT",
        "payload": {
            "deployment_id": str(deployment_id),
            "report_period_hours": report_period_hours,
        },
        "created_at": _now_iso(),
        "project_id": str(project_id),
    }
    response = client.send_message(
        QueueUrl=settings.sqs_report_queue_url,
        MessageBody=json.dumps(body),
    )
    return response["MessageId"]


def enqueue_parse_job(
    client: Any,
    job_id: uuid.UUID,
    stub_id: uuid.UUID,
    project_id: uuid.UUID,
    source_s3_key: str,
    filename: str,
) -> str:
    """Send a PARSE job message to the parse queue. Returns the SQS MessageId."""
    body = {
        "job_id": str(job_id),
        "type": "PARSE",
        "payload": {
            "source_s3_key": source_s3_key,
            "filename": filename,
            "stub_id": str(stub_id),
            "project_id": str(project_id),
        },
        "created_at": _now_iso(),
        "project_id": str(project_id),
    }
    response = client.send_message(
        QueueUrl=settings.sqs_parse_queue_url,
        MessageBody=json.dumps(body),
    )
    return response["MessageId"]
