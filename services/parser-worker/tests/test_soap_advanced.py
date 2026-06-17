"""Phase 2 Sprint 7 — SOAP advanced tests.

Verifies:
  - Namespace-aware XPath: Match-XPath-NS parsed into xpath_namespaces
  - WireMock JSON xPathNamespaces emitted correctly
  - Validation catches malformed Match-XPath-NS lines
  - Match-XPath-NS filtered from response body
  - Spring Boot template files for WS-Security and WSDL serving exist
  - End-to-end pipeline with the committed example file
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from parser_worker.detector import detect_and_parse
from parser_worker.generator.wiremock import generate_wiremock_mappings, _apply_body_matcher
from parser_worker.models import MatchCondition, MatchType, ParsedScenario
from parser_worker.parsers.soap_txt import (
    SoapTxtParser, _parse_xpath_namespaces,
)


PARSER = SoapTxtParser()

# ── helpers ───────────────────────────────────────────────────────────────────

def _write(tmp_path: Path, content: str, filename: str = "stub.txt") -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


def _mappings(tmp_path: Path, content: str) -> list[dict]:
    f = _write(tmp_path, content)
    _, _, parsed = detect_and_parse(f)
    out = tmp_path / "out"
    generate_wiremock_mappings(parsed, out)
    return [json.loads(p.read_text()) for p in sorted((out / "mappings").glob("*.json"))]


def _stub_engine_dir() -> Path:
    return Path(__file__).parent.parent / \
        "src/parser_worker/templates/stub-engine"


def _example_file() -> Path:
    return Path(__file__).parent.parent.parent.parent / \
        "docs/input-formats/examples/soap-namespace.txt"


MINIMAL_SOAP = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Customer SOAP
URL: /ws/customer

--- SCENARIO: Get Customer ---
Match-Type: soap-xpath
Match-Value: //cust:GetCustomer/cust:id
Match-XPath-NS: cust=http://example.com/customer
Status: 200
Content-Type: text/xml

<result>ok</result>

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml

<fault>error</fault>
"""

MULTI_NS_SOAP = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Multi-NS SOAP
URL: /ws/service

--- SCENARIO: Complex XPath ---
Match-Type: soap-xpath
Match-Value: //cust:Request/env:Header/auth:Token
Match-XPath-NS: env=http://schemas.xmlsoap.org/soap/envelope/
Match-XPath-NS: cust=http://example.com/customer
Match-XPath-NS: auth=http://example.com/auth
Status: 200
Content-Type: text/xml

<ok/>

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml

