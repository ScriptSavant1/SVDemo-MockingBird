"""Phase 4 Sprint 13 — deploy endpoint tests.

Tests cover:
  - Trigger deploy → 202, deployment + job created in DB
  - Trigger deploy → SQS message sent (moto mock)
  - Deploy blocked when stub not yet generated
  - Deploy blocked when already in-flight
  - List deployments for a project
  - Get single deployment
  - Suspend live deployment → 202
  - Suspend non-LIVE deployment → 409
  - Redeploy suspended deployment → 202
  - Viewer cannot trigger deploy (403)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from moto import mock_aws
import boto3
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from project_service.models import Deployment, Job, Project, Stub, User

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")

SQS_DEPLOY_QUEUE_URL = ""  # overridden in moto tests


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def project_with_generated_stub(db_session: Session, admin_user: User) -> tuple[Project, Stub]:
    project = Project(
        name="Deploy Test Project",
        team="PaymentsTeam",
        expected_tps=5000,
        created_by=admin_user.id,
    )
    db_session.add(project)
    db_session.flush()

    stub = Stub(
        project_id=project.id,
        name="Payment API Stub",
        format="level-1-txt",
        source_file_key=f"stubs/{project.id}/s1/source/payment.txt",
        generated_at=datetime.now(timezone.utc),  # marks generation complete
    )
    db_session.add(stub)
    db_session.commit()
    db_session.refresh(project)
    db_session.refresh(stub)
    return project, stub


@pytest.fixture
def project_with_ungenerated_stub(db_session: Session, admin_user: User) -> tuple[Project, Stub]:
    project = Project(
        name="Not-Generated Project",
        team="ATeam",
        expected_tps=1000,
        created_by=admin_user.id,
    )
    db_session.add(project)
    db_session.flush()

    stub = Stub(
        project_id=project.id,
        name="Ungenerated Stub",
        format="level-1-txt",
        source_file_key=f"stubs/{project.id}/s2/source/file.txt",
        generated_at=None,  # not generated yet
    )
    db_session.add(stub)
    db_session.commit()
    db_session.refresh(project)
    db_session.refresh(stub)
    return project, stub


# ── POST .../deploy ───────────────────────────────────────────────────────────

def test_trigger_deploy_returns_202(admin_client: TestClient, project_with_generated_stub, db_session: Session):
    project, stub = project_with_generated_stub
    resp = admin_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    assert resp.status_code == 202
    body = resp.json()
    assert "deployment_id" in body
    assert "job_id" in body
    assert body["status"] == "PENDING"


def test_trigger_deploy_creates_deployment_and_job(admin_client: TestClient, project_with_generated_stub, db_session: Session):
    project, stub = project_with_generated_stub
    resp = admin_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    body = resp.json()

    deployment = db_session.get(Deployment, uuid.UUID(body["deployment_id"]))
    assert deployment is not None
    assert deployment.status == "PENDING"
    assert deployment.ec2_instance_type == "c6i.2xlarge"  # 5000 TPS → 2xlarge
    assert deployment.api_key is not None
    assert len(deployment.api_key) > 20

    job = db_session.get(Job, uuid.UUID(body["job_id"]))
    assert job is not None
    assert job.type == "DEPLOY"
    assert job.status == "QUEUED"


def test_trigger_deploy_selects_xlarge_for_low_tps(db_engine, admin_user: User, db_session: Session):
    from tests.conftest import _make_client
    from project_service.dependencies import CurrentUser

    project = Project(name="Low-TPS", team="T", expected_tps=2000, created_by=admin_user.id)
    db_session.add(project)
    db_session.flush()
    stub = Stub(project_id=project.id, name="S", format="level-1-txt",
                source_file_key="stubs/x/y/source/f.txt", generated_at=datetime.now(timezone.utc))
    db_session.add(stub)
    db_session.commit()
    db_session.refresh(project)
    db_session.refresh(stub)

    client = _make_client(db_engine, CurrentUser(id=admin_user.id, username="admin", role="ADMIN"))
    resp = client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    assert resp.status_code == 202

    deployment = db_session.get(Deployment, uuid.UUID(resp.json()["deployment_id"]))
    assert deployment is not None
    assert deployment.ec2_instance_type == "c6i.xlarge"


def test_trigger_deploy_blocked_when_not_generated(admin_client: TestClient, project_with_ungenerated_stub):
    project, stub = project_with_ungenerated_stub
    resp = admin_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    assert resp.status_code == 400


def test_trigger_deploy_blocked_when_inflight(admin_client: TestClient, project_with_generated_stub, db_session: Session):
    project, stub = project_with_generated_stub
    # First deploy
    admin_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    # Second deploy while first is PENDING
    resp = admin_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    assert resp.status_code == 409


def test_trigger_deploy_returns_404_unknown_project(admin_client: TestClient):
    resp = admin_client.post(f"/api/v1/projects/{uuid.uuid4()}/stubs/{uuid.uuid4()}/deploy")
    assert resp.status_code == 404


def test_viewer_cannot_trigger_deploy(viewer_client: TestClient, project_with_generated_stub):
    project, stub = project_with_generated_stub
    resp = viewer_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    assert resp.status_code == 403


# ── GET .../deployments ───────────────────────────────────────────────────────

def test_list_deployments_empty(admin_client: TestClient, project_with_generated_stub):
    project, _ = project_with_generated_stub
    resp = admin_client.get(f"/api/v1/projects/{project.id}/deployments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_deployments_returns_created(admin_client: TestClient, project_with_generated_stub):
    project, stub = project_with_generated_stub
    admin_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")

    resp = admin_client.get(f"/api/v1/projects/{project.id}/deployments")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "PENDING"


# ── GET /deployments/{id} ─────────────────────────────────────────────────────

def test_get_deployment_returns_200(admin_client: TestClient, project_with_generated_stub):
    project, stub = project_with_generated_stub
    deploy_resp = admin_client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    deployment_id = deploy_resp.json()["deployment_id"]

    resp = admin_client.get(f"/api/v1/deployments/{deployment_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == deployment_id


def test_get_deployment_404_unknown(admin_client: TestClient):
    resp = admin_client.get(f"/api/v1/deployments/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── POST .../suspend ──────────────────────────────────────────────────────────

def _make_live_deployment(db_session: Session, project: Project, stub: Stub) -> Deployment:
    deployment = Deployment(
        project_id=project.id,
        stub_id=stub.id,
        status="LIVE",
        ec2_instance_type="c6i.2xlarge",
        api_key="test-api-key",
        terraform_state_key=f"stubs/{project.id}/{stub.id}/terraform.tfstate",
        stub_url="http://10.0.0.1:8080",
    )
    db_session.add(deployment)
    db_session.commit()
    db_session.refresh(deployment)
    return deployment


def test_suspend_live_deployment(admin_client: TestClient, project_with_generated_stub, db_session: Session):
    project, stub = project_with_generated_stub
    deployment = _make_live_deployment(db_session, project, stub)

    resp = admin_client.post(f"/api/v1/projects/{project.id}/deployments/{deployment.id}/suspend")
    assert resp.status_code == 202
    assert resp.json()["status"] == "SUSPENDED"

    db_session.refresh(deployment)
    assert deployment.status == "SUSPENDED"


def test_suspend_non_live_returns_409(admin_client: TestClient, project_with_generated_stub, db_session: Session):
    project, stub = project_with_generated_stub
    deployment = Deployment(project_id=project.id, stub_id=stub.id, status="PENDING")
    db_session.add(deployment)
    db_session.commit()
    db_session.refresh(deployment)

    resp = admin_client.post(f"/api/v1/projects/{project.id}/deployments/{deployment.id}/suspend")
    assert resp.status_code == 409


# ── POST .../redeploy ─────────────────────────────────────────────────────────

def test_redeploy_suspended_deployment(admin_client: TestClient, project_with_generated_stub, db_session: Session):
    project, stub = project_with_generated_stub
    deployment = Deployment(
        project_id=project.id,
        stub_id=stub.id,
        status="SUSPENDED",
        terraform_state_key=f"stubs/{project.id}/{stub.id}/terraform.tfstate",
        target_type="AWS",
    )
    db_session.add(deployment)
    db_session.commit()
    db_session.refresh(deployment)

    resp = admin_client.post(f"/api/v1/projects/{project.id}/deployments/{deployment.id}/redeploy")
    assert resp.status_code == 202
    body = resp.json()
    assert body["deployment_id"] == str(deployment.id)
    assert "job_id" in body

    db_session.refresh(deployment)
    assert deployment.status == "PENDING"


def test_redeploy_non_suspended_returns_409(admin_client: TestClient, project_with_generated_stub, db_session: Session):
    project, stub = project_with_generated_stub
    deployment = _make_live_deployment(db_session, project, stub)

    resp = admin_client.post(f"/api/v1/projects/{project.id}/deployments/{deployment.id}/redeploy")
    assert resp.status_code == 409


# ── SQS message sent on deploy (moto) ────────────────────────────────────────

@mock_aws
def test_deploy_sends_sqs_message(db_engine, admin_user, db_session: Session):
    import project_service.config as _cfg
    from tests.conftest import _make_client
    from project_service.dependencies import CurrentUser

    sqs = boto3.client("sqs", region_name="eu-west-2")
    queue = sqs.create_queue(QueueName="mockingbird-deploy-queue")
    queue_url = queue["QueueUrl"]
    _cfg.settings.sqs_deploy_queue_url = queue_url

    project = Project(name="SQS Deploy Test", team="T", expected_tps=10000, created_by=admin_user.id)
    db_session.add(project)
    db_session.flush()
    stub = Stub(project_id=project.id, name="S", format="level-1-txt",
                source_file_key="stubs/x/y/source/f.txt", generated_at=datetime.now(timezone.utc))
    db_session.add(stub)
    db_session.commit()
    db_session.refresh(project)
    db_session.refresh(stub)

    client = _make_client(db_engine, CurrentUser(id=admin_user.id, username="admin", role="ADMIN"))
    resp = client.post(f"/api/v1/projects/{project.id}/stubs/{stub.id}/deploy")
    assert resp.status_code == 202

    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1).get("Messages", [])
    assert len(messages) == 1
    body = json.loads(messages[0]["Body"])
    assert body["type"] == "DEPLOY"
    assert body["project_id"] == str(project.id)
    assert "generated_s3_key" in body["payload"]

    _cfg.settings.sqs_deploy_queue_url = ""
