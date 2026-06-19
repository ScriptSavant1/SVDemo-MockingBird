"""Deployer-worker SQS consumer (Phase 4 / Sprint 13).

Reads DEPLOY messages from the deploy-queue and:
  1. Triggers a GitLab CI pipeline to build the Docker image via Kaniko
  2. Runs Terraform to provision an EC2 instance
  3. Polls the EC2 Spring Boot health endpoint until ready
  4. Writes deployment details (IP, URL, status) back to PostgreSQL

SQS message payload:
  {
    "job_id": str,
    "type": "DEPLOY",
    "payload": {
      "generated_s3_key": "stubs/{project_id}/{stub_id}/generated/stub-engine.zip",
      "deployment_id": str,
      "target_type": "AWS"
    },
    "created_at": ISO-8601,
    "project_id": str
  }
"""
from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from sqlalchemy.orm import Session

from .gitlab_client import GitLabClient
from .health import wait_for_ec2_healthy
from .microcks import MicrocksDeployError, deploy_microcks
from .terraform import TerraformError, apply as tf_apply, destroy as tf_destroy

logger = logging.getLogger(__name__)

# Terraform module is baked into the deployer-worker Docker image at this path
_TERRAFORM_MODULE_DIR = Path(__file__).parent.parent.parent.parent / "terraform" / "stub-ec2"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_job(
    db: Session,
    job_id: str,
    *,
    status: str,
    error: str | None = None,
    result: dict | None = None,
) -> None:
    db.execute(
        __import__("sqlalchemy").text(
            "UPDATE jobs SET status=:s, error_message=:e, result=:r, updated_at=:u WHERE id=:id"
        ),
        {
            "s": status,
            "e": error,
            "r": json.dumps(result) if result is not None else None,
            "u": _now_iso(),
            "id": job_id,
        },
    )
    db.commit()


def _update_deployment(
    db: Session,
    deployment_id: str,
    *,
    status: str,
    gitlab_pipeline_id: str | None = None,
    ec2_instance_id: str | None = None,
    ec2_ip_address: str | None = None,
    stub_url: str | None = None,
    docker_image_tag: str | None = None,
    error_message: str | None = None,
) -> None:
    from sqlalchemy import text

    sets = ["status=:status", "updated_at=:updated_at"]
    params: dict[str, Any] = {"status": status, "updated_at": _now_iso(), "id": deployment_id}

    if gitlab_pipeline_id is not None:
        sets.append("gitlab_pipeline_id=:gitlab_pipeline_id")
        params["gitlab_pipeline_id"] = gitlab_pipeline_id
    if ec2_instance_id is not None:
        sets.append("ec2_instance_id=:ec2_instance_id")
        params["ec2_instance_id"] = ec2_instance_id
    if ec2_ip_address is not None:
        sets.append("ec2_ip_address=:ec2_ip_address")
        params["ec2_ip_address"] = ec2_ip_address
    if stub_url is not None:
        sets.append("stub_url=:stub_url")
        params["stub_url"] = stub_url
    if docker_image_tag is not None:
        sets.append("docker_image_tag=:docker_image_tag")
        params["docker_image_tag"] = docker_image_tag
    if error_message is not None:
        sets.append("error_message=:error_message")
        params["error_message"] = error_message

    db.execute(text(f"UPDATE deployments SET {', '.join(sets)} WHERE id=:id"), params)
    db.commit()


def _get_deployment_api_key(db: Session, deployment_id: str) -> str:
    from sqlalchemy import text
    row = db.execute(text("SELECT api_key FROM deployments WHERE id=:id"), {"id": deployment_id}).fetchone()
    return row[0] if row and row[0] else ""


