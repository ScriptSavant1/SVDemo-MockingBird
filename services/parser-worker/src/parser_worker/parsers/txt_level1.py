"""Level 1 TXT parser — single request, single response."""
from __future__ import annotations

import re
from typing import Optional

from ..models import (
    Delay, DelayType, FaultType, HttpMethod, MatchCondition, MatchType, ParsedFile,
    ParsedRequestSpec, ParsedScenario, ParsedStub, ValidationError, ValidationResult,
)
from .base import BaseParser

_DELAY_FIXED_RE = re.compile(r'^(\d+)ms$', re.IGNORECASE)

# User-facing fault aliases → WireMock fault type strings.
_FAULT_ALIASES: dict[str, FaultType] = {
    "connection-reset": FaultType.CONNECTION_RESET_BY_PEER,
    "empty-response":   FaultType.EMPTY_RESPONSE,
    "malformed-response": FaultType.MALFORMED_RESPONSE_CHUNK,
}
_DELAY_RANDOM_RE = re.compile(r'^random:(\d+)ms-(\d+)ms$', re.IGNORECASE)
_DELAY_CHUNKED_RE = re.compile(r'^chunked:(\d+),(\d+)ms$', re.IGNORECASE)
_DELAY_LOGNORMAL_RE = re.compile(r'^lognormal:(\d+)ms,([\d.]+)$', re.IGNORECASE)
_HEADER_PLACEHOLDER_RE = re.compile(r'<[^>]+>')
_SECTION_RE = re.compile(r'^---\s+(.+?)\s+---$')
_HEADER_LINE_RE = re.compile(r'^([A-Za-z][A-Za-z0-9\-]*):\s*(.*)')
_VALID_METHODS = {m.value for m in HttpMethod}


class TxtLevel1Parser(BaseParser):

    @property
    def format_name(self) -> str:
        return "level-1-txt"

    def can_handle(self, content: str, filename: str) -> bool:
        first_line = content.strip().splitlines()[0].strip() if content.strip() else ""
        return (
            first_line == "--- MOCKINGBIRD v1.0 ---"
            and "--- SCENARIO:" not in content
            and "--- SCENARIO DEFAULT" not in content
            and "--- RESPONSE ---" in content
        )

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []
        lines = content.strip().splitlines()

        if not lines or lines[0].strip() != "--- MOCKINGBIRD v1.0 ---":
            errors.append(ValidationError(line=1, message="File must start with '--- MOCKINGBIRD v1.0 ---'"))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        sections = _split_into_sections(lines)

        if "RESPONSE" not in sections:
            errors.append(ValidationError(message="Missing '--- RESPONSE ---' section"))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        meta = sections.get("meta", [])
        method_str = _extract_field(meta, "Method")
        if not method_str:
            errors.append(ValidationError(field="Method", message="Method is required (e.g., Method: GET)"))
        elif method_str.upper() not in _VALID_METHODS:
            errors.append(ValidationError(field="Method", message=f"'{method_str}' is not a valid HTTP method"))

        url = _extract_field(meta, "URL")
        if not url:
            errors.append(ValidationError(field="URL", message="URL is required (e.g., URL: /api/v1/resource)"))
        elif not url.startswith("/"):
            errors.append(ValidationError(field="URL", message=f"URL must start with / — got '{url}'"))

        response = sections.get("RESPONSE", [])
        status_str = _extract_field(response, "Status")
        if not status_str:
            errors.append(ValidationError(field="Status", message="Status is required (e.g., Status: 200)"))
        else:
            try:
                code = int(status_str)
                if not (100 <= code <= 599):
                    errors.append(ValidationError(field="Status", message=f"'{code}' is not a valid HTTP status code"))
            except ValueError:
                errors.append(ValidationError(field="Status", message=f"Status must be a number, got '{status_str}'"))

        fault_val = _extract_field(response, "Fault")
        if fault_val and fault_val.lower() not in _FAULT_ALIASES:
            errors.append(ValidationError(
                field="Fault",
                message=f"'{fault_val}' is not valid. Use: {', '.join(sorted(_FAULT_ALIASES))}",
            ))

        if errors:
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        return ValidationResult(
            valid=True,
            format_detected=self.format_name,
            summary="1 endpoint detected · 1 scenario",
        )

    def parse(self, content: str, source_file: str) -> ParsedFile:
        lines = content.strip().splitlines()
        sections = _split_into_sections(lines)

        meta = sections.get("meta", [])
        headers_lines = sections.get("REQUEST HEADERS", [])
        response_lines = sections.get("RESPONSE", [])

        method = HttpMethod(_extract_field(meta, "Method", default="GET").upper())
        url = _extract_field(meta, "URL", default="/")
        name = _extract_field(meta, "Name", default="Stub")

        required_headers = _parse_request_headers(headers_lines)
        status, response_headers, body, delay, fault = _parse_response_lines(response_lines)

        scenario = ParsedScenario(
            name="default",
            match=MatchCondition(type=MatchType.ALWAYS),
            status=status,
            response_headers=response_headers,
            body=body,
            delay=delay,
            fault=fault,
        )
        stub = ParsedStub(
            name=name,
            request=ParsedRequestSpec(method=method, url=url, required_headers=required_headers),
            scenarios=[scenario],
        )
        return ParsedFile(format=self.format_name, source_file=source_file, stubs=[stub])


