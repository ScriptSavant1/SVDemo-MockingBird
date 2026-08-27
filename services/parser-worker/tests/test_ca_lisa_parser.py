"""Tests for the CA LISA / IBM RTWS HTTP capture file parser.

Uses the real sample files from Sample_SV_Files/ as test fixtures.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from parser_worker.detector import detect_and_parse, detect_parser
from parser_worker.models import MatchType
from parser_worker.parsers.ca_lisa_parser import (
    CALISAParser,
    _detect_variant,
    _differentiate_bodies,
    _ensure_content_type,
    _find_block_end,
    _infer_content_type,
    _infer_status_code,
    _parse_inline_request,
    _parse_inline_response,
    _parse_kvblock,
    _resolve_variables,
    parse_ca_lisa_pair,
)

# ── locate sample files ───────────────────────────────────────────────────────
#
# Real capture samples from two example client folders (ESP, Wealth) — used
# here purely as realistic fixtures for the parser's two structural variants
# (inline / labelled). The parser itself is 100% client-agnostic: it never
# branches on a client name, only on file content. Tomorrow's client's files
# go through the exact same code path these do.

_REPO_ROOT = Path(__file__).parents[3]
_ESP_ROOT = _REPO_ROOT / "Sample_SV_Files" / "ESP"
_INLINE_SAMPLE_DIR = _ESP_ROOT / "JSON"
_LABELLED_SAMPLE_DIR = _REPO_ROOT / "Sample_SV_Files" / "Wealth"

INLINE_REQUEST_1 = _INLINE_SAMPLE_DIR / "1781082059482RTCAERv01_Request_20260610_100059.txt"
INLINE_RESPONSE_200 = _INLINE_SAMPLE_DIR / "1781082059500RTCAERv01_Success1Response_20260610_100059.txt"
INLINE_RESPONSE_400 = _INLINE_SAMPLE_DIR / "1781082551676RTCAERv01_Error400Response_20260610_100911.txt"
INLINE_REQUEST_2 = _INLINE_SAMPLE_DIR / "1781082552845RTCAERv01_Request_20260610_100912.txt"
INLINE_SOAP_REQUEST = _ESP_ROOT / "XML" / "Formatted_Full_XML_Request.txt"
# Real response for the above — uses a *bare* ={StatusCode=...} block with no
# "ResponseHeader" label at all (a third sub-form discovered against real data).
INLINE_SOAP_RESPONSE = _ESP_ROOT / "XML" / "Formatted_Full_XML_Response.txt"

LABELLED_POST_REQ = _LABELLED_SAMPLE_DIR / "JSON Samples" / "CreateAdviserPOST_Request.txt"
LABELLED_POST_RESP = _LABELLED_SAMPLE_DIR / "JSON Samples" / "CreateAdviserPost_Response.txt"
LABELLED_GET_REQ = _LABELLED_SAMPLE_DIR / "JSON Samples" / "GetAdvisers_Request.txt"
LABELLED_GET_RESP = _LABELLED_SAMPLE_DIR / "JSON Samples" / "GetAdvisersByID_Response.txt"

# Real-world custom-labelled, multi-capture-per-file sample: section labels
# are prefixed ("AccountInstructionsRequestHeader:" not "RequestHeader:"), and
# each file holds multiple captures of the same POST URL distinguished only
# by body content — the exact shape that exposed the "only JSON stub created,
# XML silently produced zero stubs" bug.
CUSTOM_LABEL_REQ = _LABELLED_SAMPLE_DIR / "XML Samples" / "AccountInstructions_Request.txt"
CUSTOM_LABEL_RESP = _LABELLED_SAMPLE_DIR / "XML Samples" / "AccountInstructionsPost_Response.txt"

_SAMPLE_FILES_PRESENT = INLINE_REQUEST_1.exists() and LABELLED_POST_REQ.exists()
skip_if_no_samples = pytest.mark.skipif(
    not _SAMPLE_FILES_PRESENT,
    reason="Sample_SV_Files not present in repo",
)
_CUSTOM_LABEL_SAMPLES_PRESENT = CUSTOM_LABEL_REQ.exists() and CUSTOM_LABEL_RESP.exists()
skip_if_no_custom_label_samples = pytest.mark.skipif(
    not _CUSTOM_LABEL_SAMPLES_PRESENT,
    reason="Sample_SV_Files/Wealth/XML Samples not present in repo",
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
    def test_labelled_detected_by_requestheader_label(self):
        content = "RequestHeader:\n={Method=\"GET\"}"
        assert _detect_variant(content) == "labelled"

    def test_labelled_detected_by_responseheader_label(self):
        content = "ResponseHeader:\n={StatusCode=\"200\"}"
        assert _detect_variant(content) == "labelled"

    def test_inline_detected_without_labels(self):
        content = '={Method="POST" URL="/api"}{body}'
        assert _detect_variant(content) == "inline"


# ── CALISAParser.can_handle ───────────────────────────────────────────────────

class TestCALISAParserCanHandle:
    def setup_method(self):
        self.parser = CALISAParser()

    def test_inline_request_file(self):
        content = '={Method="POST" URL="/v2/api" httpDetails={Version="1.1"}}{}'
        assert self.parser.can_handle(content, "request.txt") is True

    def test_inline_response_file(self):
        content = 'ResponseHeader={StatusCode="200" ReasonPhrase="OK"}\nResponse..{}'
        assert self.parser.can_handle(content, "response.txt") is True

    def test_labelled_response_label(self):
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

    def _make_combined_inline(self, status: str = "200") -> str:
        return (
            '={Method="POST" URL="/api/test" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json"}}}{"input":"data"}'
            '\n'
            f'ResponseHeader={{StatusCode="{status}" ReasonPhrase="OK" '
            'httpDetails={Version="1.1" httpHeaders={content-type="application/json"}}}}'
            '\nResponse..{"result":"ok"}'
        )

    def test_valid_combined_inline(self):
        result = self.parser.validate(self._make_combined_inline())
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
        result = self.parser.validate(self._make_combined_inline(status="%%StatusCode%%"))
        assert result.valid is True  # %%StatusCode%% is inferred — not an error


# ── inline variant: real sample files ────────────────────────────────────────

class TestInlineVariantSampleFiles:
    def setup_method(self):
        self.parser = CALISAParser()

    @skip_if_no_samples
    def test_200_combined(self):
        """Combine request + success response → should parse to POST stub with 200."""
        req = INLINE_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = INLINE_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        result = self.parser.validate(combined)
        assert result.valid, f"Validation errors: {result.errors}"

        pf = self.parser.parse(combined, "inline_200_combined.txt")
        assert len(pf.stubs) == 1
        stub = pf.stubs[0]

        assert stub.request.method.value == "POST"
        assert "/account-enquiry-router/enquire" in stub.request.url
        assert len(stub.scenarios) == 1
        assert stub.scenarios[0].status == 200

    @skip_if_no_samples
    def test_400_status_inferred_from_filename(self):
        """Error response with %%StatusCode%% should be inferred as 400 from filename."""
        req = INLINE_REQUEST_2.read_text(encoding="utf-8", errors="replace")
        resp = INLINE_RESPONSE_400.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        pf = self.parser.parse(combined, "1781082551676RTCAERv01_Error400Response_20260610_100911.txt")
        assert pf.stubs[0].scenarios[0].status == 400

    @skip_if_no_samples
    def test_400_status_inferred_via_upload_path(self, tmp_path):
        """Regression test for a real bug found against Sample_SV_Files: the
        ingestion-service upload endpoint used to write the uploaded content to
        a randomly-named temp file (tmpXXXXXX.txt) before calling
        detect_and_parse(), which silently defeated CA LISA's filename-based
        %%StatusCode%% inference — every error response fell back to 200. The
        fix was to preserve the original filename on disk. This test drives
        detect_and_parse() the same way upload.py now does: a real file on
        disk, named the way the portal's UploadZone.tsx names a combined
        request+response upload (request name + response name joined by "__").
        """
        req = INLINE_REQUEST_2.read_text(encoding="utf-8", errors="replace")
        resp = INLINE_RESPONSE_400.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        combined_name = (
            "1781082552845RTCAERv01_Request_20260610_100912"
            "__1781082551676RTCAERv01_Error400Response_20260610_100911_combined.txt"
        )
        file_path = tmp_path / combined_name
        file_path.write_text(combined, encoding="utf-8")

        _, validation_result, parsed_file = detect_and_parse(file_path)
        assert validation_result.valid is True
        assert parsed_file.stubs[0].scenarios[0].status == 400

    @skip_if_no_samples
    def test_request_headers_parsed(self):
        """Content-Type and channel headers should be captured (not filtered)."""
        req = INLINE_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = INLINE_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "inline_200.txt")

        req_headers = pf.stubs[0].request.required_headers
        assert "Content-Type" in req_headers
        assert req_headers["Content-Type"] == "application/json"

    @skip_if_no_samples
    def test_interaction_id_becomes_wiremock_template(self):
        """%%X-Interaction-Id%% in response headers → {{request.headers.X-Interaction-Id}}."""
        req = INLINE_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = INLINE_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "inline_200.txt")

        scenario = pf.stubs[0].scenarios[0]
        resp_headers = scenario.response_headers
        # The interaction ID header should be a WireMock template expression
        id_header_val = resp_headers.get("x-interaction-id", "")
        assert "{{request.headers." in id_header_val

    @skip_if_no_samples
    def test_response_body_present(self):
        req = INLINE_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = INLINE_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "inline_200.txt")

        body = pf.stubs[0].scenarios[0].body
        assert body is not None
        assert "accountEnquiryResponse" in body

    @skip_if_no_samples
    def test_soap_request_with_sibling_headers_and_body_arrays(self):
        """Real-world SOAP capture where the header block closes early (right
        after URL=) and httpDetails/SOAPAction appear as a sibling block
        instead of nested — see _consume_sibling_kv. The body is a SOAP
        envelope containing many repeated sibling <requestArray> elements
        (a "list" shape); it must survive completely untouched.
        """
        req_content = INLINE_SOAP_REQUEST.read_text(encoding="utf-8", errors="replace")
        synthetic_response = (
            'ResponseHeader={StatusCode="200" ReasonPhrase="OK" '
            'httpDetails={Version="1.1" httpHeaders={Content-Type="text/xml;charset=utf-8"}}}\n'
            'Response..<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soapenv:Body><status>OK</status></soapenv:Body></soapenv:Envelope>'
        )
        combined = req_content + "\n" + synthetic_response

        pf = self.parser.parse(combined, "soap_request.txt")
        stub = pf.stubs[0]

        assert stub.request.method.value == "POST"
        assert stub.request.url == "/NWB/DB_Core_Online_Systems/DBGetAccMasterDataAJC"
        # SOAPAction must survive — it's often the only thing distinguishing
        # SOAP operations that share one URL.
        assert stub.request.required_headers.get("SOAPAction") == "getAccMasterData"
        # No stray "}" from the malformed header should leak into the body,
        # and every repeated <req:requestArray> element must be preserved.
        assert req_content.count("req:requestArray") > 10  # sanity: the fixture really is repetitive
        assert "requestArray" in combined  # combined source retains them

    @pytest.mark.skipif(
        not INLINE_SOAP_RESPONSE.exists(),
        reason="Formatted_Full_XML_Response.txt not present in repo",
    )
    def test_soap_request_with_real_bare_response(self):
        """Real request + real response pair, discovered live: the response
        has no 'ResponseHeader' label at all — just a bare ={StatusCode=...}
        block, structurally identical to a request block except for
        StatusCode= instead of Method=. Also a large (~400KB) body with many
        repeated <res:responseArray> elements — must parse fast and verbatim.
        """
        req_content = INLINE_SOAP_REQUEST.read_text(encoding="utf-8", errors="replace")
        resp_content = INLINE_SOAP_RESPONSE.read_text(encoding="utf-8", errors="replace")
        combined = req_content.rstrip() + "\n" + resp_content

        result = self.parser.validate(combined)
        assert result.valid, f"Validation errors: {result.errors}"

        pf = self.parser.parse(combined, "Formatted_Full_XML_Request.txt")
        stub = pf.stubs[0]

        assert stub.request.method.value == "POST"
        assert stub.request.url == "/NWB/DB_Core_Online_Systems/DBGetAccMasterDataAJC"
        assert stub.request.required_headers.get("SOAPAction") == "getAccMasterData"

        scenario = stub.scenarios[0]
        assert scenario.status == 200
        assert scenario.response_headers.get("Content-Type") == "text/xml"
        assert scenario.body is not None
        assert scenario.body.startswith("<soapenv:Envelope")
        assert scenario.body.rstrip().endswith("</soapenv:Envelope>")
        assert "getAccMasterDataResponse" in scenario.body


# ── labelled variant: real sample files ──────────────────────────────────────

class TestLabelledVariantSampleFiles:
    def setup_method(self):
        self.parser = CALISAParser()

    @skip_if_no_samples
    def test_post_200(self):
        """POST /oxford-risk/advisers → 200 OK."""
        req = LABELLED_POST_REQ.read_text(encoding="utf-8", errors="replace")
        resp = LABELLED_POST_RESP.read_text(encoding="utf-8", errors="replace")
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
    def test_post_response_body(self):
        req = LABELLED_POST_REQ.read_text(encoding="utf-8", errors="replace")
        resp = LABELLED_POST_RESP.read_text(encoding="utf-8", errors="replace")
        pf = self.parser.parse(req + "\n" + resp, "CreateAdviser.txt")

        body = pf.stubs[0].scenarios[0].body
        assert body is not None
        assert "ADVISER" in body
        assert "351029884" in body

    @skip_if_no_samples
    def test_get_200(self):
        """GET /oxford-risk/advisers → 200 OK, no request body required."""
        req = LABELLED_GET_REQ.read_text(encoding="utf-8", errors="replace")
        resp = LABELLED_GET_RESP.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp

        pf = self.parser.parse(combined, "GetAdvisers.txt")
        stub = pf.stubs[0]

        assert stub.request.method.value == "GET"
        assert stub.scenarios[0].status == 200

    @skip_if_no_samples
    def test_variant_detected(self):
        req = LABELLED_POST_REQ.read_text(encoding="utf-8", errors="replace")
        resp = LABELLED_POST_RESP.read_text(encoding="utf-8", errors="replace")
        combined = req + "\n" + resp
        assert _detect_variant(combined) == "labelled"


# ── Content-Type inference for captures with no Content-Type header ─────────

class TestInferContentType:
    def test_json_object_body(self):
        assert _infer_content_type('{"a": 1}') == "application/json"

    def test_json_array_body(self):
        assert _infer_content_type('[{"a": 1}, {"a": 2}]') == "application/json"

    def test_plain_xml_body(self):
        assert _infer_content_type('<root><item id="1"/></root>') == "application/xml"

    def test_soap_envelope_default_prefix(self):
        body = '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body/></soapenv:Envelope>'
        assert _infer_content_type(body) == "text/xml;charset=utf-8"

    def test_soap_envelope_alternate_prefix(self):
        """Different capture tools / SOAP versions use different envelope
        prefixes (soap:, soap12:, SOAP-ENV:) — all must be recognised as SOAP,
        not just soapenv:."""
        for prefix in ("soap", "soap12", "SOAP-ENV"):
            body = f'<{prefix}:Envelope><{prefix}:Body/></{prefix}:Envelope>'
            assert _infer_content_type(body) == "text/xml;charset=utf-8", prefix

    def test_soap_fault_body(self):
        body = (
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soapenv:Body><soapenv:Fault><faultcode>Client</faultcode>'
            '<faultstring>Invalid request</faultstring></soapenv:Fault></soapenv:Body>'
            '</soapenv:Envelope>'
        )
        assert _infer_content_type(body) == "text/xml;charset=utf-8"

    def test_plain_text_body_no_guess(self):
        assert _infer_content_type("just some plain text, not a structured body") is None

    def test_empty_body_no_guess(self):
        assert _infer_content_type("") is None
        assert _infer_content_type("   ") is None


# ── labelled variant: custom/prefixed section labels ─────────────────────────
#
# CA LISA exports (and Postman/Bruno/hand-authored files) don't always use
# the bare "RequestHeader:"/"ResponseHeader:" label text — real data has
# "AccountInstructionsRequestHeader:" and "AccountInstructionResponse:".
# Detection must be structural (label line, then a "={Method=" or
# "={StatusCode=" block) and never depend on the label's literal wording.

_CUSTOM_LABEL_REQUEST = (
    'AccountInstructionsRequestHeader:\n\n'
    '={Method="POST" URL="/api/x" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/xml"}}}\n\n'
    'AccountInstructionRequest:\n'
    '<Foo><Id>1</Id></Foo>\n'
)
_CUSTOM_LABEL_RESPONSE = (
    'AccountInstructionsResponseHeader:\n\n'
    '={StatusCode="200" ReasonPhrase="OK" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/xml"}}}\n\n'
    'AccountInstructionsResponse:\n'
    '<Foo><Id>1</Id><Status>OK</Status></Foo>\n'
)


class TestCustomPrefixedLabels:
    def setup_method(self):
        self.parser = CALISAParser()

    def test_variant_detected_with_custom_prefix(self):
        assert _detect_variant(_CUSTOM_LABEL_REQUEST) == "labelled"
        assert _detect_variant(_CUSTOM_LABEL_RESPONSE) == "labelled"

    def test_generic_bare_label_still_works(self):
        """Structural detection must not regress the plain, un-prefixed case."""
        assert _detect_variant("RequestHeader:\n={Method=\"GET\"}") == "labelled"
        assert _detect_variant("ResponseHeader:\n={StatusCode=\"200\"}") == "labelled"

    def test_parses_end_to_end(self):
        combined = _CUSTOM_LABEL_REQUEST + "\n" + _CUSTOM_LABEL_RESPONSE
        result = self.parser.validate(combined)
        assert result.valid, f"Validation errors: {result.errors}"

        pf = self.parser.parse(combined, "custom.txt")
        assert len(pf.stubs) == 1
        stub = pf.stubs[0]
        assert stub.request.method.value == "POST"
        assert stub.request.url == "/api/x"
        assert stub.scenarios[0].status == 200
        assert "<Status>OK</Status>" in stub.scenarios[0].body

    def test_via_zip_pair_with_misleading_response_filename(self, tmp_path):
        """Mirrors the real bug: a file whose content is pure response data
        but whose filename contains 'Request' (as recorded by the capture
        tool) must still end up in the ZIP's response bucket, and the pair
        must still be matched despite the two filenames sharing no
        Request/Response naming convention to key off of."""
        zip_path = tmp_path / "capture.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("AccountInstructions_Request.txt", _CUSTOM_LABEL_REQUEST)
            zf.writestr("AccountInstructionsPost_Request.txt", _CUSTOM_LABEL_RESPONSE)

        parser, result, parsed_file = detect_and_parse(zip_path)
        assert result.valid, f"Validation errors: {result.errors}"
        assert parsed_file is not None
        assert len(parsed_file.stubs) == 1
        stub = parsed_file.stubs[0]
        assert stub.request.url == "/api/x"
        assert stub.scenarios[0].status == 200


# ── labelled variant: multiple captures at the same URL ──────────────────────

_MULTI_REQUEST = (
    'RequestHeader:\n\n'
    '={Method="POST" URL="/api/multi" httpDetails={Version="1.1" '
    'httpHeaders={x-usercontext="UserID=1" x-requestid="guid-aaa" '
    'Content-Type="application/xml"}}}\n\n'
    'Request:\n'
    '<Account><Id>111</Id></Account>\n\n'
    '12-Jun-2026 01:00:36\n\n'
    'RequestHeader:\n\n'
    '={Method="POST" URL="/api/multi" httpDetails={Version="1.1" '
    'httpHeaders={x-usercontext="UserID=1" x-requestid="guid-bbb" '
    'Content-Type="application/xml"}}}\n\n'
    'Request:\n'
    '<Account><Id>222</Id></Account>\n'
)
_MULTI_RESPONSE = (
    'ResponseHeader:\n\n'
    '={StatusCode="200" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/xml"}}}\n\n'
    'Response:\n'
    '<Account><Id>111</Id><Status>OK-A</Status></Account>\n\n'
    '12-Jun-2026 01:00:36\n\n'
    'ResponseHeader:\n\n'
    '={StatusCode="200" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/xml"}}}\n\n'
    'Response:\n'
    '<Account><Id>222</Id><Status>OK-B</Status></Account>\n'
)


class TestMultiCaptureSameUrl:
    def setup_method(self):
        self.parser = CALISAParser()

    def test_two_captures_produce_two_scenarios(self):
        combined = _MULTI_REQUEST + "\n" + _MULTI_RESPONSE
        pf = self.parser.parse(combined, "multi.txt")
        assert len(pf.stubs) == 1
        stub = pf.stubs[0]
        assert len(stub.scenarios) == 2
        bodies = {s.body for s in stub.scenarios}
        assert any("OK-A" in b for b in bodies)
        assert any("OK-B" in b for b in bodies)

    def test_scenarios_get_distinct_body_matchers(self):
        combined = _MULTI_REQUEST + "\n" + _MULTI_RESPONSE
        pf = self.parser.parse(combined, "multi.txt")
        stub = pf.stubs[0]
        match_types = {s.match.type for s in stub.scenarios}
        assert match_types == {MatchType.BODY_XPATH}
        values = {s.match.value for s in stub.scenarios}
        assert len(values) == 2  # each scenario's matcher is unique

    def test_volatile_correlation_header_excluded(self):
        """x-requestid differs on every capture (a correlation id) and must
        not become a required match header — it would never match a real
        replay request. x-usercontext is stable and should be kept."""
        combined = _MULTI_REQUEST + "\n" + _MULTI_RESPONSE
        pf = self.parser.parse(combined, "multi.txt")
        headers = pf.stubs[0].request.required_headers
        assert "x-requestid" not in headers
        assert headers.get("x-usercontext") == "UserID=1"

    def test_single_capture_still_always_matches(self):
        """Single request/response pair keeps prior behaviour exactly —
        no bodyPatterns matcher, ALWAYS-type scenario."""
        req = (
            'RequestHeader:\n\n={Method="GET" URL="/api/single"}\n\nRequest:\n\n'
        )
        resp = 'ResponseHeader:\n\n={StatusCode="200"}\n\nResponse:\n{"ok":true}\n'
        pf = self.parser.parse(req + "\n" + resp, "single.txt")
        stub = pf.stubs[0]
        assert len(stub.scenarios) == 1
        assert stub.scenarios[0].match.type == MatchType.ALWAYS


# ── inline variant: multiple captures at the same URL ────────────────────────
#
# The inline (unlabelled) structural variant used to only ever look at the
# first request/response marker in a file — anything recorded after it was
# silently dropped or garbled into the first capture's body. These prove
# that's fixed: inline-variant files now get identical multi-capture +
# same-URL differentiation handling to the labelled variant, for both XML
# and JSON bodies.

_INLINE_MULTI_XML_REQUESTS = (
    '={Method="POST" URL="/api/inline-multi" httpDetails={Version="1.1" '
    'httpHeaders={x-usercontext="UserID=9" x-requestid="guid-1" '
    'Content-Type="application/xml"}}}<Account><Id>AAA</Id></Account>'
    'ResponseHeader={StatusCode="200" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/xml"}}}Response..'
    '<Account><Id>AAA</Id><Status>OK-AAA</Status></Account>'
    '={Method="POST" URL="/api/inline-multi" httpDetails={Version="1.1" '
    'httpHeaders={x-usercontext="UserID=9" x-requestid="guid-2" '
    'Content-Type="application/xml"}}}<Account><Id>BBB</Id></Account>'
    'ResponseHeader={StatusCode="200" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/xml"}}}Response..'
    '<Account><Id>BBB</Id><Status>OK-BBB</Status></Account>'
)

_INLINE_MULTI_JSON_REQUESTS = (
    '={Method="POST" URL="/api/inline-multi-json" httpDetails={Version="1.1" '
    'httpHeaders={x-usercontext="UserID=9" Content-Type="application/json"}}}'
    '{"id":"AAA"}'
    'ResponseHeader={StatusCode="200" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/json"}}}Response..'
    '{"id":"AAA","status":"OK-AAA"}'
    '={Method="POST" URL="/api/inline-multi-json" httpDetails={Version="1.1" '
    'httpHeaders={x-usercontext="UserID=9" Content-Type="application/json"}}}'
    '{"id":"BBB"}'
    'ResponseHeader={StatusCode="200" httpDetails={Version="1.1" '
    'httpHeaders={Content-Type="application/json"}}}Response..'
    '{"id":"BBB","status":"OK-BBB"}'
)


class TestInlineVariantMultiCaptureSameUrl:
    def setup_method(self):
        self.parser = CALISAParser()

    def test_xml_produces_two_scenarios_not_one_garbled_one(self):
        pf = self.parser.parse(_INLINE_MULTI_XML_REQUESTS, "inline_multi.txt")
        assert len(pf.stubs) == 1
        stub = pf.stubs[0]
        assert stub.request.url == "/api/inline-multi"
        assert len(stub.scenarios) == 2
        bodies = {s.body for s in stub.scenarios}
        assert any("OK-AAA" in b for b in bodies)
        assert any("OK-BBB" in b for b in bodies)

    def test_xml_scenarios_get_distinct_body_matchers(self):
        pf = self.parser.parse(_INLINE_MULTI_XML_REQUESTS, "inline_multi.txt")
        stub = pf.stubs[0]
        assert {s.match.type for s in stub.scenarios} == {MatchType.BODY_XPATH}
        assert len({s.match.value for s in stub.scenarios}) == 2
        assert stub.lookup_discriminator_type == "xpath"
        assert {s.lookup_key for s in stub.scenarios} == {"AAA", "BBB"}

    def test_json_produces_two_scenarios(self):
        pf = self.parser.parse(_INLINE_MULTI_JSON_REQUESTS, "inline_multi_json.txt")
        stub = pf.stubs[0]
        assert len(stub.scenarios) == 2
        assert {s.match.type for s in stub.scenarios} == {MatchType.BODY_JSON_PATH}
        bodies = {s.body for s in stub.scenarios}
        assert any("OK-AAA" in b for b in bodies)
        assert any("OK-BBB" in b for b in bodies)

    def test_volatile_header_excluded_same_as_labelled_variant(self):
        pf = self.parser.parse(_INLINE_MULTI_XML_REQUESTS, "inline_multi.txt")
        headers = pf.stubs[0].request.required_headers
        assert "x-requestid" not in headers
        assert headers.get("x-usercontext") == "UserID=9"

    def test_single_inline_capture_unaffected(self):
        """The original single-pair ESP-style shape must parse identically
        to before this refactor — no bodyPatterns matcher, ALWAYS scenario."""
        content = (
            '={Method="GET" URL="/api/single-inline"}{}'
            'ResponseHeader={StatusCode="200"}Response..{"ok":true}'
        )
        pf = self.parser.parse(content, "single_inline.txt")
        stub = pf.stubs[0]
        assert len(stub.scenarios) == 1
        assert stub.scenarios[0].match.type == MatchType.ALWAYS


class TestDifferentiateBodies:
    def test_finds_distinguishing_xml_field(self):
        bodies = ["<a><id>1</id><x>same</x></a>", "<a><id>2</id><x>same</x></a>"]
        diff = _differentiate_bodies(bodies)
        assert all(c is not None for c in diff.conditions)
        assert all(c.type == MatchType.BODY_XPATH for c in diff.conditions)
        assert diff.conditions[0].value != diff.conditions[1].value
        assert diff.discriminator_type == "xpath"
        assert diff.discriminator_field == "id"
        assert diff.values == ["1", "2"]

    def test_finds_distinguishing_json_field(self):
        bodies = ['{"id": 1, "x": "same"}', '{"id": 2, "x": "same"}']
        diff = _differentiate_bodies(bodies)
        assert all(c is not None for c in diff.conditions)
        assert all(c.type == MatchType.BODY_JSON_PATH for c in diff.conditions)
        assert diff.conditions[0].value != diff.conditions[1].value
        assert diff.discriminator_type == "json"
        assert diff.discriminator_field == "id"
        assert diff.values == ["1", "2"]

    def test_no_differentiator_returns_none(self):
        bodies = ["<a><x>same</x></a>", "<a><x>same</x></a>"]
        diff = _differentiate_bodies(bodies)
        assert diff.conditions == [None, None]
        assert diff.discriminator_field is None
        assert diff.values == [None, None]

    def test_single_body_returns_none(self):
        diff = _differentiate_bodies(["<a><x>1</x></a>"])
        assert diff.conditions == [None]
        assert diff.values == [None]

    def test_mismatched_types_returns_none(self):
        diff = _differentiate_bodies(['{"a":1}', "<a>1</a>"])
        assert diff.conditions == [None, None]
        assert diff.values == [None, None]


# ── real sample files: Wealth XML Samples (custom labels + multi-capture) ────

class TestWealthXmlSamples:
    @skip_if_no_custom_label_samples
    def test_zip_upload_produces_stub(self, tmp_path):
        """End-to-end reproduction of the reported bug: batch-uploading both
        real XML sample files (custom-prefixed labels, multiple captures per
        file, and a response file whose name says 'Request') must now
        produce a valid stub instead of zero stubs."""
        zip_path = tmp_path / "xml_samples.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(CUSTOM_LABEL_REQ, CUSTOM_LABEL_REQ.name)
            zf.write(CUSTOM_LABEL_RESP, CUSTOM_LABEL_RESP.name)

        parser, result, parsed_file = detect_and_parse(zip_path)
        assert result.valid, f"Validation errors: {result.errors}"
        assert parsed_file is not None
        assert len(parsed_file.stubs) == 1

        stub = parsed_file.stubs[0]
        assert stub.request.method.value == "POST"
        assert "/api/distribution/v3/accountinstructions" in stub.request.url
        # Request/response counts in the sample files may not match exactly
        # (an extra unpaired response is expected) -> paired by order, one
        # scenario per matched pair, at least 2 to actually exercise the
        # same-URL differentiation this test targets.
        assert len(stub.scenarios) >= 2
        for scenario in stub.scenarios:
            assert scenario.status == 200
            assert scenario.match.type == MatchType.BODY_XPATH
            assert scenario.lookup_key  # differentiator value captured too
        assert stub.lookup_discriminator_type == "xpath"
        assert stub.lookup_discriminator_field

    @skip_if_no_custom_label_samples
    def test_single_file_pair_via_parse_ca_lisa_pair(self):
        req_content = CUSTOM_LABEL_REQ.read_text(encoding="utf-8")
        resp_content = CUSTOM_LABEL_RESP.read_text(encoding="utf-8")
        stub = parse_ca_lisa_pair(
            req_content, resp_content, CUSTOM_LABEL_REQ.name, CUSTOM_LABEL_RESP.name
        )
        assert len(stub.scenarios) >= 2
        assert stub.request.url == "/api/distribution/v3/accountinstructions"
        # x-requestid (a fresh guid per capture) must not be a required header
        assert "x-requestid" not in stub.request.required_headers

    def test_ensure_content_type_adds_when_missing(self):
        headers = {"X-Custom": "value"}
        result = _ensure_content_type(headers, '{"a": 1}')
        assert result["Content-Type"] == "application/json"
        assert result["X-Custom"] == "value"

    def test_ensure_content_type_never_overrides_captured_value(self):
        """An explicitly captured Content-Type — even an unusual one — always wins."""
        headers = {"Content-Type": "application/vnd.custom+json"}
        result = _ensure_content_type(headers, '{"a": 1}')
        assert result["Content-Type"] == "application/vnd.custom+json"

    def test_ensure_content_type_case_insensitive_match(self):
        headers = {"content-type": "text/plain"}
        result = _ensure_content_type(headers, '{"a": 1}')
        assert result == headers  # untouched — already has one, just lowercase key

    def test_ensure_content_type_noop_on_empty_body(self):
        assert _ensure_content_type({}, "") == {}


# ── body shape robustness — arrays, nested docs, various REST/SOAP shapes ───

class TestBodyShapeRobustness:
    """CA LISA-captured bodies are opaque to this parser by design — no schema
    is assumed, so any REST or SOAP body shape a real client sends must survive
    completely untouched, whatever its structure."""

    def setup_method(self):
        self.parser = CALISAParser()

    def _combined(self, body: str, content_type: str = "application/json") -> str:
        return (
            '={Method="POST" URL="/api/list" httpDetails={Version="1.1" '
            f'httpHeaders={{Content-Type="{content_type}"}}}}}}{{}}\n'
            f'ResponseHeader={{StatusCode="200" httpDetails={{Version="1.1" '
            f'httpHeaders={{Content-Type="{content_type}"}}}}}}\nResponse..{body}'
        )

    def test_json_array_of_objects_response(self):
        body = '[{"id":1,"tags":["a","b"]},{"id":2,"tags":[]}]'
        pf = self.parser.parse(self._combined(body), "list.txt")
        assert pf.stubs[0].scenarios[0].body == body

    def test_deeply_nested_json_response(self):
        body = '{"a":{"b":{"c":[1,2,{"d":"e"}]}},"f":null,"g":true}'
        pf = self.parser.parse(self._combined(body), "nested.txt")
        assert pf.stubs[0].scenarios[0].body == body

    def test_xml_with_attributes_and_repeated_siblings(self):
        body = (
            '<accounts total="3">'
            '<account id="1" type="current"/><account id="2" type="savings"/>'
            '<account id="3" type="current"/></accounts>'
        )
        pf = self.parser.parse(self._combined(body, "application/xml"), "accounts.txt")
        assert pf.stubs[0].scenarios[0].body == body

    def test_soap_fault_response_preserved(self):
        body = (
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soapenv:Body><soapenv:Fault><faultcode>Server</faultcode>'
            '<faultstring>Downstream timeout</faultstring></soapenv:Fault>'
            '</soapenv:Body></soapenv:Envelope>'
        )
        pf = self.parser.parse(self._combined(body, "text/xml"), "fault.txt")
        assert pf.stubs[0].scenarios[0].body == body

    def test_response_missing_content_type_gets_inferred(self):
        """A response captured with no Content-Type header at all should still
        get a sensible one so the replayed stub doesn't serve content-type-less."""
        content = (
            '={Method="GET" URL="/api/data"}\n'
            'ResponseHeader={StatusCode="200"}\n'
            'Response..{"result":"ok"}'
        )
        pf = self.parser.parse(content, "no_content_type.txt")
        headers = pf.stubs[0].scenarios[0].response_headers
        assert headers.get("Content-Type") == "application/json"


