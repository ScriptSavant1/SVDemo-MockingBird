"""Alembic environment — connects to the database defined in settings."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `from project_service.xxx import ...` when running alembic from the
# project-service root (i.e. the src/ directory is not on sys.path by default).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from project_service.config import settings
from project_service.models import Base  # noqa: F401 — imports all models so metadata is populated

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from Settings — never hardcode credentials
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection (useful for review/dry-run)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
