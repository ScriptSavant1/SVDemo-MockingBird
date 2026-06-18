"""002 expand deployments table

Adds Sprint 13 columns to the deployments table:
  stub_id, job_id, api_key, stub_url, docker_image_tag,
  terraform_state_key, ec2_instance_type, error_message.

All additions use nullable=True or server_default so existing rows
are unaffected (expand-contract pattern — never drop/rename columns).

Revision ID: 002
Revises: 001
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deployments", sa.Column("stub_id", sa.UUID(as_uuid=True), sa.ForeignKey("stubs.id"), nullable=True))
    op.add_column("deployments", sa.Column("job_id", sa.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=True))
    op.add_column("deployments", sa.Column("api_key", sa.String(64), nullable=True))
    op.add_column("deployments", sa.Column("stub_url", sa.String(255), nullable=True))
    op.add_column("deployments", sa.Column("docker_image_tag", sa.String(255), nullable=True))
    op.add_column("deployments", sa.Column("terraform_state_key", sa.String(255), nullable=True))
    op.add_column("deployments", sa.Column("ec2_instance_type", sa.String(30), nullable=True, server_default="c6i.2xlarge"))
    op.add_column("deployments", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("deployments", "error_message")
    op.drop_column("deployments", "ec2_instance_type")
    op.drop_column("deployments", "terraform_state_key")
    op.drop_column("deployments", "docker_image_tag")
    op.drop_column("deployments", "stub_url")
    op.drop_column("deployments", "api_key")
    op.drop_column("deployments", "job_id")
    op.drop_column("deployments", "stub_id")
