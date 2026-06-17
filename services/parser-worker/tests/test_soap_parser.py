"""Tests for the SOAP TXT parser."""
from __future__ import annotations

import json

import pytest

from parser_worker.parsers.soap_txt import SoapTxtParser

PARSER = SoapTxtParser()

# ── fixtures ──────────────────────────────────────────────────────────────────

SOAP_RESPONSE_200 = """\
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetCustomerResponse>
      <CustomerId>12345</CustomerId>
    </GetCustomerResponse>
  </soap:Body>
</soap:Envelope>"""

SOAP_FAULT = """\
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>Internal Server Error</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>"""

MINIMAL_SOAP = f"""\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Customer SOAP
URL: /services/CustomerService

--- SCENARIO: GetCustomer ---
Match-Type: soap-action
Match-Value: GetCustomer
Status: 200
Content-Type: text/xml; charset=utf-8

{SOAP_RESPONSE_200}

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml; charset=utf-8

{SOAP_FAULT}
"""

SOAP_WITH_XPATH = f"""\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Payment SOAP
URL: /services/PaymentService

--- SCENARIO: InvalidAccount ---
Match-Type: soap-xpath
Match-Value: //Payment[AccountId='INVALID']
Status: 500
Content-Type: text/xml; charset=utf-8

{SOAP_FAULT}

--- SCENARIO DEFAULT ---
Status: 200
Content-Type: text/xml; charset=utf-8

{SOAP_RESPONSE_200}
"""

SOAP_WITH_BODY_CONTAINS = f"""\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Search SOAP
URL: /services/SearchService

--- SCENARIO: NotFound ---
Match-Type: body-contains
Match-Value: <SearchId>NOTFOUND</SearchId>
Status: 500
Content-Type: text/xml; charset=utf-8

{SOAP_FAULT}

--- SCENARIO DEFAULT ---
Status: 200
Content-Type: text/xml; charset=utf-8

{SOAP_RESPONSE_200}
"""


# ── can_handle ────────────────────────────────────────────────────────────────

class TestCanHandle:
    def test_accepts_soap_header(self):
        assert PARSER.can_handle(MINIMAL_SOAP, "customer.txt")

    def test_rejects_standard_mockingbird_header(self):
        assert not PARSER.can_handle("--- MOCKINGBIRD v1.0 ---\nMethod: GET\n", "file.txt")

    def test_rejects_empty_file(self):
        assert not PARSER.can_handle("", "file.txt")

    def test_rejects_json(self):
        assert not PARSER.can_handle('{"openapi": "3.0.3"}', "api.json")