def process_message(
    message: dict,
    db: Session,
    gitlab: GitLabClient,
    gitlab_project_id: str,
    gitlab_registry: str,
    terraform_dir: Path,
    state_bucket: str,
    aws_region: str,
    locks_table: str,
    ec2_subnet_id: str,
    ec2_security_group_id: str,
    ec2_key_pair_name: str,
    ec2_iam_instance_profile: str,
    java_base_image: str,
) -> None:
    body = json.loads(message["Body"])
    job_id: str = body["job_id"]
    payload: dict = body["payload"]
    project_id: str = body["project_id"]

    # Route by engine type — Microcks skips GitLab CI (pre-built image)
    engine_type = payload.get("engine_type", "SPRINGBOOT")
    if engine_type == "MICROCKS":
        _handle_microcks_deploy(
            payload=payload,
            db=db,
            job_id=job_id,
            project_id=project_id,
            terraform_dir=terraform_dir,
            state_bucket=state_bucket,
            aws_region=aws_region,
            locks_table=locks_table,
            ec2_subnet_id=ec2_subnet_id,
            ec2_security_group_id=ec2_security_group_id,
            ec2_key_pair_name=ec2_key_pair_name,
            ec2_iam_instance_profile=ec2_iam_instance_profile,
        )
        return

    # SUSPEND action — just run terraform destroy
    if payload.get("action") == "SUSPEND":
        deployment_id = payload["deployment_id"]
        state_key = payload.get("terraform_state_key", f"stubs/{project_id}/terraform.tfstate")
        _update_job(db, job_id, status="RUNNING")
        try:
            tf_destroy(terraform_dir, state_bucket, state_key, aws_region, locks_table)
            _update_deployment(db, deployment_id, status="SUSPENDED")
            _update_job(db, job_id, status="DONE", result={"action": "SUSPENDED", "deployment_id": deployment_id})
        except TerraformError as exc:
            err = str(exc)
            logger.error("terraform destroy failed for deployment %s: %s", deployment_id, err)
            _update_job(db, job_id, status="FAILED", error=err)
        return

    # DEPLOY action
    generated_s3_key: str = payload["generated_s3_key"]
    deployment_id: str = payload["deployment_id"]
    stub_id: str = payload.get("stub_id", "unknown")

    _update_job(db, job_id, status="RUNNING")

    # Build Docker image tag: registry/stubs/{project_id}/{stub_id}:latest
    image_tag = f"{gitlab_registry}/stubs/{project_id}/{stub_id}:latest"

    # ── Step 1: GitLab CI pipeline (Kaniko build) ─────────────────────────────
    logger.info("Triggering GitLab pipeline for deployment %s", deployment_id)
    try:
        pipeline_id = gitlab.trigger_pipeline(
            gitlab_project_id,
            variables={
                "S3_GENERATED_KEY": generated_s3_key,
                "IMAGE_TAG": image_tag,
                "PROJECT_ID": project_id,
                "STUB_ID": stub_id,
            },
        )
    except Exception as exc:
        err = f"Failed to trigger GitLab pipeline: {exc}"
        logger.error(err)
        _update_deployment(db, deployment_id, status="FAILED", error_message=err)
        _update_job(db, job_id, status="FAILED", error=err)
        return

    _update_deployment(db, deployment_id, status="BUILDING", gitlab_pipeline_id=pipeline_id)

    final_status = gitlab.wait_for_pipeline(gitlab_project_id, pipeline_id)
    if final_status != "success":
        err = f"GitLab pipeline {pipeline_id} ended with status: {final_status}"
        logger.error(err)
        _update_deployment(db, deployment_id, status="FAILED", error_message=err)
        _update_job(db, job_id, status="FAILED", error=err)
        return

    logger.info("GitLab pipeline %s succeeded for deployment %s", pipeline_id, deployment_id)
    _update_deployment(db, deployment_id, status="PROVISIONING", docker_image_tag=image_tag)

    # ── Step 2: Terraform apply ───────────────────────────────────────────────
    api_key = _get_deployment_api_key(db, deployment_id)
    state_key = f"stubs/{project_id}/{stub_id}/terraform.tfstate"

    tf_vars = {
        "project_id": project_id,
        "stub_id": stub_id,
        "docker_image": image_tag,
        "stub_api_key": api_key,
        "subnet_id": ec2_subnet_id,
        "security_group_id": ec2_security_group_id,
        "key_name": ec2_key_pair_name,
        "iam_instance_profile": ec2_iam_instance_profile,
        "aws_region": aws_region,
        "java_base_image": java_base_image,
    }

    try:
        tf_outputs = tf_apply(
            terraform_dir,
            tf_vars,
            state_bucket=state_bucket,
            state_key=state_key,
            aws_region=aws_region,
            locks_table=locks_table,
        )
    except TerraformError as exc:
        err = str(exc)
        logger.error("Terraform apply failed for deployment %s: %s", deployment_id, err)
        _update_deployment(db, deployment_id, status="FAILED", error_message=err)
        _update_job(db, job_id, status="FAILED", error=err)
        return

    ec2_instance_id = tf_outputs.get("instance_id", {}).get("value", "")
    ec2_ip = tf_outputs.get("elastic_ip", {}).get("value", "")
    stub_url = f"http://{ec2_ip}:8080"

    # ── Step 3: health check ──────────────────────────────────────────────────
    logger.info("Waiting for EC2 %s to become healthy", ec2_ip)
    healthy = wait_for_ec2_healthy(ec2_ip)
    if not healthy:
        err = f"EC2 {ec2_ip} did not become healthy within timeout"
        logger.error(err)
        _update_deployment(
            db, deployment_id, status="FAILED",
            ec2_instance_id=ec2_instance_id, ec2_ip_address=ec2_ip,
            error_message=err,
        )
        _update_job(db, job_id, status="FAILED", error=err)
        return

    logger.info("Deployment %s is LIVE at %s", deployment_id, stub_url)
    _update_deployment(
        db, deployment_id,
        status="LIVE",
        ec2_instance_id=ec2_instance_id,
        ec2_ip_address=ec2_ip,
        stub_url=stub_url,
    )
    _update_job(
        db, job_id,
        status="DONE",
        result={
            "deployment_id": deployment_id,
            "stub_url": stub_url,
            "ec2_instance_id": ec2_instance_id,
            "ec2_ip_address": ec2_ip,
        },
    )