<fault/>
"""


# ── _parse_xpath_namespaces ───────────────────────────────────────────────────

class TestParseXPathNamespaces:

    def test_single_namespace_extracted(self):
        lines = [
            "Match-Type: soap-xpath",
            "Match-XPath-NS: cust=http://example.com/customer",
        ]
        ns = _parse_xpath_namespaces(lines)
        assert ns == {"cust": "http://example.com/customer"}

    def test_multiple_namespaces_extracted(self):
        lines = [
            "Match-XPath-NS: soap=http://schemas.xmlsoap.org/soap/envelope/",
            "Match-XPath-NS: cust=http://example.com/customer",
            "Match-XPath-NS: auth=http://example.com/auth",
        ]
        ns = _parse_xpath_namespaces(lines)
        assert ns["soap"] == "http://schemas.xmlsoap.org/soap/envelope/"
        assert ns["cust"] == "http://example.com/customer"
        assert ns["auth"] == "http://example.com/auth"
        assert len(ns) == 3

    def test_no_namespace_lines_returns_empty_dict(self):
        lines = ["Match-Type: soap-action", "Match-Value: GetCustomer"]
        ns = _parse_xpath_namespaces(lines)
        assert ns == {}

    def test_uri_with_equals_sign_preserved(self):
        # URNs sometimes contain = in their path
        lines = ["Match-XPath-NS: tns=http://example.com/ns?version=2"]
        ns = _parse_xpath_namespaces(lines)
        assert ns["tns"] == "http://example.com/ns?version=2"

    def test_whitespace_trimmed(self):
        lines = ["  Match-XPath-NS:  soap = http://schemas.xmlsoap.org/soap/envelope/  "]
        # strip_level2_sections will have stripped the outer whitespace already
        lines = [l.strip() for l in lines]
        ns = _parse_xpath_namespaces(lines)
        assert "soap" in ns

    def test_line_without_equals_ignored(self):
        lines = ["Match-XPath-NS: badvalue"]
        ns = _parse_xpath_namespaces(lines)
        assert ns == {}

    def test_empty_prefix_ignored(self):
        lines = ["Match-XPath-NS: =http://example.com/ns"]
        ns = _parse_xpath_namespaces(lines)
        assert ns == {}

    def test_empty_uri_ignored(self):
        lines = ["Match-XPath-NS: cust="]
        ns = _parse_xpath_namespaces(lines)
        assert ns == {}

    def test_non_ns_lines_not_returned(self):
        lines = [
            "Match-Type: soap-xpath",
            "Match-Value: //cust:GetCustomer",
            "Match-XPath-NS: cust=http://example.com/customer",
            "Status: 200",
        ]
        ns = _parse_xpath_namespaces(lines)
        assert list(ns.keys()) == ["cust"]


# ── SOAP parser namespace integration ─────────────────────────────────────────

class TestSoapParserNamespaces:

    def test_namespace_set_on_scenario(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "test.txt")
        get_customer = parsed.stubs[0].scenarios[0]  # first = Get Customer
        assert get_customer.xpath_namespaces == {"cust": "http://example.com/customer"}

    def test_multiple_namespaces_on_scenario(self):
        parsed = PARSER.parse(MULTI_NS_SOAP, "test.txt")
        scenario = parsed.stubs[0].scenarios[0]
        assert len(scenario.xpath_namespaces) == 3
        assert "env" in scenario.xpath_namespaces
        assert "cust" in scenario.xpath_namespaces
        assert "auth" in scenario.xpath_namespaces

    def test_default_scenario_has_empty_namespaces(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "test.txt")
        default = next(s for s in parsed.stubs[0].scenarios if s.name == "default")
        assert default.xpath_namespaces == {}

    def test_soap_action_scenario_has_empty_namespaces(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Action SOAP
URL: /ws/svc

--- SCENARIO: Get By Action ---
Match-Type: soap-action
Match-Value: GetCustomer
Status: 200
Content-Type: text/xml

<ok/>

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml

<fault/>
"""
        parsed = PARSER.parse(content, "action.txt")
        scenario = parsed.stubs[0].scenarios[0]
        assert scenario.xpath_namespaces == {}

    def test_namespace_lines_not_in_response_body(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "test.txt")
        scenario = parsed.stubs[0].scenarios[0]
        assert scenario.body is not None
        assert "Match-XPath-NS" not in scenario.body
        assert "cust=" not in scenario.body.split("<")[0]

    def test_namespace_lines_not_in_response_headers(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "test.txt")
        scenario = parsed.stubs[0].scenarios[0]
        for header_key in scenario.response_headers:
            assert "XPath" not in header_key

    def test_response_body_still_correctly_parsed(self):
        parsed = PARSER.parse(MINIMAL_SOAP, "test.txt")
        get_customer = parsed.stubs[0].scenarios[0]
        assert "<result>ok</result>" in get_customer.body


# ── SOAP validation of namespace fields ───────────────────────────────────────

class TestSoapNamespaceValidation:

    def test_valid_namespace_passes_validation(self):
        result = PARSER.validate(MINIMAL_SOAP)
        assert result.valid, [str(e) for e in result.errors]

    def test_multiple_namespaces_pass_validation(self):
        result = PARSER.validate(MULTI_NS_SOAP)
        assert result.valid, [str(e) for e in result.errors]

    def test_namespace_without_equals_fails(self):
        content = MINIMAL_SOAP.replace(
            "Match-XPath-NS: cust=http://example.com/customer",
            "Match-XPath-NS: badvalue",
        )
        result = PARSER.validate(content)
        assert not result.valid
        assert any("Match-XPath-NS" in str(e) for e in result.errors)

    def test_namespace_with_wrong_match_type_fails(self):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Wrong NS
URL: /ws/svc

--- SCENARIO: With Action ---
Match-Type: soap-action
Match-Value: GetCustomer
Match-XPath-NS: cust=http://example.com/customer
Status: 200
Content-Type: text/xml

<ok/>

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml

