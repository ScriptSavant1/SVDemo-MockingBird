"""Tests for the dynamic per-download HTML setup guide.

The service-reference section must be built from each stub's actual
WireMock mappings — no hardcoded example content — so every assertion here
checks that specific, distinctive data injected into a ParsedFile actually
shows up (or is correctly escaped) in the rendered HTML.
"""
from __future__ import annotations

from parser_worker.generator.setup_guide import generate_setup_guide_html
from parser_worker.models import (
    HttpMethod,
    MatchCondition,
    MatchType,
    ParsedFile,
    ParsedRequestSpec,
    ParsedScenario,
    ParsedStub,
)


def _single_stub_file(
    method=HttpMethod.POST,
    url="/api/test",
    required_headers=None,
    status=200,
    body=None,
    response_headers=None,
    match=None,
    xpath_namespaces=None,
) -> ParsedFile:
    scenario = ParsedScenario(
        name="default",
        match=match or MatchCondition(type=MatchType.ALWAYS),
        status=status,
        body=body,
        response_headers=response_headers or {},
        xpath_namespaces=xpath_namespaces or {},
    )
    stub = ParsedStub(
        name="Distinctive Stub Name",
        request=ParsedRequestSpec(method=method, url=url, required_headers=required_headers or {}),
        scenarios=[scenario],
    )
    return ParsedFile(format="test", source_file="test.txt", stubs=[stub])


class TestDynamicContent:
    def test_project_name_appears(self):
        html = generate_setup_guide_html(_single_stub_file(), "My Unique Project Name")
        assert "My Unique Project Name" in html

    def test_endpoint_count_reflects_real_mappings(self):
        parsed = _single_stub_file()
        html = generate_setup_guide_html(parsed, "P")
        assert "1 endpoint(s)" in html

    def test_multiple_scenarios_all_rendered(self):
        stub = ParsedStub(
            name="Multi",
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/multi"),
            scenarios=[
                ParsedScenario(name="ok", match=MatchCondition(type=MatchType.ALWAYS), status=200),
                ParsedScenario(name="fail", match=MatchCondition(type=MatchType.ALWAYS), status=500),
            ],
        )
        parsed = ParsedFile(format="test", source_file="t", stubs=[stub])
        html = generate_setup_guide_html(parsed, "P")
        assert "2 endpoint(s)" in html
        assert html.count("swagger-op") >= 2  # each scenario gets its own card

    def test_url_and_method_appear(self):
        html = generate_setup_guide_html(
            _single_stub_file(method=HttpMethod.GET, url="/very/distinctive/path"), "P"
        )
        assert "/very/distinctive/path" in html
        assert ">GET<" in html

    def test_required_header_appears(self):
        html = generate_setup_guide_html(
            _single_stub_file(required_headers={"X-Distinctive-Header": "distinctive-value-123"}), "P"
        )
        assert "X-Distinctive-Header" in html
        assert "distinctive-value-123" in html

    def test_rest_vs_soap_classified_correctly(self):
        rest_html = generate_setup_guide_html(
            _single_stub_file(required_headers={"Content-Type": "application/json"}), "P"
        )
        assert "REST" in rest_html
        soap_html = generate_setup_guide_html(
            _single_stub_file(required_headers={"SOAPAction": "doThing"}), "P"
        )
        assert "SOAP" in soap_html

    def test_body_pattern_xpath_rendered(self):
        html = generate_setup_guide_html(
            _single_stub_file(
                match=MatchCondition(type=MatchType.BODY_XPATH, value="//ns:distinctiveTag[text()='X']"),
                xpath_namespaces={"ns": "http://distinctive.example.com/ns"},
            ),
            "P",
        )
        assert "distinctiveTag" in html
        assert "matchesXPath" in html
        assert "http://distinctive.example.com/ns" in html

    def test_body_pattern_json_path_rendered(self):
        html = generate_setup_guide_html(
            _single_stub_file(match=MatchCondition(type=MatchType.BODY_JSON_PATH, value="$.distinctiveField")),
            "P",
        )
        assert "distinctiveField" in html
        assert "matchesJsonPath" in html

    def test_no_body_pattern_shows_hint(self):
        html = generate_setup_guide_html(_single_stub_file(), "P")
        assert "No request body pattern" in html

    def test_response_status_appears(self):
        html = generate_setup_guide_html(_single_stub_file(status=201), "P")
        assert "<code>201</code>" in html

    def test_response_body_preview_appears(self):
        html = generate_setup_guide_html(
            _single_stub_file(body='{"distinctiveKey":"distinctiveResponseValue"}'), "P"
        )
        assert "distinctiveResponseValue" in html

    def test_large_response_body_truncated(self):
        big_body = "x" * 5000
        html = generate_setup_guide_html(_single_stub_file(body=big_body), "P")
        assert "truncated" in html.lower()
        # The full 5000-char body should not appear verbatim
        assert big_body not in html

    def test_empty_stub_shows_zero_endpoints(self):
        parsed = ParsedFile(format="test", source_file="t", stubs=[])
        html = generate_setup_guide_html(parsed, "Empty Project")
        assert "0 endpoint(s)" in html


