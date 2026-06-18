"""Phase 4 Sprint 13 — deployer-worker tests.

Tests cover:
  - process_message with mocked GitLab + mocked Terraform → job DONE, deployment LIVE
  - GitLab pipeline failure → job FAILED, deployment FAILED
  - Terraform apply failure → job FAILED
  - EC2 health check timeout → job FAILED
  - SUSPEND action → terraform destroy called, deployment SUSPENDED
  - GitLabClient.trigger_pipeline makes correct API call
  - GitLabClient.wait_for_pipeline polls until success
  - GitLabClient.wait_for_pipeline returns timeout when deadline exceeded
  - TerraformError raised on non-zero subprocess return
  - terraform.apply writes auto.tfvars.json with correct content
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import responses as responses_lib
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")

# UUIDs start with hex letters (SQLite NUMERIC affinity guard)
PROJECT_ID = str(uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"))
STUB_ID = str(uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001"))
DEPLOYMENT_ID = str(uuid.UUID("cccccccc-0000-0000-0000-000000000001"))
JOB_ID = str(uuid.UUID("dddddddd-0000-0000-0000-000000000001"))
GENERATED_KEY = f"stubs/{PROJECT_ID}/{STUB_ID}/generated/stub-engine.zip"

GITLAB_URL = "https://gitlab.internal"
GITLAB_PROJECT_ID = "42"
GITLAB_REGISTRY = "registry.internal"
GITLAB_TOKEN = "test-token"

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
        conn.execute(text(
            "CREATE TABLE deployments ("
            "id TEXT PRIMARY KEY, project_id TEXT, stub_id TEXT, job_id TEXT, status TEXT, "
            "target_type TEXT DEFAULT 'AWS', ec2_instance_type TEXT DEFAULT 'c6i.2xlarge', "
            "ec2_instance_id TEXT, ec2_ip_address TEXT, gitlab_pipeline_id TEXT, "
            "docker_image_tag TEXT, terraform_state_key TEXT, api_key TEXT, stub_url TEXT, "
            "error_message TEXT, deployed_at TEXT, terminated_at TEXT, "
            "created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        conn.commit()
    Session = sessionmaker(bind=engine)
    return Session


def _seed(db, *, job_status="QUEUED", deployment_status="PENDING"):
    db.execute(
        text("INSERT INTO jobs (id, type, status, project_id, stub_id, payload) "
             "VALUES (:id, 'DEPLOY', :s, :pid, :sid, '{}')"),
        {"id": JOB_ID, "s": job_status, "pid": PROJECT_ID, "sid": STUB_ID},
    )
    db.execute(
        text("INSERT INTO deployments (id, project_id, stub_id, job_id, status, api_key, "
             "terraform_state_key) VALUES (:id, :pid, :sid, :jid, :s, 'test-api-key', :tskey)"),
        {"id": DEPLOYMENT_ID, "pid": PROJECT_ID, "sid": STUB_ID, "jid": JOB_ID,
         "s": deployment_status, "tskey": f"stubs/{PROJECT_ID}/{STUB_ID}/terraform.tfstate"},
    )
    db.commit()


def _get_job(db) -> dict:
    row = db.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": JOB_ID}).fetchone()
    return dict(row._mapping)


def _get_deployment(db) -> dict:
    row = db.execute(text("SELECT * FROM deployments WHERE id=:id"), {"id": DEPLOYMENT_ID}).fetchone()
    return dict(row._mapping)


def _make_message(payload: dict | None = None) -> dict:
    body = {
        "job_id": JOB_ID,
        "type": "DEPLOY",
        "payload": payload or {
            "generated_s3_key": GENERATED_KEY,
            "deployment_id": DEPLOYMENT_ID,
            "stub_id": STUB_ID,
            "target_type": "AWS",
        },
        "created_at": "2026-06-18T12:00:00Z",
        "project_id": PROJECT_ID,
    }
    return {"MessageId": "msg-1", "ReceiptHandle": "rh-1", "Body": json.dumps(body)}


def _common_kwargs() -> dict:
    """Keyword args that follow the 6 positional params of process_message."""
    return dict(
        state_bucket="mockingbird-terraform-state",
        aws_region="eu-west-2",
        locks_table="mockingbird-terraform-locks",
        ec2_subnet_id="subnet-abc",
        ec2_security_group_id="sg-abc",
        ec2_key_pair_name="mockingbird-key",
        ec2_iam_instance_profile="MockingbirdProfile",
        java_base_image="registry.internal/java:21",
    )


# ── GitLab client tests ───────────────────────────────────────────────────────

@responses_lib.activate
def test_gitlab_trigger_pipeline_makes_correct_api_call():
    from deployer_worker.gitlab_client import GitLabClient

    responses_lib.add(
        responses_lib.POST,
        f"{GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/pipeline",
        json={"id": 99, "status": "created"},
        status=201,
    )

    client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    pipeline_id = client.trigger_pipeline(GITLAB_PROJECT_ID, variables={"S3_KEY": "stubs/x/y.zip"})

    assert pipeline_id == "99"
    assert len(responses_lib.calls) == 1
    body = json.loads(responses_lib.calls[0].request.body)
    assert body["ref"] == "main"
    assert {"key": "S3_KEY", "value": "stubs/x/y.zip"} in body["variables"]


@responses_lib.activate
def test_gitlab_trigger_pipeline_raises_on_error():
    from deployer_worker.gitlab_client import GitLabClient, GitLabError

    responses_lib.add(
        responses_lib.POST,
        f"{GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/pipeline",
        json={"message": "Unauthorized"},
        status=401,
    )

    client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    with pytest.raises(GitLabError):
        client.trigger_pipeline(GITLAB_PROJECT_ID)


@responses_lib.activate
def test_gitlab_wait_for_pipeline_success():
    from deployer_worker.gitlab_client import GitLabClient

    responses_lib.add(
        responses_lib.GET,
        f"{GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/pipelines/10",
        json={"id": 10, "status": "running"},
        status=200,
    )
    responses_lib.add(
        responses_lib.GET,
        f"{GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/pipelines/10",
        json={"id": 10, "status": "success"},
        status=200,
    )

    client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    with patch("time.sleep"):  # skip actual sleep
        status = client.wait_for_pipeline(GITLAB_PROJECT_ID, "10", poll_interval=0)

    assert status == "success"


@responses_lib.activate
def test_gitlab_wait_for_pipeline_timeout():
    from deployer_worker.gitlab_client import GitLabClient

    responses_lib.add(
        responses_lib.GET,
        f"{GITLAB_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/pipelines/10",
        json={"id": 10, "status": "running"},
        status=200,
    )

    client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    with patch("time.monotonic", side_effect=[0, 0.1, 999]):  # deadline exceeded on 3rd call
        status = client.wait_for_pipeline(GITLAB_PROJECT_ID, "10", timeout_seconds=1, poll_interval=0)

    assert status == "timeout"


# ── Terraform tests ───────────────────────────────────────────────────────────

def test_terraform_apply_writes_tfvars(tmp_path):
    from deployer_worker.terraform import apply as tf_apply, TerraformError

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        tf_apply(
            tmp_path,
            variables={"project_id": PROJECT_ID, "stub_id": STUB_ID},
            state_bucket="test-bucket",
            state_key="test/state.tfstate",
            aws_region="eu-west-2",
        )

    tfvars = tmp_path / "terraform.auto.tfvars.json"
    assert tfvars.exists()
    data = json.loads(tfvars.read_text())
    assert data["project_id"] == PROJECT_ID
    assert data["stub_id"] == STUB_ID


def test_terraform_apply_runs_init_then_apply_then_output(tmp_path):
    from deployer_worker.terraform import apply as tf_apply

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        tf_apply(tmp_path, {}, "bucket", "key", "eu-west-2")

    commands = [c.args[0][1] for c in mock_run.call_args_list]
    assert commands == ["init", "apply", "output"]


def test_terraform_raises_on_non_zero_exit(tmp_path):
    from deployer_worker.terraform import apply as tf_apply, TerraformError

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error: something went wrong")
        with pytest.raises(TerraformError, match="something went wrong"):
            tf_apply(tmp_path, {}, "bucket", "key", "eu-west-2")


# ── worker.process_message tests ─────────────────────────────────────────────

def _mock_gitlab_success() -> MagicMock:
    g = MagicMock()
    g.trigger_pipeline.return_value = "pipeline-99"
    g.wait_for_pipeline.return_value = "success"
    return g


def _mock_terraform_success() -> dict:
    return {
        "instance_id": {"value": "i-0123456789abcdef0"},
        "elastic_ip": {"value": "10.0.1.100"},
    }


def test_process_message_full_success(tmp_path):
    from deployer_worker.worker import process_message

    Session = _build_db()
    db = Session()
    _seed(db)

    gitlab = _mock_gitlab_success()

    with patch("deployer_worker.worker.tf_apply", return_value=_mock_terraform_success()), \
         patch("deployer_worker.worker.wait_for_ec2_healthy", return_value=True):
        process_message(_make_message(), db, gitlab, GITLAB_PROJECT_ID, GITLAB_REGISTRY,
                        tmp_path, **_common_kwargs())

    job = _get_job(db)
    assert job["status"] == "DONE"

    deployment = _get_deployment(db)
    assert deployment["status"] == "LIVE"
    assert deployment["stub_url"] == "http://10.0.1.100:8080"
    assert deployment["ec2_instance_id"] == "i-0123456789abcdef0"
    assert deployment["gitlab_pipeline_id"] == "pipeline-99"

    db.close()


def test_process_message_gitlab_failure_sets_failed(tmp_path):
    from deployer_worker.worker import process_message

    Session = _build_db()
    db = Session()
    _seed(db)

    gitlab = MagicMock()
    gitlab.trigger_pipeline.side_effect = Exception("GitLab 500")

    process_message(_make_message(), db, gitlab, GITLAB_PROJECT_ID, GITLAB_REGISTRY,
                    tmp_path, **_common_kwargs())

    assert _get_job(db)["status"] == "FAILED"
    assert _get_deployment(db)["status"] == "FAILED"
    db.close()


def test_process_message_pipeline_failed_status(tmp_path):
    from deployer_worker.worker import process_message

    Session = _build_db()
    db = Session()
    _seed(db)

    gitlab = MagicMock()
    gitlab.trigger_pipeline.return_value = "pipeline-99"
    gitlab.wait_for_pipeline.return_value = "failed"

    process_message(_make_message(), db, gitlab, GITLAB_PROJECT_ID, GITLAB_REGISTRY,
                    tmp_path, **_common_kwargs())

    assert _get_job(db)["status"] == "FAILED"
    assert _get_deployment(db)["status"] == "FAILED"
    db.close()


def test_process_message_terraform_failure(tmp_path):
    from deployer_worker.worker import process_message
    from deployer_worker.terraform import TerraformError

    Session = _build_db()
    db = Session()
    _seed(db)

    gitlab = _mock_gitlab_success()

    with patch("deployer_worker.worker.tf_apply", side_effect=TerraformError("No such subnet")):
        process_message(_make_message(), db, gitlab, GITLAB_PROJECT_ID, GITLAB_REGISTRY,
                        tmp_path, **_common_kwargs())

    assert _get_job(db)["status"] == "FAILED"
    assert _get_deployment(db)["status"] == "FAILED"
    db.close()


def test_process_message_ec2_health_timeout(tmp_path):
    from deployer_worker.worker import process_message

    Session = _build_db()
    db = Session()
    _seed(db)

    gitlab = _mock_gitlab_success()

    with patch("deployer_worker.worker.tf_apply", return_value=_mock_terraform_success()), \
         patch("deployer_worker.worker.wait_for_ec2_healthy", return_value=False):
        process_message(_make_message(), db, gitlab, GITLAB_PROJECT_ID, GITLAB_REGISTRY,
                        tmp_path, **_common_kwargs())

    assert _get_job(db)["status"] == "FAILED"
    assert "healthy" in (_get_job(db)["error_message"] or "")
    db.close()


def test_process_message_suspend_action(tmp_path):
    from deployer_worker.worker import process_message

    Session = _build_db()
    db = Session()
    _seed(db, deployment_status="LIVE")

    gitlab = MagicMock()
    suspend_payload = {
        "action": "SUSPEND",
        "deployment_id": DEPLOYMENT_ID,
        "terraform_state_key": f"stubs/{PROJECT_ID}/{STUB_ID}/terraform.tfstate",
    }

    with patch("deployer_worker.worker.tf_destroy") as mock_destroy:
        process_message(_make_message(suspend_payload), db, gitlab, GITLAB_PROJECT_ID,
                        GITLAB_REGISTRY, tmp_path, **_common_kwargs())

    mock_destroy.assert_called_once()
    gitlab.trigger_pipeline.assert_not_called()
    assert _get_deployment(db)["status"] == "SUSPENDED"
    assert _get_job(db)["status"] == "DONE"
    db.close()
