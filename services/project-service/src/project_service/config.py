"""Service configuration — all values come from environment variables.

In production, env vars are injected by HashiCorp Vault via ECS task definitions.
In local development, set them in a .env file or docker-compose.yml.
NEVER hard-code secrets here.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database — injected from Vault in production
    database_url: str = "sqlite:///./mockingbird.db"

    # JWT — must match the secret used by auth-service
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"

    # SQS queue URLs — injected from environment / Vault
    sqs_parse_queue_url: str = ""
    sqs_generate_queue_url: str = ""
    sqs_deploy_queue_url: str = ""
    sqs_report_queue_url: str = ""
    aws_region: str = "eu-west-2"
    s3_bucket: str = "mockingbird-stubs"

    # Service identity
    service_name: str = "project-service"
    environment: str = "local"


settings = Settings()
