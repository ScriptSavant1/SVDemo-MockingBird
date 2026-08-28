"""Tests for generator/jmeter.py — automatic JMeter NFT test plan generation
(Phase 1, see docs/progress/PHASE1_JMETER_NFT_GENERATION.md).

Real end-to-end validation (actual JMeter 5.6.3 running non-GUI against a
real stub-engine jar) is logged in that progress doc rather than repeated
here — these are the fast, deterministic unit tests covering the generator
in isolation: CSV correctness (including the verified JMeter newline
constraint), XML well-formedness, and all three scenario shapes the parser
can produce.
"""
from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET

from parser_worker.generator.jmeter import build_jmeter_test_plan_files
from parser_worker.models import (
    HttpMethod,
    MatchCondition,
    MatchType,
    ParsedFile,
    ParsedRequestSpec,
    ParsedScenario,
    ParsedStub,
)


def _csv_rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _single_scenario_file(captured_body: str | None = None) -> ParsedFile:
    scenario = ParsedScenario(
        name="default",
        match=MatchCondition(type=MatchType.ALWAYS),
        status=200,
        body='{"ok":true}',
        captured_request_body=captured_body,
    )
    stub = ParsedStub(
        name="Simple Stub",
        request=ParsedRequestSpec(
            method=HttpMethod.POST, url="/api/test", required_headers={"Content-Type": "application/json"}
        ),
        scenarios=[scenario],
    )
    return ParsedFile(format="test", source_file="t", stubs=[stub])


def _body_differentiated_file() -> ParsedFile:
    scenarios = [
        ParsedScenario(
            name="variant-1",
            match=MatchCondition(type=MatchType.BODY_XPATH, value="//*[local-name()='Full' and text()='Alice']"),
            status=200,
            body="<r><Full>Alice</Full></r>",
            lookup_key="Alice",
            captured_request_body="<req><Full>Alice</Full><Extra>x</Extra></req>",
        ),
        ParsedScenario(
            name="variant-2",
            match=MatchCondition(type=MatchType.BODY_XPATH, value="//*[local-name()='Full' and text()='Bob']"),
            status=404,
            body="<error/>",
            lookup_key="Bob",
            captured_request_body="<req><Full>Bob</Full><Extra>y</Extra></req>",
        ),
    ]
    stub = ParsedStub(
        name="Body Differentiated",
        request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/accounts", required_headers={}),
        scenarios=scenarios,
        lookup_discriminator_type="xpath",
        lookup_discriminator_field="Full",
    )
    return ParsedFile(format="test", source_file="t", stubs=[stub])


def _url_segment_file() -> ParsedFile:
    scenarios = [
        ParsedScenario(
            name="variant-1",
            match=MatchCondition(type=MatchType.ALWAYS),
            status=200,
            body="<r>1</r>",
            lookup_key="cust-1",
            url_override="/api/customers/cust-1/profile",
            captured_request_body="<req>data-1</req>",
        ),
        ParsedScenario(
            name="variant-2",
            match=MatchCondition(type=MatchType.ALWAYS),
            status=200,
            body="<r>2</r>",
            lookup_key="cust-2",
            url_override="/api/customers/cust-2/profile",
            captured_request_body="<req>data-2</req>",
        ),
    ]
    stub = ParsedStub(
        name="URL Segment Stub",
        request=ParsedRequestSpec(
            method=HttpMethod.GET, url="/api/customers/([^/]+)/profile", required_headers={}
        ),
        scenarios=scenarios,
        lookup_discriminator_type="url-segment",
        lookup_url_pattern="/api/customers/([^/]+)/profile",
    )
    return ParsedFile(format="test", source_file="t", stubs=[stub])


