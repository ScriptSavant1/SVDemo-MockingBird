"""Phase 2 Sprint 5 — dynamic response tests.

Verifies that Handlebars template expressions in response bodies:
  1. Cause the WireMock 'response-template' transformer to be added to the mapping.
  2. Are passed through to the mapping body verbatim (WireMock evaluates them at runtime).

Also verifies all delay formats produce correct WireMock JSON output.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from parser_worker.models import Delay, DelayType, ParsedScenario, MatchCondition, MatchType
from parser_worker.parsers.txt_level1 import _parse_delay
from parser_worker.detector import detect_and_parse
from parser_worker.generator.wiremock import generate_wiremock_mappings


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


def _parse_stub(tmp_path: Path, filename: str, content: str):
    f = _write(tmp_path, filename, content)
    _, _, parsed = detect_and_parse(f)
    return parsed


def _mappings(tmp_path: Path, content: str, filename: str = "stub.txt") -> list[dict]:
    """Parse content and return list of WireMock mapping dicts."""
    parsed = _parse_stub(tmp_path, filename, content)
    out = tmp_path / "out"
    generate_wiremock_mappings(parsed, out)
    return [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]


# ── transformer detection ─────────────────────────────────────────────────────

class TestTransformerDetection:
    """response-template transformer must appear iff body contains {{...}}."""

    def test_static_body_no_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Static API
Method: GET
URL: /api/v1/resource

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"id": "123", "name": "Fixed response"}
"""
        mappings = _mappings(tmp_path, content)
        assert len(mappings) == 1
        assert "transformers" not in mappings[0]["response"]

    def test_path_param_echo_adds_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Customer API
Method: GET
URL: /api/v1/customers/{customerId}

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"id": "{{request.pathParam.customerId}}", "name": "John Smith"}
"""
        mappings = _mappings(tmp_path, content)
        assert "response-template" in mappings[0]["response"]["transformers"]

    def test_now_expression_adds_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Timestamp API
Method: GET
URL: /api/v1/time

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"timestamp": "{{now format='yyyy-MM-dd'}}"}
"""
        mappings = _mappings(tmp_path, content)
        assert "response-template" in mappings[0]["response"]["transformers"]

    def test_uuid_expression_adds_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: UUID API
Method: POST
URL: /api/v1/transactions

--- RESPONSE ---
Status: 201
Content-Type: application/json

{"transactionId": "{{randomValue type='UUID'}}", "status": "created"}
"""
        mappings = _mappings(tmp_path, content)
        assert "response-template" in mappings[0]["response"]["transformers"]

    def test_numeric_random_adds_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Reference API
Method: POST
URL: /api/v1/references

--- RESPONSE ---
Status: 201
Content-Type: application/json

{"reference": "REF-{{randomValue type='NUMERIC' length=8}}"}
"""
        mappings = _mappings(tmp_path, content)
        assert "response-template" in mappings[0]["response"]["transformers"]

    def test_alphanumeric_random_adds_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Token API