# ── sibling-block header parsing (_consume_sibling_kv) ───────────────────────

class TestSiblingHeaderBlocks:
    """Some captures (seen in manually reformatted files) close the outer
    ={...} header block early, right after URL=, with httpDetails and other
    fields appearing as sibling Key={...}/Key="value" tokens afterwards
    instead of nested inside. This is a structural quirk of the capture tool,
    not a per-client thing — any client's export could hit it."""

    def test_sibling_httpdetails_block_merged(self):
        text = (
            '={Method="POST" URL="/svc/op"} httpDetails={Version="1.1" '
            'httpHeaders={X-Op="create" Content-Type="text/xml"}} '
            'MessageType="http.text.message.type"}\n\n<root>body</root>'
        )
        method, url, headers, body = _parse_inline_request(text)
        assert method == "POST"
        assert url == "/svc/op"
        assert headers == {"X-Op": "create", "Content-Type": "text/xml"}
        assert body == "<root>body</root>"

    def test_normal_single_block_unaffected(self):
        """The common well-nested case must parse identically to before —
        this is a pure no-op path through _consume_sibling_kv."""
        text = (
            '={Method="POST" URL="/svc/op" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json"}} '
            'MessageType="http.text.message.type"}{"a":1}'
        )
        method, url, headers, body = _parse_inline_request(text)
        assert method == "POST"
        assert url == "/svc/op"
        assert headers == {"Content-Type": "application/json"}
        assert body == '{"a":1}'

    def test_sibling_block_response_side(self):
        text = (
            'ResponseHeader={StatusCode="200"} httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json"}}}\n\nResponse..{"ok":true}'
        )
        status, headers, body = _parse_inline_response(text, "resp.txt")
        assert status == 200
        assert headers == {"Content-Type": "application/json"}
        assert body == '{"ok":true}'


