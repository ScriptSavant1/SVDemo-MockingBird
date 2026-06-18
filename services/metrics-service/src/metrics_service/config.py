from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../config/local.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./metrics.db"
    aws_region: str = "eu-west-2"
    redis_url: str = "redis://localhost:6379"
    timestream_database: str = "mockingbird"
    timestream_table: str = "stub_metrics"
    scrape_interval_seconds: int = 30
    scrape_timeout_seconds: int = 5
    scrape_port: int = 8080
    environment: str = "local"


settings = Settings()