class TestLookupTableStubRendering:
    """A stub that crossed the lookup-table threshold (generator/lookup_table.py)
    must still be documented — not silently dropped because it's absent from
    build_wiremock_mappings' output — and the "check your startup log" count
    must match what WireMock itself will actually report (static mappings
    only; lookup-table entries never become WireMock StubMappings)."""

    def _lookup_stub(self, scenario_count=20) -> ParsedFile:
        from parser_worker.generator.lookup_table import LOOKUP_TABLE_THRESHOLD
        assert scenario_count > LOOKUP_TABLE_THRESHOLD
        scenarios = [
            ParsedScenario(
                name=f"variant-{i + 1}",
                match=MatchCondition(type=MatchType.BODY_XPATH, value=f"//*[local-name()='AcctId' and text()='id-{i}']"),
                status=200,
                response_headers={"Content-Type": "application/xml"},
                body=f"<A><AcctId>id-{i}</AcctId></A>",
                lookup_key=f"id-{i}",
            )
            for i in range(scenario_count)
        ]
        stub = ParsedStub(
            name="Distinctive Lookup Operation",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/lookup-op"),
            scenarios=scenarios,
            lookup_discriminator_type="xpath",
            lookup_discriminator_field="AcctId",
        )
        return ParsedFile(format="test", source_file="t", stubs=[stub])

    def test_lookup_stub_gets_its_own_card_not_dropped(self):
        html = generate_setup_guide_html(self._lookup_stub(), "P")
        assert "Distinctive Lookup Operation" in html
        assert "dynamic lookup" in html
        assert "/api/lookup-op" in html
        assert "AcctId" in html

    def test_verify_log_line_counts_only_real_wiremock_mappings(self):
        """A lookup-table stub contributes zero WireMock StubMappings —
        the 'check your startup log' line must say 0, not the scenario count,
        or it would tell people to expect a number the server never prints."""
        html = generate_setup_guide_html(self._lookup_stub(20), "P")
        assert "Loaded 0 stub mappings" in html

    def test_hero_endpoint_count_includes_lookup_variants(self):
        html = generate_setup_guide_html(self._lookup_stub(20), "P")
        assert "20 endpoint(s)" in html

    def test_mixed_static_and_lookup_stubs_both_documented(self):
        static_file = _single_stub_file(url="/api/static-op")
        lookup_file = self._lookup_stub(20)
        combined = ParsedFile(
            format="test", source_file="t",
            stubs=[*static_file.stubs, *lookup_file.stubs],
        )
        html = generate_setup_guide_html(combined, "P")
        assert "/api/static-op" in html
        assert "/api/lookup-op" in html
        # 1 real WireMock mapping (the static stub) + 20 logical lookup variants
        assert "Loaded 1 stub mappings" in html
        assert "21 endpoint(s)" in html


class TestHtmlEscaping:
    """Captured header/URL/body values end up rendered into HTML — must be
    escaped so a capture containing HTML-special characters can't break the
    page structure or inject markup when the user opens their own guide."""

    def test_header_value_with_html_is_escaped(self):
        html = generate_setup_guide_html(
            _single_stub_file(required_headers={"X-Evil": "<script>alert(1)</script>"}), "P"
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_project_name_with_html_is_escaped(self):
        html = generate_setup_guide_html(_single_stub_file(), "<img src=x onerror=alert(1)>")
        assert "<img src=x onerror=alert(1)>" not in html
        assert "&lt;img" in html

    def test_response_body_with_html_is_escaped(self):
        html = generate_setup_guide_html(
            _single_stub_file(body="<script>alert('resp')</script>"), "P"
        )
        assert "<script>alert('resp')</script>" not in html
        assert "&lt;script&gt;" in html

    def test_url_with_html_is_escaped(self):
        html = generate_setup_guide_html(_single_stub_file(url='/api/"><script>x</script>'), "P")
        assert "<script>x</script>" not in html
