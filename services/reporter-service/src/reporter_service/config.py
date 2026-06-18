from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../config/local.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./reporter.db"
    aws_region: str = "eu-west-2"
    s3_bucket: str = "mockingbird-stubs"
    sqs_report_queue_url: str = ""
    timestream_database: str = "mockingbird"
    timestream_table: str = "stub_metrics"
    sqs_poll_wait_seconds: int = 20
    environment: str = "local"

    # Branding defaults — overridden by U1 assets when provided
    brand_primary_colour: str = "#003875"   # navy
    brand_secondary_colour: str = "#00A9E0" # sky blue
    brand_company_name: str = "Your Organisation"


settings = Settings()
