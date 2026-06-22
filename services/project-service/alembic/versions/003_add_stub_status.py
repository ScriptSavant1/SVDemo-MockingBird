"""003 add stub status column

Adds a status column to the stubs table so each stub tracks its lifecycle
independently of the project-level status.

Default: READY — uploaded stubs are immediately ready to deploy.

Also backfills generated_at for existing stubs that have a source_file_key,
so the Deploy button unblocks for stubs created before this migration.

Revision ID: 003
Revises: 002
Create Date: 2026-06-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stubs",
        sa.Column("status", sa.String(20), nullable=False, server_default="READY"),
    )
    # Backfill generated_at for stubs that have a source file (i.e. were uploaded).
    # Uses updated_at as a reasonable approximation of when generation happened.
    op.execute(
        "UPDATE stubs SET generated_at = updated_at "
        "WHERE source_file_key IS NOT NULL AND generated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("stubs", "status")
