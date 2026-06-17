"""Phase 2 Sprint 8 — Fault injection tests.

Verifies:
  - FaultType enum values match WireMock exactly
  - _parse_fault helper maps aliases correctly
  - _parse_response_lines returns fault as 5th element
  - Level 1 parse() sets fault on scenario
  - Level 2 parse() sets fault on scenario
  - SOAP parse() sets fault on scenario
  - Stateful parse() sets fault on scenario
  - WireMock JSON emits "fault" key correctly
  - Fault + delay combo emits both fields
  - Validation rejects unknown fault values in all formats
  - Fault absent → None in model → no "fault" key in JSON
  - Example file round-trip
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from parser_worker.detector import detect_and_parse
from parser_worker.generator.wiremock import generate_wiremock_mappings
from parser_worker.models import FaultType
from parser_worker.parsers.txt_level1 import (
    TxtLevel1Parser, _FAULT_ALIASES, _parse_fault, _parse_response_lines,
)
from parser_worker.parsers.txt_level2 import TxtLevel2Parser
from parser_worker.parsers.soap_txt import SoapTxtParser
from parser_worker.parsers.stateful_txt import StatefulTxtParser


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(tmp_path: Path, content: str, filename: str = "stub.txt") -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


def _mappings(tmp_path: Path, content: str, filename: str = "stub.txt") -> list[dict]:
    f = _write(tmp_path, content, filename)
    _, _, parsed = detect_and_parse(f)
    out = tmp_path / "out"
    generate_wiremock_mappings(parsed, out)
    return [json.loads(p.read_text()) for p in sorted((out / "mappings").glob("*.json"))]


def _example_file() -> Path:
    return Path(__file__).parent.parent.parent.parent / \
        "docs/input-formats/examples/fault-injection.txt"


LEVEL1_PARSER = TxtLevel1Parser()
LEVEL2_PARSER = TxtLevel2Parser()
SOAP_PARSER = SoapTxtParser()
STATEFUL_PARSER = StatefulTxtParser()


# ── FaultType enum ─────────────────────────────────────────────────────────────

class TestFaultTypeEnum:

    def test_connection_reset_value_is_wiremock_string(self):
        assert FaultType.CONNECTION_RESET_BY_PEER.value == "CONNECTION_RESET_BY_PEER"

    def test_empty_response_value_is_wiremock_string(self):
        assert FaultType.EMPTY_RESPONSE.value == "EMPTY_RESPONSE"

    def test_malformed_response_value_is_wiremock_string(self):
        assert FaultType.MALFORMED_RESPONSE_CHUNK.value == "MALFORMED_RESPONSE_CHUNK"

    def test_all_three_fault_types_exist(self):
        names = {f.name for f in FaultType}
        assert "CONNECTION_RESET_BY_PEER" in names
        assert "EMPTY_RESPONSE" in names
        assert "MALFORMED_RESPONSE_CHUNK" in names

    def test_fault_type_count(self):
        assert len(FaultType) == 3


# ── _FAULT_ALIASES and _parse_fault ───────────────────────────────────────────

class TestFaultAliases:

    def test_connection_reset_alias(self):
        assert _FAULT_ALIASES["connection-reset"] is FaultType.CONNECTION_RESET_BY_PEER

    def test_empty_response_alias(self):
        assert _FAULT_ALIASES["empty-response"] is FaultType.EMPTY_RESPONSE

    def test_malformed_response_alias(self):
        assert _FAULT_ALIASES["malformed-response"] is FaultType.MALFORMED_RESPONSE_CHUNK

    def test_exactly_three_aliases(self):
        assert len(_FAULT_ALIASES) == 3

    def test_parse_fault_connection_reset(self):
        assert _parse_fault("connection-reset") is FaultType.CONNECTION_RESET_BY_PEER

    def test_parse_fault_empty_response(self):
        assert _parse_fault("empty-response") is FaultType.EMPTY_RESPONSE

    def test_parse_fault_malformed_response(self):
        assert _parse_fault("malformed-response") is FaultType.MALFORMED_RESPONSE_CHUNK

    def test_parse_fault_case_insensitive(self):
        assert _parse_fault("Connection-Reset") is FaultType.CONNECTION_RESET_BY_PEER
        assert _parse_fault("EMPTY-RESPONSE") is FaultType.EMPTY_RESPONSE
        assert _parse_fault("Malformed-Response") is FaultType.MALFORMED_RESPONSE_CHUNK

    def test_parse_fault_unknown_returns_none(self):
        assert _parse_fault("network-error") is None
        assert _parse_fault("") is None
        assert _parse_fault("CONNECTION_RESET_BY_PEER") is None  # WireMock value, not alias


# ── _parse_response_lines 5-tuple ─────────────────────────────────────────────

class TestParseResponseLinesFaultField:

    def test_returns_five_values(self):
        lines = ["Status: 200"]
        result = _parse_response_lines(lines)
        assert len(result) == 5

    def test_fault_none_when_absent(self):
        lines = ["Status: 200", "Content-Type: application/json"]
        _, _, _, _, fault = _parse_response_lines(lines)
        assert fault is None

    def test_connection_reset_parsed(self):
        lines = ["Status: 503", "Fault: connection-reset"]
        _, _, _, _, fault = _parse_response_lines(lines)
        assert fault is FaultType.CONNECTION_RESET_BY_PEER

    def test_empty_response_parsed(self):
        lines = ["Status: 504", "Fault: empty-response"]
        _, _, _, _, fault = _parse_response_lines(lines)
        assert fault is FaultType.EMPTY_RESPONSE

    def test_malformed_response_parsed(self):
        lines = ["Status: 200", "Fault: malformed-response"]
        _, _, _, _, fault = _parse_response_lines(lines)
        assert fault is FaultType.MALFORMED_RESPONSE_CHUNK

    def test_fault_case_insensitive_in_response_lines(self):
        lines = ["Status: 503", "Fault: Connection-Reset"]
        _, _, _, _, fault = _parse_response_lines(lines)
        assert fault is FaultType.CONNECTION_RESET_BY_PEER

    def test_fault_unknown_value_returns_none(self):
        lines = ["Status: 500", "Fault: network-error"]
        _, _, _, _, fault = _parse_response_lines(lines)
        assert fault is None

    def test_fault_and_delay_both_parsed(self):
        lines = ["Status: 503", "Delay: 2000ms", "Fault: empty-response"]
        _, _, _, delay, fault = _parse_response_lines(lines)
        assert delay is not None
        assert delay.ms == 2000
        assert fault is FaultType.EMPTY_RESPONSE

    def test_fault_does_not_consume_body(self):
        lines = ["Status: 503", "Fault: connection-reset", '{"error": "reset"}']
        _, _, body, _, fault = _parse_response_lines(lines)
        assert fault is FaultType.CONNECTION_RESET_BY_PEER
        assert body is not None
        assert "error" in body

    def test_status_still_parsed_with_fault(self):
        lines = ["Status: 503", "Fault: connection-reset"]
        status, _, _, _, _ = _parse_response_lines(lines)
        assert status == 503

    def test_headers_still_parsed_with_fault(self):
        lines = ["Status: 503", "Content-Type: text/plain", "Fault: connection-reset"]
        _, headers, _, _, _ = _parse_response_lines(lines)
        assert headers.get("Content-Type") == "text/plain"


# ── Level 1 fault parsing ──────────────────────────────────────────────────────

class TestLevel1FaultParsing:

    def _make_level1(self, fault_line: str = "", delay_line: str = "") -> str:
        lines = [
            "--- MOCKINGBIRD v1.0 ---",
            "Name: Test Stub",
            "Method: POST",
            "URL: /api/test",
            "",
            "--- RESPONSE ---",
            "Status: 503",
        ]
        if delay_line:
            lines.append(delay_line)
        if fault_line:
            lines.append(fault_line)
        return "\n".join(lines)

    def test_fault_set_on_scenario(self):
        content = self._make_level1("Fault: connection-reset")
        parsed = LEVEL1_PARSER.parse(content, "test.txt")
        assert parsed.stubs[0].scenarios[0].fault is FaultType.CONNECTION_RESET_BY_PEER

    def test_no_fault_field_gives_none(self):
        content = self._make_level1()
        parsed = LEVEL1_PARSER.parse(content, "test.txt")
        assert parsed.stubs[0].scenarios[0].fault is None

    def test_fault_and_delay_both_set(self):
        content = self._make_level1("Fault: empty-response", "Delay: 5000ms")
        parsed = LEVEL1_PARSER.parse(content, "test.txt")
        scenario = parsed.stubs[0].scenarios[0]
        assert scenario.fault is FaultType.EMPTY_RESPONSE
        assert scenario.delay is not None
        assert scenario.delay.ms == 5000

    def test_validation_rejects_unknown_fault(self):
        content = self._make_level1("Fault: network-error")
        result = LEVEL1_PARSER.validate(content)
        assert not result.valid
        assert any("Fault" in str(e) for e in result.errors)

    def test_validation_accepts_valid_faults(self):
        for alias in _FAULT_ALIASES:
            content = self._make_level1(f"Fault: {alias}")
            result = LEVEL1_PARSER.validate(content)
            assert result.valid, f"Expected valid for Fault: {alias}, got errors: {result.errors}"


# ── Level 2 fault parsing ──────────────────────────────────────────────────────

LEVEL2_WITH_FAULT = """\
--- MOCKINGBIRD v1.0 ---

