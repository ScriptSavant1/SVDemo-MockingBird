"""Tests for the dynamic lookup-table generator (generator/lookup_table.py).

Covers the threshold decision, the data file this module writes for
DynamicLookupRequestFilter.java to consume, and that the static-mapping
generator (generator/wiremock.py) correctly steps aside for any stub this
module claims.
"""
from __future__ import annotations

import json

from parser_worker.generator.lookup_table import (
    LOOKUP_TABLE_THRESHOLD,
    generate_lookup_tables,
    should_use_lookup_table,
)
from parser_worker.generator.wiremock import build_wiremock_mappings, generate_wiremock_mappings
from parser_worker.models import (
    HttpMethod,
    MatchCondition,
    MatchType,
    ParsedFile,
    ParsedRequestSpec,
    ParsedScenario,
    ParsedStub,
)


def _make_stub(scenario_count: int, discriminator_field: str | None = "Full") -> ParsedStub:
    scenarios = [
        ParsedScenario(
            name=f"variant-{i + 1}",
            match=MatchCondition(type=MatchType.BODY_XPATH, value=f"//*[local-name()='Full' and text()='user-{i}']"),
            status=200,
            response_headers={"Content-Type": "application/xml"},
            body=f"<Account><Full>user-{i}</Full></Account>",
            lookup_key=f"user-{i}" if discriminator_field else None,
        )
        for i in range(scenario_count)
    ]
    return ParsedStub(
        name="Account Instructions",
        request=ParsedRequestSpec(
            method=HttpMethod.POST,
            url="/api/distribution/v3/accountinstructions",
            required_headers={"x-usercontext": "UserID=542849"},
        ),
        scenarios=scenarios,
        lookup_discriminator_type="xpath" if discriminator_field else None,
        lookup_discriminator_field=discriminator_field,
    )


class TestShouldUseLookupTable:
    def test_below_threshold_uses_static_mappings(self):
        stub = _make_stub(LOOKUP_TABLE_THRESHOLD)  # exactly at threshold, not over
        assert should_use_lookup_table(stub) is False

    def test_above_threshold_uses_lookup_table(self):
        stub = _make_stub(LOOKUP_TABLE_THRESHOLD + 1)
        assert should_use_lookup_table(stub) is True

    def test_no_discriminator_never_qualifies_even_with_many_scenarios(self):
        stub = _make_stub(LOOKUP_TABLE_THRESHOLD + 10, discriminator_field=None)
        assert should_use_lookup_table(stub) is False

    def test_single_scenario_stub_never_qualifies(self):
        stub = _make_stub(1)
        assert should_use_lookup_table(stub) is False


class TestGenerateLookupTables:
    def test_writes_one_file_for_qualifying_stub(self, tmp_path):
        stub = _make_stub(LOOKUP_TABLE_THRESHOLD + 5)
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[stub])

        created = generate_lookup_tables(parsed, tmp_path)

        assert len(created) == 1
        assert created[0].parent.name == "lookup-tables"
        assert created[0].exists()

    def test_skips_stub_below_threshold(self, tmp_path):
        stub = _make_stub(3)
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[stub])

        created = generate_lookup_tables(parsed, tmp_path)

        assert created == []
        assert not (tmp_path / "lookup-tables").exists()

    def test_table_content_matches_stub(self, tmp_path):
        count = LOOKUP_TABLE_THRESHOLD + 3
        stub = _make_stub(count)
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[stub])

        [path] = generate_lookup_tables(parsed, tmp_path)
        table = json.loads(path.read_text(encoding="utf-8"))

        assert table["method"] == "POST"
        assert table["urlPath"] == "/api/distribution/v3/accountinstructions"
        assert table["discriminatorType"] == "xpath"
        assert table["discriminatorField"] == "Full"
        assert table["requiredHeaders"] == {"x-usercontext": "UserID=542849"}
        assert len(table["entries"]) == count
        assert {"key": "user-0", "status": 200,
                "headers": {"Content-Type": "application/xml"},
                "body": "<Account><Full>user-0</Full></Account>"} in table["entries"]

    def test_wildcard_required_headers_excluded(self, tmp_path):
        stub = _make_stub(LOOKUP_TABLE_THRESHOLD + 1)
        stub.request.required_headers["X-Any"] = "*"
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[stub])

        [path] = generate_lookup_tables(parsed, tmp_path)
        table = json.loads(path.read_text(encoding="utf-8"))

        assert "X-Any" not in table["requiredHeaders"]


class TestWiremockGeneratorSkipsLookupTableStubs:
    def test_build_wiremock_mappings_excludes_qualifying_stub(self):
        lookup_stub = _make_stub(LOOKUP_TABLE_THRESHOLD + 1)
        static_stub = _make_stub(2)
        static_stub.name = "Small Operation"
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[lookup_stub, static_stub])

        triples = build_wiremock_mappings(parsed)

        assert all(stub.name != "Account Instructions" for stub, _, _ in triples)
        assert any(stub.name == "Small Operation" for stub, _, _ in triples)
        assert len(triples) == 2  # static_stub's 2 scenarios only

    def test_generate_wiremock_mappings_writes_no_files_for_lookup_stub(self, tmp_path):
        lookup_stub = _make_stub(LOOKUP_TABLE_THRESHOLD + 1)
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[lookup_stub])

        created = generate_wiremock_mappings(parsed, tmp_path)

        assert created == []

    def test_both_generators_together_produce_disjoint_output(self, tmp_path):
        lookup_stub = _make_stub(LOOKUP_TABLE_THRESHOLD + 1)
        static_stub = _make_stub(2)
        static_stub.name = "Small Operation"
        parsed = ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[lookup_stub, static_stub])

        mapping_files = generate_wiremock_mappings(parsed, tmp_path)
        table_files = generate_lookup_tables(parsed, tmp_path)

        assert len(mapping_files) == 2   # static_stub's scenarios
        assert len(table_files) == 1     # lookup_stub's table
