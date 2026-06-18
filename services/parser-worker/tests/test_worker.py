"""Phase 3 Sprint 11 — parser-worker SQS consumer tests.

Tests cover:
  - Valid Level-1 TXT file is parsed, result uploaded to S3, GENERATE job created
  - Invalid file sets job status to FAILED
  - DB job status transitions: QUEUED → RUNNING → DONE/FAILED
  - GENERATE job message is sent to generate-queue
"""
from __future__ import annotations

import json
import os
import uuid

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")

# ── Constants ─────────────────────────────────────────────────────────────────

REGION = "eu-west-2"
S3_BUCKET = "test-mockingbird-stubs"
# UUIDs start with hex letters to avoid SQLite NUMERIC affinity collapse
PROJECT_ID = str(uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001"))
STUB_ID = str(uuid.UUID("cccccccc-0000-0000-0000-000000000001"))

VALID_TXT = b"""--- MOCKINGBIRD v1.0 ---
Stub-Name: Payment API
Team: PaymentsTeam
Method: POST
URL: /payments/domestic

--- REQUEST ---
Content-Type: application/json

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"transactionId": "TXN-001", "status": "ACCEPTED"}
"""

INVALID_TXT = b"this is not a recognised format"

SOURCE_S3_KEY = f"stubs/{PROJECT_ID}/{STUB_ID}/source/payment.txt"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_db():
    """Create an in-memory SQLite DB with the jobs table."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    engine.execute = lambda *a, **k: engine.connect().execute(*a, **k)  # type: ignore[attr-defined]
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE jobs ("
            "id TEXT PRIMARY KEY, type TEXT, status TEXT, project_id TEXT, stub_id TEXT, "
            "payload TEXT, result TEXT, error_message TEXT, sqs_message_id TEXT, "
            "created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        conn.commit()
    Session = sessionmaker(bind=engine)
    return engine, Session


def _insert_job(db, job_id: str, project_id: str = PROJECT_ID, stub_id: str = STUB_ID) -> None:
    db.execute(
        text("INSERT INTO jobs (id, type, status, project_id, stub_id, payload) VALUES (:id, 'PARSE', 'QUEUED', :pid, :sid, '{}')"),
        {"id": job_id, "pid": project_id, "sid": stub_id},
    )
    db.commit()


def _get_job(db, job_id: str) -> dict:
    row = db.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).fetchone()
    return dict(row._mapping) if row else {}


def _build_sqs_message(job_id: str, s3_key: str = SOURCE_S3_KEY) -> dict:
    body = {
        "job_id": job_id,
        "type": "PARSE",
        "payload": {
            "source_s3_key": s3_key,
            "filename": "payment.txt",
            "stub_id": STUB_ID,
            "project_id": PROJECT_ID,
        },
        "created_at": "2026-06-18T12:00:00Z",
        "project_id": PROJECT_ID,
    }
    return {"MessageId": "msg-1", "ReceiptHandle": "rh-1", "Body": json.dumps(body)}


# ── Tests ─────────────────────────────────────────────────────────────────────

@mock_aws
def test_valid_file_parses_and_uploads_result():
    from parser_worker.worker import process_message

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=S3_BUCKET, Key=SOURCE_S3_KEY, Body=VALID_TXT)

    sqs = boto3.client("sqs", region_name=REGION)
    gen_queue_url = sqs.create_queue(QueueName="generate-queue")["QueueUrl"]

    engine, Session = _build_db()
    db = Session()
    job_id = str(uuid.uuid4())
    _insert_job(db, job_id)

    message = _build_sqs_message(job_id)
    process_message(message, s3, sqs, S3_BUCKET, gen_queue_url, db)

    job = _get_job(db, job_id)
    assert job["status"] == "DONE"
    assert job["error_message"] is None

    result = json.loads(job["result"])
    parsed_key = result["parsed_s3_key"]
    assert parsed_key == f"stubs/{PROJECT_ID}/{STUB_ID}/parsed/result.json"
    assert "generate_job_id" in result

    # Verify S3 has the parsed result
    parsed_obj = s3.get_object(Bucket=S3_BUCKET, Key=parsed_key)
    parsed_data = json.loads(parsed_obj["Body"].read())
    assert parsed_data["format"] == "level-1-txt"
    assert len(parsed_data["stubs"]) == 1

    db.close()


@mock_aws
def test_invalid_file_sets_job_to_failed():
    from parser_worker.worker import process_message

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=S3_BUCKET, Key=SOURCE_S3_KEY, Body=INVALID_TXT)

    sqs = boto3.client("sqs", region_name=REGION)
    gen_queue_url = sqs.create_queue(QueueName="generate-queue")["QueueUrl"]

    engine, Session = _build_db()
    db = Session()
    job_id = str(uuid.uuid4())
    _insert_job(db, job_id)

    message = _build_sqs_message(job_id)
    process_message(message, s3, sqs, S3_BUCKET, gen_queue_url, db)

    job = _get_job(db, job_id)
    assert job["status"] == "FAILED"
    assert job["error_message"] is not None
    assert len(job["error_message"]) > 0

    # No message sent to generate-queue
    msgs = sqs.receive_message(QueueUrl=gen_queue_url).get("Messages", [])
    assert len(msgs) == 0

    db.close()


@mock_aws
def test_valid_file_sends_generate_job_to_queue():
    from parser_worker.worker import process_message

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=S3_BUCKET, Key=SOURCE_S3_KEY, Body=VALID_TXT)

    sqs = boto3.client("sqs", region_name=REGION)
    gen_queue_url = sqs.create_queue(QueueName="generate-queue")["QueueUrl"]

    engine, Session = _build_db()
    db = Session()
    job_id = str(uuid.uuid4())
    _insert_job(db, job_id)

    process_message(_build_sqs_message(job_id), s3, sqs, S3_BUCKET, gen_queue_url, db)

    msgs = sqs.receive_message(QueueUrl=gen_queue_url, MaxNumberOfMessages=1).get("Messages", [])
    assert len(msgs) == 1
    body = json.loads(msgs[0]["Body"])
    assert body["type"] == "GENERATE"
    assert "parsed_s3_key" in body["payload"]
    assert body["payload"]["stub_id"] == STUB_ID
    assert body["payload"]["project_id"] == PROJECT_ID

    db.close()


@mock_aws
def test_generate_job_created_in_db_after_parse():
    from parser_worker.worker import process_message

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=S3_BUCKET, Key=SOURCE_S3_KEY, Body=VALID_TXT)

    sqs = boto3.client("sqs", region_name=REGION)
    gen_queue_url = sqs.create_queue(QueueName="generate-queue")["QueueUrl"]

    engine, Session = _build_db()
    db = Session()
    job_id = str(uuid.uuid4())
    _insert_job(db, job_id)

    process_message(_build_sqs_message(job_id), s3, sqs, S3_BUCKET, gen_queue_url, db)

    parse_job = _get_job(db, job_id)
    gen_job_id = json.loads(parse_job["result"])["generate_job_id"]
    gen_job = _get_job(db, gen_job_id)
    assert gen_job is not None
    assert gen_job["type"] == "GENERATE"
    assert gen_job["status"] == "QUEUED"
    assert gen_job["stub_id"] == STUB_ID

    db.close()
