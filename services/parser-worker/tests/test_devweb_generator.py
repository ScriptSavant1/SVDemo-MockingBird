"""Tests for generator/devweb.py — automatic LoadRunner DevWeb (VuGen)
project generation (Phase 2, see docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md).

Real Node.js execution of the generated main.js against a mock `load`
namespace (built from the official SDK docs) is logged in that progress
doc rather than repeated here. These are the fast, deterministic unit
tests: output shape, real JS syntax validity (via `node --check`), XML
well-formedness, parameters.yml correctness (namespacing + "same as"
row-locking), and CSV content — the same three scenario shapes already
covered for the sibling JMeter generator, since both share
generator/nft_common.py for that part.
"""
from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from parser_worker.generator.devweb import build_devweb_project_files
from parser_worker.models import (
    HttpMethod,
    MatchCondition,
    MatchType,
    ParsedFile,
    ParsedRequestSpec,
    ParsedScenario,
    ParsedStub,
)

_NODE_AVAILABLE = shutil.which("node") is not None


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
    def test_produces_all_mandatory_files(self):
        files = build_devweb_project_files(_single_scenario_file(), "My Project")
        assert "main.js" in files
        assert "My_Project.usr" in files
        assert "default.cfg" in files
        assert "default.usp" in files
        assert "rts.yml" in files
        assert "parameters.yml" in files
        assert "tsconfig.json" in files
        assert "ScriptUploadMetadata.xml" in files
        assert "README.md" in files
        assert any(k.startswith("data/") and k.endswith(".csv") for k in files)

    def test_one_csv_per_stub(self):
        f1 = _single_scenario_file()
        f2 = _body_differentiated_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        files = build_devweb_project_files(combined)
        csv_files = [k for k in files if k.startswith("data/") and k.endswith(".csv")]
        assert len(csv_files) == 2

    def test_one_body_file_per_scenario(self):
        """Bodies are never embedded in the CSV (see module docstring —
        a real VuGen open failed on a CSV field containing RFC4180-quoted
        JSON/XML). f2's stub has 2 scenarios, f1's has 1 -> 3 body files."""
        f1 = _single_scenario_file()
        f2 = _body_differentiated_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        files = build_devweb_project_files(combined)
        body_files = [k for k in files if k.startswith("data/") and k.endswith(".body.txt")]
        assert len(body_files) == 3

    def test_upload_metadata_is_well_formed_xml(self):
        files = build_devweb_project_files(_body_differentiated_file())
        ET.fromstring(files["ScriptUploadMetadata.xml"])

    def test_does_not_bundle_the_vendor_sdk_file(self):
        """Deliberate: DevWebSdk.d.ts is Micro Focus/OpenText's proprietary
        SDK type file — see the module docstring for why this generator
        does not redistribute a copy."""
        files = build_devweb_project_files(_single_scenario_file())
        assert "DevWebSdk.d.ts" not in files


