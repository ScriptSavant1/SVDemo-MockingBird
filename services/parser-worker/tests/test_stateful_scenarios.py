"""Phase 2 Sprint 6 — stateful scenario tests.

Tests cover:
  - Validation: required fields, duplicate names, step count, warnings
  - Parsing: scenario name, step count, per-step fields, state transitions
  - WireMock output: scenarioName + requiredScenarioState + newScenarioState
  - Integration: detector, full pipeline, dynamic bodies with transformer
  - Example file: banking-session.txt round-trip
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from parser_worker.detector import detect_and_parse
from parser_worker.generator.wiremock import generate_wiremock_mappings
from parser_worker.models import MatchType
from parser_worker.parsers.stateful_txt import (
    StatefulTxtParser, _split_stateful_sections, _strip_request_fields,
)


# ── shared helpers ────────────────────────────────────────────────────────────

PARSER = StatefulTxtParser()

MINIMAL_TWO_STEP = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

Scenario: Auth Flow

--- STEP: Login ---
State-In: Started
State-Out: Active
Method: POST
URL: /auth/login
Status: 200
Content-Type: application/json

{"token": "abc123"}

--- STEP: Logout ---
State-In: Active
State-Out: Started
Method: DELETE
URL: /auth/logout
Status: 204
"""

BANKING_FIVE_STEP = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

Scenario: Banking Session
Description: Full banking flow

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

{"accountId": "ACC-001", "balance": 15000.00}

--- STEP: Initiate Transfer ---
State-In: Authenticated
State-Out: TransferPending
Method: POST
URL: /api/v1/transfers
Status: 201
Content-Type: application/json

{"transferId": "TXN-{{randomValue type='NUMERIC' length=8}}", "status": "pending"}

--- STEP: Confirm Transfer ---
State-In: TransferPending
State-Out: Authenticated
Method: PUT
URL: /api/v1/transfers/confirm
Status: 200
Content-Type: application/json

{"status": "confirmed"}

--- STEP: Logout ---
State-In: Authenticated
State-Out: Started
Method: DELETE
URL: /auth/logout
Status: 204
"""


def _write(tmp_path: Path, content: str, filename: str = "stub.txt") -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


def _mappings(tmp_path: Path, content: str) -> list[dict]:
    """Parse content and return all generated WireMock mapping dicts."""
    f = _write(tmp_path, content)
    _, _, parsed = detect_and_parse(f)
    out = tmp_path / "out"
    generate_wiremock_mappings(parsed, out)
    return [json.loads(p.read_text()) for p in sorted((out / "mappings").glob("*.json"))]


def _example_file() -> Path:
    return Path(__file__).parent.parent.parent.parent / \
        "docs/input-formats/examples/banking-session.txt"


# ── section splitter ──────────────────────────────────────────────────────────

class TestSplitStatefulSections:

    def test_extracts_meta_lines(self):
        meta, _ = _split_stateful_sections([
            "--- MOCKINGBIRD v1.0 STATEFUL ---",
            "Scenario: My Flow",
            "Description: A test",
            "--- STEP: First ---",
            "State-In: Started",
        ])
        assert "Scenario: My Flow" in meta
        assert "Description: A test" in meta

    def test_extracts_step_names(self):
        _, steps = _split_stateful_sections(MINIMAL_TWO_STEP.splitlines())
        assert [name for name, _ in steps] == ["Login", "Logout"]

    def test_step_lines_do_not_contain_header(self):
        _, steps = _split_stateful_sections(MINIMAL_TWO_STEP.splitlines())
        for _, lines in steps:
            assert "--- MOCKINGBIRD v1.0 STATEFUL ---" not in lines

    def test_blank_and_comment_lines_skipped(self):
        content = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

# This is a comment
Scenario: Flow

--- STEP: Step A ---
# Another comment

State-In: Started
State-Out: Done
"""
        _, steps = _split_stateful_sections(content.splitlines())
        assert len(steps) == 1
        for line in steps[0][1]:
            assert not line.startswith("#")

    def test_five_steps_extracted(self):
        _, steps = _split_stateful_sections(BANKING_FIVE_STEP.splitlines())
        assert len(steps) == 5


# ── strip request fields ──────────────────────────────────────────────────────