Name: Payment Stub
Method: POST
URL: /payments/domestic

--- SCENARIO: Connection Reset ---
Match-Type: body-contains
Match-Value: simulate-reset
Status: 503
Fault: connection-reset

--- SCENARIO: Empty Response ---
Match-Type: body-contains
Match-Value: simulate-empty
Status: 503
Delay: 3000ms
Fault: empty-response

--- SCENARIO DEFAULT ---
Status: 200
Content-Type: application/json

{"paymentId": "PAY-001", "status": "ACCEPTED"}
"""


class TestLevel2FaultParsing:

    def test_connection_reset_scenario(self):
        parsed = LEVEL2_PARSER.parse(LEVEL2_WITH_FAULT, "test.txt")
        reset = next(s for s in parsed.stubs[0].scenarios if "Reset" in s.name)
        assert reset.fault is FaultType.CONNECTION_RESET_BY_PEER

    def test_empty_response_scenario(self):
        parsed = LEVEL2_PARSER.parse(LEVEL2_WITH_FAULT, "test.txt")
        empty = next(s for s in parsed.stubs[0].scenarios if "Empty" in s.name)
        assert empty.fault is FaultType.EMPTY_RESPONSE

    def test_default_scenario_has_no_fault(self):
        parsed = LEVEL2_PARSER.parse(LEVEL2_WITH_FAULT, "test.txt")
        default = next(s for s in parsed.stubs[0].scenarios if s.name == "default")
        assert default.fault is None

    def test_fault_and_delay_combined(self):
        parsed = LEVEL2_PARSER.parse(LEVEL2_WITH_FAULT, "test.txt")
        empty = next(s for s in parsed.stubs[0].scenarios if "Empty" in s.name)
        assert empty.fault is FaultType.EMPTY_RESPONSE
        assert empty.delay is not None
        assert empty.delay.ms == 3000

    def test_validation_rejects_unknown_fault(self):
        content = LEVEL2_WITH_FAULT.replace("Fault: connection-reset", "Fault: bad-type")
        result = LEVEL2_PARSER.validate(content)
        assert not result.valid
        assert any("Fault" in str(e) for e in result.errors)

    def test_validation_passes_with_valid_faults(self):
        result = LEVEL2_PARSER.validate(LEVEL2_WITH_FAULT)
        assert result.valid, [str(e) for e in result.errors]

    def test_malformed_response_in_level2(self):
        content = LEVEL2_WITH_FAULT.replace(
            "Fault: connection-reset", "Fault: malformed-response"
        )
        parsed = LEVEL2_PARSER.parse(content, "test.txt")
        scenario = next(s for s in parsed.stubs[0].scenarios if "Reset" in s.name)
        assert scenario.fault is FaultType.MALFORMED_RESPONSE_CHUNK


# ── SOAP fault parsing ─────────────────────────────────────────────────────────

SOAP_WITH_FAULT = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Payment SOAP Stub
URL: /ws/payments

--- SCENARIO: Timeout Fault ---
Match-Type: body-contains
Match-Value: TimeoutRequest
Status: 503
Delay: 10000ms
Fault: connection-reset

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml

<fault/>
"""


