"""Reporter-worker SQS consumer (Phase 5 Sprint 15).

Reads REPORT messages from the report-queue and:
  1. Loads deployment + project metadata from PostgreSQL
  2. Queries Timestream for time-series metrics
  3. Renders PDF (WeasyPrint), Excel (openpyxl), PowerPoint (python-pptx)
  4. Uploads all three files to S3
  5. Updates Job record with S3 keys (status DONE or FAILED)

SQS message payload:
  {
    "job_id": str,
    "type": "REPORT",
    "payload": {
      "deployment_id": str,
      "report_period_hours": int   (default 24)
    },
    "created_at": ISO-8601,
    "project_id": str
  }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .config import settings
from .data_loader import build_report_data
from .models import ReportPaths
from .renderers.excel import render_excel
from .renderers.pdf import render_html  # render_pdf imports WeasyPrint lazily
from .renderers.ppt import render_ppt
from .s3_store import upload_excel, upload_pdf, upload_ppt

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_job(db: Session, job_id: str, *, status: str, error: str | None = None, result: dict | None = None) -> None:
    db.execute(
        text("UPDATE jobs SET status=:s, error_message=:e, result=:r, updated_at=:u WHERE id=:id"),
        {"s": status, "e": error, "r": json.dumps(result) if result else None, "u": _now_iso(), "id": job_id},
    )
    db.commit()


def process_message(
    message: dict,
    db: Session,
    ts_query_client: Any,
    s3_client: Any,
) -> None:
    body = json.loads(message["Body"])
    job_id: str = body["job_id"]
    payload: dict = body["payload"]
    deployment_id: str = payload["deployment_id"]
    hours: int = int(payload.get("report_period_hours", 24))

    _update_job(db, job_id, status="RUNNING")

    # ── Step 1: Assemble report data ──────────────────────────────────────────
    try:
        report_data = build_report_data(
            db, ts_query_client,
            settings.timestream_database,
            settings.timestream_table,
            deployment_id,
            hours=hours,
        )
    except Exception as exc:
        err = f"Failed to load report data: {exc}"
        logger.error(err)
        _update_job(db, job_id, status="FAILED", error=err)
        return

    primary = settings.brand_primary_colour
    secondary = settings.brand_secondary_colour
    company = settings.brand_company_name
    dt = report_data.generated_at

    # ── Step 2: Render all three formats ─────────────────────────────────────
    report_paths = ReportPaths()

    # PDF — WeasyPrint; in local/test mode without WeasyPrint, skip gracefully
    try:
        from .renderers.pdf import render_pdf
        pdf_bytes = render_pdf(report_data, primary, secondary, company)
        report_paths.pdf_key = upload_pdf(s3_client, settings.s3_bucket, deployment_id, pdf_bytes, dt)
    except ImportError:
        logger.warning("WeasyPrint not available — skipping PDF")
    except Exception as exc:
        logger.error("PDF render/upload failed for %s: %s", deployment_id, exc)

    # Excel
    try:
        xlsx_bytes = render_excel(report_data, primary, secondary, company)
        report_paths.excel_key = upload_excel(s3_client, settings.s3_bucket, deployment_id, xlsx_bytes, dt)
    except Exception as exc:
        logger.error("Excel render/upload failed for %s: %s", deployment_id, exc)

    # PowerPoint
    try:
        ppt_bytes = render_ppt(report_data, primary, secondary, company)
        report_paths.ppt_key = upload_ppt(s3_client, settings.s3_bucket, deployment_id, ppt_bytes, dt)
    except Exception as exc:
        logger.error("PPT render/upload failed for %s: %s", deployment_id, exc)

    result = report_paths.model_dump()
    _update_job(db, job_id, status="DONE", result=result)
    logger.info("Report job %s done for deployment %s — %s", job_id, deployment_id, result)


def run_loop(
    sqs_client: Any,
    db_factory: Any,
    ts_query_client: Any,
    s3_client: Any,
    queue_url: str,
    poll_wait: int = 20,
) -> None:
    logger.info("reporter-worker started, polling %s", queue_url)
    while True:
        resp = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=poll_wait,
        )
        for message in resp.get("Messages", []):
            db = db_factory()
            try:
                process_message(message, db, ts_query_client, s3_client)
            except Exception as exc:
                logger.exception("Unhandled error processing message %s: %s", message.get("MessageId"), exc)
            finally:
                db.close()
                sqs_client.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