@pytest.mark.skipif(not _NODE_AVAILABLE, reason="Node.js not available to syntax-check generated JS")
class TestMainJsSyntax:
    def test_main_js_is_valid_javascript(self):
        files = build_devweb_project_files(_body_differentiated_file(), "Syntax Check")
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "main.js"
            script_path.write_text(files["main.js"], encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"node --check failed:\n{result.stderr}"

    def test_main_js_for_every_scenario_shape_is_valid_javascript(self):
        combined = ParsedFile(
            format="test",
            source_file="t",
            stubs=[
                *_single_scenario_file().stubs,
                *_body_differentiated_file().stubs,
                *_url_segment_file().stubs,
            ],
        )
        files = build_devweb_project_files(combined, "All Shapes")
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "main.js"
            script_path.write_text(files["main.js"], encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"node --check failed:\n{result.stderr}"


class TestParametersYml:
    def test_namespaced_per_stub_no_collisions(self):
        f1 = _single_scenario_file()
        f2 = _body_differentiated_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        params_yml = build_devweb_project_files(combined)["parameters.yml"]
        assert "stub00_" in params_yml
        assert "stub01_" in params_yml
        # 2 stubs * 3 columns = 6 "- name:" entries, all distinct
        names = [line.strip() for line in params_yml.splitlines() if line.strip().startswith("- name:")]
        assert len(names) == 6
        assert len(set(names)) == 6

    def test_body_and_status_locked_to_same_row_as_path(self):
        params_yml = build_devweb_project_files(_single_scenario_file())["parameters.yml"]
        assert "nextRow: same as stub00_simple_stub_requestPath" in params_yml

    def test_each_param_points_at_its_stub_csv_file(self):
        files = build_devweb_project_files(_url_segment_file())
        params_yml = files["parameters.yml"]
        [csv_key] = [k for k in files if k.startswith("data/") and k.endswith(".csv")]
        assert f"fileName: {csv_key}" in params_yml

    def test_body_column_holds_a_file_reference_not_the_raw_body(self):
        params_yml = build_devweb_project_files(_single_scenario_file())["parameters.yml"]
        assert "columnName: requestBodyFile" in params_yml
        assert "name: stub00_simple_stub_requestBodyFile" in params_yml

    def test_every_parameter_entry_has_nextvalue_even_same_as_ones(self):
        """Real VuGen bug: 'nextValue: iteration' omitted on the 'same as'
        entries (requestBodyFile/expectedStatus) because the docs describe
        it as "ignored" there — which turned out to mean ignored in
        row-selection, not optional in the YAML. VuGen's real parser threw
        'nextValue getter was not defined' without it. The vendor's own
        example YAML and the real reference converter's output both always
        include it, confirming this fix rather than guessing at it."""
        params_yml = build_devweb_project_files(_single_scenario_file())["parameters.yml"]
        blocks = params_yml.split("  - name:")[1:]  # each parameter's own YAML block
        assert len(blocks) == 3
        for block in blocks:
            assert "nextValue: iteration" in block, f"missing nextValue in block:\n{block}"


class TestRequestId:
    """VuGen uses WebRequest's `id` to generate the matching snapshot file
    for the Replay view — the real reference converter's own output
    numbers every request this way; an earlier version of this generator
    omitted it."""

    def test_single_stub_request_has_id_1(self):
        main_js = build_devweb_project_files(_single_scenario_file())["main.js"]
        assert "id: 1," in main_js

    def test_multiple_stubs_get_sequential_ids(self):
        f1 = _single_scenario_file()
        f2 = _url_segment_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        main_js = build_devweb_project_files(combined)["main.js"]
        assert "id: 1," in main_js
        assert "id: 2," in main_js


class TestUsrFile:
    def test_transactions_order_lists_all_stubs_with_delimiter(self):
        f1 = _single_scenario_file()
        f2 = _url_segment_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        files = build_devweb_project_files(combined, "Order Test")
        usr = files["Order_Test.usr"]
        assert "stub00_simple_stub__*delimiter*__stub01_url_segment_stub" in usr
        assert "Type=DevWeb" in usr


def _csv_files_only(files: dict) -> dict:
    return {k: v for k, v in files.items() if k.startswith("data/") and k.endswith(".csv")}


def _body_text(files: dict, body_filename: str) -> str:
    return files[body_filename]


class TestCsvContent:
    def test_single_scenario_one_row(self):
        files = build_devweb_project_files(_single_scenario_file())
        [csv_text] = _csv_files_only(files).values()
        rows = _csv_rows(csv_text)
        assert len(rows) == 1
        assert rows[0]["requestPath"] == "/api/test"
        assert rows[0]["expectedStatus"] == "200"
        assert rows[0]["requestBodyFile"].startswith("data/") and rows[0]["requestBodyFile"].endswith(".body.txt")

    def test_uses_real_captured_body_when_available(self):
        files = build_devweb_project_files(_single_scenario_file(captured_body="<real>payload</real>"))
        [csv_text] = _csv_files_only(files).values()
        row = _csv_rows(csv_text)[0]
        assert _body_text(files, row["requestBodyFile"]) == "<real>payload</real>"

    def test_url_segment_produces_distinct_paths(self):
        files = build_devweb_project_files(_url_segment_file())
        [csv_text] = _csv_files_only(files).values()
        rows = _csv_rows(csv_text)
        paths = {r["requestPath"] for r in rows}
        assert paths == {"/api/customers/cust-1/profile", "/api/customers/cust-2/profile"}

    def test_each_scenario_gets_its_own_distinct_body_file(self):
        files = build_devweb_project_files(_url_segment_file())
        [csv_text] = _csv_files_only(files).values()
        rows = _csv_rows(csv_text)
        body_files = {r["requestBodyFile"] for r in rows}
        assert len(body_files) == 2  # 2 scenarios -> 2 distinct body files, no collision

    def test_embedded_newlines_collapsed_to_single_line_in_body_file(self):
        """Same conservative precaution as JMeter — see nft_common's module
        docstring for why this is applied to DevWeb's body files too,
        absent a positive confirmation from the vendor doc either way."""
        multiline_body = "<a>\n  <b>1</b>\n  <c>2</c>\n</a>"
        files = build_devweb_project_files(_single_scenario_file(captured_body=multiline_body))
        [csv_text] = _csv_files_only(files).values()
        row = _csv_rows(csv_text)[0]
        body_text = _body_text(files, row["requestBodyFile"])
        assert "\n" not in body_text
        assert "<b>1</b>" in body_text and "<c>2</c>" in body_text

    def test_csv_field_never_needs_quote_escaping_for_body_content(self):
        """The whole point of the bodyPath fix: a body containing quotes
        and commas (e.g. JSON) must never end up needing CSV-level
        escaping in the first place, since it's never a CSV field."""
        tricky_body = '{ "email": "joe.doe@doe", "note": "has, a comma too" }'
        files = build_devweb_project_files(_single_scenario_file(captured_body=tricky_body))
        [csv_text] = _csv_files_only(files).values()
        row = _csv_rows(csv_text)[0]
        assert '"' not in row["requestBodyFile"]
        assert _body_text(files, row["requestBodyFile"]) == tricky_body


class TestReadme:
    def test_readme_lists_every_stub_and_project(self):
        f1 = _single_scenario_file()
        f2 = _url_segment_file()
        combined = ParsedFile(format="test", source_file="t", stubs=[*f1.stubs, *f2.stubs])
        readme = build_devweb_project_files(combined, "My DevWeb Project")["README.md"]
        assert "My DevWeb Project" in readme
        assert "Simple Stub" in readme
        assert "URL Segment Stub" in readme

    def test_readme_states_out_of_scope_items_including_devweb_specific(self):
        readme = build_devweb_project_files(_single_scenario_file())["README.md"]
        assert "WS-Security" in readme
        assert "fault" in readme.lower()
        assert "correlation" in readme.lower()

    def test_readme_flags_sdk_file_not_bundled(self):
        readme = build_devweb_project_files(_single_scenario_file())["README.md"]
        assert "DevWebSdk.d.ts" in readme


class TestFilenameSafety:
    def test_stub_names_produce_distinct_safe_names(self):
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
        files = build_devweb_project_files(pf)
        csv_keys = list(_csv_files_only(files))
        assert len(csv_keys) == 2
        assert len(set(csv_keys)) == 2  # no collision


@pytest.mark.skipif(not _NODE_AVAILABLE, reason="Node.js not available to syntax-check generated JS")
class TestRobustnessAgainstUnusualInputs:
    """'Different input params tomorrow' coverage — a real, previously
    shipped bug (see PHASE2_DEVWEB_NFT_GENERATION.md §7) was found only
    once real, messy data hit real VuGen. These tests exist so the next
    unusual input is caught here instead of on a user's machine.
    Everything is checked with a real `node --check`, not string matching.
    """

    def _assert_valid_js(self, main_js: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "main.js"
            script_path.write_text(main_js, encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script_path)], capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0, f"node --check failed:\n{result.stderr}\n\n--- main.js ---\n{main_js}"

    def test_project_name_containing_block_comment_closer_does_not_break_js(self):
        """Real, reproduced bug: a stub/project name containing a literal
        `*/` prematurely closes main.js's header docblock, turning the
        rest of the comment into raw (syntactically invalid) JS source."""
        pf = _single_scenario_file()
        files = build_devweb_project_files(pf, "Weird */ alert(1); /* Project Name")
        self._assert_valid_js(files["main.js"])

    def test_captured_url_containing_newline_does_not_break_js(self):
        """A `//` line comment only ends at a newline — an embedded
        newline in a captured URL would spill the rest of the comment out
        as raw source."""
        stub = ParsedStub(
            name="Newline URL Stub",
            request=ParsedRequestSpec(
                method=HttpMethod.POST, url="/a/b\nconst injected = true;", required_headers={}
            ),
            scenarios=[ParsedScenario(name="d", match=MatchCondition(type=MatchType.ALWAYS), status=200, captured_request_body="{}")],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_devweb_project_files(pf, "Newline Test")
        self._assert_valid_js(files["main.js"])

    def test_unicode_stub_name_and_body_do_not_break_generation(self):
        """No sample data seen so far has exercised non-ASCII content —
        real wealth/banking data eventually will (accented names, currency
        symbols). This must not crash the generator or produce invalid JS,
        regardless of what VuGen's own file-encoding assumptions turn out
        to be (see PHASE2_DEVWEB_NFT_GENERATION.md §7 for that open,
        flagged question)."""
        stub = ParsedStub(
            name="Client François Müller — £ / € Ünïcödé",
            request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/clients/François", required_headers={"X-Name": "Müller"}),
            scenarios=[
                ParsedScenario(
                    name="d",
                    match=MatchCondition(type=MatchType.ALWAYS),
                    status=200,
                    captured_request_body='{"name": "François Müller", "amount": "£1,234.56 / €999"}',
                )
            ],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_devweb_project_files(pf, "Ünïcödé Project 日本語")
        self._assert_valid_js(files["main.js"])
        [body_key] = [k for k in files if k.endswith(".body.txt")]
        assert files[body_key] == '{"name": "François Müller", "amount": "£1,234.56 / €999"}'

    def test_apostrophe_in_stub_name_does_not_break_anything(self):
        stub = ParsedStub(
            name="O'Brien's Adviser Stub",
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/a", required_headers={}),
            scenarios=[ParsedScenario(name="d", match=MatchCondition(type=MatchType.ALWAYS), status=200)],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_devweb_project_files(pf, "O'Brien's Project")
        self._assert_valid_js(files["main.js"])
        ET.fromstring(files["ScriptUploadMetadata.xml"])

    def test_all_common_http_methods_produce_valid_js(self):
        for method in [HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT, HttpMethod.DELETE, HttpMethod.PATCH]:
            stub = ParsedStub(
                name=f"{method.value} Stub",
                request=ParsedRequestSpec(method=method, url="/a", required_headers={}),
                scenarios=[ParsedScenario(name="d", match=MatchCondition(type=MatchType.ALWAYS), status=200)],
            )
            pf = ParsedFile(format="test", source_file="t", stubs=[stub])
            files = build_devweb_project_files(pf, f"{method.value} Project")
            self._assert_valid_js(files["main.js"])

    def test_very_long_project_and_stub_names_are_capped_and_valid(self):
        long_name = "Extremely Long Project Name " * 20  # ~580 chars
        stub = ParsedStub(
            name="Also A Very Long Stub Name " * 10,
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/a", required_headers={}),
            scenarios=[ParsedScenario(name="d", match=MatchCondition(type=MatchType.ALWAYS), status=200)],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_devweb_project_files(pf, long_name)
        self._assert_valid_js(files["main.js"])
        [usr_key] = [k for k in files if k.endswith(".usr")]
        assert len(usr_key) < 120  # capped, not unbounded

    def test_stub_name_that_is_only_punctuation_still_produces_valid_output(self):
        stub = ParsedStub(
            name="!!! /// *** ???",
            request=ParsedRequestSpec(method=HttpMethod.GET, url="/a", required_headers={}),
            scenarios=[ParsedScenario(name="d", match=MatchCondition(type=MatchType.ALWAYS), status=200)],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_devweb_project_files(pf, "!!!")
        self._assert_valid_js(files["main.js"])
        [csv_key] = [k for k in files if k.endswith(".csv")]
        assert "stub00_stub" in csv_key  # falls back to a safe default, never empty

    def test_header_value_containing_quotes_and_backslashes_produces_valid_js(self):
        stub = ParsedStub(
            name="Tricky Headers",
            request=ParsedRequestSpec(
                method=HttpMethod.POST,
                url="/a",
                required_headers={"X-Custom": 'value with "quotes" and \\backslashes\\ and\ttabs'},
            ),
            scenarios=[ParsedScenario(name="d", match=MatchCondition(type=MatchType.ALWAYS), status=200, captured_request_body="{}")],
        )
        pf = ParsedFile(format="test", source_file="t", stubs=[stub])
        files = build_devweb_project_files(pf, "Tricky Headers Project")
        self._assert_valid_js(files["main.js"])
