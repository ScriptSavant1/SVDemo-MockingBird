"""006 move TLS config from projects to stubs

Migration 005 put the HTTP/HTTPS/mTLS protocol config on `projects`. That
was wrong: each *stub*, not each project, is the actual deployable unit —
deployer-worker builds a separate Docker image and provisions a separate
EC2 instance per stub. A project-level setting forced every stub in a
project to share one protocol, which doesn't match real usage (a team adds
services over time, sometimes wanting HTTP for one stub and HTTPS for
another). This migration moves the same six columns from `projects` to
`stubs`.

The project-level columns are dropped outright here rather than left in
place unused — normally this project's migrations only ever add columns
(expand-only, never drop/rename), but 005 shipped in the same work session
as this fix with no real deployment depending on it yet, so there's nothing
to protect by keeping the dead columns around.

Revision ID: 006
Revises: 005
Create Date: 2026-09-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stubs", sa.Column("protocol", sa.String(20), nullable=False, server_default="HTTP"))
    op.add_column("stubs", sa.Column("mtls_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("stubs", sa.Column("tls_cert_source", sa.String(20), nullable=True))
    op.add_column("stubs", sa.Column("tls_cert_s3_key", sa.String(500), nullable=True))
    op.add_column("stubs", sa.Column("tls_key_s3_key", sa.String(500), nullable=True))
    op.add_column("stubs", sa.Column("tls_ca_bundle_s3_key", sa.String(500), nullable=True))

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("protocol")
        batch_op.drop_column("mtls_enabled")
        batch_op.drop_column("tls_cert_source")
        batch_op.drop_column("tls_cert_s3_key")
        batch_op.drop_column("tls_key_s3_key")
        batch_op.drop_column("tls_ca_bundle_s3_key")


def downgrade() -> None:
    op.add_column("projects", sa.Column("protocol", sa.String(20), nullable=False, server_default="HTTP"))
    op.add_column("projects", sa.Column("mtls_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("projects", sa.Column("tls_cert_source", sa.String(20), nullable=True))
    op.add_column("projects", sa.Column("tls_cert_s3_key", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("tls_key_s3_key", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("tls_ca_bundle_s3_key", sa.String(500), nullable=True))

    with op.batch_alter_table("stubs") as batch_op:
        batch_op.drop_column("protocol")
        batch_op.drop_column("mtls_enabled")
        batch_op.drop_column("tls_cert_source")
        batch_op.drop_column("tls_cert_s3_key")
        batch_op.drop_column("tls_key_s3_key")
        batch_op.drop_column("tls_ca_bundle_s3_key")
