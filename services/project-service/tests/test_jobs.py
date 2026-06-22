"""Phase 3 Sprint 11 — job trigger and status polling tests.

12 tests covering:
  - POST /generate creates a QUEUED PARSE job
  - 400 when stub has no source file
  - 404 for unknown project / stub in wrong project
  - 403 for VIEWER role
  - GET /jobs/{id} returns job state
  - 404 for unknown job
  - SQS message sent when queue URL is configured
"""
from __future__ import annotations

import json
import os
import uuid

import boto3
import pytest
from moto import mock_aws
from sqlalchemy.orm import Session

import project_service.config as _cfg
from project_service.models import Job, Project, Stub

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def project_with_stub(db_session: Session, sv_user):
    project = Project(name="Payments API", team="PaymentsTeam", created_by=sv_user.id)
    db_session.add(project)
    db_session.flush()
    stub = Stub(
        project_id=project.id,
        name="Domestic Payment",
        format="level-1-txt",
        source_file_key=f"stubs/{project.id}/{uuid.uuid4()}/source/domestic.txt",
        wiremock_mapping_count=1,
    )
    db_session.add(stub)
    db_session.commit()
    db_session.refresh(stub)
    db_session.refresh(project)
    return project, stub


@pytest.fixture()
def project_no_stub_file(db_session: Session, sv_user):
    project = Project(name="Empty Project", team="T", created_by=sv_user.id)
    db_session.add(project)
    db_session.flush()
    stub = Stub(
        project_id=project.id,
        name="Stub Without File",
        format="level-1-txt",
        wiremock_mapping_count=0,
    )
    db_session.add(stub)
    db_session.commit()
    db_session.refresh(stub)
    db_session.refresh(project)
    return project, stub


# ── Trigger endpoint ──────────────────────────────────────────────────────────

def test_trigger_generate_returns_202_and_job_id(sv_client, project_with_stub):
    project, stub = project_with_stub
    resp = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    assert resp.status_code == 202
    body = resp.json()
    # No SQS in test env → local-dev path completes inline → status is DONE
    assert body["status"] in ("QUEUED", "DONE")
    assert body["type"] == "PARSE"
    assert uuid.UUID(body["job_id"])  # valid UUID


def test_trigger_generate_records_job_in_db(sv_client, db_session, project_with_stub):
    project, stub = project_with_stub
    resp = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    assert resp.status_code == 202
    job_id = uuid.UUID(resp.json()["job_id"])

    job = db_session.get(Job, job_id)
    assert job is not None
    assert job.type == "PARSE"
    assert job.status in ("QUEUED", "DONE")  # DONE when no SQS (local dev inline path)
    assert job.stub_id == stub.id
    assert job.project_id == project.id
    assert job.payload["source_s3_key"] == stub.source_file_key
    assert job.payload["filename"] == "domestic.txt"


def test_trigger_generate_stub_without_source_file_returns_400(sv_client, project_no_stub_file):
    project, stub = project_no_stub_file
    resp = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    assert resp.status_code == 400


def test_trigger_generate_unknown_project_returns_404(sv_client):
    resp = sv_client.post(f"/api/v1/projects/{uuid.uuid4()}/stubs/{uuid.uuid4()}/generate")
    assert resp.status_code == 404


def test_trigger_generate_stub_wrong_project_returns_404(sv_client, db_session, sv_user):
    p1 = Project(name="P1", team="T", created_by=sv_user.id)
    p2 = Project(name="P2", team="T", created_by=sv_user.id)
    db_session.add(p1)
    db_session.add(p2)
    db_session.flush()
    stub = Stub(project_id=p1.id, name="S", format="level-1-txt", source_file_key="k/f.txt", wiremock_mapping_count=0)
    db_session.add(stub)
    db_session.commit()

    resp = sv_client.post(f"/api/v1/projects/{p2.id}/stubs/{stub.id}/generate")
    assert resp.status_code == 404


def test_trigger_generate_viewer_role_returns_403(viewer_client, project_with_stub):
    project, stub = project_with_stub
    resp = viewer_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    assert resp.status_code == 403


def test_trigger_generate_sends_sqs_message_when_queue_configured(sv_client, project_with_stub):
    project, stub = project_with_stub
    original_url = _cfg.settings.sqs_parse_queue_url

    with mock_aws():
        sqs = boto3.client("sqs", region_name="eu-west-2")
        queue_url = sqs.create_queue(QueueName="parse-queue")["QueueUrl"]
        _cfg.settings.sqs_parse_queue_url = queue_url

        try:
            resp = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
            assert resp.status_code == 202
            job_id = resp.json()["job_id"]

            msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1).get("Messages", [])
            assert len(msgs) == 1
            body = json.loads(msgs[0]["Body"])
            assert body["job_id"] == job_id
            assert body["type"] == "PARSE"
            assert body["payload"]["source_s3_key"] == stub.source_file_key
            assert body["project_id"] == str(project.id)
        finally:
            _cfg.settings.sqs_parse_queue_url = original_url


# ── Status polling ────────────────────────────────────────────────────────────

def test_get_job_returns_queued_state(sv_client, project_with_stub):
    project, stub = project_with_stub
    trigger = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    job_id = trigger.json()["job_id"]

    resp = sv_client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("QUEUED", "DONE")  # DONE when no SQS
    assert body["type"] == "PARSE"
    assert body["project_id"] == str(project.id)
    assert body["stub_id"] == str(stub.id)


def test_get_job_viewer_can_read(viewer_client, sv_client, project_with_stub):
    project, stub = project_with_stub
    trigger = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    job_id = trigger.json()["job_id"]

    resp = viewer_client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200


def test_get_job_unknown_returns_404(sv_client):
    resp = sv_client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_multiple_generate_calls_create_separate_jobs(sv_client, project_with_stub):
    project, stub = project_with_stub
    r1 = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    r2 = sv_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/generate")
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["job_id"] != r2.json()["job_id"]


def test_get_job_requires_auth(db_engine):
    """A client with no auth override gets 401."""
    from fastapi.testclient import TestClient
    from project_service.main import create_app
    from project_service.database import get_db
    from sqlalchemy.orm import sessionmaker

    app = create_app()
    TestSession = sessionmaker(bind=db_engine)

    def override_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 401