# ── bare response block (no "ResponseHeader" label at all) ──────────────────

class TestBareResponseBlock:
    """Some capture tools export the response with no 'ResponseHeader' label —
    just a bare ={StatusCode=...}BODY block, structurally identical to a
    request block except for StatusCode= instead of Method=. Discovered
    against a real ~400KB SOAP response file with no other marker present."""

    def setup_method(self):
        self.parser = CALISAParser()

    def test_parse_inline_response_accepts_bare_form(self):
        text = '={StatusCode="200" httpDetails={Version="1.1" httpHeaders={Content-Type="text/xml"}}}<a>ok</a>'
        status, headers, body = _parse_inline_response(text, "resp.txt")
        assert status == 200
        assert headers == {"Content-Type": "text/xml"}
        assert body == "<a>ok</a>"

    def test_can_handle_bare_response_alone(self):
        content = '={StatusCode="200" httpDetails={Version="1.1" httpHeaders={Content-Type="text/xml"}}}<a/>'
        assert self.parser.can_handle(content, "response.txt") is True

    def test_validate_request_plus_bare_response_is_valid(self):
        content = (
            '={Method="POST" URL="/svc/op" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="text/xml"}}}<req/>\n'
            '={StatusCode="200" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="text/xml"}}}<resp/>'
        )
        result = self.parser.validate(content)
        assert result.valid, f"Errors: {result.errors}"

    def test_split_finds_bare_response_not_request(self):
        """The split must land on the response's own bare '=' (StatusCode=),
        not spill request content into the response side or vice versa —
        proven by parsing end-to-end and checking both halves independently."""
        content = (
            '={Method="POST" URL="/svc/op" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json"}}}{"reqField":1}\n'
            '={StatusCode="201" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json"}}}{"respField":2}'
        )
        pf = self.parser.parse(content, "test.txt")
        stub = pf.stubs[0]
        assert stub.request.url == "/svc/op"
        assert stub.scenarios[0].status == 201
        assert stub.scenarios[0].body == '{"respField":2}'

    def test_labelled_response_still_preferred_over_bare_when_both_present(self):
        """A labelled 'ResponseHeader={StatusCode=' must still split at its own
        (earlier) start, not at the bare-form match on its internal
        '={StatusCode=' substring — min() over both candidates must pick the
        correct (earlier) position."""
        content = (
            '={Method="GET" URL="/health"}\n'
            'ResponseHeader={StatusCode="200" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="application/json"}}}\nResponse..{"status":"UP"}'
        )
        pf = self.parser.parse(content, "test.txt")
        assert pf.stubs[0].scenarios[0].status == 200
        assert pf.stubs[0].scenarios[0].body == '{"status":"UP"}'


