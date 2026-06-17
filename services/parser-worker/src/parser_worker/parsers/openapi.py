"""OpenAPI 3.x and Swagger 2.0 parser (JSON and YAML)."""
from __future__ import annotations

import json
from typing import Any, Optional

from ..models import (
    HttpMethod, MatchCondition, MatchType, ParsedFile,
    ParsedRequestSpec, ParsedScenario, ParsedStub,
    ValidationError, ValidationResult,
)
from .base import BaseParser

_VALID_METHODS = {m.value for m in HttpMethod}


class OpenApiParser(BaseParser):

    @property
    def format_name(self) -> str:
        return "openapi"

    def can_handle(self, content: str, filename: str) -> bool:
        data = _load_content(content)
        if not isinstance(data, dict):
            return False
        return bool(data.get("openapi") or data.get("swagger") == "2.0")

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []

        data = _load_content(content)
        if data is None:
            return ValidationResult(
                valid=False,
                format_detected=self.format_name,
                errors=[ValidationError(message="File is not valid JSON or YAML")],
            )
        if not isinstance(data, dict):
            return ValidationResult(
                valid=False,
                format_detected=self.format_name,
                errors=[ValidationError(message="Expected a JSON/YAML object at the root level")],
            )

        version = data.get("openapi") or data.get("swagger")
        if not version:
            errors.append(ValidationError(
                field="openapi",
                message="Missing 'openapi' (3.x) or 'swagger' (2.0) version field",
            ))

        if "paths" not in data:
            errors.append(ValidationError(field="paths", message="Missing 'paths' object"))

        if errors:
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        paths = data.get("paths", {})
        endpoint_count = sum(
            1
            for path_item in paths.values()
            if isinstance(path_item, dict)
            for key in path_item
            if key.upper() in _VALID_METHODS
        )

        if endpoint_count == 0:
            errors.append(ValidationError(
                field="paths",
                message="No HTTP operations found. Ensure paths contain GET/POST/PUT/PATCH/DELETE operations.",
            ))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        openapi_ver = data.get("openapi", "")
        swagger_ver = data.get("swagger", "")
        spec_label = f"OpenAPI {openapi_ver}" if openapi_ver else f"Swagger {swagger_ver}"

        return ValidationResult(
            valid=True,
            format_detected=self.format_name,
            summary=f"{endpoint_count} endpoint(s) · {spec_label}",
        )

    def parse(self, content: str, source_file: str) -> ParsedFile:
        data = _load_content(content)
        is_swagger2 = "swagger" in data and "openapi" not in data

        # For $ref resolution: components/schemas (OpenAPI 3) or definitions (Swagger 2)
        if is_swagger2:
            components: dict[str, Any] = {"schemas": data.get("definitions", {})}
        else:
            components = data.get("components", {})

        stubs: list[ParsedStub] = []
        for path, path_item in data.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method.upper() not in _VALID_METHODS:
                    continue
                if not isinstance(operation, dict):
                    continue
                stub = _operation_to_stub(path, method, operation, components, is_swagger2)
                if stub is not None:
                    stubs.append(stub)

        return ParsedFile(format=self.format_name, source_file=source_file, stubs=stubs)


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_content(content: str) -> Optional[dict[str, Any]]:
    """Parse content as JSON, then YAML as fallback."""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        import yaml  # pyyaml — listed in pyproject.toml dependencies
        result = yaml.safe_load(content)
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def _operation_to_stub(
    path: str,
    method: str,
    operation: dict[str, Any],
    components: dict[str, Any],
    is_swagger2: bool,
) -> Optional[ParsedStub]:
    name = (
        operation.get("summary")
        or operation.get("operationId")
        or f"{method.upper()} {path}"
    )
    responses = operation.get("responses", {})
    scenarios = _build_scenarios(responses, components, is_swagger2)

    if not scenarios:
        return None

    return ParsedStub(
        name=name,
        description=operation.get("description", ""),
        request=ParsedRequestSpec(method=HttpMethod(method.upper()), url=path),
        scenarios=scenarios,
    )


