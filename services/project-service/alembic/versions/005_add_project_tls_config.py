"""005 add project tls config

Backs the per-project HTTP/HTTPS/mTLS protocol selector: each project
chooses a stub traffic protocol (HTTP / HTTPS / BOTH) and, when HTTPS or
BOTH is selected, may optionally enforce mTLS backed by an uploaded CA
bundle. Certificate file validation/upload itself is handled by
ingestion-service — this migration only adds the metadata/pointer columns
project-service stores (S3 key strings ingestion-service hands back).

Revision ID: 005
Revises: 004
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("protocol", sa.String(20), nullable=False, server_default="HTTP"),
    )
    op.add_column(
        "projects",
        sa.Column("mtls_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("projects", sa.Column("tls_cert_source", sa.String(20), nullable=True))
    op.add_column("projects", sa.Column("tls_cert_s3_key", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("tls_key_s3_key", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("tls_ca_bundle_s3_key", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "tls_ca_bundle_s3_key")
    op.drop_column("projects", "tls_key_s3_key")
    op.drop_column("projects", "tls_cert_s3_key")
    op.drop_column("projects", "tls_cert_source")
    op.drop_column("projects", "mtls_enabled")
    op.drop_column("projects", "protocol")
