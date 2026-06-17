"""Tests for Level 2 multi-scenario TXT parser."""
import pytest
from parser_worker.parsers.txt_level2 import TxtLevel2Parser
from parser_worker.models import MatchType, HttpMethod

PARSER = TxtLevel2Parser()

VALID_MULTI = """\
--- MOCKINGBIRD v1.0 ---
Name: Payment Processing API
Method: POST
URL: /api/v1/payments/process

--- REQUEST HEADERS ---
Authorization: Bearer <token>
Content-Type: application/json

--- SCENARIO: Insufficient Funds (402) ---
Match-Type: body-contains
Match-Value: "accountNumber": "00000001"
Status: 402
Delay: 120ms

Content-Type: application/json

{"status": "FAILED", "errorCode": "INSUFFICIENT_FUNDS"}

--- SCENARIO: Not Found (404) ---
Match-Type: body-contains
Match-Value: "accountNumber": "99999999"
Status: 404

Content-Type: application/json

{"status": "FAILED", "errorCode": "ACCOUNT_NOT_FOUND"}

--- SCENARIO DEFAULT ---
Match-Type: always
Status: 200
Delay: 120ms

Content-Type: application/json

{"transactionId": "TXN-001", "status": "COMPLETED"}
"""

VALID_URL_MATCH = """\
--- MOCKINGBIRD v1.0 ---
Name: Customer API
Method: GET
URL: /api/v1/customers/{customerId}

--- SCENARIO: Not Found ---
Match-Type: url-contains
Match-Value: /99999
Status: 404

Content-Type: application/json

{"error": "NOT_FOUND"}

--- SCENARIO DEFAULT ---
Match-Type: always
Status: 200

Content-Type: application/json

{"customerId": "12345"}
"""

INVALID_MISSING_DEFAULT = """\
--- MOCKINGBIRD v1.0 ---
Name: Missing Default
Method: GET
URL: /api/test

--- SCENARIO: Error ---
Match-Type: url-contains
Match-Value: /error
Status: 500

Content-Type: application/json

{"error": "err"}
"""

INVALID_MISSING_MATCH_VALUE = """\
--- MOCKINGBIRD v1.0 ---
Name: Missing Match Value
Method: GET
URL: /api/test

--- SCENARIO: Error ---
Match-Type: url-contains
Status: 404

Content-Type: application/json

{"error": "err"}

--- SCENARIO DEFAULT ---
Match-Type: always
Status: 200

Content-Type: text/plain

OK
"""


class TestCanHandle:
    def test_accepts_multi_scenario(self):
        assert PARSER.can_handle(VALID_MULTI, "test.txt")

    def test_accepts_default_only(self):
        content = "--- MOCKINGBIRD v1.0 ---\nName: Test\nMethod: GET\nURL: /api\n--- SCENARIO DEFAULT ---\nStatus: 200\nContent-Type: text/plain\nOK"
        assert PARSER.can_handle(content, "test.txt")

    def test_rejects_level1_format(self):
        assert not PARSER.can_handle(
            "--- MOCKINGBIRD v1.0 ---\nName: X\nMethod: GET\nURL: /api\n--- RESPONSE ---\nStatus: 200\nContent-Type: text/plain\nOK",
            "test.txt"
        )


class TestValidate:
    def test_valid_multi_passes(self):
        result = PARSER.validate(VALID_MULTI)
        assert result.valid
        assert "3 scenarios" in result.summary

    def test_missing_default_fails(self):
        result = PARSER.validate(INVALID_MISSING_DEFAULT)
        assert not result.valid
        assert any("DEFAULT" in str(e) or "default" in str(e) for e in result.errors)

    def test_missing_match_value_fails(self):
        result = PARSER.validate(INVALID_MISSING_MATCH_VALUE)
        assert not result.valid
        assert any("Match-Value" in str(e) for e in result.errors)

    def test_url_match_type_valid(self):
        result = PARSER.validate(VALID_URL_MATCH)
        assert result.valid


class TestParse:
    def test_parses_three_scenarios(self):
        _, parsed = PARSER.validate_and_parse(VALID_MULTI, "test.txt")
        assert len(parsed.stubs[0].scenarios) == 3

    def test_first_scenario_match_type(self):
        _, parsed = PARSER.validate_and_parse(VALID_MULTI, "test.txt")
        first = parsed.stubs[0].scenarios[0]
        assert first.match.type == MatchType.BODY_CONTAINS
        assert '"accountNumber": "00000001"' in first.match.value

    def test_first_scenario_status(self):
        _, parsed = PARSER.validate_and_parse(VALID_MULTI, "test.txt")
        assert parsed.stubs[0].scenarios[0].status == 402

    def test_default_scenario_last_and_always(self):
        _, parsed = PARSER.validate_and_parse(VALID_MULTI, "test.txt")
        last = parsed.stubs[0].scenarios[-1]
        assert last.match.type == MatchType.ALWAYS

    def test_url_match_scenario(self):
        _, parsed = PARSER.validate_and_parse(VALID_URL_MATCH, "test.txt")
        first = parsed.stubs[0].scenarios[0]
        assert first.match.type == MatchType.URL_CONTAINS
        assert first.match.value == "/99999"

    def test_delay_parsed_in_first_scenario(self):
        _, parsed = PARSER.validate_and_parse(VALID_MULTI, "test.txt")
        delay = parsed.stubs[0].scenarios[0].delay
        assert delay is not None
        assert delay.ms == 120

    def test_response_body_present(self):
        _, parsed = PARSER.validate_and_parse(VALID_MULTI, "test.txt")
        body = parsed.stubs[0].scenarios[0].body
        assert "INSUFFICIENT_FUNDS" in body

    def test_method_parsed(self):
        _, parsed = PARSER.validate_and_parse(VALID_MULTI, "test.txt")
        assert parsed.stubs[0].request.method == HttpMethod.POST
