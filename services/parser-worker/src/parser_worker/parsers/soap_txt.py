"""SOAP stub TXT parser — same structure as Level 2 but for SOAP/XML services."""
from __future__ import annotations

from ..models import (
    HttpMethod, MatchCondition, MatchType, ParsedFile,
    ParsedRequestSpec, ParsedScenario, ParsedStub,
    ValidationError, ValidationResult,
)
from .base import BaseParser
from .txt_level1 import (
    _extract_field, _FAULT_ALIASES, _parse_request_headers, _parse_response_lines,
)
from .txt_level2 import _split_level2_sections

_SOAP_HEADER = "--- MOCKINGBIRD v1.0 SOAP ---"
_STANDARD_HEADER = "--- MOCKINGBIRD v1.0 ---"

# Match-Type values accepted in SOAP format
_SOAP_MATCH_TYPES = {"soap-action", "soap-xpath", "body-contains", "always"}

# Prefix for namespace declarations in SOAP scenarios
_XPATH_NS_PREFIX = "Match-XPath-NS:"


class SoapTxtParser(BaseParser):

    @property
    def format_name(self) -> str:
        return "soap-txt"

    def can_handle(self, content: str, filename: str) -> bool:
        first_line = content.strip().splitlines()[0].strip() if content.strip() else ""
        return first_line == _SOAP_HEADER

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []
        lines = content.strip().splitlines()

        if not lines or lines[0].strip() != _SOAP_HEADER:
            errors.append(ValidationError(line=1, message=f"File must start with '{_SOAP_HEADER}'"))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        meta_lines, _, raw_scenarios = _split_level2_sections(_normalise_header(lines))

        url = _extract_field(meta_lines, "URL")
        if not url:
            errors.append(ValidationError(field="URL", message="URL is required (e.g., URL: /services/PaymentService)"))
        elif not url.startswith("/"):
            errors.append(ValidationError(field="URL", message=f"URL must start with / — got '{url}'"))

        if not raw_scenarios:
            errors.append(ValidationError(
                message="No scenarios found. Add '--- SCENARIO: Name ---' and '--- SCENARIO DEFAULT ---' sections."
            ))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        has_default = any(name == "default" for name, _ in raw_scenarios)
        if not has_default:
            errors.append(ValidationError(
                message="Missing '--- SCENARIO DEFAULT ---'. Every SOAP stub needs a fallback SOAP Fault response."
            ))

        for scenario_name, scenario_lines in raw_scenarios:
            if scenario_name == "default":
                continue
            match_type = _extract_field(scenario_lines, "Match-Type")
            if not match_type:
                errors.append(ValidationError(
                    field="Match-Type",
                    message=f"Scenario '{scenario_name}' is missing Match-Type. "
                            f"Use: {', '.join(sorted(_SOAP_MATCH_TYPES))}",
                ))
            elif match_type not in _SOAP_MATCH_TYPES:
                errors.append(ValidationError(
                    field="Match-Type",
                    message=f"Scenario '{scenario_name}': '{match_type}' is not valid. "
                            f"SOAP accepts: {', '.join(sorted(_SOAP_MATCH_TYPES))}",
                ))
            if match_type in ("soap-action", "soap-xpath", "body-contains"):
                match_value = _extract_field(scenario_lines, "Match-Value")
                if not match_value:
                    errors.append(ValidationError(
                        field="Match-Value",
                        message=f"Scenario '{scenario_name}' has Match-Type '{match_type}' but no Match-Value",
                    ))

            # Validate Match-XPath-NS: lines — each must be prefix=uri
            ns_lines = [l for l in scenario_lines if l.startswith(_XPATH_NS_PREFIX)]
            for ns_line in ns_lines:
                value = ns_line[len(_XPATH_NS_PREFIX):].strip()
                if "=" not in value or not value.split("=", 1)[0].strip():
                    errors.append(ValidationError(
                        field="Match-XPath-NS",
                        message=(
                            f"Scenario '{scenario_name}': invalid namespace declaration '{value}'. "
                            f"Expected format: Match-XPath-NS: prefix=http://namespace-uri"
                        ),
                    ))
                elif match_type and match_type != "soap-xpath":
                    errors.append(ValidationError(
                        field="Match-XPath-NS",
                        message=(
                            f"Scenario '{scenario_name}': Match-XPath-NS is only valid "
                            f"with Match-Type: soap-xpath, not '{match_type}'"
                        ),
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

        named = [(n, s) for n, s in raw_scenarios if n != "default"]
        return ValidationResult(
            valid=True,
            format_detected=self.format_name,
            summary=f"1 SOAP endpoint · {len(raw_scenarios)} scenario(s)",
        )

    def parse(self, content: str, source_file: str) -> ParsedFile:
        lines = content.strip().splitlines()
        meta_lines, header_lines, raw_scenarios = _split_level2_sections(_normalise_header(lines))

        url = _extract_field(meta_lines, "URL", default="/")
        name = _extract_field(meta_lines, "Name", default="SOAP Stub")
        required_headers = _parse_request_headers(header_lines)

        scenarios: list[ParsedScenario] = []
        for scenario_name, scenario_lines in raw_scenarios:
            match = _parse_soap_match(scenario_lines, is_default=(scenario_name == "default"))
            xpath_namespaces = _parse_xpath_namespaces(scenario_lines)

            # Strip match and namespace fields — leave Status, Content-Type, Delay, body.
            response_lines = [
                line for line in scenario_lines
                if not line.startswith("Match-Type:")
                and not line.startswith("Match-Value:")
                and not line.startswith(_XPATH_NS_PREFIX)
            ]
            status, response_headers, body, delay, fault = _parse_response_lines(response_lines)

            scenarios.append(ParsedScenario(
                name="default" if scenario_name == "default" else scenario_name,
                match=match,
                status=status,
                response_headers=response_headers,
                body=body,
                delay=delay,
                fault=fault,
                xpath_namespaces=xpath_namespaces,
            ))

        stub = ParsedStub(
            name=name,
            request=ParsedRequestSpec(
                method=HttpMethod.POST,   # SOAP is always HTTP POST
                url=url,
                required_headers=required_headers,
            ),
            scenarios=scenarios,
        )
        return ParsedFile(format=self.format_name, source_file=source_file, stubs=[stub])


# ── helpers ───────────────────────────────────────────────────────────────────

def _normalise_header(lines: list[str]) -> list[str]:
    """Replace SOAP file header with the standard header so _split_level2_sections works."""
    if lines and lines[0].strip() == _SOAP_HEADER:
        return [_STANDARD_HEADER] + lines[1:]
    return lines


def _parse_xpath_namespaces(scenario_lines: list[str]) -> dict[str, str]:
    """Extract all Match-XPath-NS: prefix=uri declarations from a scenario's lines.

    Example input line: "Match-XPath-NS: soap=http://schemas.xmlsoap.org/soap/envelope/"
    Returns: {"soap": "http://schemas.xmlsoap.org/soap/envelope/"}
    """
    namespaces: dict[str, str] = {}
    for line in scenario_lines:
        if not line.startswith(_XPATH_NS_PREFIX):
            continue
        value = line[len(_XPATH_NS_PREFIX):].strip()
        if "=" not in value:
            continue
        prefix, _, uri = value.partition("=")
        prefix = prefix.strip()
        uri = uri.strip()
        if prefix and uri:
            namespaces[prefix] = uri
    return namespaces


def _parse_soap_match(scenario_lines: list[str], is_default: bool) -> MatchCondition:
    if is_default:
        return MatchCondition(type=MatchType.ALWAYS)

    match_type_str = _extract_field(scenario_lines, "Match-Type", default="always")
    match_value = _extract_field(scenario_lines, "Match-Value")

    if match_type_str == "soap-action":
        # SOAPAction HTTP header match
        return MatchCondition(
            type=MatchType.HEADER_EQUALS,
            value=f"SOAPAction == {match_value}",
        )
    if match_type_str == "soap-xpath":
        # XPath expression against the SOAP request body
        return MatchCondition(type=MatchType.BODY_XPATH, value=match_value or "")
    if match_type_str == "body-contains":
        return MatchCondition(type=MatchType.BODY_CONTAINS, value=match_value or "")

    return MatchCondition(type=MatchType.ALWAYS)
