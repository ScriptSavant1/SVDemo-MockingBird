"""Postman v2.1 collection parser."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..models import (
    HttpMethod, MatchCondition, MatchType, ParsedFile,
    ParsedRequestSpec, ParsedScenario, ParsedStub,
    ValidationError, ValidationResult,
)
from .base import BaseParser

_VALID_METHODS = {m.value for m in HttpMethod}
_POSTMAN_VAR_RE = re.compile(r'\{\{([^}]+)\}\}')


class PostmanParser(BaseParser):

    @property
    def format_name(self) -> str:
        return "postman-v2.1"

    def can_handle(self, content: str, filename: str) -> bool:
        try:
            data = json.loads(content)
            schema = data.get("info", {}).get("schema", "")
            return (
                isinstance(data, dict)
                and "info" in data
                and "item" in data
                and "v2.1" in schema
            )
        except (json.JSONDecodeError, AttributeError):
            return False

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return ValidationResult(
                valid=False,
                format_detected=self.format_name,
                errors=[ValidationError(message=f"Invalid JSON: {exc}")],
            )

        schema = data.get("info", {}).get("schema", "")
        if "v2.1" not in schema:
            errors.append(ValidationError(
                field="info.schema",
                message="Expected Postman v2.1 schema (info.schema must contain 'v2.1')",
            ))

        if "item" not in data:
            errors.append(ValidationError(field="item", message="Collection is missing 'item' array"))

        if errors:
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        requests = list(_flatten_items(data.get("item", [])))
        if not requests:
            return ValidationResult(
                valid=False,
                format_detected=self.format_name,
                errors=[ValidationError(
                    field="item",
                    message="No requests found (collection may contain only empty folders)",
                )],
            )

        total_responses = sum(len(r.get("response", [])) for r in requests)
        warnings: list[str] = []
        if total_responses == 0:
            warnings.append(
                "No saved responses found in collection. Stubs will return HTTP 200 with an empty "
                "body. Open each request in Postman, send it, and use 'Save Response' to capture "
                "examples — then re-export the collection."
            )

        return ValidationResult(
            valid=True,
            format_detected=self.format_name,
            summary=f"{len(requests)} endpoint(s) · {total_responses} saved response(s)",
            warnings=warnings,
        )

    def parse(self, content: str, source_file: str) -> ParsedFile:
        data = json.loads(content)
        requests = list(_flatten_items(data.get("item", [])))

        stubs: list[ParsedStub] = []
        for item in requests:
            stub = _item_to_stub(item)
            if stub is not None:
                stubs.append(stub)

        return ParsedFile(format=self.format_name, source_file=source_file, stubs=stubs)


# ── helpers ───────────────────────────────────────────────────────────────────

def _flatten_items(items: list[dict[str, Any]]) -> Any:
    """Recursively yield leaf request items, skipping folder containers."""
    for item in items:
        if "item" in item:
            yield from _flatten_items(item["item"])
        elif "request" in item:
            yield item


def _item_to_stub(item: dict[str, Any]) -> Optional[ParsedStub]:
    request_data = item.get("request", {})
    if not isinstance(request_data, dict):
        return None

    method_str = request_data.get("method", "GET").upper()
    if method_str not in _VALID_METHODS:
        method_str = "GET"

    url = _extract_url(request_data.get("url", ""))
    if not url:
        return None

    required_headers: dict[str, str] = {}
    for h in request_data.get("header", []):
        key = h.get("key", "")
        value = h.get("value", "")
        if key and value and not h.get("disabled") and "{{" not in value:
            required_headers[key] = value

    saved_responses = [r for r in item.get("response", []) if isinstance(r, dict)]
    scenarios = _build_scenarios(saved_responses)

    return ParsedStub(
        name=item.get("name", "Stub"),
        request=ParsedRequestSpec(
            method=HttpMethod(method_str),
            url=url,
            required_headers=required_headers,
        ),
        scenarios=scenarios,
    )


def _extract_url(url_field: Any) -> str:
    """Extract a clean path string from a Postman URL (string or object)."""
    if isinstance(url_field, str):
        raw = url_field
    elif isinstance(url_field, dict):
        raw = url_field.get("raw", "")
        if not raw:
            path_parts = url_field.get("path", [])
            raw = "/" + "/".join(str(p) for p in path_parts) if path_parts else ""
    else:
        return ""

    if not raw:
        return ""

    # Strip protocol + host (https://host/path → /path)
    if "://" in raw:
        after = raw.split("://", 1)[1]
        raw = "/" + after.split("/", 1)[1] if "/" in after else "/"

    # Strip bare Postman host variable: {{baseUrl}}/path → /path
    elif raw.startswith("{{") and "/" in raw:
        raw = "/" + raw.split("/", 1)[1]

    # Remove query string and fragment
    raw = raw.split("?")[0].split("#")[0].strip()

    # Convert Postman {{varName}} path segments → WireMock {varName}
    raw = _POSTMAN_VAR_RE.sub(r'{\1}', raw)

    return raw if raw.startswith("/") else f"/{raw}"


def _build_scenarios(saved_responses: list[dict[str, Any]]) -> list[ParsedScenario]:
    """Convert Postman saved responses to ParsedScenario list.

    2xx responses are placed first (highest WireMock priority) so they are returned
    by default with ALWAYS match. Non-2xx responses follow at lower priority — they
    are dormant until the user adds body/header conditions to their mapping files.
    """
    if not saved_responses:
        return [ParsedScenario(
            name="default",
            match=MatchCondition(type=MatchType.ALWAYS),
            status=200,
            response_headers={"Content-Type": "application/json"},
        )]

    def _is_success(r: dict[str, Any]) -> bool:
        return 200 <= int(r.get("code", 200)) <= 299

    # 2xx first (scenario[0] → highest WireMock priority → returned by default)
    # non-2xx after (lower priority, dormant until conditions added)
    sorted_responses = sorted(saved_responses, key=lambda r: (0 if _is_success(r) else 1))

    scenarios: list[ParsedScenario] = []
    for resp in sorted_responses:
        code = int(resp.get("code", 200))
        name = resp.get("name", f"response-{code}")

        headers: dict[str, str] = {}
        for h in resp.get("header", []):
            key = h.get("key", "")
            value = h.get("value", "")
            if key and value and not h.get("disabled"):
                headers[key] = value

        body_raw = resp.get("body") or ""
        body: Optional[str] = body_raw.strip() or None

        scenarios.append(ParsedScenario(
            name=name,
            match=MatchCondition(type=MatchType.ALWAYS),
            status=code,
            response_headers=headers,
            body=body,
        ))

    return scenarios
