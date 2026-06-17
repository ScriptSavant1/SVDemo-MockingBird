"""Tests for WireMock JSON mapping generator."""
import json
import pytest
from pathlib import Path
from parser_worker.parsers.txt_level1 import TxtLevel1Parser
from parser_worker.parsers.txt_level2 import TxtLevel2Parser
from parser_worker.generator.wiremock import generate_wiremock_mappings

L1_PARSER = TxtLevel1Parser()
L2_PARSER = TxtLevel2Parser()

SIMPLE_STUB = """\
--- MOCKINGBIRD v1.0 ---
Name: Customer Lookup API
Method: GET
URL: /api/v1/customers/12345

--- RESPONSE ---
Status: 200
Delay: 75ms

Content-Type: application/json

{"customerId": "12345", "name": "John Smith"}
"""

MULTI_STUB = """\
--- MOCKINGBIRD v1.0 ---
Name: Payment API
Method: POST
URL: /api/v1/payments

--- SCENARIO: Not Found (404) ---
Match-Type: body-contains
Match-Value: "accountNumber": "99999"
Status: 404

Content-Type: application/json

{"error": "NOT_FOUND"}

--- SCENARIO DEFAULT ---
Match-Type: always
Status: 200

Content-Type: application/json

{"transactionId": "TXN-001"}
"""

DYNAMIC_STUB = """\
--- MOCKINGBIRD v1.0 ---
Name: Dynamic Customer
Method: GET
URL: /api/v1/customers/{customerId}

--- RESPONSE ---
Status: 200

Content-Type: application/json

{"customerId": "{{request.pathParam.customerId}}", "name": "John"}
"""


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "output"


class TestSimpleStubGeneration:
    def test_creates_mappings_directory(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(SIMPLE_STUB, "test.txt")
        generate_wiremock_mappings(parsed, tmp_output)
        assert (tmp_output / "mappings").is_dir()

    def test_creates_one_file_for_level1(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(SIMPLE_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        assert len(files) == 1

    def test_mapping_has_correct_method(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(SIMPLE_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["request"]["method"] == "GET"

    def test_mapping_has_correct_url(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(SIMPLE_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["request"]["urlPath"] == "/api/v1/customers/12345"

    def test_mapping_has_correct_status(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(SIMPLE_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["response"]["status"] == 200

    def test_mapping_has_delay(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(SIMPLE_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["response"]["fixedDelayMilliseconds"] == 75

    def test_mapping_has_response_body(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(SIMPLE_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert "John Smith" in mapping["response"]["body"]


class TestMultiScenarioGeneration:
    def test_creates_two_files_for_two_scenarios(self, tmp_output):
        _, parsed = L2_PARSER.validate_and_parse(MULTI_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        assert len(files) == 2

    def test_first_scenario_has_higher_priority(self, tmp_output):
        _, parsed = L2_PARSER.validate_and_parse(MULTI_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mappings = [json.loads(f.read_text()) for f in files]
        priorities = [m["priority"] for m in mappings]
        assert priorities[0] > priorities[1]

    def test_not_found_uses_body_contains(self, tmp_output):
        _, parsed = L2_PARSER.validate_and_parse(MULTI_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        first_mapping = json.loads(files[0].read_text())
        assert "bodyPatterns" in first_mapping["request"]
        assert first_mapping["request"]["bodyPatterns"][0]["contains"] == '"accountNumber": "99999"'

    def test_default_scenario_has_no_body_pattern(self, tmp_output):
        _, parsed = L2_PARSER.validate_and_parse(MULTI_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        last_mapping = json.loads(files[-1].read_text())
        assert "bodyPatterns" not in last_mapping["request"]


class TestDynamicResponseGeneration:
    def test_adds_response_template_transformer_for_placeholders(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(DYNAMIC_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert "response-template" in mapping["response"].get("transformers", [])

    def test_uses_url_pattern_for_path_params(self, tmp_output):
        _, parsed = L1_PARSER.validate_and_parse(DYNAMIC_STUB, "test.txt")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert "urlPattern" in mapping["request"]
        assert "{customerId}" not in mapping["request"]["urlPattern"]
        assert "[^/]+" in mapping["request"]["urlPattern"]
