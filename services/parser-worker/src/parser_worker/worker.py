"""SQS consumer for the parse-queue.

Polls the parse-queue, calls detect_and_parse on each uploaded source file,
uploads the ParsedFile JSON to S3, creates a GENERATE job, and sends it
to the generate-queue.

Usage:
    sv-parse-worker          # loops forever
    sv-parse-worker --once   # process one SQS batch then exit (useful in tests)

Required environment variables:
    DATABASE_URL
    SQS_PARSE_QUEUE_URL
    SQS_GENERATE_QUEUE_URL
    S3_BUCKET
    AWS_REGION
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── DB helpers (raw SQL — no ORM import needed at worker startup) ─────────────

def _make_db_session() -> Any:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    db_url = os.environ["DATABASE_URL"]
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    return Session()


def _update_job(db: Any, job_id: str, *, status: str, error: str | None = None, result: dict | None = None, sqs_generate_message_id: str | None = None) -> None:
    from sqlalchemy import text
    updates: dict[str, Any] = {
        "status": status,
        "error_message": error,
        "result": json.dumps(result) if result is not None else None,
    }
    if sqs_generate_message_id is not None:
        updates["sqs_message_id"] = sqs_generate_message_id
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    db.execute(text(f"UPDATE jobs SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {**updates, "id": job_id})
    db.commit()


def _create_generate_job(db: Any, stub_id: str, project_id: str, parsed_s3_key: str) -> str:
    """Insert a GENERATE job and return its ID."""
    from sqlalchemy import text
    new_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO jobs (id, type, status, project_id, stub_id, payload, created_at, updated_at) "
            "VALUES (:id, 'GENERATE', 'QUEUED', :project_id, :stub_id, :payload, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {
            "id": new_id,
            "project_id": project_id,
            "stub_id": stub_id,
            "payload": json.dumps({"parsed_s3_key": parsed_s3_key, "stub_id": stub_id, "project_id": project_id}),
        },
    )
    db.commit()
    return new_id


# ── Message processor ─────────────────────────────────────────────────────────

def process_message(
    message: dict,
    s3_client: Any,
    sqs_client: Any,
    s3_bucket: str,
    generate_queue_url: str,
    db: Any,
) -> None:
    """Process one SQS PARSE message end-to-end."""
    body = json.loads(message["Body"])
    job_id: str = body["job_id"]
    payload: dict = body.get("payload", {})
    source_s3_key: str = payload["source_s3_key"]
    filename: str = payload.get("filename", "source.txt")
    stub_id: str = payload.get("stub_id", "")
    project_id: str = payload.get("project_id", "")

    logger.info("Processing PARSE job %s (stub=%s)", job_id, stub_id)
    _update_job(db, job_id, status="RUNNING")

    # Download source file from S3
    obj = s3_client.get_object(Bucket=s3_bucket, Key=source_s3_key)
    content: bytes = obj["Body"].read()

    suffix = Path(filename).suffix or ".txt"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        from .detector import detect_and_parse
        _parser, vr, pf = detect_and_parse(tmp_path)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    if not vr.valid or pf is None:
        errors = "; ".join(str(e) for e in vr.errors)
        logger.warning("PARSE job %s failed: %s", job_id, errors)
        _update_job(db, job_id, status="FAILED", error=errors)
        return

    # Upload ParsedFile JSON to S3
    parsed_key = f"stubs/{project_id}/{stub_id}/parsed/result.json"
    s3_client.put_object(
        Bucket=s3_bucket,
        Key=parsed_key,
        Body=pf.model_dump_json(),
        ContentType="application/json",
    )
    logger.info("PARSE job %s uploaded parsed result to %s", job_id, parsed_key)

    # Create GENERATE job in DB + send to generate-queue
    gen_job_id = _create_generate_job(db, stub_id, project_id, parsed_key)
    gen_body = {
        "job_id": gen_job_id,
        "type": "GENERATE",
        "payload": {
            "parsed_s3_key": parsed_key,
            "stub_id": stub_id,
            "project_id": project_id,
            "parent_parse_job_id": job_id,
        },
        "created_at": _now_iso(),
        "project_id": project_id,
    }
    send_response = sqs_client.send_message(
        QueueUrl=generate_queue_url,
        MessageBody=json.dumps(gen_body),
    )
    gen_msg_id = send_response["MessageId"]

    _update_job(
        db, job_id,
        status="DONE",
        result={"parsed_s3_key": parsed_key, "format": vr.format_detected, "generate_job_id": gen_job_id},
        sqs_generate_message_id=gen_msg_id,
    )
    logger.info("PARSE job %s done — generate job %s queued", job_id, gen_job_id)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_loop(*, once: bool = False) -> None:
    """Poll the parse-queue and process messages indefinitely (or once if once=True)."""
    import boto3

    parse_queue_url = os.environ["SQS_PARSE_QUEUE_URL"]
    generate_queue_url = os.environ["SQS_GENERATE_QUEUE_URL"]
    s3_bucket = os.environ["S3_BUCKET"]
    aws_region = os.environ.get("AWS_REGION", "eu-west-2")

    sqs = boto3.client("sqs", region_name=aws_region)
    s3 = boto3.client("s3", region_name=aws_region)

    logger.info("sv-parse-worker started, polling %s", parse_queue_url)

    while True:
        response = sqs.receive_message(
            QueueUrl=parse_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
        )
        messages = response.get("Messages", [])
        db = _make_db_session()
        try:
            for message in messages:
                try:
                    process_message(message, s3, sqs, s3_bucket, generate_queue_url, db)
                    sqs.delete_message(QueueUrl=parse_queue_url, ReceiptHandle=message["ReceiptHandle"])
                except Exception:
                    logger.exception("Unhandled error processing message %s", message.get("MessageId"))
        finally:
            db.close()

        if once:
            break


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format='{"time":"%(asctime)s","level":"%(levelname)s","service":"parse-worker","message":"%(message)s"}')
    parser = argparse.ArgumentParser(description="Mockingbird parse-queue SQS consumer")
    parser.add_argument("--once", action="store_true", help="Process one batch then exit")
    args = parser.parse_args()
    run_loop(once=args.once)


if __name__ == "__main__":
    main()
