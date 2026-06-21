"""Tests for the CA LISA / IBM RTWS HTTP capture file parser.

Uses the real sample files from Sample_SV_Files/ as test fixtures.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from parser_worker.detector import detect_and_parse, detect_parser
from parser_worker.parsers.ca_lisa_parser import (
    CALISAParser,
    _detect_variant,
    _find_block_end,
    _infer_status_code,
    _parse_esp_request,
    _parse_esp_response,
    _parse_kvblock,
    _resolve_variables,
)

# ── locate sample files ───────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parents[3]
_ESP_DIR = _REPO_ROOT / "Sample_SV_Files" / "ESP"
_WEALTH_DIR = _REPO_ROOT / "Sample_SV_Files" / "Wealth"

ESP_REQUEST_1 = _ESP_DIR / "1781082059482RTCAERv01_Request_20260610_100059.txt"
ESP_RESPONSE_200 = _ESP_DIR / "1781082059500RTCAERv01_Success1Response_20260610_100059.txt"
ESP_RESPONSE_400 = _ESP_DIR / "1781082551676RTCAERv01_Error400Response_20260610_100911.txt"
ESP_REQUEST_2 = _ESP_DIR / "1781082552845RTCAERv01_Request_20260610_100912.txt"

WEALTH_POST_REQ = _WEALTH_DIR / "CreateAdviserPOST_Request.txt"
WEALTH_POST_RESP = _WEALTH_DIR / "CreateAdviserPost_Response.txt"
WEALTH_GET_REQ = _WEALTH_DIR / "GetAdvisers_Request.txt"
WEALTH_GET_RESP = _WEALTH_DIR / "GetAdvisersByID_Response.txt"

_SAMPLE_FILES_PRESENT = ESP_REQUEST_1.exists() and WEALTH_POST_REQ.exists()
skip_if_no_samples = pytest.mark.skipif(
    not _SAMPLE_FILES_PRESENT,
    reason="Sample_SV_Files not present in repo",
)


# ── unit: _find_block_end ─────────────────────────────────────────────────────

class TestFindBlockEnd:
    def test_simple_block(self):
        text = "{a=1}"
        assert _find_block_end(text, 0) == 5

    def test_nested_block(self):
        text = '{a={b="val"}}'
        assert _find_block_end(text, 0) == len(text)

    def test_brace_inside_string_not_counted(self):
        text = '{key="has{brace}"}'
        assert _find_block_end(text, 0) == len(text)

    def test_body_after_block(self):
        text = '{Method="POST"}{"json":"body"}'
        end = _find_block_end(text, 0)
        assert text[end:] == '{"json":"body"}'


# ── unit: _parse_kvblock ──────────────────────────────────────────────────────

class TestParseKvBlock:
    def test_simple_key_values(self):
        result = _parse_kvblock('{Method="POST" URL="/api/v1"}')
        assert result["Method"] == "POST"
        assert result["URL"] == "/api/v1"

    def test_nested_block(self):
        result = _parse_kvblock(
            '{httpDetails={Version="1.1" httpHeaders={Content-Type="application/json"}}}'
        )
        assert isinstance(result["httpDetails"], dict)
        assert result["httpDetails"]["Version"] == "1.1"
        assert result["httpDetails"]["httpHeaders"]["Content-Type"] == "application/json"

    def test_outer_braces_optional(self):
        r1 = _parse_kvblock('{Method="GET"}')
        r2 = _parse_kvblock('Method="GET"')
        assert r1 == r2

    def test_multiline(self):
        text = """{Method="POST"
URL="/v2/accounts"
StatusCode="200"}"""
        result = _parse_kvblock(text)
        assert result["Method"] == "POST"
        assert result["StatusCode"] == "200"

    def test_empty_value(self):
        result = _parse_kvblock('{key=""}')
        assert result["key"] == ""


# ── unit: _resolve_variables ──────────────────────────────────────────────────

class TestResolveVariables:
    def test_interaction_id_replaced(self):
        text = '{"id": "%%X-Interaction-Id%%"}'
        resolved, uses_template = _resolve_variables(text, "response.txt")
        assert "{{request.headers.X-Interaction-Id}}" in resolved
        assert uses_template is True

    def test_status_code_not_replaced(self):
        text = "%%StatusCode%%"
        resolved, uses_template = _resolve_variables(text, "Error400Response.txt")
        assert "%%StatusCode%%" in resolved  # left as-is
        assert uses_template is False

    def test_single_percent_artefact(self):
        # Some CA LISA recordings use %Var%% instead of %%Var%%
        text = '%X-Interaction-Id%%'
        resolved, uses_template = _resolve_variables(text, "resp.txt")
        assert "{{request.headers.X-Interaction-Id}}" in resolved
        assert uses_template is True

    def test_no_variables(self):
        text = '{"status": "ok"}'
        resolved, uses_template = _resolve_variables(text, "resp.txt")
        assert resolved == text
        assert uses_template is False


# ── unit: _infer_status_code ──────────────────────────────────────────────────

class TestInferStatusCode:
    def test_numeric_value(self):
        assert _infer_status_code("200", "") == 200
        assert _infer_status_code("404", "") == 404

    def test_error_400_from_filename(self):
        assert _infer_status_code("%%StatusCode%%", "Error400Response.txt") == 400

    def test_error_500_from_filename(self):
        assert _infer_status_code("%%StatusCode%%", "Error500_response.txt") == 500

    def test_success_from_filename(self):
        assert _infer_status_code("%%StatusCode%%", "SuccessResponse.txt") == 200

    def test_generic_error_from_filename(self):
        assert _infer_status_code("%%StatusCode%%", "ErrorResponse.txt") == 400

    def test_no_hint_defaults_to_200(self):
        assert _infer_status_code("%%StatusCode%%", "unknown.txt") == 200


# ── unit: _detect_variant ─────────────────────────────────────────────────────

class TestDetectVariant:
    def test_wealth_detected_by_requestheader_label(self):
        content = "RequestHeader:\n={Method=\"GET\"}"
        assert _detect_variant(content) == "wealth"

    def test_wealth_detected_by_responseheader_label(self):
        content = "ResponseHeader:\n={StatusCode=\"200\"}"
        assert _detect_variant(content) == "wealth"

    def test_esp_detected_without_labels(self):
        content = '={Method="POST" URL="/api"}{body}'
        assert _detect_variant(content) == "esp"


# ── CALISAParser.can_handle ───────────────────────────────────────────────────

class TestCALISAParserCanHandle:
    def setup_method(self):
        self.parser = CALISAParser()

    def test_esp_request_file(self):
        content = '={Method="POST" URL="/v2/api" httpDetails={Version="1.1"}}{}'
        assert self.parser.can_handle(content, "request.txt") is True

    def test_esp_response_file(self):
        content = 'ResponseHeader={StatusCode="200" ReasonPhrase="OK"}\nResponse..{}'
        assert self.parser.can_handle(content, "response.txt") is True

    def test_wealth_response_label(self):
        content = "ResponseHeader:\n={StatusCode=\"200\"}"
        assert self.parser.can_handle(content, "response.txt") is True

    def test_rejects_mockingbird_txt(self):
        content = "--- MOCKINGBIRD v1.0 ---\nMethod: POST\nURL: /api\n--- RESPONSE ---\nStatus: 200"
        assert self.parser.can_handle(content, "stub.txt") is False

    def test_rejects_json(self):
        content = '{"_mockingbird": "1.0", "stubs": []}'
        assert self.parser.can_handle(content, "stub.json") is False


# ── CALISAParser.validate ─────────────────────────────────────────────────────

class TestCALISAParserValidate:
    def setup_method(self):
        self.parser = CALISAParser()

    def _make_combined_esp(self, status: str = "200") -> str:
        return (
            '={Method="POST" URL="/api/test" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json"}}}{"input":"data"}'
            '\n'
            f'ResponseHeader={{StatusCode="{status}" ReasonPhrase="OK" '
            'httpDetails={Version="1.1" httpHeaders={content-type="application/json"}}}}'
            '\nResponse..{"result":"ok"}'
        )

    def test_valid_combined_esp(self):
        result = self.parser.validate(self._make_combined_esp())
        assert result.valid is True
        assert "ca-lisa" in result.format_detected

    def test_request_only_invalid(self):
        content = '={Method="POST" URL="/api"}{}'
        result = self.parser.validate(content)
        assert result.valid is False
        assert any("response" in str(e).lower() for e in result.errors)

    def test_response_only_invalid(self):
        content = 'ResponseHeader={StatusCode="200"}\nResponse..{}'
        result = self.parser.validate(content)
        assert result.valid is False
        assert any("request" in str(e).lower() for e in result.errors)

    def test_status_code_variable_valid(self):
        result = self.parser.validate(self._make_combined_esp(status="%%StatusCode%%"))
        assert result.valid is True  # %%StatusCode%% is inferred — not an error


# ── ESP format: real sample files ────────────────────────────────────────────

class TestESPFormat:
    def setup_method(self):
        self.parser = CALISAParser()

    @skip_if_no_samples
    def test_esp_200_combined(self):
        """Combine request + success response → should parse to POST stub with 200."""
        req = ESP_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = ESP_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        result = self.parser.validate(combined)
        assert result.valid, f"Validation errors: {result.errors}"

        pf = self.parser.parse(combined, "ESP_200_combined.txt")
        assert len(pf.stubs) == 1
        stub = pf.stubs[0]

        assert stub.request.method.value == "POST"
        assert "/account-enquiry-router/enquire" in stub.request.url
        assert len(stub.scenarios) == 1
        assert stub.scenarios[0].status == 200

    @skip_if_no_samples
    def test_esp_400_status_inferred_from_filename(self):
        """Error response with %%StatusCode%% should be inferred as 400 from filename."""
        req = ESP_REQUEST_2.read_text(encoding="utf-8", errors="replace")
        resp = ESP_RESPONSE_400.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        pf = self.parser.parse(combined, "1781082551676RTCAERv01_Error400Response_20260610_100911.txt")
        assert pf.stubs[0].scenarios[0].status == 400

    @skip_if_no_samples
    def test_esp_request_headers_parsed(self):
        """Content-Type and channel headers should be captured (not filtered)."""
        req = ESP_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = ESP_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "ESP_200.txt")

        req_headers = pf.stubs[0].request.required_headers
        assert "Content-Type" in req_headers
        assert req_headers["Content-Type"] == "application/json"

    @skip_if_no_samples
    def test_esp_interaction_id_becomes_wiremock_template(self):
        """%%X-Interaction-Id%% in response headers → {{request.headers.X-Interaction-Id}}."""
        req = ESP_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = ESP_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "ESP_200.txt")

        scenario = pf.stubs[0].scenarios[0]
        resp_headers = scenario.response_headers
        # The interaction ID header should be a WireMock template expression
        id_header_val = resp_headers.get("x-interaction-id", "")
        assert "{{request.headers." in id_header_val

    @skip_if_no_samples
    def test_esp_response_body_present(self):
        req = ESP_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = ESP_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "ESP_200.txt")

        body = pf.stubs[0].scenarios[0].body
        assert body is not None
        assert "accountEnquiryResponse" in body


# ── Wealth format: real sample files ─────────────────────────────────────────

class TestWealthFormat:
    def setup_method(self):
        self.parser = CALISAParser()

    @skip_if_no_samples
    def test_wealth_post_200(self):
        """POST /oxford-risk/advisers → 200 OK."""
        req = WEALTH_POST_REQ.read_text(encoding="utf-8", errors="replace")
        resp = WEALTH_POST_RESP.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        result = self.parser.validate(combined)
        assert result.valid, f"Validation errors: {result.errors}"

        pf = self.parser.parse(combined, "CreateAdviser_combined.txt")
        assert len(pf.stubs) == 1
        stub = pf.stubs[0]

        assert stub.request.method.value == "POST"
        assert "/oxford-risk/advisers" in stub.request.url
        assert stub.scenarios[0].status == 200

    @skip_if_no_samples
    def test_wealth_post_response_body(self):
        req = WEALTH_POST_REQ.read_text(encoding="utf-8", errors="replace")
        resp = WEALTH_POST_RESP.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "CreateAdviser.txt")

        body = pf.stubs[0].scenarios[0].body
        assert body is not None
        assert "ADVISER" in body
        assert "351029884" in body

    @skip_if_no_samples
    def test_wealth_get_200(self):
        """GET /oxford-risk/advisers → 200 OK, no request body required."""
        req = WEALTH_GET_REQ.read_text(encoding="utf-8", errors="replace")
        resp = WEALTH_GET_RESP.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        pf = self.parser.parse(combined, "GetAdvisers.txt")
        stub = pf.stubs[0]

        assert stub.request.method.value == "GET"
        assert stub.scenarios[0].status == 200

    @skip_if_no_samples
    def test_wealth_variant_detected(self):
        req = WEALTH_POST_REQ.read_text(encoding="utf-8", errors="replace")
        resp = WEALTH_POST_RESP.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp
        assert _detect_variant(combined) == "wealth"


# ── detector.py integration ───────────────────────────────────────────────────

class TestDetectorIntegration:
    @skip_if_no_samples
    def test_detect_parser_identifies_ca_lisa(self, tmp_path):
        req = ESP_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = ESP_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        combined = tmp_path / "ESP_combined.txt"
        combined.write_text(req + "\n" + resp, encoding="utf-8")

        parser, validation, parsed = detect_and_parse(combined)
        assert parser is not None
        assert parser.format_name == "ca-lisa-http-pair"
        assert validation.valid is True
        assert parsed is not None

    @skip_if_no_samples
    def test_detect_and_parse_zip(self, tmp_path):
        """ZIP containing ESP request + response pair should produce one stub."""
        zip_path = tmp_path / "esp_stubs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(ESP_REQUEST_1, ESP_REQUEST_1.name)
            zf.write(ESP_RESPONSE_200, ESP_RESPONSE_200.name)

        parser, validation, parsed = detect_and_parse(zip_path)
        assert validation.valid is True, f"Errors: {validation.errors}"
        assert parsed is not None
        assert len(parsed.stubs) == 1
        assert parsed.stubs[0].request.method.value == "POST"

    @skip_if_no_samples
    def test_zip_with_multiple_pairs(self, tmp_path):
        """ZIP with two ESP pairs should produce two stubs."""
        zip_path = tmp_path / "esp_multi.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(ESP_REQUEST_1, ESP_REQUEST_1.name)
            zf.write(ESP_RESPONSE_200, ESP_RESPONSE_200.name)
            zf.write(ESP_REQUEST_2, ESP_REQUEST_2.name)
            zf.write(ESP_RESPONSE_400, ESP_RESPONSE_400.name)

        parser, validation, parsed = detect_and_parse(zip_path)
        assert validation.valid is True
        assert parsed is not None
        assert len(parsed.stubs) == 2

    def test_zip_with_no_txt_files(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.md", "# nothing")

        parser, validation, parsed = detect_and_parse(zip_path)
        assert validation.valid is False
        assert any("no .txt" in str(e).lower() for e in validation.errors)


# ── format_name and ParsedFile structure ─────────────────────────────────────

class TestParsedFileStructure:
    def setup_method(self):
        self.parser = CALISAParser()

    def test_format_name(self):
        assert self.parser.format_name == "ca-lisa-http-pair"

    def _minimal_combined(self) -> str:
        return (
            '={Method="GET" URL="/health" httpDetails={Version="1.1" '
            'httpHeaders={Accept="application/json"}}}\n'
            'ResponseHeader={StatusCode="200" ReasonPhrase="OK" '
            'httpDetails={Version="1.1" httpHeaders={content-type="application/json"}}}\n'
            'Response..{"status":"UP"}'
        )

    def test_parse_returns_parsed_file(self):
        pf = self.parser.parse(self._minimal_combined(), "test.txt")
        assert pf.format == "ca-lisa-http-pair"
        assert len(pf.stubs) == 1

    def test_stub_has_one_scenario(self):
        pf = self.parser.parse(self._minimal_combined(), "test.txt")
        assert len(pf.stubs[0].scenarios) == 1

    def test_method_and_url(self):
        pf = self.parser.parse(self._minimal_combined(), "test.txt")
        assert pf.stubs[0].request.method.value == "GET"
        assert pf.stubs[0].request.url == "/health"

    def test_response_body(self):
        pf = self.parser.parse(self._minimal_combined(), "test.txt")
        assert pf.stubs[0].scenarios[0].body == '{"status":"UP"}'

    def test_host_header_filtered_from_request_matching(self):
        """Host and User-Agent should not be included in WireMock request matchers."""
        content = (
            '={Method="POST" URL="/api" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json" Host="myserver:8080" '
            'User-Agent="Java/1.8" Connection="keep-alive"}}}{}\n'
            'ResponseHeader={StatusCode="200" httpDetails={Version="1.1" '
            'httpHeaders={content-type="application/json"}}}\nResponse..{}'
        )
        pf = self.parser.parse(content, "test.txt")
        req_headers = pf.stubs[0].request.required_headers
        assert "Host" not in req_headers
        assert "User-Agent" not in req_headers
        assert "Connection" not in req_headers
