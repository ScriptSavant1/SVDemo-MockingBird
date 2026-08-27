"""Tests for generator/springboot.py — the full Spring Boot project builder.

build_springboot_project_files is the single in-memory source of truth for
project contents; generate_springboot_project (disk) and
generate_springboot_project_zip (ZIP bytes) are thin wrappers around it and
must always agree on what a project contains.
"""
from __future__ import annotations

import io
import zipfile

from parser_worker.generator.lookup_table import LOOKUP_TABLE_THRESHOLD
from parser_worker.generator.springboot import (
    build_springboot_project_files,
    generate_springboot_project,
    generate_springboot_project_zip,
)
from parser_worker.models import (
    HttpMethod,
    MatchCondition,
    MatchType,
    ParsedFile,
    ParsedRequestSpec,
    ParsedScenario,
    ParsedStub,
)


def _simple_parsed_file(url="/api/test") -> ParsedFile:
    scenario = ParsedScenario(
        name="default", match=MatchCondition(type=MatchType.ALWAYS), status=200, body='{"ok":true}',
    )
    stub = ParsedStub(
        name="Distinctive Stub",
        request=ParsedRequestSpec(method=HttpMethod.GET, url=url),
        scenarios=[scenario],
    )
    return ParsedFile(format="test", source_file="t", stubs=[stub])


def _high_variant_parsed_file(count: int = LOOKUP_TABLE_THRESHOLD + 5) -> ParsedFile:
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
        name="High Variant Stub",
        request=ParsedRequestSpec(method=HttpMethod.POST, url="/api/high-variant"),
        scenarios=scenarios,
        lookup_discriminator_type="xpath",
        lookup_discriminator_field="Id",
    )
    return ParsedFile(format="ca-lisa-http-pair", source_file="t", stubs=[stub])


class TestBuildProjectFilesInMemory:
    def test_expected_files_present(self):
        files = build_springboot_project_files(_simple_parsed_file(), "proj", "Proj Name")
        assert "pom.xml" in files
        assert "Dockerfile" in files
        assert "STUB_ENGINE_SETUP_GUIDE.html" in files
        assert "src/main/java/com/mockingbird/stubs/StubApplication.java" in files
        assert "src/main/java/com/mockingbird/stubs/DynamicLookupRequestFilter.java" in files
        assert any(p.startswith("src/main/resources/mappings/") for p in files)

    def test_pom_placeholders_substituted(self):
        files = build_springboot_project_files(_simple_parsed_file(), "my-proj-id", "My Project Name")
        pom = files["pom.xml"].decode("utf-8")
        assert "{{project_id}}" not in pom
        assert "{{project_name}}" not in pom
        assert "my-proj-id" in pom
        assert "My Project Name" in pom

    def test_no_top_level_mappings_duplicate(self):
        """Mappings live only under src/main/resources/mappings/ — a
        top-level mappings/ copy would be dead weight nothing reads."""
        files = build_springboot_project_files(_simple_parsed_file(), "p", "P")
        assert not any(p.startswith("mappings/") for p in files)

    def test_high_variant_stub_produces_lookup_table_not_static_mappings(self):
        files = build_springboot_project_files(_high_variant_parsed_file(), "p", "P")
        assert any(p.startswith("src/main/resources/lookup-tables/") for p in files)
        assert not any(p.startswith("src/main/resources/mappings/") for p in files)

    def test_low_variant_stub_produces_static_mappings_not_lookup_table(self):
        files = build_springboot_project_files(_simple_parsed_file(), "p", "P")
        assert any(p.startswith("src/main/resources/mappings/") for p in files)
        assert not any(p.startswith("src/main/resources/lookup-tables/") for p in files)


class TestDiskAndZipAgreeWithInMemoryBuild:
    def test_disk_write_matches_in_memory_build(self, tmp_path):
        parsed = _simple_parsed_file()
        in_memory = build_springboot_project_files(parsed, "p", "P")

        generate_springboot_project(parsed, tmp_path, project_id="p", project_name="P")

        for relative_path, content in in_memory.items():
            on_disk = (tmp_path / relative_path).read_bytes()
            assert on_disk == content, f"disk content for {relative_path} diverged from in-memory build"

    def test_zip_bytes_match_in_memory_build(self):
        parsed = _simple_parsed_file()
        in_memory = build_springboot_project_files(parsed, "p", "P")

        zip_bytes = generate_springboot_project_zip(parsed, project_id="p", project_name="P")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zipped = {name: zf.read(name) for name in zf.namelist()}

        assert zipped.keys() == in_memory.keys()
        for relative_path, content in in_memory.items():
            assert zipped[relative_path] == content

    def test_zip_never_touches_disk_outside_read_only_templates(self, tmp_path, monkeypatch):
        """generate_springboot_project_zip must not write anywhere on disk —
        the whole point is skipping the write-then-reread-then-delete cycle
        the old temp-directory approach used."""
        import pathlib

        original_write_bytes = pathlib.Path.write_bytes
        original_write_text = pathlib.Path.write_text
        original_mkdir = pathlib.Path.mkdir

        def _fail(*args, **kwargs):
            raise AssertionError("generate_springboot_project_zip must not write to disk")

        monkeypatch.setattr(pathlib.Path, "write_bytes", _fail)
        monkeypatch.setattr(pathlib.Path, "write_text", _fail)
        monkeypatch.setattr(pathlib.Path, "mkdir", _fail)
        try:
            generate_springboot_project_zip(_high_variant_parsed_file(), project_id="p", project_name="P")
        finally:
            monkeypatch.setattr(pathlib.Path, "write_bytes", original_write_bytes)
            monkeypatch.setattr(pathlib.Path, "write_text", original_write_text)
            monkeypatch.setattr(pathlib.Path, "mkdir", original_mkdir)


class TestGenerateSpringbootProjectDiskWrapper:
    def test_returns_output_dir(self, tmp_path):
        result = generate_springboot_project(_simple_parsed_file(), tmp_path, project_id="p", project_name="P")
        assert result == tmp_path

    def test_writes_real_files(self, tmp_path):
        generate_springboot_project(_simple_parsed_file(), tmp_path, project_id="p", project_name="P")
        assert (tmp_path / "pom.xml").exists()
        assert (tmp_path / "src/main/java/com/mockingbird/stubs/StubApplication.java").exists()
