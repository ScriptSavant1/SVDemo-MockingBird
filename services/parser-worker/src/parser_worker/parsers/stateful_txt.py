"""Stateful TXT parser — multi-step state machine flows for WireMock.

Format example (banking session):

    --- MOCKINGBIRD v1.0 STATEFUL ---

    Scenario: Banking Session
    Description: Login, fetch account, transfer, logout

    --- STEP: Login ---
    State-In: Started
    State-Out: Authenticated
    Method: POST
    URL: /auth/login
    Status: 200
    Content-Type: application/json

    {"token": "{{randomValue type='UUID'}}", "expiresAt": "{{now format='yyyy-MM-ddTHH:mm:ss'}}"}

    --- STEP: Get Account ---
    State-In: Authenticated
    State-Out: Authenticated
    Method: GET
    URL: /api/v1/account
    Status: 200
    Content-Type: application/json

    {"accountId": "ACC-001", "balance": 15000.00, "currency": "GBP"}

    --- STEP: Logout ---
    State-In: Authenticated
    State-Out: Started
    Method: DELETE
    URL: /auth/logout
    Status: 204

Each step becomes one WireMock mapping file with:
    scenarioName            → Scenario: field
    requiredScenarioState   → State-In: field
    newScenarioState        → State-Out: field

WireMock initialises every scenario to state "Started" on startup.
State transitions are per-scenario-name, shared across all stub mappings
that declare the same scenarioName.

Branching flows (multiple steps sharing the same State-In) are supported —
WireMock picks the first matching stub in that state, using request
method + URL to disambiguate.
"""
from __future__ import annotations

import re
from typing import Optional

from ..models import (
    HttpMethod, MatchCondition, MatchType,
    ParsedFile, ParsedRequestSpec, ParsedScenario, ParsedStub,
    ValidationError, ValidationResult,
)
from .base import BaseParser
from .txt_level1 import _extract_field, _FAULT_ALIASES, _parse_response_lines, _VALID_METHODS

_STATEFUL_HEADER = "--- MOCKINGBIRD v1.0 STATEFUL ---"
_STEP_RE = re.compile(r'^--- STEP:\s*(.+?)\s*---$')

# Fields that belong to the request/state spec, not the response section.
_REQUEST_FIELDS = frozenset({"State-In", "State-Out", "Method", "URL"})