class TestStripRequestFields:

    def test_removes_state_in(self):
        lines = ["State-In: Started", "Status: 200", '{"ok": true}']
        result = _strip_request_fields(lines)
        assert not any(l.startswith("State-In:") for l in result)

    def test_removes_state_out(self):
        lines = ["State-Out: Authenticated", "Status: 200", '{"ok": true}']
        result = _strip_request_fields(lines)
        assert not any(l.startswith("State-Out:") for l in result)

    def test_removes_method(self):
        lines = ["Method: POST", "Status: 201", '{"id": "1"}']
        result = _strip_request_fields(lines)
        assert not any(l.startswith("Method:") for l in result)

    def test_removes_url(self):
        lines = ["URL: /api/v1/thing", "Status: 200", '{"ok": true}']
        result = _strip_request_fields(lines)
        assert not any(l.startswith("URL:") for l in result)

    def test_preserves_status(self):
        lines = ["State-In: Started", "Status: 201", '{"id": "1"}']
        result = _strip_request_fields(lines)
        assert "Status: 201" in result

    def test_preserves_content_type(self):
        lines = ["Method: POST", "Status: 200", "Content-Type: application/json", '{"ok": true}']
        result = _strip_request_fields(lines)
        assert "Content-Type: application/json" in result

    def test_preserves_body(self):
        lines = ["State-In: X", "Status: 200", '{"hello": "world"}']
        result = _strip_request_fields(lines)
        assert '{"hello": "world"}' in result

    def test_preserves_delay(self):
        lines = ["State-In: X", "Status: 200", "Delay: 500ms", '{"ok": true}']
        result = _strip_request_fields(lines)
        assert "Delay: 500ms" in result


# ── validation ────────────────────────────────────────────────────────────────

class TestStatefulValidation:

    def test_valid_two_step_file_passes(self):
        result = PARSER.validate(MINIMAL_TWO_STEP)
        assert result.valid

    def test_valid_five_step_file_passes(self):
        result = PARSER.validate(BANKING_FIVE_STEP)
        assert result.valid

    def test_wrong_header_fails(self):
        content = MINIMAL_TWO_STEP.replace(
            "--- MOCKINGBIRD v1.0 STATEFUL ---",
            "--- MOCKINGBIRD v1.0 ---",
        )
        result = PARSER.validate(content)
        assert not result.valid

    def test_missing_scenario_name_fails(self):
        content = MINIMAL_TWO_STEP.replace("Scenario: Auth Flow\n", "")
        result = PARSER.validate(content)
        assert not result.valid
        assert any("Scenario" in str(e) for e in result.errors)

    def test_only_one_step_fails(self):
        content = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

Scenario: Flow

--- STEP: Only Step ---
State-In: Started
State-Out: Done
Method: GET
URL: /api/v1/thing
Status: 200
"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("2 steps" in str(e) for e in result.errors)

    def test_duplicate_step_names_fail(self):
        content = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

Scenario: Flow

--- STEP: Login ---
State-In: Started
State-Out: Active
Method: POST
URL: /auth/login
Status: 200

{"ok": true}

--- STEP: Login ---
State-In: Active
State-Out: Started
Method: DELETE
URL: /auth/logout
Status: 204
"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("Duplicate" in str(e) for e in result.errors)

    def test_missing_state_in_fails(self):
        content = MINIMAL_TWO_STEP.replace("State-In: Started\n", "", 1)
        result = PARSER.validate(content)
        assert not result.valid
        assert any("State-In" in str(e) for e in result.errors)

    def test_missing_state_out_fails(self):
        content = MINIMAL_TWO_STEP.replace("State-Out: Active\n", "", 1)
        result = PARSER.validate(content)
        assert not result.valid
        assert any("State-Out" in str(e) for e in result.errors)

    def test_missing_method_fails(self):
        content = MINIMAL_TWO_STEP.replace("Method: POST\n", "", 1)
        result = PARSER.validate(content)
        assert not result.valid
        assert any("Method" in str(e) for e in result.errors)

    def test_invalid_method_fails(self):
        content = MINIMAL_TWO_STEP.replace("Method: POST", "Method: TELEPORT")
        result = PARSER.validate(content)
        assert not result.valid

    def test_missing_url_fails(self):
        content = MINIMAL_TWO_STEP.replace("URL: /auth/login\n", "", 1)
        result = PARSER.validate(content)
        assert not result.valid
        assert any("URL" in str(e) for e in result.errors)

    def test_url_not_starting_with_slash_fails(self):
        content = MINIMAL_TWO_STEP.replace("URL: /auth/login", "URL: auth/login")
        result = PARSER.validate(content)
        assert not result.valid

    def test_missing_status_fails(self):
        content = MINIMAL_TWO_STEP.replace("Status: 200\n", "", 1)
        result = PARSER.validate(content)
        assert not result.valid
        assert any("Status" in str(e) for e in result.errors)

    def test_invalid_status_fails(self):
        content = MINIMAL_TWO_STEP.replace("Status: 200", "Status: abc")
        result = PARSER.validate(content)
        assert not result.valid

    def test_non_started_first_state_generates_warning(self):
        content = MINIMAL_TWO_STEP.replace("State-In: Started", "State-In: Authenticated", 1)
        result = PARSER.validate(content)
        assert result.valid
        assert result.warnings
        assert any("Started" in w for w in result.warnings)

    def test_summary_contains_step_count(self):
        result = PARSER.validate(BANKING_FIVE_STEP)
        assert result.valid
        assert "5" in result.summary

    def test_summary_contains_scenario_name(self):
        result = PARSER.validate(BANKING_FIVE_STEP)
        assert "Banking Session" in result.summary