class TestSoapFaultParsing:

    def test_fault_set_on_soap_scenario(self):
        parsed = SOAP_PARSER.parse(SOAP_WITH_FAULT, "test.txt")
        timeout = next(s for s in parsed.stubs[0].scenarios if "Timeout" in s.name)
        assert timeout.fault is FaultType.CONNECTION_RESET_BY_PEER

    def test_default_soap_scenario_has_no_fault(self):
        parsed = SOAP_PARSER.parse(SOAP_WITH_FAULT, "test.txt")
        default = next(s for s in parsed.stubs[0].scenarios if s.name == "default")
        assert default.fault is None

    def test_soap_fault_and_delay_combined(self):
        parsed = SOAP_PARSER.parse(SOAP_WITH_FAULT, "test.txt")
        timeout = next(s for s in parsed.stubs[0].scenarios if "Timeout" in s.name)
        assert timeout.fault is FaultType.CONNECTION_RESET_BY_PEER
        assert timeout.delay is not None
        assert timeout.delay.ms == 10000

    def test_soap_validation_rejects_unknown_fault(self):
        content = SOAP_WITH_FAULT.replace("Fault: connection-reset", "Fault: not-a-fault")
        result = SOAP_PARSER.validate(content)
        assert not result.valid
        assert any("Fault" in str(e) for e in result.errors)

    def test_soap_validation_passes_with_valid_fault(self):
        result = SOAP_PARSER.validate(SOAP_WITH_FAULT)
        assert result.valid, [str(e) for e in result.errors]


