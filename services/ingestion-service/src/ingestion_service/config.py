from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./ingestion.db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    s3_bucket: str = "mockingbird-stubs"
    aws_region: str = "eu-west-2"
    # Set to http://localstack:4566 for local development; leave blank in production
    aws_endpoint_url: Optional[str] = None
    # 10 MB hard ceiling on uploaded spec files
    max_upload_bytes: int = 10 * 1024 * 1024
    service_name: str = "ingestion-service"
    environment: str = "local"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
