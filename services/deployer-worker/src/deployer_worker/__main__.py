"""Entry point for the sv-deploy-worker CLI command."""
from __future__ import annotations

import logging
from pathlib import Path

import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings
from .gitlab_client import GitLabClient
from .worker import _TERRAFORM_MODULE_DIR, run_loop

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "service": "deployer-worker", "message": "%(message)s"}',
)


def main() -> None:
    if not settings.sqs_deploy_queue_url:
        raise SystemExit("SQS_DEPLOY_QUEUE_URL is required")
    if not settings.gitlab_token:
        raise SystemExit("GITLAB_TOKEN is required")

    engine = create_engine(settings.database_url)
    SessionFactory = sessionmaker(bind=engine)

    sqs = boto3.client("sqs", region_name=settings.aws_region)
    gitlab = GitLabClient(settings.gitlab_url, settings.gitlab_token)

    run_loop(
        sqs_client=sqs,
        db_factory=SessionFactory,
        gitlab=gitlab,
        gitlab_project_id=settings.gitlab_stub_builder_project_id,
        gitlab_registry=settings.gitlab_registry,
        terraform_dir=_TERRAFORM_MODULE_DIR,
        queue_url=settings.sqs_deploy_queue_url,
        state_bucket=settings.terraform_state_bucket,
        aws_region=settings.aws_region,
        locks_table=settings.terraform_locks_table,
        ec2_subnet_id=settings.ec2_subnet_id,
        ec2_security_group_id=settings.ec2_security_group_id,
        ec2_key_pair_name=settings.ec2_key_pair_name,
        ec2_iam_instance_profile=settings.ec2_iam_instance_profile,
        java_base_image=settings.java_base_image,
        poll_wait=settings.sqs_poll_wait_seconds,
    )
