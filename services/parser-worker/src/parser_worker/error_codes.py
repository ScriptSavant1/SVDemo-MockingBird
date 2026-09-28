"""Mockingbird error codes for the upload / parse / generate path.

The user-facing catalogue (meaning + what to do) is docs/ERROR_CODES.md —
keep the two in step. Codes are stable once shipped: never renumber or
reuse one, only add new ones.

Lives in parser-worker because every service on this path (ingestion-service,
parser-worker, generator-worker) already depends on this package.
"""
from __future__ import annotations

from .models import ValidationError

# ── Upload / validation (MB-UPL) ──────────────────────────────────────────────
UPL_EMPTY_FILE = "MB-UPL-001"
UPL_TOO_LARGE = "MB-UPL-002"
UPL_FORMAT_NOT_RECOGNISED = "MB-UPL-003"
UPL_REFERENCED_FILE_MISSING = "MB-UPL-004"
UPL_ARCHIVE_REJECTED = "MB-UPL-005"
UPL_INVALID_PROTOCOL = "MB-UPL-006"
UPL_TLS_CERT_INVALID = "MB-UPL-007"
UPL_SPEC_INVALID = "MB-UPL-008"
UPL_ZIP_PAIRING_FAILED = "MB-UPL-009"
UPL_FILE_UNREADABLE = "MB-UPL-010"
UPL_WORKBOOK_INVALID = "MB-UPL-011"

# ── Generation (MB-GEN) ───────────────────────────────────────────────────────
GEN_STUB_PROJECT_FAILED = "MB-GEN-001"
GEN_WIREMOCK_FAILED = "MB-GEN-002"
GEN_WORKER_FAILED = "MB-GEN-003"


def job_error(code: str, message: str, ref: str | None = None) -> str:
    """The single-line text stored in jobs.error_message and shown as-is on
    the portal's job page: "MB-GEN-003 · <message> (ref abc123)"."""
    text = f"{code} · {message}"
    return f"{text} (ref {ref})" if ref else text


_MAX_SUMMARY_CHARS = 200
_MAX_LISTED_FILES = 3


def summarise_validation_errors(errors: list[ValidationError]) -> tuple[str, str]:
    """One code + one short line for a failed validation — what the user
    sees first. Missing referenced files are listed by name (that's the
    actionable part); anything else shows the first error, trimmed."""
    if not errors:
        return UPL_SPEC_INVALID, "The file failed validation"

    missing = [e.subject for e in errors if e.code == UPL_REFERENCED_FILE_MISSING and e.subject]
    if missing:
        unique = list(dict.fromkeys(missing))
        listed = ", ".join(unique[:_MAX_LISTED_FILES])
        more = f" (+{len(unique) - _MAX_LISTED_FILES} more)" if len(unique) > _MAX_LISTED_FILES else ""
        noun = "file is" if len(unique) == 1 else f"{len(unique)} files are"
        return UPL_REFERENCED_FILE_MISSING, f"Referenced {noun} missing from the upload: {listed}{more}"

    first = errors[0]
    code = first.code or UPL_SPEC_INVALID
    text = first.message
    if len(text) > _MAX_SUMMARY_CHARS:
        text = text[: _MAX_SUMMARY_CHARS - 1].rstrip() + "…"
    if len(errors) > 1:
        text += f" (+{len(errors) - 1} more)"
    return code, text
