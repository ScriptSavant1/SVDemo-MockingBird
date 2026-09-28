"""Mockingbird error codes for report generation (docs/ERROR_CODES.md).

Codes are stable once shipped: never renumber or reuse one. The
job_error() format is identical across services.
"""
from __future__ import annotations

RPT_DATA_LOAD_FAILED = "MB-RPT-001"
RPT_NO_FORMAT_PRODUCED = "MB-RPT-002"
RPT_FORMAT_FAILED = "MB-RPT-003"
RPT_WORKER_FAILED = "MB-RPT-004"


def job_error(code: str, message: str, ref: str | None = None) -> str:
    """One line for jobs.error_message / result warnings, shown as-is in the
    portal: "MB-RPT-001 · <message> (ref abc123)"."""
    text = f"{code} · {message}"
    return f"{text} (ref {ref})" if ref else text