<fault/>
"""
        result = PARSER.validate(content)
        assert not result.valid
        assert any("soap-xpath" in str(e) for e in result.errors)


# ── WireMock JSON output ───────────────────────────────────────────────────────

class TestXPathNamespacesWireMockOutput:

    def test_single_namespace_in_mapping(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_SOAP)
        xpath_mapping = next(m for m in mappings if "Get Customer" in m["name"])
        patterns = xpath_mapping["request"]["bodyPatterns"]
        assert len(patterns) == 1
        assert "xPathNamespaces" in patterns[0]
        assert patterns[0]["xPathNamespaces"]["cust"] == "http://example.com/customer"

    def test_multiple_namespaces_in_mapping(self, tmp_path):
        mappings = _mappings(tmp_path, MULTI_NS_SOAP)
        xpath_mapping = next(m for m in mappings if "Complex XPath" in m["name"])
        ns = xpath_mapping["request"]["bodyPatterns"][0]["xPathNamespaces"]
        assert ns["env"] == "http://schemas.xmlsoap.org/soap/envelope/"
        assert ns["cust"] == "http://example.com/customer"
        assert ns["auth"] == "http://example.com/auth"

    def test_no_namespaces_no_xpath_namespaces_field(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Plain XPath
URL: /ws/svc

--- SCENARIO: Get Customer ---
Match-Type: soap-xpath
Match-Value: //GetCustomer/id
Status: 200
Content-Type: text/xml

<ok/>

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml

<fault/>
"""
        mappings = _mappings(tmp_path, content)
        xpath_mapping = next(m for m in mappings if "Get Customer" in m["name"])
        pattern = xpath_mapping["request"]["bodyPatterns"][0]
        assert "xPathNamespaces" not in pattern
        assert "matchesXPath" in pattern

    def test_matches_xpath_value_correct(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_SOAP)
        xpath_mapping = next(m for m in mappings if "Get Customer" in m["name"])
        assert xpath_mapping["request"]["bodyPatterns"][0]["matchesXPath"] == \
            "//cust:GetCustomer/cust:id"

    def test_soap_action_mapping_has_no_xpath_namespaces(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 SOAP ---

Name: Action Only
URL: /ws/svc

--- SCENARIO: By Action ---
Match-Type: soap-action
Match-Value: GetCustomer
Status: 200
Content-Type: text/xml

<ok/>

--- SCENARIO DEFAULT ---
Status: 500
Content-Type: text/xml

<fault/>
"""
        mappings = _mappings(tmp_path, content)
        by_action = next(m for m in mappings if "By Action" in m["name"])
        assert "bodyPatterns" not in by_action["request"]

    def test_default_scenario_has_no_body_pattern(self, tmp_path):
        mappings = _mappings(tmp_path, MINIMAL_SOAP)
        default = next(m for m in mappings if "default" in m["name"].lower())
        assert "bodyPatterns" not in default["request"]


# ── _apply_body_matcher directly ──────────────────────────────────────────────

class TestApplyBodyMatcherNamespaces:

    def test_xpath_with_namespaces(self):
        block: dict = {}
        match = MatchCondition(type=MatchType.BODY_XPATH, value="//cust:GetCustomer")
        namespaces = {"cust": "http://example.com/customer"}
        _apply_body_matcher(block, match, namespaces)
        pattern = block["bodyPatterns"][0]
        assert pattern["matchesXPath"] == "//cust:GetCustomer"
        assert pattern["xPathNamespaces"] == {"cust": "http://example.com/customer"}

    def test_xpath_without_namespaces_no_field(self):
        block: dict = {}
        match = MatchCondition(type=MatchType.BODY_XPATH, value="//GetCustomer")
        _apply_body_matcher(block, match, None)
        pattern = block["bodyPatterns"][0]
        assert "xPathNamespaces" not in pattern
        assert pattern["matchesXPath"] == "//GetCustomer"

    def test_xpath_empty_namespaces_dict_no_field(self):
        block: dict = {}
        match = MatchCondition(type=MatchType.BODY_XPATH, value="//GetCustomer")
        _apply_body_matcher(block, match, {})
        pattern = block["bodyPatterns"][0]
        assert "xPathNamespaces" not in pattern

    def test_body_contains_unaffected_by_namespace_param(self):
        block: dict = {}
        match = MatchCondition(type=MatchType.BODY_CONTAINS, value="hello")
        _apply_body_matcher(block, match, {"ns": "http://example.com"})
        assert block["bodyPatterns"][0] == {"contains": "hello"}

    def test_namespaces_dict_is_a_copy(self):
        block: dict = {}
        match = MatchCondition(type=MatchType.BODY_XPATH, value="//x")
        original = {"cust": "http://example.com"}
        _apply_body_matcher(block, match, original)
        # Mutating original must not affect what was stored in the mapping
        original["cust"] = "CHANGED"
        assert block["bodyPatterns"][0]["xPathNamespaces"]["cust"] == "http://example.com"


# ── template files existence ──────────────────────────────────────────────────

class TestSpringBootSoapTemplates:

    def test_ws_security_config_exists(self):
        f = _stub_engine_dir() / \
            "src/main/java/com/natwest/mockingbird/stubs/WsSecurityConfig.java"
        assert f.exists(), f"WsSecurityConfig.java not found at {f}"

    def test_wsdl_config_exists(self):
        f = _stub_engine_dir() / \
            "src/main/java/com/natwest/mockingbird/stubs/WsdlConfig.java"
        assert f.exists(), f"WsdlConfig.java not found at {f}"

    def test_wsdl_placeholder_exists(self):
        f = _stub_engine_dir() / "src/main/resources/wsdl/service.wsdl"
        assert f.exists(), f"service.wsdl not found at {f}"

    def test_ws_security_config_conditional_on_property(self):
        f = _stub_engine_dir() / \
            "src/main/java/com/natwest/mockingbird/stubs/WsSecurityConfig.java"
        content = f.read_text(encoding="utf-8")
        assert "ConditionalOnProperty" in content
        assert "ws-security.enabled" in content

    def test_wsdl_config_conditional_on_property(self):
        f = _stub_engine_dir() / \
            "src/main/java/com/natwest/mockingbird/stubs/WsdlConfig.java"
        content = f.read_text(encoding="utf-8")
        assert "ConditionalOnProperty" in content
        assert "wsdl.enabled" in content

    def test_ws_security_config_no_hardcoded_credentials(self):
        f = _stub_engine_dir() / \
            "src/main/java/com/natwest/mockingbird/stubs/WsSecurityConfig.java"
        content = f.read_text(encoding="utf-8")
        # Credentials must come from @Value injection, never be hardcoded strings
        assert "password123" not in content
        assert "changeme" not in content
        assert "@Value" in content

    def test_wsdl_file_is_valid_xml(self):
        import xml.etree.ElementTree as ET
        f = _stub_engine_dir() / "src/main/resources/wsdl/service.wsdl"
        # Should parse without raising ParseError
        tree = ET.parse(f)
        root = tree.getroot()
        assert root is not None

    def test_pom_has_spring_ws_security(self):
        pom = (_stub_engine_dir() / "pom.xml").read_text(encoding="utf-8")
        assert "spring-ws-security" in pom

    def test_pom_has_wss4j(self):
        pom = (_stub_engine_dir() / "pom.xml").read_text(encoding="utf-8")
        assert "wss4j-ws-security-dom" in pom

    def test_application_yml_has_soap_section(self):
        yml = (_stub_engine_dir() / "src/main/resources/application.yml").read_text(encoding="utf-8")
        assert "mockingbird.soap" in yml or "mockingbird:" in yml
        assert "ws-security" in yml
        assert "wsdl" in yml

    def test_springboot_generator_copies_ws_security_config(self, tmp_path):
        from parser_worker.generator.springboot import generate_springboot_project
        from parser_worker.models import (
            HttpMethod, MatchCondition, MatchType,
            ParsedFile, ParsedRequestSpec, ParsedScenario, ParsedStub,
        )
        parsed = ParsedFile(
            format="soap-txt",
            source_file="test.txt",
            stubs=[
                ParsedStub(
                    name="Test",
                    request=ParsedRequestSpec(method=HttpMethod.POST, url="/ws/test"),
                    scenarios=[
                        ParsedScenario(
                            name="default",
                            match=MatchCondition(type=MatchType.ALWAYS),
                            status=200,
                            body="<ok/>",
                        )
                    ],
                )
            ],
        )
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "test-stub", "Test Stub")
        java_dir = out / "src/main/java/com/natwest/mockingbird/stubs"
        assert (java_dir / "WsSecurityConfig.java").exists()
        assert (java_dir / "WsdlConfig.java").exists()
        assert (out / "src/main/resources/wsdl/service.wsdl").exists()


# ── example file round-trip ────────────────────────────────────────────────────

class TestSoapNamespaceExampleFile:

    def test_example_file_exists(self):
        assert _example_file().exists(), \
            f"soap-namespace.txt not found at {_example_file()}"

    def test_example_file_validates(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("soap-namespace.txt not found")
        result = PARSER.validate(example.read_text(encoding="utf-8"))
        assert result.valid, [str(e) for e in result.errors]

    def test_example_file_detected_as_soap_txt(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("soap-namespace.txt not found")
        _, result, _ = detect_and_parse(example)
        assert result.format_detected == "soap-txt"

    def test_example_file_namespace_scenario_has_namespaces(self):
        example = _example_file()
        if not example.exists():
            pytest.skip("soap-namespace.txt not found")
        _, _, parsed = detect_and_parse(example)
        scenarios = parsed.stubs[0].scenarios
        xpath_scenario = next(s for s in scenarios if s.match.type == MatchType.BODY_XPATH)
        assert "soap" in xpath_scenario.xpath_namespaces
        assert "cust" in xpath_scenario.xpath_namespaces

    def test_example_file_wireMock_has_xpath_namespaces(self, tmp_path):
        example = _example_file()
        if not example.exists():
            pytest.skip("soap-namespace.txt not found")
        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        xpath_mapping = next(
            m for m in mapping_dicts
            if m["request"].get("bodyPatterns")
            and "matchesXPath" in m["request"]["bodyPatterns"][0]
        )
        assert "xPathNamespaces" in xpath_mapping["request"]["bodyPatterns"][0]