# ── shared helpers ────────────────────────────────────────────────────────────

def _split_into_sections(lines: list[str]) -> dict[str, list[str]]:
    """Group lines by section delimiter '--- SECTION NAME ---'."""
    sections: dict[str, list[str]] = {"meta": []}
    current = "meta"
    for line in lines:
        stripped = line.strip()
        if stripped == "--- MOCKINGBIRD v1.0 ---":
            continue
        if stripped.startswith("#") or not stripped:
            continue
        m = _SECTION_RE.match(stripped)
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(stripped)
    return sections


def _extract_field(lines: list[str], key: str, default: str = "") -> str:
    prefix = f"{key}:"
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return default


def _parse_request_headers(lines: list[str]) -> dict[str, str]:
    """Parse header lines, skipping entries that contain placeholder values like <token>."""
    headers: dict[str, str] = {}
    for line in lines:
        m = _HEADER_LINE_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if not _HEADER_PLACEHOLDER_RE.search(value):
                headers[key] = value
    return headers


def _parse_response_lines(
    lines: list[str],
) -> tuple[int, dict[str, str], Optional[str], Optional[Delay], Optional[FaultType]]:
    """Extract status, response headers, body, delay, and fault from a RESPONSE section."""
    status = 200
    delay: Optional[Delay] = None
    fault: Optional[FaultType] = None
    response_headers: dict[str, str] = {}
    body_start_idx: Optional[int] = None

    for i, line in enumerate(lines):
        if body_start_idx is not None:
            break
        m = _HEADER_LINE_RE.match(line)
        if not m:
            body_start_idx = i
            continue
        key, value = m.group(1), m.group(2).strip()
        if key == "Status":
            try:
                status = int(value)
            except ValueError:
                pass
        elif key == "Delay":
            delay = _parse_delay(value)
        elif key == "Fault":
            fault = _FAULT_ALIASES.get(value.lower())
        else:
            response_headers[key] = value

    body: Optional[str] = None
    if body_start_idx is not None:
        body = "\n".join(lines[body_start_idx:]).strip() or None

    return status, response_headers, body, delay, fault


def _parse_fault(value: str) -> Optional[FaultType]:
    """Map a user-facing fault alias to a FaultType. Returns None for unknown values."""
    return _FAULT_ALIASES.get(value.strip().lower())


def _parse_delay(value: str) -> Optional[Delay]:
    """Parse a Delay field value into a Delay model.

    Supported formats:
        500ms                    → fixed 500 ms
        random:100ms-500ms       → uniform random between 100 and 500 ms
        chunked:5,1000ms         → chunked dribble: 5 chunks over 1000 ms total
        lognormal:80ms,0.4       → log-normal: median 80 ms, sigma 0.4
    """
    v = value.strip()

    m = _DELAY_FIXED_RE.match(v)
    if m:
        return Delay(type=DelayType.FIXED, ms=int(m.group(1)))

    m = _DELAY_RANDOM_RE.match(v)
    if m:
        return Delay(type=DelayType.RANDOM, min_ms=int(m.group(1)), max_ms=int(m.group(2)))

    m = _DELAY_CHUNKED_RE.match(v)
    if m:
        return Delay(type=DelayType.CHUNKED, chunks=int(m.group(1)), chunk_ms=int(m.group(2)))

    m = _DELAY_LOGNORMAL_RE.match(v)
    if m:
        return Delay(type=DelayType.LOGNORMAL, ms=int(m.group(1)), sigma=float(m.group(2)))

    return None
