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
import uuid
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
from . import error_codes as ec
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


def _ref() -> str:
    return uuid.uuid4().hex[:8]


def _mark_failed_after_crash(db: Session, message: dict) -> None:
    """An exception escaped process_message: log it under a ref and mark the
    job FAILED so the portal doesn't show the report as in progress forever."""
    ref = _ref()
    logger.exception("[ref %s] Unhandled error processing message %s", ref, message.get("MessageId"))
    try:
        job_id = json.loads(message["Body"])["job_id"]
        db.rollback()
        _update_job(db, job_id, status="FAILED", error=ec.job_error(
            ec.RPT_WORKER_FAILED, "Report generation failed unexpectedly â€” the details are in the server log", ref,
        ))
    except Exception:
        logger.exception("[ref %s] Could not mark the job FAILED", ref)


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

    # â”€â”€ Step 1: Assemble report data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        report_data = build_report_data(
            db, ts_query_client,
            settings.timestream_database,
            settings.timestream_table,
            deployment_id,
            hours=hours,
        )
    except Exception as exc:
        ref = _ref()
        logger.error("[ref %s] Failed to load report data for %s: %r", ref, deployment_id, exc)
        _update_job(db, job_id, status="FAILED", error=ec.job_error(
            ec.RPT_DATA_LOAD_FAILED, "The metrics for this report could not be loaded", ref,
        ))
        return

    primary = settings.brand_primary_colour
    secondary = settings.brand_secondary_colour
    company = settings.brand_company_name
    dt = report_data.generated_at

    # â”€â”€ Step 2: Render all three formats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    report_paths = ReportPaths()
    warnings: list[str] = []

    def _format_failed(label: str, exc: Exception) -> None:
        ref = _ref()
        logger.error("[ref %s] %s render/upload failed for %s: %r", ref, label, deployment_id, exc)
        warnings.append(ec.job_error(ec.RPT_FORMAT_FAILED, f"The {label} report could not be produced", ref))

    # PDF â€” WeasyPrint; in local/test mode without WeasyPrint, skip gracefully
    try:
        from .renderers.pdf import render_pdf
        pdf_bytes = render_pdf(report_data, primary, secondary, company)
        report_paths.pdf_key = upload_pdf(s3_client, settings.s3_bucket, deployment_id, pdf_bytes, dt)
    except ImportError:
        logger.warning("WeasyPrint not available â€” skipping PDF")
        warnings.append(ec.job_error(ec.RPT_FORMAT_FAILED, "PDF reports are not available on this server (WeasyPrint not installed)"))
    except Exception as exc:
        _format_failed("PDF", exc)

    # Excel
    try:
        xlsx_bytes = render_excel(report_data, primary, secondary, company)
        report_paths.excel_key = upload_excel(s3_client, settings.s3_bucket, deployment_id, xlsx_bytes, dt)
    except Exception as exc:
        _format_failed("Excel", exc)

    # PowerPoint
    try:
        ppt_bytes = render_ppt(report_data, primary, secondary, company)
        report_paths.ppt_key = upload_ppt(s3_client, settings.s3_bucket, deployment_id, ppt_bytes, dt)
    except Exception as exc:
        _format_failed("PowerPoint", exc)

    result = report_paths.model_dump()
    if not any(result.values()):
        # Nothing to download â€” reporting DONE here used to look like success.
        _update_job(db, job_id, status="FAILED", error=ec.job_error(
            ec.RPT_NO_FORMAT_PRODUCED, "No report could be produced in any format â€” see the server log",
        ), result={"warnings": warnings})
        return
    if warnings:
        result["warnings"] = warnings
    _update_job(db, job_id, status="DONE", result=result)
    logger.info("Report job %s done for deployment %s â€” %s", job_id, deployment_id, result)


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
                # Only delete on success â€” an unhandled exception leaves the
                # message in the queue so it's redelivered (and eventually
                # DLQ'd) instead of being silently discarded as "handled."
                sqs_client.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
            except Exception:
                _mark_failed_after_crash(db, message)
            finally:
                db.close()
