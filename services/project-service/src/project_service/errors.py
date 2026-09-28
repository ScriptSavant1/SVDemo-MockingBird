"""One error shape for every response this service sends.

Every non-2xx response body is RFC 7807 Problem JSON plus a Mockingbird code:

    {"type": "...", "title": "...", "status": 413, "code": "MB-UPL-002",
     "detail": "File exceeds the 50 MB upload limit", "ref": "a1b2c3d4"}

`detail` is always ONE short, human-readable line — the portal shows
"<code> · <detail>" as-is. `ref` appears only on unexpected (5xx) errors and
ties the user's message to the full traceback in the server log; tracebacks,
file paths and exception text never go in the response itself.

Catalogue of codes: docs/ERROR_CODES.md.

Kept as a small per-service module (ingestion-service has an identical copy)
rather than a shared package: services deploy independently, and this is
too small to be worth a cross-service dependency.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

SYS_UNEXPECTED = "MB-SYS-001"
SYS_COMPONENT_MISSING = "MB-SYS-002"

_TYPE_BASE = "https://mockingbird.internal/errors/"
_TITLES = {
    400: "Bad request",
    401: "Not signed in",
    403: "Not allowed",
    404: "Not found",
    409: "Conflict",
    413: "Too large",
    422: "Invalid request",
    500: "Server error",
    502: "Upstream error",
    503: "Service unavailable",
}
# Location segments that say where a field came from, not which field it is.
_LOC_NOISE = {"body", "query", "path", "form", "header", "cookie"}


class MockingbirdError(StarletteHTTPException):
    """Raise for any error with a specific code: MockingbirdError(413,
    "MB-UPL-002", "File exceeds the 50 MB upload limit")."""

    def __init__(self, status_code: int, code: str, detail: str, title: str | None = None) -> None:
        super().__init__(
            status_code=status_code,
            detail={"code": code, "title": title or _TITLES.get(status_code, "Request failed"), "detail": detail},
        )


def request_code(status_code: int) -> str:
    """Generic code for an error nobody gave a specific one: MB-REQ-404 etc."""
    return f"MB-REQ-{status_code}"


def problem_response(
    status_code: int,
    code: str,
    detail: str,
    title: str | None = None,
    ref: str | None = None,
    headers: dict[str, str] | None = None,
    type_uri: str | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type_uri or _TYPE_BASE + code.lower(),
        "title": title or _TITLES.get(status_code, "Request failed"),
        "status": status_code,
        "code": code,
        "detail": detail,
    }
    if ref:
        body["ref"] = ref
    return JSONResponse(body, status_code=status_code, media_type="application/problem+json", headers=headers)


def _http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = request_code(exc.status_code)
    title = _TITLES.get(exc.status_code, "Request failed")
    type_uri: str | None = None
    raw = exc.detail
    if isinstance(raw, dict):
        # MockingbirdError, or an older raise site passing a ProblemDetail
        # dict as `detail` — flattened so `detail` is always a string.
        code = str(raw.get("code") or code)
        title = str(raw.get("title") or title)
        text = str(raw.get("detail") or title)
        type_uri = str(raw["type"]) if raw.get("type") else None
    else:
        text = str(raw) if raw else title
    return problem_response(
        exc.status_code, code, text, title, headers=getattr(exc, "headers", None), type_uri=type_uri,
    )


def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = ".".join(str(p) for p in first.get("loc", ()) if p not in _LOC_NOISE) or "request"
    text = f"Invalid value for '{field}': {str(first.get('msg', 'invalid')).lower()}"
    if len(errors) > 1:
        text += f" (+{len(errors) - 1} more)"
    return problem_response(422, request_code(422), text)


def install_error_handlers(app: FastAPI, service_name: str) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]

    def _unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        ref = uuid.uuid4().hex[:8]
        logger.exception("[ref %s] Unhandled error on %s %s", ref, request.method, request.url.path)
        if isinstance(exc, ImportError):
            # A dependency the code needs isn't installed in this service's
            # environment (seen for real: openpyxl missing from a venv built
            # before it was added). The module name is safe to show; it's the
            # one thing an admin needs to fix it.
            component = exc.name or "a required"
            return problem_response(
                500, SYS_COMPONENT_MISSING,
                f"Server is missing the '{component}' component — ask an admin to reinstall "
                f"{service_name}'s dependencies (ref {ref})",
                ref=ref,
            )
        return problem_response(
            500, SYS_UNEXPECTED,
            f"Unexpected error in {service_name} (ref {ref}) — the details are in the server log",
            ref=ref,
        )

    app.add_exception_handler(Exception, _unexpected_handler)
