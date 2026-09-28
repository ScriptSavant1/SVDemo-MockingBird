"""Mockingbird error codes for the deploy path (docs/ERROR_CODES.md).

Codes are stable once shipped: never renumber or reuse one. Kept local to
this worker (it doesn't depend on parser-worker, where the upload/generate
codes live); the job_error() format is identical across services.
"""
from __future__ import annotations

DEP_BUILD_TRIGGER_FAILED = "MB-DEP-001"
DEP_BUILD_FAILED = "MB-DEP-002"
DEP_PROVISION_FAILED = "MB-DEP-003"
DEP_UNHEALTHY = "MB-DEP-004"
DEP_SUSPEND_FAILED = "MB-DEP-005"
DEP_MICROCKS_SSH_FAILED = "MB-DEP-006"
DEP_MICROCKS_FAILED = "MB-DEP-007"
DEP_WORKER_FAILED = "MB-DEP-008"


def job_error(code: str, message: str, ref: str | None = None) -> str:
    """The single-line text stored in jobs/deployments.error_message and
    shown as-is in the portal: "MB-DEP-003 · <message> (ref abc123)"."""
    text = f"{code} · {message}"
    return f"{text} (ref {ref})" if ref else text
