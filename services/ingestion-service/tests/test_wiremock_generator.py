"""Tests for ingestion_service.wiremock_generator — the local-dev-only
duplicate of parser_worker.generator.wiremock (see module docstring: this one
runs inline at upload time so local dev works without an SQS worker).

Because it's a separate implementation rather than a shared import, bugs
fixed in parser_worker's generator do NOT automatically apply here — each
fix has to be made (and tested) in both places. That's exactly how the query
parameter decoding bug below was missed on the first pass.
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