# ── Stateful fault parsing ─────────────────────────────────────────────────────

STATEFUL_WITH_FAULT = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

Scenario: Session With Fault
Description: Login then simulate connection drop on account fetch

--- STEP: Login ---
State-In: Started
State-Out: Authenticated
Method: POST
URL: /auth/login
Status: 200
Content-Type: application/json

{"token": "test-token"}

--- STEP: Account Fetch Fault ---
State-In: Authenticated
State-Out: Started
Method: GET
URL: /api/account
Status: 503
Delay: 1000ms
Fault: connection-reset
"""


class TestStatefulFaultParsing:

    def test_fault_set_on_step(self):
        parsed = STATEFUL_PARSER.parse(STATEFUL_WITH_FAULT, "test.txt")
        fault_step = next(
            s for stub in parsed.stubs for s in stub.scenarios
            if "Fault" in s.name
        )
        assert fault_step.fault is FaultType.CONNECTION_RESET_BY_PEER

    def test_non_fault_step_has_no_fault(self):
        parsed = STATEFUL_PARSER.parse(STATEFUL_WITH_FAULT, "test.txt")
        login_step = next(
            s for stub in parsed.stubs for s in stub.scenarios
            if s.name == "Login"
        )
        assert login_step.fault is None

    def test_stateful_fault_and_delay(self):
        parsed = STATEFUL_PARSER.parse(STATEFUL_WITH_FAULT, "test.txt")
        fault_step = next(
            s for stub in parsed.stubs for s in stub.scenarios
            if "Fault" in s.name
        )
        assert fault_step.fault is FaultType.CONNECTION_RESET_BY_PEER
        assert fault_step.delay is not None
        assert fault_step.delay.ms == 1000

    def test_stateful_validation_rejects_unknown_fault(self):
        content = STATEFUL_WITH_FAULT.replace("Fault: connection-reset", "Fault: bad")
        result = STATEFUL_PARSER.validate(content)
        assert not result.valid
        assert any("Fault" in str(e) for e in result.errors)

    def test_stateful_validation_passes_with_valid_fault(self):
        result = STATEFUL_PARSER.validate(STATEFUL_WITH_FAULT)
        assert result.valid, [str(e) for e in result.errors]


# ── WireMock JSON output ───────────────────────────────────────────────────────

class TestWireMockFaultOutput:

    def test_connection_reset_in_json(self, tmp_path):
        mappings = _mappings(tmp_path, LEVEL2_WITH_FAULT)
        reset = next(m for m in mappings if "Reset" in m["name"])
        assert reset["response"]["fault"] == "CONNECTION_RESET_BY_PEER"

    def test_empty_response_in_json(self, tmp_path):
        mappings = _mappings(tmp_path, LEVEL2_WITH_FAULT)
        empty = next(m for m in mappings if "Empty" in m["name"])
        assert empty["response"]["fault"] == "EMPTY_RESPONSE"

    def test_no_fault_field_when_absent(self, tmp_path):
        mappings = _mappings(tmp_path, LEVEL2_WITH_FAULT)
        default = next(m for m in mappings if "default" in m["name"].lower())
        assert "fault" not in default["response"]

    def test_malformed_response_in_json(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Malformed Stub
Method: GET
URL: /api/broken

--- RESPONSE ---
Status: 200
Fault: malformed-response
"""
        mappings = _mappings(tmp_path, content)
        assert mappings[0]["response"]["fault"] == "MALFORMED_RESPONSE_CHUNK"

    def test_fault_and_delay_both_in_json(self, tmp_path):
        mappings = _mappings(tmp_path, LEVEL2_WITH_FAULT)
        empty = next(m for m in mappings if "Empty" in m["name"])
        response = empty["response"]
        assert response["fault"] == "EMPTY_RESPONSE"
        assert "fixedDelayMilliseconds" in response
        assert response["fixedDelayMilliseconds"] == 3000

    def test_fault_value_matches_wiremock_exact_strings(self, tmp_path):
        valid_wiremock_faults = {
            "CONNECTION_RESET_BY_PEER",
            "EMPTY_RESPONSE",
            "MALFORMED_RESPONSE_CHUNK",
        }
        mappings = _mappings(tmp_path, LEVEL2_WITH_FAULT)
        for m in mappings:
            if "fault" in m["response"]:
                assert m["response"]["fault"] in valid_wiremock_faults

    def test_status_preserved_alongside_fault(self, tmp_path):
        mappings = _mappings(tmp_path, LEVEL2_WITH_FAULT)
        reset = next(m for m in mappings if "Reset" in m["name"])
        assert reset["response"]["status"] == 503

    def test_soap_fault_in_json(self, tmp_path):
        mappings = _mappings(tmp_path, SOAP_WITH_FAULT, "stub.txt")
        timeout = next(m for m in mappings if "Timeout" in m["name"])
        assert timeout["response"]["fault"] == "CONNECTION_RESET_BY_PEER"

    def test_level1_fault_in_json(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Reset Stub
Method: POST
URL: /api/reset

--- RESPONSE ---
Status: 503
Fault: connection-reset
"""
        mappings = _mappings(tmp_path, content)
        assert mappings[0]["response"]["fault"] == "CONNECTION_RESET_BY_PEER"


# ── Example file round-trip ────────────────────────────────────────────────────

class TestFaultInjectionExampleFile:

    def test_example_file_exists(self):
        assert _example_file().exists(), f"fault-injection.txt not found at {_example_file()}"

    def test_example_file_validates(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("fault-injection.txt not found")
        result = LEVEL1_PARSER.validate(example.read_text(encoding="utf-8"))
        assert result.valid, [str(e) for e in result.errors]

    def test_example_file_detected_as_level1(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("fault-injection.txt not found")
        _, result, _ = detect_and_parse(example)
        assert result.format_detected == "level-1-txt"

    def test_example_file_fault_parsed(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("fault-injection.txt not found")
        _, _, parsed = detect_and_parse(example)
        assert parsed.stubs[0].scenarios[0].fault is FaultType.CONNECTION_RESET_BY_PEER

    def test_example_file_wiremock_output(self, tmp_path):
        example = _example_file()
        if not example.exists():
            pytest.skip("fault-injection.txt not found")
        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mappings = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        assert len(mappings) == 1
        assert mappings[0]["response"]["fault"] == "CONNECTION_RESET_BY_PEER"
        assert mappings[0]["response"]["fixedDelayMilliseconds"] == 2000