def _build_scenarios(
    responses: dict[str, Any],
    components: dict[str, Any],
    is_swagger2: bool,
) -> list[ParsedScenario]:
    """Build scenarios from OpenAPI/Swagger response objects.

    2xx responses are placed first (highest WireMock priority, ALWAYS match → default).
    Non-2xx follow at lower priority — dormant until the user adds conditions.
    """
    scenarios: list[ParsedScenario] = []

    def _is_success(code_str: str) -> bool:
        try:
            return 200 <= int(code_str) <= 299
        except ValueError:
            return True  # "default" key → treat as success

    # 2xx first, non-2xx after
    sorted_codes = sorted(responses.keys(), key=lambda c: (0 if _is_success(c) else 1))

    for code_str in sorted_codes:
        response = responses[code_str]
        if not isinstance(response, dict):
            continue

        try:
            status = int(code_str)
        except ValueError:
            status = 200  # "default" key

        body, content_type = (
            _extract_swagger2_body(response, components)
            if is_swagger2
            else _extract_openapi3_body(response, components)
        )

        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        for header_name, header_spec in response.get("headers", {}).items():
            if isinstance(header_spec, dict) and "example" in header_spec:
                headers[header_name] = str(header_spec["example"])

        name = response.get("description") or f"HTTP {status}"

        scenarios.append(ParsedScenario(
            name=name,
            match=MatchCondition(type=MatchType.ALWAYS),
            status=status,
            response_headers=headers,
            body=body,
        ))

    return scenarios


def _extract_openapi3_body(
    response: dict[str, Any],
    components: dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    content = response.get("content", {})
    if not content:
        return None, None

    # Prefer JSON; accept anything
    content_type: Optional[str] = None
    media_obj: Optional[dict[str, Any]] = None
    for ct in ("application/json", "text/plain", "application/xml"):
        if ct in content:
            content_type, media_obj = ct, content[ct]
            break
    if media_obj is None:
        ct_key, media_obj = next(iter(content.items()), (None, None))
        content_type = ct_key

    if not isinstance(media_obj, dict):
        return None, content_type

    # Priority: inline example → named examples → schema example → generated
    if "example" in media_obj:
        return _serialise(media_obj["example"], content_type), content_type

    named_examples = media_obj.get("examples", {})
    if named_examples:
        first = next(iter(named_examples.values()), None)
        if isinstance(first, dict) and "value" in first:
            return _serialise(first["value"], content_type), content_type

    schema = _resolve_ref(media_obj.get("schema", {}), components)
    if "example" in schema:
        return _serialise(schema["example"], content_type), content_type

    generated = _generate_from_schema(schema, components, depth=0)
    return (_serialise(generated, content_type) if generated is not None else None), content_type


def _extract_swagger2_body(
    response: dict[str, Any],
    components: dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    examples = response.get("examples", {})
    if examples:
        json_ex = examples.get("application/json")
        if json_ex is not None:
            return _serialise(json_ex, "application/json"), "application/json"
        first_ct, first_val = next(iter(examples.items()), (None, None))
        if first_val is not None:
            return _serialise(first_val, first_ct), first_ct

    schema = _resolve_ref(response.get("schema", {}), components)
    if "example" in schema:
        return _serialise(schema["example"], "application/json"), "application/json"

    generated = _generate_from_schema(schema, components, depth=0)
    return (_serialise(generated, "application/json") if generated is not None else None, "application/json")


def _resolve_ref(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local $ref (e.g. '#/components/schemas/Foo') within this spec."""
    ref = schema.get("$ref", "")
    if not ref or not ref.startswith("#/"):
        return schema
    parts = ref.lstrip("#/").split("/")
    # parts[0] = "components" or "definitions"; parts[1] = "schemas"; parts[2] = name
    node: Any = components
    for part in parts[1:]:  # skip the first segment ("components"/"definitions")
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def _generate_from_schema(
    schema: dict[str, Any],
    components: dict[str, Any],
    depth: int,
) -> Any:
    """Generate a minimal example value from an OpenAPI schema."""
    if depth > 2:
        return None

    schema = _resolve_ref(schema, components)
    if not schema:
        return None

    if "example" in schema:
        return schema["example"]

    # Treat as object if properties present even without explicit type
    schema_type = schema.get("type") or ("object" if "properties" in schema else None)

    if schema_type == "object" or "properties" in schema:
        result: dict[str, Any] = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            val = _generate_from_schema(prop_schema, components, depth + 1)
            result[prop_name] = val
        return result

    if schema_type == "array":
        item = _generate_from_schema(schema.get("items", {}), components, depth + 1)
        return [item] if item is not None else []

    if schema_type == "string":
        if schema.get("enum"):
            return schema["enum"][0]
        fmt = schema.get("format", "")
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "date":
            return "2024-01-01"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return "string"

    if schema_type in ("integer", "number"):
        return 0

    if schema_type == "boolean":
        return True

    return None


def _serialise(value: Any, content_type: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2)
