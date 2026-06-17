"""Tests for Level 1 TXT parser."""
import pytest
from parser_worker.parsers.txt_level1 import TxtLevel1Parser
from parser_worker.models import MatchType, HttpMethod

PARSER = TxtLevel1Parser()

VALID_SIMPLE = """\
--- MOCKINGBIRD v1.0 ---
Name: Customer Lookup API
Method: GET
URL: /api/v1/customers/12345

--- REQUEST HEADERS ---
Authorization: Bearer <token>
Accept: application/json

--- RESPONSE ---
Status: 200
Delay: 75ms

Content-Type: application/json

{
  "customerId": "12345",
  "name": "John Smith",
  "status": "ACTIVE"
}
"""

VALID_POST = """\
--- MOCKINGBIRD v1.0 ---
Name: Create Payment
Method: POST
URL: /api/v1/payments

--- RESPONSE ---
Status: 201

Content-Type: application/json

{"transactionId": "TXN-001", "status": "CREATED"}
"""

INVALID_NO_RESPONSE = """\
--- MOCKINGBIRD v1.0 ---
Name: Missing Response
Method: GET
URL: /api/v1/test
"""

INVALID_BAD_STATUS = """\
--- MOCKINGBIRD v1.0 ---
Name: Bad Status
Method: GET
URL: /api/v1/test

--- RESPONSE ---
Status: 999
Content-Type: application/json
{}
"""

INVALID_URL_NO_SLASH = """\
--- MOCKINGBIRD v1.0 ---
Name: Bad URL
Method: GET
URL: api/v1/test

--- RESPONSE ---
Status: 200
Content-Type: text/plain
OK
"""


class TestCanHandle:
    def test_accepts_valid_level1(self):
        assert PARSER.can_handle(VALID_SIMPLE, "test.txt")

    def test_rejects_file_without_header(self):
        assert not PARSER.can_handle("Name: Test\nMethod: GET\nURL: /api", "test.txt")

    def test_rejects_level2_format(self):
        content = "--- MOCKINGBIRD v1.0 ---\n--- SCENARIO: test ---\n"
        assert not PARSER.can_handle(content, "test.txt")


class TestValidate:
    def test_valid_file_passes(self):
        result = PARSER.validate(VALID_SIMPLE)
        assert result.valid
        assert result.format_detected == "level-1-txt"
        assert "1 endpoint" in result.summary

    def test_valid_post_passes(self):
        result = PARSER.validate(VALID_POST)
        assert result.valid

    def test_missing_response_fails(self):
        result = PARSER.validate(INVALID_NO_RESPONSE)
        assert not result.valid
        assert any("RESPONSE" in str(e) for e in result.errors)

    def test_invalid_status_fails(self):
        result = PARSER.validate(INVALID_BAD_STATUS)
        assert not result.valid
        assert any("999" in str(e) for e in result.errors)

    def test_url_without_slash_fails(self):
        result = PARSER.validate(INVALID_URL_NO_SLASH)
        assert not result.valid
        assert any("/" in str(e) for e in result.errors)

    def test_invalid_method_fails(self):
        content = VALID_SIMPLE.replace("Method: GET", "Method: FETCH")
        result = PARSER.validate(content)
        assert not result.valid
        assert any("FETCH" in str(e) for e in result.errors)


class TestParse:
    def test_parses_name(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        assert parsed.stubs[0].name == "Customer Lookup API"

    def test_parses_method(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        assert parsed.stubs[0].request.method == HttpMethod.GET

    def test_parses_url(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        assert parsed.stubs[0].request.url == "/api/v1/customers/12345"

    def test_parses_status(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        assert parsed.stubs[0].scenarios[0].status == 200

    def test_parses_delay(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        delay = parsed.stubs[0].scenarios[0].delay
        assert delay is not None
        assert delay.ms == 75

    def test_parses_response_body(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        body = parsed.stubs[0].scenarios[0].body
        assert body is not None
        assert "customerId" in body

    def test_skips_placeholder_headers(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        headers = parsed.stubs[0].request.required_headers
        assert "Authorization" not in headers  # has <token> placeholder — skipped

    def test_keeps_concrete_headers(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        headers = parsed.stubs[0].request.required_headers
        assert headers.get("Accept") == "application/json"

    def test_response_content_type_header(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        resp_headers = parsed.stubs[0].scenarios[0].response_headers
        assert resp_headers.get("Content-Type") == "application/json"

    def test_scenario_is_always_match(self):
        _, parsed = PARSER.validate_and_parse(VALID_SIMPLE, "test.txt")
        match = parsed.stubs[0].scenarios[0].match
        assert match.type == MatchType.ALWAYS

    def test_post_method_parsed(self):
        _, parsed = PARSER.validate_and_parse(VALID_POST, "test.txt")
        assert parsed.stubs[0].request.method == HttpMethod.POST

    def test_created_status_parsed(self):
        _, parsed = PARSER.validate_and_parse(VALID_POST, "test.txt")
        assert parsed.stubs[0].scenarios[0].status == 201