def _handle_microcks_deploy(
    payload: dict,
    db: Session,
    job_id: str,
    project_id: str,
    terraform_dir: Path,
    state_bucket: str,
    aws_region: str,
    locks_table: str,
    ec2_subnet_id: str,
    ec2_security_group_id: str,
    ec2_key_pair_name: str,
    ec2_iam_instance_profile: str,
) -> None:
    """Deploy a Microcks container to EC2 (no GitLab CI build required)."""
    deployment_id: str = payload["deployment_id"]
    stub_id: str = payload.get("stub_id", "unknown")
    microcks_s3_key: str = payload["microcks_s3_key"]
    ssh_key_path: str = os.environ.get("EC2_SSH_KEY_PATH", "/secrets/ec2-key.pem")

    _update_job(db, job_id, status="RUNNING")
    _update_deployment(db, deployment_id, status="PROVISIONING")

    # ── Step 1: Terraform apply ───────────────────────────────────────────────
    api_key = _get_deployment_api_key(db, deployment_id)
    state_key = f"stubs/{project_id}/{stub_id}/terraform.tfstate"
    tf_vars = {
        "project_id": project_id,
        "stub_id": stub_id,
        "docker_image": "",
        "stub_api_key": api_key,
        "subnet_id": ec2_subnet_id,
        "security_group_id": ec2_security_group_id,
        "key_name": ec2_key_pair_name,
        "iam_instance_profile": ec2_iam_instance_profile,
        "aws_region": aws_region,
        "java_base_image": "",
    }

    try:
        tf_outputs = tf_apply(
            terraform_dir, tf_vars,
            state_bucket=state_bucket, state_key=state_key,
            aws_region=aws_region, locks_table=locks_table,
        )
    except TerraformError as exc:
        err = str(exc)
        logger.error("Terraform apply failed for Microcks deployment %s: %s", deployment_id, err)
        _update_deployment(db, deployment_id, status="FAILED", error_message=err)
        _update_job(db, job_id, status="FAILED", error=err)
        return

    ec2_instance_id = tf_outputs.get("instance_id", {}).get("value", "")
    ec2_ip = tf_outputs.get("elastic_ip", {}).get("value", "")

    # ── Step 2: Download + extract microcks config zip from S3 ───────────────
    s3 = boto3.client("s3", region_name=aws_region)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            zip_path = tmp_dir / "microcks-config.zip"
            s3.download_file(state_bucket, microcks_s3_key, str(zip_path))
            config_dir = tmp_dir / "config"
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(config_dir)

            # ── Step 3: SSH deploy ────────────────────────────────────────────
            logger.info("SSH-deploying Microcks to EC2 %s for deployment %s", ec2_ip, deployment_id)
            deploy_microcks(ec2_ip, ssh_key_path, config_dir)

    except MicrocksDeployError as exc:
        err = str(exc)
        logger.error("Microcks SSH deploy failed for %s: %s", deployment_id, err)
        _update_deployment(
            db, deployment_id, status="FAILED",
            ec2_instance_id=ec2_instance_id, ec2_ip_address=ec2_ip,
            error_message=err,
        )
        _update_job(db, job_id, status="FAILED", error=err)
        return
    except Exception as exc:
        err = f"Microcks deploy error: {exc}"
        logger.error(err)
        _update_deployment(db, deployment_id, status="FAILED", error_message=err)
        _update_job(db, job_id, status="FAILED", error=err)
        return

    # ── Step 4: health check ──────────────────────────────────────────────────
    healthy = wait_for_ec2_healthy(ec2_ip)
    if not healthy:
        err = f"EC2 {ec2_ip} (Microcks) did not become healthy within timeout"
        logger.error(err)
        _update_deployment(
            db, deployment_id, status="FAILED",
            ec2_instance_id=ec2_instance_id, ec2_ip_address=ec2_ip,
            error_message=err,
        )
        _update_job(db, job_id, status="FAILED", error=err)
        return

    stub_url = f"http://{ec2_ip}:8080"
    logger.info("Microcks deployment %s LIVE at %s", deployment_id, stub_url)
    _update_deployment(
        db, deployment_id, status="LIVE",
        ec2_instance_id=ec2_instance_id, ec2_ip_address=ec2_ip, stub_url=stub_url,
    )
    _update_job(
        db, job_id, status="DONE",
        result={
            "deployment_id": deployment_id,
            "stub_url": stub_url,
            "ec2_instance_id": ec2_instance_id,
            "ec2_ip_address": ec2_ip,
            "engine_type": "MICROCKS",
        },
    )


def run_loop(
    sqs_client: Any,
    db_factory: Any,
    gitlab: GitLabClient,
    gitlab_project_id: str,
    gitlab_registry: str,
    terraform_dir: Path,
    queue_url: str,
    state_bucket: str,
    aws_region: str,
    locks_table: str,
    ec2_subnet_id: str,
    ec2_security_group_id: str,
    ec2_key_pair_name: str,
    ec2_iam_instance_profile: str,
    java_base_image: str,
    poll_wait: int = 20,
) -> None:
    logger.info("deployer-worker started, polling %s", queue_url)
    while True:
        resp = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=poll_wait,
        )
        for message in resp.get("Messages", []):
            db = db_factory()
            try:
                process_message(
                    message, db, gitlab, gitlab_project_id, gitlab_registry,
                    terraform_dir, state_bucket, aws_region, locks_table,
                    ec2_subnet_id, ec2_security_group_id, ec2_key_pair_name,
                    ec2_iam_instance_profile, java_base_image,
                )
            except Exception as exc:
                logger.exception("Unhandled error processing message %s: %s", message.get("MessageId"), exc)
            finally:
                db.close()
                sqs_client.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
