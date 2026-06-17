"""Level 2 TXT parser — single request, multiple named scenarios."""
from __future__ import annotations

import re
from typing import Optional

from ..models import (
    Delay, HttpMethod, MatchCondition, MatchType, ParsedFile,
    ParsedRequestSpec, ParsedScenario, ParsedStub, ValidationError, ValidationResult,
)
from .base import BaseParser
from .txt_level1 import (
    _extract_field, _FAULT_ALIASES, _parse_delay, _parse_request_headers,
    _parse_response_lines, _split_into_sections, _VALID_METHODS,
)

_NAMED_SCENARIO_RE = re.compile(r'^--- SCENARIO:\s*(.+?)\s*---$')
_DEFAULT_SCENARIO_RE = re.compile(r'^--- SCENARIO DEFAULT\s*---$')
_MATCH_TYPES = {m.value for m in MatchType}


class TxtLevel2Parser(BaseParser):

    @property
    def format_name(self) -> str:
        return "level-2-txt"

    def can_handle(self, content: str, filename: str) -> bool:
        first_line = content.strip().splitlines()[0].strip() if content.strip() else ""
        return (
            first_line == "--- MOCKINGBIRD v1.0 ---"
            and (
                "--- SCENARIO:" in content
                or "--- SCENARIO DEFAULT ---" in content
            )
        )

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []
        lines = content.strip().splitlines()

        if not lines or lines[0].strip() != "--- MOCKINGBIRD v1.0 ---":
            errors.append(ValidationError(line=1, message="File must start with '--- MOCKINGBIRD v1.0 ---'"))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        meta_lines, _, raw_scenarios = _split_level2_sections(lines)

        method_str = _extract_field(meta_lines, "Method")
        if not method_str:
            errors.append(ValidationError(field="Method", message="Method is required"))
        elif method_str.upper() not in _VALID_METHODS:
            errors.append(ValidationError(field="Method", message=f"'{method_str}' is not a valid HTTP method"))

        url = _extract_field(meta_lines, "URL")
        if not url:
            errors.append(ValidationError(field="URL", message="URL is required"))
        elif not url.startswith("/"):
            errors.append(ValidationError(field="URL", message=f"URL must start with / — got '{url}'"))

        if not raw_scenarios:
            errors.append(ValidationError(message="No scenarios found. Add at least '--- SCENARIO DEFAULT ---'"))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        has_default = any(name == "default" for name, _ in raw_scenarios)
        if not has_default:
            errors.append(ValidationError(message="Missing '--- SCENARIO DEFAULT ---' at end of file"))

        for scenario_name, scenario_lines in raw_scenarios:
            if scenario_name == "default":
                continue
            match_type = _extract_field(scenario_lines, "Match-Type")
            if not match_type:
                errors.append(ValidationError(
                    field="Match-Type",
                    message=f"Scenario '{scenario_name}' is missing Match-Type"
                ))
            elif match_type not in _MATCH_TYPES:
                errors.append(ValidationError(
                    field="Match-Type",
                    message=f"Scenario '{scenario_name}': '{match_type}' is not a valid match type. "
                            f"Valid: {', '.join(sorted(_MATCH_TYPES))}"
                ))
            match_value = _extract_field(scenario_lines, "Match-Value")
            if match_type and match_type != MatchType.ALWAYS.value and not match_value:
                errors.append(ValidationError(
                    field="Match-Value",
                    message=f"Scenario '{scenario_name}' has Match-Type '{match_type}' but no Match-Value"
                ))

            fault_val = _extract_field(scenario_lines, "Fault")
            if fault_val and fault_val.lower() not in _FAULT_ALIASES:
                errors.append(ValidationError(
                    field="Fault",
                    message=(
                        f"Scenario '{scenario_name}': '{fault_val}' is not valid. "
                        f"Use: {', '.join(sorted(_FAULT_ALIASES))}"
                    ),
                ))

        if errors:
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        endpoint_count = 1
        scenario_count = len(raw_scenarios)
        return ValidationResult(
            valid=True,
            format_detected=self.format_name,
            summary=f"{endpoint_count} endpoint detected · {scenario_count} scenarios",
        )

    def parse(self, content: str, source_file: str) -> ParsedFile:
        lines = content.strip().splitlines()
        meta_lines, header_lines, raw_scenarios = _split_level2_sections(lines)

        method = HttpMethod(_extract_field(meta_lines, "Method", default="GET").upper())
        url = _extract_field(meta_lines, "URL", default="/")
        name = _extract_field(meta_lines, "Name", default="Stub")
        required_headers = _parse_request_headers(header_lines)

        request = ParsedRequestSpec(method=method, url=url, required_headers=required_headers)

        total = len(raw_scenarios)
        scenarios: list[ParsedScenario] = []

        for i, (scenario_name, scenario_lines) in enumerate(raw_scenarios):
            priority_index = i

            if scenario_name == "default":
                match = MatchCondition(type=MatchType.ALWAYS)
            else:
                raw_type = _extract_field(scenario_lines, "Match-Type", default="always")
                raw_value = _extract_field(scenario_lines, "Match-Value")
                match = MatchCondition(
                    type=MatchType(raw_type),
                    value=raw_value or None,
                )

            response_only_lines = [
                line for line in scenario_lines
                if not line.startswith("Match-Type:")
                and not line.startswith("Match-Value:")
            ]
            status, response_headers, body, delay, fault = _parse_response_lines(response_only_lines)

            scenarios.append(ParsedScenario(
                name=scenario_name,
                match=match,
                status=status,
                response_headers=response_headers,
                body=body,
                delay=delay,
                fault=fault,
            ))

        stub = ParsedStub(name=name, request=request, scenarios=scenarios)
        return ParsedFile(format=self.format_name, source_file=source_file, stubs=[stub])


def _split_level2_sections(
    lines: list[str],
) -> tuple[list[str], list[str], list[tuple[str, list[str]]]]:
    """Split Level 2 file into (meta_lines, header_lines, [(scenario_name, lines)])."""
    meta_lines: list[str] = []
    header_lines: list[str] = []
    scenarios: list[tuple[str, list[str]]] = []

    current_section = "meta"
    current_scenario_name: Optional[str] = None
    current_scenario_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == "--- MOCKINGBIRD v1.0 ---" or stripped.startswith("#") or not stripped:
            continue

        if stripped == "--- REQUEST HEADERS ---":
            current_section = "headers"
            continue

        if _DEFAULT_SCENARIO_RE.match(stripped):
            if current_scenario_name is not None:
                scenarios.append((current_scenario_name, current_scenario_lines))
            current_scenario_name = "default"
            current_scenario_lines = []
            current_section = "scenario"
            continue

        m = _NAMED_SCENARIO_RE.match(stripped)
        if m:
            if current_scenario_name is not None:
                scenarios.append((current_scenario_name, current_scenario_lines))
            current_scenario_name = m.group(1)
            current_scenario_lines = []
            current_section = "scenario"
            continue

        if current_section == "meta":
            meta_lines.append(stripped)
        elif current_section == "headers":
            header_lines.append(stripped)
        elif current_section == "scenario" and current_scenario_name is not None:
            current_scenario_lines.append(stripped)

    if current_scenario_name is not None:
        scenarios.append((current_scenario_name, current_scenario_lines))

    return meta_lines, header_lines, scenarios
