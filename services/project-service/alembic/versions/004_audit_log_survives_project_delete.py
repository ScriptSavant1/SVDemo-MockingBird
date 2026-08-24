"""004 audit_log survives project delete

audit_log.project_id was ON DELETE CASCADE, meaning deleting a project wiped
out its entire audit trail with it -- the opposite of what an audit log is
for. Changes it to ON DELETE SET NULL so the historical record survives
(delete_project() snapshots identifying details into `detail` for exactly
this reason, before deleting the project).

Revision ID: 004
Revises: 003
Create Date: 2026-08-24
"""
from __future__ import annotations

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("audit_log_project_id_fkey", "audit_log", type_="foreignkey")
    op.create_foreign_key(
        "audit_log_project_id_fkey",
        "audit_log",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("audit_log_project_id_fkey", "audit_log", type_="foreignkey")
    op.create_foreign_key(
        "audit_log_project_id_fkey",
        "audit_log",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