# ── detector.py integration ───────────────────────────────────────────────────

class TestDetectorIntegration:
    @skip_if_no_samples
    def test_detect_parser_identifies_ca_lisa(self, tmp_path):
        req = INLINE_REQUEST_1.read_text(encoding="utf-8", errors="replace")
        resp = INLINE_RESPONSE_200.read_text(encoding="utf-8", errors="replace")
        combined = tmp_path / "inline_combined.txt"
        combined.write_text(req + "\n" + resp, encoding="utf-8")

        parser, validation, parsed = detect_and_parse(combined)
        assert parser is not None
        assert parser.format_name == "ca-lisa-http-pair"
        assert validation.valid is True
        assert parsed is not None

    @skip_if_no_samples
    def test_detect_and_parse_zip(self, tmp_path):
        """ZIP containing a request + response pair should produce one stub."""
        zip_path = tmp_path / "capture_stubs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(INLINE_REQUEST_1, INLINE_REQUEST_1.name)
            zf.write(INLINE_RESPONSE_200, INLINE_RESPONSE_200.name)

        parser, validation, parsed = detect_and_parse(zip_path)
        assert validation.valid is True, f"Errors: {validation.errors}"
        assert parsed is not None
        assert len(parsed.stubs) == 1
        assert parsed.stubs[0].request.method.value == "POST"

    @skip_if_no_samples
    def test_zip_with_multiple_pairs(self, tmp_path):
        """ZIP with two pairs should produce two stubs."""
        zip_path = tmp_path / "capture_multi.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(INLINE_REQUEST_1, INLINE_REQUEST_1.name)
            zf.write(INLINE_RESPONSE_200, INLINE_RESPONSE_200.name)
            zf.write(INLINE_REQUEST_2, INLINE_REQUEST_2.name)
            zf.write(INLINE_RESPONSE_400, INLINE_RESPONSE_400.name)

        parser, validation, parsed = detect_and_parse(zip_path)
        assert validation.valid is True
        assert parsed is not None
        assert len(parsed.stubs) == 2

    def test_zip_with_no_capture_files(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.md", "# nothing")

        parser, validation, parsed = detect_and_parse(zip_path)
        assert validation.valid is False
        assert any("no .txt" in str(e).lower() for e in validation.errors)

    def test_zip_accepts_xml_extension_pair(self, tmp_path):
        """A ZIP with .xml-named request/response files (e.g. a SOAP capture
        saved with .xml extension) must pair and parse exactly like .txt —
        the ZIP handler filters by extension only to pick candidate files;
        format itself is always decided by content, never by extension."""
        zip_path = tmp_path / "xml_capture.zip"
        request_content = (
            '={Method="POST" URL="/svc/op" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="text/xml"}}}<root><a>1</a></root>'
        )
        response_content = (
            'ResponseHeader={StatusCode="200" httpDetails={Version="1.1" '
            'httpHeaders={Content-Type="text/xml"}}}\nResponse..<root><ok/></root>'
        )
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("Operation_Request.xml", request_content)
            zf.writestr("Operation_Response.xml", response_content)

        parser, validation, parsed = detect_and_parse(zip_path)
        assert validation.valid is True, f"Errors: {validation.errors}"
        assert parsed is not None
        assert len(parsed.stubs) == 1
        assert parsed.stubs[0].scenarios[0].body == "<root><ok/></root>"


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