# ── validate ──────────────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_minimal_soap(self):
        result = PARSER.validate(MINIMAL_SOAP)
        assert result.valid
        assert "SOAP endpoint" in result.summary
        assert "2 scenario" in result.summary

    def test_invalid_missing_url(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Missing URL

--- SCENARIO DEFAULT ---
Status: 500

"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("URL" in e.message for e in result.errors)

    def test_invalid_url_without_slash(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

URL: services/CustomerService

--- SCENARIO DEFAULT ---
Status: 500

"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("must start with /" in e.message for e in result.errors)

    def test_invalid_missing_default_scenario(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

URL: /services/CustomerService

--- SCENARIO: GetCustomer ---
Match-Type: soap-action
Match-Value: GetCustomer
Status: 200

"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("SCENARIO DEFAULT" in e.message for e in result.errors)

    def test_invalid_missing_match_type_in_named_scenario(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

URL: /services/CustomerService

--- SCENARIO: GetCustomer ---
Status: 200

--- SCENARIO DEFAULT ---
Status: 500

"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("Match-Type" in e.message for e in result.errors)

    def test_invalid_missing_match_value_for_soap_action(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

URL: /services/CustomerService

--- SCENARIO: GetCustomer ---
Match-Type: soap-action
Status: 200

--- SCENARIO DEFAULT ---
Status: 500

"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("Match-Value" in e.message for e in result.errors)

    def test_invalid_unknown_match_type(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

URL: /services/CustomerService

--- SCENARIO: GetCustomer ---
Match-Type: rest-json
Match-Value: something
Status: 200

--- SCENARIO DEFAULT ---
Status: 500

"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("rest-json" in e.message for e in result.errors)


# ── parse ─────────────────────────────────────────────────────────────────────

class TestParse:
    def test_method_is_always_post(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        assert parsed.stubs[0].request.method.value == "POST"

    def test_extracts_url(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        assert parsed.stubs[0].request.url == "/services/CustomerService"

    def test_soap_action_becomes_header_equals_match(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        stub = parsed.stubs[0]
        action_scenario = next(s for s in stub.scenarios if s.name == "GetCustomer")
        assert action_scenario.match.type.value == "header-equals"
        assert action_scenario.match.value == "SOAPAction == GetCustomer"

    def test_soap_xpath_becomes_body_xpath_match(self):
        parsed = PARSER.parse(SOAP_WITH_XPATH, "payment.txt")
        stub = parsed.stubs[0]
        xpath_scenario = next(s for s in stub.scenarios if s.name == "InvalidAccount")
        assert xpath_scenario.match.type.value == "body-xpath"
        assert xpath_scenario.match.value == "//Payment[AccountId='INVALID']"

    def test_body_contains_match(self):
        parsed = PARSER.parse(SOAP_WITH_BODY_CONTAINS, "search.txt")
        stub = parsed.stubs[0]
        contains_scenario = next(s for s in stub.scenarios if s.name == "NotFound")
        assert contains_scenario.match.type.value == "body-contains"
        assert "<SearchId>NOTFOUND</SearchId>" in contains_scenario.match.value

    def test_default_scenario_uses_always_match(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        default = next(s for s in parsed.stubs[0].scenarios if s.name == "default")
        assert default.match.type.value == "always"

    def test_xml_response_body_preserved(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        action_scenario = next(
            s for s in parsed.stubs[0].scenarios if s.name == "GetCustomer"
        )
        assert "<GetCustomerResponse>" in action_scenario.body
        assert "<CustomerId>12345</CustomerId>" in action_scenario.body

    def test_default_scenario_returns_soap_fault(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        default = next(s for s in parsed.stubs[0].scenarios if s.name == "default")
        assert default.status == 500
        assert "<soap:Fault>" in default.body

    def test_content_type_header_preserved(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        action_scenario = next(
            s for s in parsed.stubs[0].scenarios if s.name == "GetCustomer"
        )
        assert action_scenario.response_headers.get("Content-Type") == "text/xml; charset=utf-8"

    def test_stub_name_from_file(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        assert parsed.stubs[0].name == "Customer SOAP"

    def test_two_scenarios_parsed(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        assert len(parsed.stubs[0].scenarios) == 2


# ── wiremock mapping output ───────────────────────────────────────────────────

class TestSoapWireMockOutput:
    def test_soap_action_generates_header_matcher(self, tmp_path):
        from parser_worker.generator.wiremock import generate_wiremock_mappings
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        generate_wiremock_mappings(parsed, tmp_path)

        mapping_files = list((tmp_path / "mappings").glob("*.json"))
        contents = [json.loads(f.read_text()) for f in mapping_files]

        # Find the GetCustomer mapping
        action_mapping = next(
            (m for m in contents if "GetCustomer" in str(m.get("name", ""))), None
        )
        assert action_mapping is not None
        assert action_mapping["request"]["headers"]["SOAPAction"]["equalTo"] == "GetCustomer"

    def test_soap_xpath_generates_body_xpath_pattern(self, tmp_path):
        from parser_worker.generator.wiremock import generate_wiremock_mappings
        parsed = PARSER.parse(SOAP_WITH_XPATH, "payment.txt")
        generate_wiremock_mappings(parsed, tmp_path)

        mapping_files = list((tmp_path / "mappings").glob("*.json"))
        contents = [json.loads(f.read_text()) for f in mapping_files]

        xpath_mapping = next(
            (m for m in contents if "InvalidAccount" in str(m.get("name", ""))), None
        )
        assert xpath_mapping is not None
        body_patterns = xpath_mapping["request"]["bodyPatterns"]
        assert any("matchesXPath" in p for p in body_patterns)
        assert body_patterns[0]["matchesXPath"] == "//Payment[AccountId='INVALID']"

    def test_default_scenario_has_no_body_pattern(self, tmp_path):
        from parser_worker.generator.wiremock import generate_wiremock_mappings
        parsed = PARSER.parse(MINIMAL_SOAP, "customer.txt")
        generate_wiremock_mappings(parsed, tmp_path)

        mapping_files = list((tmp_path / "mappings").glob("*.json"))
        contents = [json.loads(f.read_text()) for f in mapping_files]

        default_mapping = next(
            (m for m in contents if "default" in str(m.get("name", ""))), None
        )
        assert default_mapping is not None
        assert "bodyPatterns" not in default_mapping["request"]
        assert "headers" not in default_mapping["request"]
