"""SQS consumer for the generate-queue.

Polls the generate-queue, downloads the ParsedFile JSON from S3 (produced by
the parser-worker), runs the Spring Boot project generator, zips the output,
and uploads the zip to S3.

Usage:
    sv-generate-worker          # loops forever
    sv-generate-worker --once   # process one batch then exit

Required environment variables:
    DATABASE_URL
    SQS_GENERATE_QUEUE_URL
    S3_BUCKET
    AWS_REGION
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from typing import Any

logger = logging.getLogger(__name__)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _make_db_session() -> Any:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(os.environ["DATABASE_URL"])
    return sessionmaker(bind=engine)()


def _update_job(db: Any, job_id: str, *, status: str, error: str | None = None, result: dict | None = None) -> None:
    from sqlalchemy import text
    updates = {
        "status": status,
        "error_message": error,
        "result": json.dumps(result) if result is not None else None,
    }
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    db.execute(text(f"UPDATE jobs SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {**updates, "id": job_id})
    db.commit()


# ── Message processor ─────────────────────────────────────────────────────────

def process_message(
    message: dict,
    s3_client: Any,
    s3_bucket: str,
    db: Any,
) -> None:
    """Process one SQS GENERATE message end-to-end."""
    body = json.loads(message["Body"])
    job_id: str = body["job_id"]
    payload: dict = body.get("payload", {})
    parsed_s3_key: str = payload["parsed_s3_key"]
    stub_id: str = payload.get("stub_id", "")
    project_id: str = payload.get("project_id", "")

    logger.info("Processing GENERATE job %s (stub=%s)", job_id, stub_id)
    _update_job(db, job_id, status="RUNNING")

    # Download ParsedFile JSON from S3
    obj = s3_client.get_object(Bucket=s3_bucket, Key=parsed_s3_key)
    parsed_json = obj["Body"].read()

    from parser_worker.models import ParsedFile
    parsed = ParsedFile.model_validate_json(parsed_json)

    # Generate the Spring Boot project into a temp directory
    out_dir = tempfile.mkdtemp(prefix="mockingbird-gen-")
    zip_bytes: bytes
    try:
        from parser_worker.generator.springboot import generate_springboot_project
        generate_springboot_project(parsed, output_dir=__import__("pathlib").Path(out_dir))

        # Zip the generated project
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in __import__("pathlib").Path(out_dir).rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(out_dir))
        zip_bytes = buf.getvalue()
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)

    # Upload zip to S3
    generated_key = f"stubs/{project_id}/{stub_id}/generated/stub-engine.zip"
    s3_client.put_object(
        Bucket=s3_bucket,
        Key=generated_key,
        Body=zip_bytes,
        ContentType="application/zip",
    )
    logger.info("GENERATE job %s uploaded %d bytes to %s", job_id, len(zip_bytes), generated_key)

    _update_job(
        db, job_id,
        status="DONE",
        result={"generated_s3_key": generated_key, "zip_size_bytes": len(zip_bytes)},
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_loop(*, once: bool = False) -> None:
    import boto3

    generate_queue_url = os.environ["SQS_GENERATE_QUEUE_URL"]
    s3_bucket = os.environ["S3_BUCKET"]
    aws_region = os.environ.get("AWS_REGION", "eu-west-2")

    sqs = boto3.client("sqs", region_name=aws_region)
    s3 = boto3.client("s3", region_name=aws_region)

    logger.info("sv-generate-worker started, polling %s", generate_queue_url)

    while True:
        response = sqs.receive_message(
            QueueUrl=generate_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
        )
        messages = response.get("Messages", [])
        db = _make_db_session()
        try:
            for message in messages:
                try:
                    process_message(message, s3, s3_bucket, db)
                    sqs.delete_message(QueueUrl=generate_queue_url, ReceiptHandle=message["ReceiptHandle"])
                except Exception:
                    logger.exception("Unhandled error processing message %s", message.get("MessageId"))
        finally:
            db.close()

        if once:
            break


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format='{"time":"%(asctime)s","level":"%(levelname)s","service":"generate-worker","message":"%(message)s"}')
    parser = argparse.ArgumentParser(description="Mockingbird generate-queue SQS consumer")
    parser.add_argument("--once", action="store_true", help="Process one batch then exit")
    args = parser.parse_args()
    run_loop(once=args.once)


if __name__ == "__main__":
    main()
