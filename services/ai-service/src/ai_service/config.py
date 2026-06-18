from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./mockingbird_ai.db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"

    # Claude models — NEVER hard-code API key; inject via Vault / env var
    anthropic_api_key: str = ""
    generation_model: str = "claude-sonnet-4-6"
    classification_model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 8192

    # Rate limiting: max AI generations per user per hour
    rate_limit_per_hour: int = 10

    service_name: str = "ai-service"
    environment: str = "local"


settings = Settings()