class TestOutputShape:
    def test_produces_jmx_csv_and_readme(self):
        files = build_jmeter_test_plan_files(_single_scenario_file())
        assert "test-plan.jmx" in files
        assert "README.md" in files
        assert any(k.startswith("data/") and k.endswith(".csv") for k in files)

    def test_jmx_is_well_formed_xml(self):
        files = build_jmeter_test_plan_files(_body_differentiated_file())
        ET.fromstring(files["test-plan.jmx"])  # raises if malformed

    def test_one_csv_per_stub(self):
        f1 = _single_scenario_file()
        f2 = _body_differentiated_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        files = build_jmeter_test_plan_files(combined)
        csv_files = [k for k in files if k.startswith("data/")]
        assert len(csv_files) == 2


class TestCsvContent:
    def test_single_scenario_one_row(self):
        files = build_jmeter_test_plan_files(_single_scenario_file())
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        rows = _csv_rows(csv_text)
        assert len(rows) == 1
        assert rows[0]["requestPath"] == "/api/test"
        assert rows[0]["expectedStatus"] == "200"

    def test_body_differentiated_produces_one_row_per_scenario_same_path(self):
        files = build_jmeter_test_plan_files(_body_differentiated_file())
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        rows = _csv_rows(csv_text)
        assert len(rows) == 2
        assert {r["requestPath"] for r in rows} == {"/api/accounts"}  # same URL for both
        assert {r["expectedStatus"] for r in rows} == {"200", "404"}  # per-scenario status preserved
        bodies = {r["requestBody"] for r in rows}
        assert any("Alice" in b for b in bodies)
        assert any("Bob" in b for b in bodies)

    def test_url_segment_produces_distinct_paths(self):
        files = build_jmeter_test_plan_files(_url_segment_file())
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        rows = _csv_rows(csv_text)
        paths = {r["requestPath"] for r in rows}
        assert paths == {"/api/customers/cust-1/profile", "/api/customers/cust-2/profile"}

    def test_uses_real_captured_body_when_available(self):
        files = build_jmeter_test_plan_files(_single_scenario_file(captured_body="<real>payload</real>"))
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        rows = _csv_rows(csv_text)
        assert rows[0]["requestBody"] == "<real>payload</real>"

    def test_synthesises_matching_body_for_xpath_discriminator_when_no_capture(self):
        scenario = ParsedScenario(
            name="v1",
            match=MatchCondition(type=MatchType.BODY_XPATH, value="//*[local-name()='Name' and text()='X']"),
            status=200,
            body="<r/>",
            lookup_key="X",
            captured_request_body=None,  # e.g. a non-CA-LISA source
        )
        scenario2 = ParsedScenario(
            name="v2",
            match=MatchCondition(type=MatchType.BODY_XPATH, value="//*[local-name()='Name' and text()='Y']"),
            status=200,
            body="<r/>",
            lookup_key="Y",
            captured_request_body=None,
        )
        stub = ParsedStub(
            name="No Capture",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/x", required_headers={}),
            scenarios=[scenario, scenario2],
            lookup_discriminator_type="xpath",
            lookup_discriminator_field="Name",
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_jmeter_test_plan_files(pf)
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        rows = _csv_rows(csv_text)
        bodies = [r["requestBody"] for r in rows]
        # Each synthesised body must actually satisfy ITS OWN scenario's match.
        assert any("<Name>X</Name>" in b for b in bodies)
        assert any("<Name>Y</Name>" in b for b in bodies)
        for b in bodies:
            ET.fromstring(b)  # must be well-formed XML

    def test_synthesises_matching_body_for_json_discriminator(self):
        scenario = ParsedScenario(
            name="v1",
            match=MatchCondition(type=MatchType.BODY_JSON_PATH, value="$[?(@.id=='42')]"),
            status=200,
            body="{}",
            lookup_key="42",
            captured_request_body=None,
        )
        stub = ParsedStub(
            name="JSON No Capture",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/y", required_headers={}),
            scenarios=[scenario, scenario],  # duplicate is fine for this unit test
            lookup_discriminator_type="json",
            lookup_discriminator_field="id",
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_jmeter_test_plan_files(pf)
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        rows = _csv_rows(csv_text)
        import json
        for r in rows:
            parsed = json.loads(r["requestBody"])
            assert parsed == {"id": "42"}

    def test_embedded_newlines_collapsed_to_single_line(self):
        """Verified real JMeter constraint (see module docstring / progress
        doc): CSVDataSet reads the file line-by-line before applying quote
        parsing, so an embedded newline in a field — even a properly
        RFC4180-quoted one — would corrupt row boundaries. Every CSV field
        must therefore be exactly one physical line."""
        multiline_body = "<a>\n  <b>1</b>\n  <c>2</c>\n</a>"
        files = build_jmeter_test_plan_files(_single_scenario_file(captured_body=multiline_body))
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        # No physical line in the raw CSV text may contain a bare newline
        # inside what should be one logical row -- simplest proof: the
        # number of physical lines equals header + 1 data row exactly.
        assert len(csv_text.strip("\n").split("\n")) == 2
        rows = _csv_rows(csv_text)
        assert "\n" not in rows[0]["requestBody"]
        assert "<b>1</b>" in rows[0]["requestBody"]
        assert "<c>2</c>" in rows[0]["requestBody"]

    def test_csv_field_with_embedded_quotes_and_commas_round_trips(self):
        tricky_body = 'value with "quotes", a comma, and more "quotes"'
        files = build_jmeter_test_plan_files(_single_scenario_file(captured_body=tricky_body))
        [csv_text] = [v for k, v in files.items() if k.startswith("data/")]
        rows = _csv_rows(csv_text)
        assert rows[0]["requestBody"] == tricky_body


class TestHeadersAndMethod:
    def test_required_headers_appear_in_header_manager(self):
        files = build_jmeter_test_plan_files(_single_scenario_file())
        jmx = files["test-plan.jmx"]
        assert "Content-Type" in jmx
        assert "application/json" in jmx

    def test_no_required_headers_still_produces_valid_xml(self):
        stub = ParsedStub(
            name="No Headers",
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/api/none", required_headers={}),
            scenarios=[ParsedScenario(name="default", match=MatchCondition(type=MatchType.ALWAYS), status=200)],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_jmeter_test_plan_files(pf)
        ET.fromstring(files["test-plan.jmx"])

    def test_method_appears_in_sampler(self):
        files = build_jmeter_test_plan_files(_url_segment_file())
        assert ">GET " in files["test-plan.jmx"] or "HTTPSampler.method\">GET<" in files["test-plan.jmx"]


class TestReadme:
    def test_readme_lists_every_stub(self):
        f1 = _single_scenario_file()
        f2 = _url_segment_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        readme = build_jmeter_test_plan_files(combined, "My Project")["README.md"]
        assert "My Project" in readme
        assert "Simple Stub" in readme
        assert "URL Segment Stub" in readme

    def test_readme_states_out_of_scope_items(self):
        readme = build_jmeter_test_plan_files(_single_scenario_file())["README.md"]
        assert "WS-Security" in readme
        assert "fault" in readme.lower()


class TestFilenameSafety:
    def test_stub_names_produce_distinct_safe_csv_filenames(self):
        stub_a = ParsedStub(
            name="Weird / Name: With Punctuation!",
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/a", required_headers={}),
            scenarios=[ParsedScenario(name="default", match=MatchCondition(type=MatchType.ALWAYS), status=200)],
        )
        stub_b = ParsedStub(
            name="Another (Stub) #2",
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/b", required_headers={}),
            scenarios=[ParsedScenario(name="default", match=MatchCondition(type=MatchType.ALWAYS), status=200)],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub_a, stub_b])
        files = build_jmeter_test_plan_files(pf)
        csv_keys = [k for k in files if k.startswith("data/")]
        assert len(csv_keys) == 2
        assert len(set(csv_keys)) == 2  # no collision
