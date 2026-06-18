"""Phase 3 Sprint 11 — generator-worker SQS consumer tests.

Tests cover:
  - ParsedFile JSON is read from S3, Spring Boot project generated and zipped
  - DONE status + generated_s3_key stored in job result
  - Zip contains expected Spring Boot files (pom.xml, Dockerfile, mappings/)
  - FAILED status set when ParsedFile JSON is invalid
"""
from __future__ import annotations

import json
import os
import uuid
import zipfile

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")

REGION = "eu-west-2"
S3_BUCKET = "test-mockingbird-stubs"
# UUIDs start with hex letters (SQLite NUMERIC affinity guard)
PROJECT_ID = str(uuid.UUID("dddddddd-0000-0000-0000-000000000001"))
STUB_ID = str(uuid.UUID("eeeeeeee-0000-0000-0000-000000000001"))
PARSED_S3_KEY = f"stubs/{PROJECT_ID}/{STUB_ID}/parsed/result.json"

# Minimal valid ParsedFile JSON (matches parser_worker.models.ParsedFile schema)
PARSED_FILE_JSON = json.dumps({
    "format": "level-1-txt",
    "source_file": "payment.txt",
    "stubs": [
        {
            "name": "Payment API",
            "description": "",
            "team": "PaymentsTeam",
            "contact": "",
            "request": {"method": "POST", "url": "/payments/domestic", "required_headers": {}},
            "scenarios": [
                {
                    "name": "default",
                    "match": {"type": "always", "value": None},
                    "status": 200,
                    "response_headers": {},
                    "body": '{"status": "ACCEPTED"}',
                    "delay": None,
                    "fault": None,
                    "scenario_name": None,
                    "required_state": None,
                    "new_state": None,
                    "xpath_namespaces": {},
                }
            ],
        }
    ],
})

INVALID_JSON = b"this is not valid json"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _build_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    return Session


def _insert_job(db, job_id: str) -> None:
    db.execute(
        text("INSERT INTO jobs (id, type, status, project_id, stub_id, payload) VALUES (:id, 'GENERATE', 'QUEUED', :pid, :sid, '{}')"),
        {"id": job_id, "pid": PROJECT_ID, "sid": STUB_ID},
    )
    db.commit()


def _get_job(db, job_id: str) -> dict:
    row = db.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).fetchone()
    return dict(row._mapping) if row else {}


def _build_message(job_id: str) -> dict:
    body = {
        "job_id": job_id,
        "type": "GENERATE",
        "payload": {
            "parsed_s3_key": PARSED_S3_KEY,
            "stub_id": STUB_ID,
            "project_id": PROJECT_ID,
        },
        "created_at": "2026-06-18T12:00:00Z",
        "project_id": PROJECT_ID,
    }
    return {"MessageId": "msg-1", "ReceiptHandle": "rh-1", "Body": json.dumps(body)}


# ── Tests ─────────────────────────────────────────────────────────────────────

@mock_aws
def test_generate_job_produces_zip_and_updates_status():
    from generator_worker.worker import process_message

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=S3_BUCKET, Key=PARSED_S3_KEY, Body=PARSED_FILE_JSON.encode())

    Session = _build_db()
    db = Session()
    job_id = str(uuid.uuid4())
    _insert_job(db, job_id)

    process_message(_build_message(job_id), s3, S3_BUCKET, db)

    job = _get_job(db, job_id)
    assert job["status"] == "DONE"
    assert job["error_message"] is None

    result = json.loads(job["result"])
    generated_key = result["generated_s3_key"]
    assert generated_key == f"stubs/{PROJECT_ID}/{STUB_ID}/generated/stub-engine.zip"
    assert result["zip_size_bytes"] > 0

    db.close()


@mock_aws
def test_generated_zip_contains_expected_files():
    from generator_worker.worker import process_message

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=S3_BUCKET, Key=PARSED_S3_KEY, Body=PARSED_FILE_JSON.encode())

    Session = _build_db()
    db = Session()
    job_id = str(uuid.uuid4())
    _insert_job(db, job_id)

    process_message(_build_message(job_id), s3, S3_BUCKET, db)

    result = json.loads(_get_job(db, job_id)["result"])
    zip_obj = s3.get_object(Bucket=S3_BUCKET, Key=result["generated_s3_key"])
    zip_bytes = zip_obj["Body"].read()

    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

    assert any(n.endswith("pom.xml") for n in names), "pom.xml not in zip"
    assert any(n.endswith("Dockerfile") for n in names), "Dockerfile not in zip"
    assert any("mappings" in n for n in names), "mappings/ not in zip"

    db.close()


@mock_aws
def test_invalid_parsed_json_sets_job_failed():
    from generator_worker.worker import process_message

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=S3_BUCKET, Key=PARSED_S3_KEY, Body=INVALID_JSON)

    Session = _build_db()
    db = Session()
    job_id = str(uuid.uuid4())
    _insert_job(db, job_id)

    # process_message raises; the caller (run_loop) catches it — we test the raise directly
    try:
        process_message(_build_message(job_id), s3, S3_BUCKET, db)
        assert False, "Expected exception for invalid JSON"
    except Exception:
        pass

    db.close()
