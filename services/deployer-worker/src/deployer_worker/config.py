"""Deployer-worker configuration.

All values come from environment variables.
In production these are injected by HashiCorp Vault via ECS task definition.
NEVER hard-code secrets here.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./deployer.db"

    # AWS
    aws_region: str = "eu-west-2"
    sqs_deploy_queue_url: str = ""
    s3_bucket: str = "mockingbird-stubs"

    # Terraform state backend
    terraform_state_bucket: str = "mockingbird-terraform-state"
    terraform_locks_table: str = "mockingbird-terraform-locks"

    # GitLab — injected from Vault in production
    gitlab_url: str = "https://gitlab.internal"
    gitlab_token: str = ""
    # GitLab project ID for the shared stub-builder project
    gitlab_stub_builder_project_id: str = ""
    gitlab_registry: str = ""

    # EC2 networking — set per AWS account
    ec2_subnet_id: str = ""
    ec2_security_group_id: str = ""
    ec2_key_pair_name: str = "mockingbird-key"
    ec2_iam_instance_profile: str = "MockingbirdStubInstanceProfile"

    # Container images (pulled from GitLab registry via Artifactory proxy)
    java_base_image: str = ""

    # Worker behaviour
    sqs_poll_wait_seconds: int = 20
    environment: str = "local"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
