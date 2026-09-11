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
    # SQLite has no real ALTER-a-constraint support, and (unlike Postgres)
    # doesn't reliably expose the FK's name for alembic's batch/copy-move
    # mode to target either — the "audit_log_project_id_fkey" name only
    # ever existed because the *model* declares it via ForeignKey(...,
    # name=...); SQLite's own schema reflection doesn't preserve it the
    # same way. SQLite also only enforces FK ondelete behavior at all when
    # a session sets `PRAGMA foreign_keys=ON` (this project's engine
    # doesn't), so skipping this rename there changes nothing observable —
    # it's a no-op on the one dialect where it can't be done cleanly.
    # Postgres (the real production target — see CLAUDE.md) still gets the
    # actual constraint change below.
    if op.get_bind().dialect.name == "sqlite":
        return
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
    if op.get_bind().dialect.name == "sqlite":
        return
    op.drop_constraint("audit_log_project_id_fkey", "audit_log", type_="foreignkey")
    op.create_foreign_key(
        "audit_log_project_id_fkey",
        "audit_log",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
