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

    def test_adds_transformer_for_placeholder_that_lives_only_in_a_header(self, tmp_output):
        """Regression test: found by loading a real generated mapping into an
        actual WireMock instance. A CA LISA capture that echoes a request
        header back via %%X-Interaction-Id%% produces a response with the
        {{...}} placeholder ONLY in response_headers, not body. Before the
        fix, has_dynamic_placeholders() only scanned body, so this mapping got
        no "transformers" entry — WireMock would then serve the literal
        unresolved "{{request.headers.X-Interaction-Id}}" string instead of
        the real value.
        """
        from parser_worker.models import (
            HttpMethod, MatchCondition, MatchType, ParsedFile,
            ParsedRequestSpec, ParsedScenario, ParsedStub,
        )

        scenario = ParsedScenario(
            name="default",
            match=MatchCondition(type=MatchType.ALWAYS),
            status=200,
            response_headers={"x-interaction-id": "{{request.headers.X-Interaction-Id}}"},
            body=None,
        )
        stub = ParsedStub(
            name="Header Echo",
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/api/v1/echo"),
            scenarios=[scenario],
        )
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="test.txt", stubs=[stub])

        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert "response-template" in mapping["response"].get("transformers", [])


class TestQueryParameterDecoding:
    """Regression tests: found by loading a real generated mapping into an
    actual WireMock instance and firing a real HTTP request at it. WireMock
    URL-decodes incoming query strings (application/x-www-form-urlencoded
    rules: '+' -> space, %XX -> byte) before comparing against queryParameters
    matchers, so a stored matcher built from the raw, still-encoded capture
    text never matches a real request — even though the mapping "looked"
    correct in the generated JSON.
    """

    def _stub_with_url(self, url: str):
        from parser_worker.models import (
            HttpMethod, MatchCondition, MatchType, ParsedFile,
            ParsedRequestSpec, ParsedScenario, ParsedStub,
        )

        scenario = ParsedScenario(
            name="default", match=MatchCondition(type=MatchType.ALWAYS),
            status=200, body='{"ok":true}',
        )
        stub = ParsedStub(
            name="Query Test",
            request=ParsedRequestSpec(method=HttpMethod.GET, url=url),
            scenarios=[scenario],
        )
        return ParsedFile(format="ca-lisa-http-pair", source_file="test.txt", stubs=[stub])

    def test_plus_sign_decoded_to_space(self, tmp_output):
        parsed = self._stub_with_url("/api/enquire?aggregate=SUP+FLAGS")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["request"]["urlPath"] == "/api/enquire"
        assert mapping["request"]["queryParameters"]["aggregate"]["equalTo"] == "SUP FLAGS"

    def test_percent_encoded_value_decoded(self, tmp_output):
        parsed = self._stub_with_url("/api/search?q=foo%26bar")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["request"]["queryParameters"]["q"]["equalTo"] == "foo&bar"

    def test_percent_encoded_key_decoded(self, tmp_output):
        parsed = self._stub_with_url("/api/search?my%20key=value")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert "my key" in mapping["request"]["queryParameters"]
        assert mapping["request"]["queryParameters"]["my key"]["equalTo"] == "value"

    def test_plain_value_unaffected(self, tmp_output):
        parsed = self._stub_with_url("/api/enquire?aggregate=FLAGS")
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["request"]["queryParameters"]["aggregate"]["equalTo"] == "FLAGS"


class TestContentTypeHeaderCaseInsensitive:
    """Regression: found by loading a real generated mapping into an actual
    WireMock instance and sending it a real request. Jetty (WireMock's
    underlying HTTP server) normalises the Content-Type header's charset
    casing before the equalTo matcher runs — a mapping storing the verbatim
    captured "charset=utf-8" never matched, regardless of what case the
    client actually sent. Content-Type's media type and parameters are
    case-insensitive per RFC 7231 3.1.1.1 anyway, so it's matched
    case-insensitively rather than case-exact like other headers.
    """

    def _stub_with_headers(self, headers: dict[str, str]):
        from parser_worker.models import (
            HttpMethod, MatchCondition, MatchType, ParsedFile,
            ParsedRequestSpec, ParsedScenario, ParsedStub,
        )

        scenario = ParsedScenario(name="default", match=MatchCondition(type=MatchType.ALWAYS), status=200)
        stub = ParsedStub(
            name="Header Test",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/op", required_headers=headers),
            scenarios=[scenario],
        )
        return ParsedFile(format="ca-lisa-http-pair", source_file="test.txt", stubs=[stub])

    def test_content_type_matcher_is_case_insensitive(self, tmp_output):
        parsed = self._stub_with_headers({"Content-Type": "text/xml;charset=utf-8"})
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["request"]["headers"]["Content-Type"]["caseInsensitive"] is True
        assert mapping["request"]["headers"]["Content-Type"]["equalTo"] == "text/xml;charset=utf-8"

    def test_content_type_matcher_case_insensitive_regardless_of_header_name_casing(self, tmp_output):
        parsed = self._stub_with_headers({"content-type": "application/json"})
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert mapping["request"]["headers"]["content-type"]["caseInsensitive"] is True

    def test_other_headers_stay_case_exact(self, tmp_output):
        """Only Content-Type gets the case-insensitive treatment — an opaque
        value like SOAPAction should still require an exact match, since
        differently-cased values there could be genuinely different operations."""
        parsed = self._stub_with_headers({"SOAPAction": "getAccMasterData"})
        files = generate_wiremock_mappings(parsed, tmp_output)
        mapping = json.loads(files[0].read_text())
        assert "caseInsensitive" not in mapping["request"]["headers"]["SOAPAction"]
