"""Tests for ingestion_service.wiremock_generator — the ZIP-packaging wrapper
around parser_worker.generator.wiremock.build_wiremock_mappings, run inline
at upload time so local dev works without an SQS worker.

Mapping construction itself is delegated to parser_worker's generator (see
that module's docstring) — this used to be a completely separate, simpler
reimplementation with no bodyPatterns support, which is how the query
parameter decoding bug below was originally missed on its first pass here.
These tests stay to guard the ZIP-packaging behavior (one file per
stub/scenario, README included) and confirm delegation didn't silently
change what gets produced.
"""
from __future__ import annotations

import json
import zipfile
import io

from parser_worker.models import (
    HttpMethod,
    MatchCondition,
    MatchType,
    ParsedFile,
    ParsedRequestSpec,
    ParsedScenario,
    ParsedStub,
)

from ingestion_service.wiremock_generator import generate_wiremock_zip


def _single_stub_file(url: str, response_headers: dict | None = None) -> ParsedFile:
    scenario = ParsedScenario(
        name="default",
        match=MatchCondition(type=MatchType.ALWAYS),
        status=200,
        response_headers=response_headers or {},
        body='{"ok":true}',
    )
    stub = ParsedStub(
        name="Query Test",
        request=ParsedRequestSpec(method=HttpMethod.GET, url=url),
        scenarios=[scenario],
    )
    return ParsedFile(format="ca-lisa-http-pair", source_file="test.txt", stubs=[stub])


def _first_mapping(parsed_file: ParsedFile) -> dict:
    zip_bytes = generate_wiremock_zip(parsed_file)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        mapping_names = [n for n in zf.namelist() if n.endswith(".json")]
        assert mapping_names, "no mapping JSON written into the ZIP"
        return json.loads(zf.read(mapping_names[0]))


class TestQueryParameterDecoding:
    """Regression: found by loading a real generated mapping into an actual
    WireMock instance. WireMock URL-decodes incoming query strings
    (application/x-www-form-urlencoded rules: '+' -> space, %XX -> byte)
    before matching queryParameters, so a matcher built from raw, still-
    encoded capture text never matches a real request.
    """

    def test_plus_sign_decoded_to_space(self):
        mapping = _first_mapping(_single_stub_file("/api/enquire?aggregate=SUP+FLAGS"))
        assert mapping["request"]["urlPath"] == "/api/enquire"
        assert mapping["request"]["queryParameters"]["aggregate"]["equalTo"] == "SUP FLAGS"

    def test_percent_encoded_value_decoded(self):
        mapping = _first_mapping(_single_stub_file("/api/search?q=foo%26bar"))
        assert mapping["request"]["queryParameters"]["q"]["equalTo"] == "foo&bar"

    def test_plain_value_unaffected(self):
        mapping = _first_mapping(_single_stub_file("/api/enquire?aggregate=FLAGS"))
        assert mapping["request"]["queryParameters"]["aggregate"]["equalTo"] == "FLAGS"


class TestDynamicPlaceholderTransformer:
    def test_transformer_added_for_header_only_placeholder(self):
        mapping = _first_mapping(
            _single_stub_file(
                "/api/echo",
                response_headers={"x-interaction-id": "{{request.headers.X-Interaction-Id}}"},
            )
        )
        assert "response-template" in mapping["response"].get("transformers", [])

    def test_no_transformer_when_no_placeholder(self):
        mapping = _first_mapping(_single_stub_file("/api/plain"))
        assert "transformers" not in mapping["response"]


class TestContentTypeHeaderCaseInsensitive:
    """Regression: Jetty (WireMock's underlying HTTP server) normalises the
    Content-Type header's charset casing before matching, so a verbatim-
    captured value never matches live traffic. See the identical test in
    parser-worker's test_wiremock_generator.py for the full story."""

    def _stub_with_headers(self, headers: dict) -> ParsedFile:
        scenario = ParsedScenario(name="default", match=MatchCondition(type=MatchType.ALWAYS), status=200)
        stub = ParsedStub(
            name="Header Test",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/op", required_headers=headers),
            scenarios=[scenario],
        )
        return ParsedFile(format="ca-lisa-http-pair", source_file="test.txt", stubs=[stub])

    def test_content_type_matcher_is_case_insensitive(self):
        mapping = _first_mapping(self._stub_with_headers({"Content-Type": "text/xml;charset=utf-8"}))
        assert mapping["request"]["headers"]["Content-Type"]["caseInsensitive"] is True

    def test_other_headers_stay_case_exact(self):
        mapping = _first_mapping(self._stub_with_headers({"SOAPAction": "getAccMasterData"}))
        assert "caseInsensitive" not in mapping["request"]["headers"]["SOAPAction"]


class TestSameUrlMultiCaptureDoesNotCollide:
    """Regression: the old standalone implementation here had no
    bodyPatterns support at all, so a stub with several scenarios recorded
    at the same URL (see parser_worker's ca_lisa_parser same-URL
    differentiation) would produce mapping files that collide in WireMock —
    every scenario had an identical, unconditional request matcher, so only
    the first one registered could ever actually be returned.
    """

    def test_scenarios_get_distinct_body_matchers(self):
        scenarios = [
            ParsedScenario(
                name=f"variant-{i}",
                match=MatchCondition(
                    type=MatchType.BODY_XPATH,
                    value=f"//*[local-name()='Id' and text()='{i}']",
                ),
                status=200,
                body=f"<A><Id>{i}</Id></A>",
                lookup_key=str(i),
            )
            for i in range(3)
        ]
        stub = ParsedStub(
            name="Multi Capture",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/multi"),
            scenarios=scenarios,
        )
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[stub])

        zip_bytes = generate_wiremock_zip(parsed)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            mapping_names = [n for n in zf.namelist() if n.endswith(".json")]
            mappings = [json.loads(zf.read(n)) for n in mapping_names]

        assert len(mappings) == 3
        body_patterns = [m["request"].get("bodyPatterns") for m in mappings]
        assert all(bp for bp in body_patterns), "every scenario must carry a distinguishing bodyPatterns matcher"
        xpaths = {bp[0]["matchesXPath"] for bp in body_patterns}
        assert len(xpaths) == 3  # each scenario's matcher is unique — no two collide

    def test_high_variant_stub_still_gets_static_mappings_here(self):
        """Above generator/lookup_table.py's threshold, the full Spring Boot
        project switches to the dynamic lookup-table engine — but this plain
        JSON-files ZIP has no Java extension to run that engine, so it must
        still get one static mapping per scenario regardless of the count."""
        from parser_worker.generator.lookup_table import LOOKUP_TABLE_THRESHOLD

        count = LOOKUP_TABLE_THRESHOLD + 5
        scenarios = [
            ParsedScenario(
                name=f"variant-{i}",
                match=MatchCondition(type=MatchType.BODY_XPATH, value=f"//*[local-name()='Id' and text()='{i}']"),
                status=200,
                body=f"<A><Id>{i}</Id></A>",
                lookup_key=str(i),
            )
            for i in range(count)
        ]
        stub = ParsedStub(
            name="High Variant",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/high-variant"),
            scenarios=scenarios,
            lookup_discriminator_type="xpath",
            lookup_discriminator_field="Id",
        )
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[stub])

        zip_bytes = generate_wiremock_zip(parsed)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            mapping_names = [n for n in zf.namelist() if n.endswith(".json")]
        assert len(mapping_names) == count