Method: POST
URL: /api/v1/tokens

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"token": "{{randomValue type='ALPHANUMERIC' length=16}}"}
"""
        mappings = _mappings(tmp_path, content)
        assert "response-template" in mappings[0]["response"]["transformers"]

    def test_json_path_extraction_adds_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Echo API
Method: POST
URL: /api/v1/echo

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"echo": "{{jsonPath request.body '$.message'}}"}
"""
        mappings = _mappings(tmp_path, content)
        assert "response-template" in mappings[0]["response"]["transformers"]

    def test_header_echo_adds_transformer(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Header Echo API
Method: GET
URL: /api/v1/whoami

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"correlationId": "{{request.headers.X-Correlation-ID}}"}
"""
        mappings = _mappings(tmp_path, content)
        assert "response-template" in mappings[0]["response"]["transformers"]

    def test_multiple_expressions_single_transformer_entry(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Multi-Dynamic API
Method: GET
URL: /api/v1/items/{itemId}

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"id": "{{request.pathParam.itemId}}", "uuid": "{{randomValue type='UUID'}}", "ts": "{{now}}"}
"""
        mappings = _mappings(tmp_path, content)
        transformers = mappings[0]["response"]["transformers"]
        assert transformers.count("response-template") == 1

    def test_dynamic_body_verbatim_in_mapping(self, tmp_path):
        """WireMock evaluates {{...}} at runtime — the raw expression must be in the JSON."""
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Echo Path
Method: GET
URL: /api/v1/items/{itemId}

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"id": "{{request.pathParam.itemId}}"}
"""
        mappings = _mappings(tmp_path, content)
        body = mappings[0]["response"]["body"]
        assert "{{request.pathParam.itemId}}" in body

    def test_level2_dynamic_default_scenario(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Customer API
Method: GET
URL: /api/v1/customers/{customerId}

--- SCENARIO: Not Found ---
Match-Type: url-contains
Match-Value: UNKNOWN
Status: 404
Content-Type: application/json

{"error": "not found"}

--- SCENARIO DEFAULT ---
Status: 200
Content-Type: application/json

{"id": "{{request.pathParam.customerId}}", "name": "John Smith", "ts": "{{now format='yyyy-MM-dd'}}"}
"""
        parsed = _parse_stub(tmp_path, "customer.txt", content)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mappings = {p.name: json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")}

        default = next(m for m in mappings.values() if "default" in m["name"].lower())
        not_found = next(m for m in mappings.values() if "not found" in m["name"].lower())

        assert "response-template" in default["response"]["transformers"]
        assert "transformers" not in not_found["response"]

    def test_now_iso8601_verbatim(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Time API
Method: GET
URL: /api/v1/time

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"ts": "{{now format='yyyy-MM-ddTHH:mm:ssZ'}}"}
"""
        mappings = _mappings(tmp_path, content)
        body = mappings[0]["response"]["body"]
        assert "{{now format=" in body


# ── delay parsing ─────────────────────────────────────────────────────────────

class TestDelayParsing:
    """_parse_delay must correctly parse all supported delay formats."""

    def test_fixed_delay(self):
        d = _parse_delay("500ms")
        assert d is not None
        assert d.type == DelayType.FIXED
        assert d.ms == 500

    def test_fixed_delay_case_insensitive(self):
        d = _parse_delay("200MS")
        assert d is not None
        assert d.type == DelayType.FIXED
        assert d.ms == 200

    def test_random_delay(self):
        d = _parse_delay("random:100ms-500ms")
        assert d is not None
        assert d.type == DelayType.RANDOM
        assert d.min_ms == 100
        assert d.max_ms == 500

    def test_random_delay_case_insensitive(self):
        d = _parse_delay("RANDOM:50ms-200ms")
        assert d is not None
        assert d.type == DelayType.RANDOM
        assert d.min_ms == 50
        assert d.max_ms == 200

    def test_chunked_delay(self):
        d = _parse_delay("chunked:5,1000ms")
        assert d is not None
        assert d.type == DelayType.CHUNKED
        assert d.chunks == 5
        assert d.chunk_ms == 1000

    def test_chunked_delay_10_chunks(self):
        d = _parse_delay("chunked:10,3000ms")
        assert d is not None
        assert d.chunks == 10
        assert d.chunk_ms == 3000

    def test_lognormal_delay(self):
        d = _parse_delay("lognormal:80ms,0.4")
        assert d is not None
        assert d.type == DelayType.LOGNORMAL
        assert d.ms == 80
        assert abs(d.sigma - 0.4) < 0.001

    def test_lognormal_delay_other_values(self):
        d = _parse_delay("lognormal:200ms,0.8")
        assert d is not None
        assert d.ms == 200
        assert abs(d.sigma - 0.8) < 0.001

    def test_unknown_format_returns_none(self):
        assert _parse_delay("invalid") is None
        assert _parse_delay("500") is None
        assert _parse_delay("500s") is None
        assert _parse_delay("") is None

    def test_whitespace_trimmed(self):
        d = _parse_delay("  300ms  ")
        assert d is not None
        assert d.ms == 300


# ── delay WireMock output ─────────────────────────────────────────────────────

class TestDelayWireMockOutput:
    """Each delay type must produce the correct WireMock JSON structure."""

    def _mapping_with_delay(self, tmp_path: Path, delay_line: str) -> dict:
        content = f"""\
--- MOCKINGBIRD v1.0 ---

Name: Delay Test
Method: GET
URL: /api/v1/test

--- RESPONSE ---
Status: 200
{delay_line}
Content-Type: application/json

{{"result": "ok"}}
"""
        return _mappings(tmp_path, content)[0]

    def test_fixed_delay_wireMock_output(self, tmp_path):
        m = self._mapping_with_delay(tmp_path, "Delay: 500ms")
        assert m["response"]["fixedDelayMilliseconds"] == 500
        assert "delayDistribution" not in m["response"]

    def test_random_delay_wireMock_output(self, tmp_path):
        m = self._mapping_with_delay(tmp_path, "Delay: random:200ms-800ms")
        dist = m["response"]["delayDistribution"]
        assert dist["type"] == "uniform"
        assert dist["lower"] == 200
        assert dist["upper"] == 800

    def test_chunked_delay_wireMock_output(self, tmp_path):
        m = self._mapping_with_delay(tmp_path, "Delay: chunked:5,1000ms")
        chunked = m["response"]["chunkedDribbleDelay"]
        assert chunked["numberOfChunks"] == 5
        assert chunked["totalDuration"] == 1000

    def test_lognormal_delay_wireMock_output(self, tmp_path):
        m = self._mapping_with_delay(tmp_path, "Delay: lognormal:80ms,0.4")
        dist = m["response"]["delayDistribution"]
        assert dist["type"] == "lognormal"
        assert dist["median"] == 80
        assert abs(dist["sigma"] - 0.4) < 0.001

    def test_no_delay_no_delay_fields(self, tmp_path):
        m = self._mapping_with_delay(tmp_path, "")
        assert "fixedDelayMilliseconds" not in m["response"]
        assert "delayDistribution" not in m["response"]
        assert "chunkedDribbleDelay" not in m["response"]

    def test_delay_and_dynamic_body_together(self, tmp_path):
        content = """\
--- MOCKINGBIRD v1.0 ---

Name: Slow Dynamic API
Method: GET
URL: /api/v1/items/{itemId}

--- RESPONSE ---
Status: 200
Delay: random:100ms-300ms
Content-Type: application/json

{"id": "{{request.pathParam.itemId}}", "correlationId": "{{randomValue type='UUID'}}"}
"""
        mappings = _mappings(tmp_path, content)
        m = mappings[0]
        assert "response-template" in m["response"]["transformers"]
        dist = m["response"]["delayDistribution"]
        assert dist["type"] == "uniform"
        assert dist["lower"] == 100
        assert dist["upper"] == 300


# ── end-to-end: dynamic example file ─────────────────────────────────────────

class TestDynamicExampleFile:
    """Verify the committed dynamic example file parses and generates correctly."""

    def test_example_file_parses_and_generates(self, tmp_path):
        example = Path(__file__).parent.parent.parent.parent / \
            "docs/input-formats/examples/dynamic-customer.txt"
        if not example.exists():
            pytest.skip("dynamic-customer.txt not found — check project root")

        _, result, parsed = detect_and_parse(example)
        assert result.valid, result.errors
        assert result.format_detected == "level-2-txt"

        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)
        mappings = list((out / "mappings").glob("*.json"))
        assert len(mappings) == 4  # not-found, slow, chunked, default

    def test_example_file_default_has_transformer(self, tmp_path):
        example = Path(__file__).parent.parent.parent.parent / \
            "docs/input-formats/examples/dynamic-customer.txt"
        if not example.exists():
            pytest.skip("dynamic-customer.txt not found")

        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)

        mapping_dicts = {p.name: json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")}
        default_mapping = next(
            m for m in mapping_dicts.values()
            if "default" in m["name"].lower()
        )
        assert "response-template" in default_mapping["response"]["transformers"]

    def test_example_file_slow_scenario_has_random_delay(self, tmp_path):
        example = Path(__file__).parent.parent.parent.parent / \
            "docs/input-formats/examples/dynamic-customer.txt"
        if not example.exists():
            pytest.skip("dynamic-customer.txt not found")

        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)

        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        slow_mapping = next(m for m in mapping_dicts if "slow" in m["name"].lower())
        dist = slow_mapping["response"]["delayDistribution"]
        assert dist["type"] == "uniform"
        assert dist["lower"] == 500
        assert dist["upper"] == 2000

    def test_example_file_chunked_scenario_has_chunked_delay(self, tmp_path):
        example = Path(__file__).parent.parent.parent.parent / \
            "docs/input-formats/examples/dynamic-customer.txt"
        if not example.exists():
            pytest.skip("dynamic-customer.txt not found")

        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)

        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        chunked_mapping = next(m for m in mapping_dicts if "chunked" in m["name"].lower())
        chunked = chunked_mapping["response"]["chunkedDribbleDelay"]
        assert chunked["numberOfChunks"] == 10
        assert chunked["totalDuration"] == 3000

    def test_example_file_default_has_lognormal_delay(self, tmp_path):
        example = Path(__file__).parent.parent.parent.parent / \
            "docs/input-formats/examples/dynamic-customer.txt"
        if not example.exists():
            pytest.skip("dynamic-customer.txt not found")

        _, _, parsed = detect_and_parse(example)
        out = tmp_path / "out"
        generate_wiremock_mappings(parsed, out)

        mapping_dicts = [json.loads(p.read_text()) for p in (out / "mappings").glob("*.json")]
        default_mapping = next(m for m in mapping_dicts if "default" in m["name"].lower())
        dist = default_mapping["response"]["delayDistribution"]
        assert dist["type"] == "lognormal"
        assert dist["median"] == 80