class StatefulTxtParser(BaseParser):

    @property
    def format_name(self) -> str:
        return "stateful-txt"

    def can_handle(self, content: str, filename: str) -> bool:
        first_line = content.strip().splitlines()[0].strip() if content.strip() else ""
        return first_line == _STATEFUL_HEADER

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []
        lines = content.strip().splitlines()

        if not lines or lines[0].strip() != _STATEFUL_HEADER:
            errors.append(ValidationError(
                line=1,
                message=f"File must start with '{_STATEFUL_HEADER}'",
            ))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        meta_lines, steps = _split_stateful_sections(lines)

        scenario_name = _extract_field(meta_lines, "Scenario")
        if not scenario_name:
            errors.append(ValidationError(
                field="Scenario",
                message="Scenario name is required (e.g., Scenario: Banking Session)",
            ))

        if len(steps) < 2:
            errors.append(ValidationError(
                message=(
                    f"Stateful flows require at least 2 steps — "
                    f"{len(steps)} found. "
                    f"Add '--- STEP: Name ---' sections."
                ),
            ))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        seen_names: set[str] = set()
        for step_name, step_lines in steps:
            if step_name in seen_names:
                errors.append(ValidationError(
                    field="Step",
                    message=f"Duplicate step name: '{step_name}' — step names must be unique within a file",
                ))
            seen_names.add(step_name)

            method_str = _extract_field(step_lines, "Method")
            if not method_str:
                errors.append(ValidationError(
                    field="Method",
                    message=f"Step '{step_name}': Method is required",
                ))
            elif method_str.upper() not in _VALID_METHODS:
                errors.append(ValidationError(
                    field="Method",
                    message=f"Step '{step_name}': '{method_str}' is not a valid HTTP method",
                ))

            url = _extract_field(step_lines, "URL")
            if not url:
                errors.append(ValidationError(
                    field="URL",
                    message=f"Step '{step_name}': URL is required",
                ))
            elif not url.startswith("/"):
                errors.append(ValidationError(
                    field="URL",
                    message=f"Step '{step_name}': URL must start with / — got '{url}'",
                ))

            if not _extract_field(step_lines, "State-In"):
                errors.append(ValidationError(
                    field="State-In",
                    message=f"Step '{step_name}': State-In is required (e.g., State-In: Started)",
                ))

            if not _extract_field(step_lines, "State-Out"):
                errors.append(ValidationError(
                    field="State-Out",
                    message=f"Step '{step_name}': State-Out is required (e.g., State-Out: Authenticated)",
                ))

            status_str = _extract_field(step_lines, "Status")
            if not status_str:
                errors.append(ValidationError(
                    field="Status",
                    message=f"Step '{step_name}': Status is required",
                ))
            else:
                try:
                    code = int(status_str)
                    if not (100 <= code <= 599):
                        errors.append(ValidationError(
                            field="Status",
                            message=f"Step '{step_name}': {code} is not a valid HTTP status code",
                        ))
                except ValueError:
                    errors.append(ValidationError(
                        field="Status",
                        message=f"Step '{step_name}': Status must be a number, got '{status_str}'",
                    ))

            fault_val = _extract_field(step_lines, "Fault")
            if fault_val and fault_val.lower() not in _FAULT_ALIASES:
                errors.append(ValidationError(
                    field="Fault",
                    message=(
                        f"Step '{step_name}': '{fault_val}' is not valid. "
                        f"Use: {', '.join(sorted(_FAULT_ALIASES))}"
                    ),
                ))

        warnings: list[str] = []
        if not errors and steps:
            first_state_in = _extract_field(steps[0][1], "State-In")
            if first_state_in and first_state_in != "Started":
                warnings.append(
                    f"First step '{steps[0][0]}' has State-In: '{first_state_in}' "
                    f"but WireMock initialises all scenarios to 'Started'. "
                    f"This step will not match until state is manually set."
                )

        if errors:
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        return ValidationResult(
            valid=True,
            format_detected=self.format_name,
            warnings=warnings,
            summary=f"{len(steps)} steps in stateful scenario '{scenario_name}'",
        )

    def parse(self, content: str, source_file: str) -> ParsedFile:
        lines = content.strip().splitlines()
        meta_lines, steps = _split_stateful_sections(lines)

        scenario_name = _extract_field(meta_lines, "Scenario", default="Scenario")
        description = _extract_field(meta_lines, "Description", default="")

        stubs: list[ParsedStub] = []
        for step_name, step_lines in steps:
            state_in = _extract_field(step_lines, "State-In", default="Started")
            state_out = _extract_field(step_lines, "State-Out", default="Started")
            method_str = _extract_field(step_lines, "Method", default="GET").upper()
            url = _extract_field(step_lines, "URL", default="/")

            # Strip request/state meta fields — leave Status, Content-Type, Delay, body.
            # Only strip lines that appear BEFORE the body starts (header-style lines).
            # We filter by key name to avoid touching body content.
            response_lines = _strip_request_fields(step_lines)
            status, response_headers, body, delay, fault = _parse_response_lines(response_lines)

            scenario = ParsedScenario(
                name=step_name,
                match=MatchCondition(type=MatchType.ALWAYS),
                status=status,
                response_headers=response_headers,
                body=body,
                delay=delay,
                fault=fault,
                scenario_name=scenario_name,
                required_state=state_in,
                new_state=state_out,
            )
            stub = ParsedStub(
                name=scenario_name,
                description=description,
                request=ParsedRequestSpec(
                    method=HttpMethod(method_str),
                    url=url,
                ),
                scenarios=[scenario],
            )
            stubs.append(stub)

        return ParsedFile(format=self.format_name, source_file=source_file, stubs=stubs)


# ── private helpers ───────────────────────────────────────────────────────────

def _split_stateful_sections(
    lines: list[str],
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Return (meta_lines, [(step_name, step_lines)]).

    meta_lines: lines before the first STEP delimiter.
    step_lines: raw lines inside each STEP block (blanks and comments stripped).
    """
    meta_lines: list[str] = []
    steps: list[tuple[str, list[str]]] = []
    current_step_name: Optional[str] = None
    current_step_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped == _STATEFUL_HEADER or stripped.startswith("#") or not stripped:
            continue

        m = _STEP_RE.match(stripped)
        if m:
            if current_step_name is not None:
                steps.append((current_step_name, current_step_lines))
            current_step_name = m.group(1)
            current_step_lines = []
            continue

        if current_step_name is None:
            meta_lines.append(stripped)
        else:
            current_step_lines.append(stripped)

    if current_step_name is not None:
        steps.append((current_step_name, current_step_lines))

    return meta_lines, steps


def _strip_request_fields(step_lines: list[str]) -> list[str]:
    """Remove request/state meta fields from step_lines, leaving response fields + body.

    Only strips lines whose key (before the first colon) matches a known request field.
    This avoids falsely removing body content that starts with these strings.
    Lines that don't contain ':' are always kept (they're body content).
    """
    result: list[str] = []
    body_started = False
    for line in step_lines:
        if body_started:
            result.append(line)
            continue
        if ":" not in line:
            # First non-header line → body has started
            body_started = True
            result.append(line)
            continue
        key = line.split(":", 1)[0].strip()
        if key in _REQUEST_FIELDS:
            continue  # drop this request meta field
        # Check if this is a response header or the start of a body
        # response headers: Status, Content-Type, Delay, etc.
        # body lines: start with {, [, <, or any non-header character
        result.append(line)

    return result
