"""Level 3 JSON parser — full Mockingbird JSON format with dynamic parameters."""
from __future__ import annotations

import json
from typing import Any, Optional

from ..models import (
    Delay, DelayType, FaultType, HttpMethod, MatchCondition, MatchType,
    ParsedFile, ParsedRequestSpec, ParsedScenario, ParsedStub,
    ValidationError, ValidationResult,
)
from .base import BaseParser

_VALID_METHODS = {m.value for m in HttpMethod}
_VALID_MATCH_TYPES = {m.value for m in MatchType}
_VALID_FAULT_TYPES = {f.value for f in FaultType}


class JsonLevel3Parser(BaseParser):

    @property
    def format_name(self) -> str:
        return "level-3-json"

    def can_handle(self, content: str, filename: str) -> bool:
        try:
            data = json.loads(content)
            return (
                isinstance(data, dict)
                and data.get("_mockingbird") == "1.0"
                and "request" in data
                and "scenarios" in data
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

        if data.get("_mockingbird") != "1.0":
            errors.append(ValidationError(field="_mockingbird", message="Must be '1.0'"))

        request = data.get("request", {})
        method = request.get("method", "")
        if not method:
            errors.append(ValidationError(field="request.method", message="method is required"))
        elif method.upper() not in _VALID_METHODS:
            errors.append(ValidationError(field="request.method", message=f"'{method}' is not a valid HTTP method"))

        url = request.get("url", "")
        if not url:
            errors.append(ValidationError(field="request.url", message="url is required"))
        elif not url.startswith("/"):
            errors.append(ValidationError(field="request.url", message=f"url must start with / — got '{url}'"))

        scenarios = data.get("scenarios", [])
        if not scenarios:
            errors.append(ValidationError(field="scenarios", message="At least one scenario is required"))
        else:
            has_always = any(
                s.get("match", {}).get("type") == MatchType.ALWAYS.value
                for s in scenarios
                if not str(s.get("_scenario", "")).startswith("_")
            )
            if not has_always:
                errors.append(ValidationError(
                    field="scenarios",
                    message="Missing a default (type: always) scenario as the last scenario"
                ))

            for i, scenario in enumerate(scenarios):
                if isinstance(scenario, dict) and "_scenario" in scenario:
                    if all(k.startswith("_") for k in scenario):
                        continue
                match = scenario.get("match", {})
                match_type = match.get("type")
                if not match_type:
                    errors.append(ValidationError(
                        field=f"scenarios[{i}].match.type",
                        message="match.type is required"
                    ))
                elif match_type not in _VALID_MATCH_TYPES:
                    errors.append(ValidationError(
                        field=f"scenarios[{i}].match.type",
                        message=f"'{match_type}' is not valid. Use: {', '.join(sorted(_VALID_MATCH_TYPES))}"
                    ))

                status = scenario.get("response", {}).get("status")
                if status is not None:
                    try:
                        code = int(status)
                        if not (100 <= code <= 599):
                            errors.append(ValidationError(
                                field=f"scenarios[{i}].response.status",
                                message=f"{code} is not a valid HTTP status code"
                            ))
                    except (TypeError, ValueError):
                        errors.append(ValidationError(
                            field=f"scenarios[{i}].response.status",
                            message=f"status must be a number"
                        ))

        if errors:
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        endpoint_count = 1
        real_scenarios = [s for s in scenarios if not all(k.startswith("_") for k in s)]
        return ValidationResult(
            valid=True,
            format_detected=self.format_name,
            summary=f"{endpoint_count} endpoint detected · {len(real_scenarios)} scenarios",
        )

    def parse(self, content: str, source_file: str) -> ParsedFile:
        data = json.loads(content)

        stub_meta = data.get("stub", {})
        request_data = data.get("request", {})
        scenarios_data = data.get("scenarios", [])

        method = HttpMethod(request_data["method"].upper())
        url = request_data["url"]
        required_headers: dict[str, str] = {}
        header_config = request_data.get("headers", {})
        for h in header_config.get("required", []):
            required_headers[h] = "*"

        request = ParsedRequestSpec(method=method, url=url, required_headers=required_headers)

        scenarios: list[ParsedScenario] = []
        for scenario_data in scenarios_data:
            if all(k.startswith("_") for k in scenario_data):
                continue

            match_data = scenario_data.get("match", {})
            match = MatchCondition(
                type=MatchType(match_data.get("type", MatchType.ALWAYS.value)),
                value=match_data.get("value"),
            )

            response = scenario_data.get("response", {})
            status = int(response.get("status", 200))

            response_headers: dict[str, str] = {}
            for k, v in response.get("headers", {}).items():
                if not k.startswith("_"):
                    response_headers[k] = str(v)

            body_data = response.get("body")
            body: Optional[str] = None
            if body_data is not None:
                if isinstance(body_data, (dict, list)):
                    body = json.dumps(body_data, indent=2)
                else:
                    body = str(body_data)

            delay = _parse_delay_config(response.get("delay"))

            fault_str = response.get("fault")
            fault = FaultType(fault_str) if fault_str in _VALID_FAULT_TYPES else None

            scenario_name = scenario_data.get("_scenario", f"scenario-{len(scenarios)+1}")
            scenario_name = scenario_name.split("—")[-1].strip() if "—" in scenario_name else scenario_name

            scenarios.append(ParsedScenario(
                name=scenario_name,
                match=match,
                status=status,
                response_headers=response_headers,
                body=body,
                delay=delay,
                fault=fault,
            ))

        stub = ParsedStub(
            name=stub_meta.get("name", "Stub"),
            description=stub_meta.get("description", ""),
            team=stub_meta.get("team", ""),
            contact=stub_meta.get("contact", ""),
            request=request,
            scenarios=scenarios,
        )
        return ParsedFile(format=self.format_name, source_file=source_file, stubs=[stub])


def _parse_delay_config(delay_data: Optional[dict[str, Any]]) -> Optional[Delay]:
    if not delay_data or not isinstance(delay_data, dict):
        return None
    delay_type = DelayType(delay_data.get("type", DelayType.FIXED.value))
    return Delay(
        type=delay_type,
        ms=delay_data.get("ms"),
        min_ms=delay_data.get("min_ms"),
        max_ms=delay_data.get("max_ms"),
        start_ms=delay_data.get("start_ms"),
        increment_ms=delay_data.get("increment_ms"),
        max_limit_ms=delay_data.get("max_ms"),
        chunk_ms=delay_data.get("chunk_ms"),
        chunk_size_bytes=delay_data.get("chunk_size_bytes"),
    )
