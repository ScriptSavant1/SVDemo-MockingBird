"""001 initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users — must be created before projects (FK constraint)
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="VIEWER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("team", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False, server_default="TEST"),
        sa.Column("expected_tps", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("stub_url", sa.String(500), nullable=True),
        sa.Column("api_key", sa.String(100), nullable=True),
        sa.Column("created_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "stubs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("source_file_key", sa.String(500), nullable=True),
        sa.Column("wiremock_mapping_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "deployments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False, server_default="AWS"),
        sa.Column("ec2_instance_id", sa.String(50), nullable=True),
        sa.Column("ec2_ip_address", sa.String(45), nullable=True),
        sa.Column("gitlab_pipeline_id", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("project_id", sa.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("stub_id", sa.UUID(as_uuid=True), sa.ForeignKey("stubs.id"), nullable=True),
        sa.Column("sqs_message_id", sa.String(255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Indexes for common query patterns
    op.create_index("ix_projects_created_by", "projects", ["created_by"])
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_stubs_project_id", "stubs", ["project_id"])
    op.create_index("ix_deployments_project_id", "deployments", ["project_id"])
    op.create_index("ix_audit_log_project_id", "audit_log", ["project_id"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_jobs_status", "jobs")
    op.drop_index("ix_jobs_project_id", "jobs")
    op.drop_index("ix_audit_log_user_id", "audit_log")
    op.drop_index("ix_audit_log_project_id", "audit_log")
    op.drop_index("ix_deployments_project_id", "deployments")
    op.drop_index("ix_stubs_project_id", "stubs")
    op.drop_index("ix_projects_status", "projects")
    op.drop_index("ix_projects_created_by", "projects")
    op.drop_table("jobs")
    op.drop_table("audit_log")
    op.drop_table("deployments")
    op.drop_table("stubs")
    op.drop_table("projects")
    op.drop_table("users")