# ── parsing ───────────────────────────────────────────────────────────────────

class TestStatefulParsing:

    def test_parsed_format_is_stateful_txt(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        assert parsed.format == "stateful-txt"

    def test_two_steps_become_two_stubs(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        assert len(parsed.stubs) == 2

    def test_five_steps_become_five_stubs(self):
        parsed = PARSER.parse(BANKING_FIVE_STEP, "test.txt")
        assert len(parsed.stubs) == 5

    def test_all_stubs_share_scenario_name(self):
        parsed = PARSER.parse(BANKING_FIVE_STEP, "test.txt")
        names = {stub.scenarios[0].scenario_name for stub in parsed.stubs}
        assert names == {"Banking Session"}

    def test_each_stub_has_exactly_one_scenario(self):
        parsed = PARSER.parse(BANKING_FIVE_STEP, "test.txt")
        for stub in parsed.stubs:
            assert len(stub.scenarios) == 1

    def test_scenario_match_type_is_always(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        for stub in parsed.stubs:
            assert stub.scenarios[0].match.type == MatchType.ALWAYS

    def test_login_step_method_is_post(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        login_stub = parsed.stubs[0]
        assert login_stub.request.method.value == "POST"

    def test_login_step_url(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        login_stub = parsed.stubs[0]
        assert login_stub.request.url == "/auth/login"

    def test_logout_step_method_is_delete(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        logout_stub = parsed.stubs[1]
        assert logout_stub.request.method.value == "DELETE"

    def test_state_in_set_on_scenario(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        login_scenario = parsed.stubs[0].scenarios[0]
        assert login_scenario.required_state == "Started"

    def test_state_out_set_on_scenario(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        login_scenario = parsed.stubs[0].scenarios[0]
        assert login_scenario.new_state == "Active"

    def test_state_unchanged_when_state_in_equals_state_out(self):
        parsed = PARSER.parse(BANKING_FIVE_STEP, "test.txt")
        get_account = parsed.stubs[1].scenarios[0]  # Get Account: Auth → Auth
        assert get_account.required_state == "Authenticated"
        assert get_account.new_state == "Authenticated"

    def test_step_body_correctly_parsed(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        login_scenario = parsed.stubs[0].scenarios[0]
        assert login_scenario.body is not None
        assert "abc123" in login_scenario.body

    def test_step_status_correctly_parsed(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        login_scenario = parsed.stubs[0].scenarios[0]
        assert login_scenario.status == 200

    def test_no_body_step_has_none_body(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        logout_scenario = parsed.stubs[1].scenarios[0]
        assert logout_scenario.status == 204
        assert logout_scenario.body is None

    def test_dynamic_body_preserved_verbatim(self):
        parsed = PARSER.parse(BANKING_FIVE_STEP, "test.txt")
        login_scenario = parsed.stubs[0].scenarios[0]
        assert "{{randomValue type='UUID'}}" in login_scenario.body

    def test_description_set_on_stubs(self):
        parsed = PARSER.parse(BANKING_FIVE_STEP, "test.txt")
        for stub in parsed.stubs:
            assert stub.description == "Full banking flow"

    def test_step_name_set_as_scenario_name(self):
        parsed = PARSER.parse(MINIMAL_TWO_STEP, "test.txt")
        assert parsed.stubs[0].scenarios[0].name == "Login"
        assert parsed.stubs[1].scenarios[0].name == "Logout"

    def test_step_with_delay_field(self):
        content = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

Scenario: Slow Flow

--- STEP: First ---
State-In: Started
State-Out: Done
Method: GET
URL: /api/v1/thing
Delay: random:100ms-500ms
Status: 200
Content-Type: application/json

{"ok": true}

--- STEP: Second ---
State-In: Done
State-Out: Started
Method: DELETE
URL: /api/v1/thing
Status: 204
"""
        parsed = PARSER.parse(content, "slow.txt")
        first = parsed.stubs[0].scenarios[0]
        assert first.delay is not None
        assert first.delay.min_ms == 100
        assert first.delay.max_ms == 500


# ── WireMock output ───────────────────────────────────────────────────────────

class TestStatefulWireMockOutput:

    def test_mapping_has_scenario_name(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        for m in mappings:
            assert m["scenarioName"] == "Auth Flow"

    def test_login_has_required_state_started(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        login = next(m for m in mappings if "Login" in m["name"])
        assert login["requiredScenarioState"] == "Started"

    def test_login_has_new_state_active(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        login = next(m for m in mappings if "Login" in m["name"])
        assert login["newScenarioState"] == "Active"

    def test_logout_has_required_state_active(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        logout = next(m for m in mappings if "Logout" in m["name"])
        assert logout["requiredScenarioState"] == "Active"

    def test_logout_has_new_state_started(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        logout = next(m for m in mappings if "Logout" in m["name"])
        assert logout["newScenarioState"] == "Started"

    def test_no_body_step_has_no_body_in_mapping(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        logout = next(m for m in mappings if "Logout" in m["name"])
        assert "body" not in logout["response"]

    def test_login_body_in_mapping(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        login = next(m for m in mappings if "Login" in m["name"])
        assert "abc123" in login["response"]["body"]

    def test_dynamic_step_gets_response_template_transformer(self, tmp_path):
        mappings = _mappings(tmp_path, BANKING_FIVE_STEP)
        login = next(m for m in mappings if "Login" in m["name"])
        assert "response-template" in login["response"]["transformers"]

    def test_static_step_no_transformer(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        login = next(m for m in mappings if "Login" in m["name"])
        assert "transformers" not in login["response"]

    def test_five_steps_produce_five_mapping_files(self, tmp_path):
        mappings = _mappings(tmp_path, BANKING_FIVE_STEP)
        assert len(mappings) == 5

    def test_all_five_mappings_share_same_scenario_name(self, tmp_path):
        mappings = _mappings(tmp_path, BANKING_FIVE_STEP)
        names = {m["scenarioName"] for m in mappings}
        assert names == {"Banking Session"}

    def test_state_unchanged_step_has_same_required_and_new(self, tmp_path):
        mappings = _mappings(tmp_path, BANKING_FIVE_STEP)
        get_account = next(m for m in mappings if "Get Account" in m["name"])
        assert get_account["requiredScenarioState"] == "Authenticated"
        assert get_account["newScenarioState"] == "Authenticated"

    def test_transfer_pending_state_transition(self, tmp_path):
        mappings = _mappings(tmp_path, BANKING_FIVE_STEP)
        initiate = next(m for m in mappings if "Initiate Transfer" in m["name"])
        assert initiate["requiredScenarioState"] == "Authenticated"
        assert initiate["newScenarioState"] == "TransferPending"

    def test_confirm_returns_from_pending(self, tmp_path):
        mappings = _mappings(tmp_path, BANKING_FIVE_STEP)
        confirm = next(m for m in mappings if "Confirm Transfer" in m["name"])
        assert confirm["requiredScenarioState"] == "TransferPending"
        assert confirm["newScenarioState"] == "Authenticated"

    def test_logout_returns_to_started(self, tmp_path):
        mappings = _mappings(tmp_path, BANKING_FIVE_STEP)
        logout = next(m for m in mappings if "Logout" in m["name"])
        assert logout["requiredScenarioState"] == "Authenticated"
        assert logout["newScenarioState"] == "Started"

    def test_delay_in_step_emitted_correctly(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 STATEFUL ---

Scenario: Slow Flow

--- STEP: Step A ---
State-In: Started
State-Out: Done
Method: GET
URL: /api/v1/thing
Delay: 300ms
Status: 200
Content-Type: application/json

{"ok": true}

--- STEP: Step B ---
State-In: Done
State-Out: Started
Method: DELETE
URL: /api/v1/thing
Status: 204
"""
        mappings = _mappings(tmp_path, content)
        step_a = next(m for m in mappings if "Step A" in m["name"])
        assert step_a["response"]["fixedDelayMilliseconds"] == 300

    def test_mapping_method_correct(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        login = next(m for m in mappings if "Login" in m["name"])
        assert login["request"]["method"] == "POST"

    def test_mapping_url_correct(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_TWO_STEP)
        login = next(m for m in mappings if "Login" in m["name"])
        assert login["request"]["urlPath"] == "/auth/login"

    def test_non_stateful_stubs_have_no_scenario_fields(self, tmp_path):
        """Ensure stateful fields are NOT emitted for regular (non-stateful) stubs."""
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Simple API
Method: GET
URL: /api/v1/thing

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"ok": true}
"""
        f = tmp_path / "stub.txt"
        f.write_text(content, encoding="utf-8")
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mapping = json.loads(next((out / "mappings").glob("*.json")).read_text())

        assert "scenarioName" not in mapping
        assert "requiredScenarioState" not in mapping
        assert "newScenarioState" not in mapping


# ── detector integration ──────────────────────────────────────────────────────

class TestStatefulDetection:

    def test_stateful_file_detected_as_stateful_txt(self, tmp_path):
        f = tmp_path / "flow.txt"
        f.write_text(MINIMAL_TWO_STEP, encoding="utf-8")
        parser, result, parsed = detect_and_parse(f)
        assert result.valid
        assert result.format_detected == "stateful-txt"

    def test_level2_file_not_confused_with_stateful(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Customer API
Method: GET
URL: /api/v1/customers/{id}

--- SCENARIO: Not Found ---
Match-Type: url-contains
Match-Value: UNKNOWN
Status: 404
Content-Type: application/json

{"error": "not found"}

--- SCENARIO DEFAULT ---
Status: 200
Content-Type: application/json

{"id": "123"}
"""
        f = tmp_path / "level2.txt"
        f.write_text(content, encoding="utf-8")
        parser, result, _ = detect_and_parse(f)
        assert result.format_detected == "level-2-txt"

    def test_soap_file_not_confused_with_stateful(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Customer SOAP
Method: POST
URL: /soap/customer

--- SCENARIO DEFAULT ---
Match-Type: always
Status: 200
Content-Type: text/xml

<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><GetCustomerResponse><id>123</id></GetCustomerResponse></soap:Body></soap:Envelope>
"""
        f = tmp_path / "soap.txt"
        f.write_text(content, encoding="utf-8")
        parser, result, _ = detect_and_parse(f)
        assert result.format_detected == "soap-txt"

    def test_stateful_parse_result_is_parsed_file(self, tmp_path):
        f = tmp_path / "flow.txt"
        f.write_text(BANKING_FIVE_STEP, encoding="utf-8")
        _, _, parsed = detect_and_parse(f)
        assert parsed is not None
        assert len(parsed.stubs) == 5


# ── example file round-trip ───────────────────────────────────────────────────

class TestBankingSessionExampleFile:

    def test_example_file_exists(self):
        assert _example_file().exists(), \
            f"banking-session.txt not found at {_example_file()}"

    def test_example_file_validates(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        content = example.read_text(encoding="utf-8")
        result = PARSER.validate(content)
        assert result.valid, [str(e) for e in result.errors]

    def test_example_file_format_detected(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, result, _ = detect_and_parse(example)
        assert result.format_detected == "stateful-txt"

    def test_example_file_produces_five_steps(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, _, parsed = detect_and_parse(example)
        assert len(parsed.stubs) == 5

    def test_example_file_scenario_name(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, _, parsed = detect_and_parse(example)
        for stub in parsed.stubs:
            assert stub.scenarios[0].scenario_name == "Banking Session"

    def test_example_file_produces_five_mappings(self, tmp_path):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        assert len(list((out / "mappings").glob("*.json"))) == 5

    def test_example_file_login_state_transition(self, tmp_path):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        login = next(m for m in mapping_dicts if "Login" in m["name"])
        assert login["requiredScenarioState"] == "Started"
        assert login["newScenarioState"] == "Authenticated"

    def test_example_file_logout_returns_to_started(self, tmp_path):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        logout = next(m for m in mapping_dicts if "Logout" in m["name"])
        assert logout["requiredScenarioState"] == "Authenticated"
        assert logout["newScenarioState"] == "Started"

    def test_example_file_dynamic_steps_have_transformer(self, tmp_path):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        login = next(m for m in mapping_dicts if "Login" in m["name"])
        assert "response-template" in login["response"]["transformers"]

    def test_example_file_logout_has_no_body(self, tmp_path):
        example = _example_file()
        if not example.exists():
            pytest.skip("banking-session.txt not found")
        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        logout = next(m for m in mapping_dicts if "Logout" in m["name"])
        assert "body" not in logout["response"]
        assert logout["response"]["status"] == 204
