"""Integration tests — full pipeline from input file to generated Spring Boot project.

These tests exercise the complete sv-gen pipeline end-to-end:
  input file → detect format → validate → parse → generate WireMock mappings
              → generate Spring Boot project → verify all output files exist and are correct.

Docker/Maven build steps are NOT tested here — those require NatWest GitLab CI
with Artifactory access. Tests cover everything up to 'docker build' input readiness.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from parser_worker.cli import main
from parser_worker.detector import detect_and_parse
from parser_worker.generator.springboot import generate_springboot_project
from parser_worker.generator.wiremock import generate_wiremock_mappings

# ── shared input fixtures ─────────────────────────────────────────────────────

LEVEL1_TXT = """\
--- MOCKINGBIRD v1.0 ---

Name: Payment API
Method: POST
URL: /api/v1/payments

--- RESPONSE ---
Status: 200
Content-Type: application/json

{"id": "pay-001", "status": "accepted", "amount": 100.00}
"""

LEVEL2_TXT = """\
--- MOCKINGBIRD v1.0 ---

Name: Customer API
Method: GET
URL: /api/v1/customers/{customerId}

--- SCENARIO: Customer Not Found ---
Match-Type: url-contains
Match-Value: UNKNOWN
Status: 404
Content-Type: application/json

{"error": "Customer not found", "code": "CUST_404"}

--- SCENARIO DEFAULT ---
Status: 200
Content-Type: application/json

{"id": "{{request.pathParam.customerId}}", "name": "John Smith", "status": "ACTIVE"}
"""

OPENAPI_JSON = json.dumps({
    "openapi": "3.0.3",
    "info": {"title": "Accounts API", "version": "1.0.0"},
    "paths": {
        "/accounts/{id}": {
            "get": {
                "summary": "Get Account",
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "example": {"id": "acc-001", "balance": 5000.00}
                            }
                        },
                    },
                    "404": {
                        "description": "Not Found",
                        "content": {
                            "application/json": {
                                "example": {"error": "Account not found"}
                            }
                        },
                    },
                },
            }
        }
    },
})

POSTMAN_COLLECTION = json.dumps({
    "info": {
        "name": "Orders API",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [
        {
            "name": "Create Order",
            "request": {
                "method": "POST",
                "url": "/api/v1/orders",
                "header": [{"key": "Content-Type", "value": "application/json"}],
            },
            "response": [
                {
                    "name": "Order Created",
                    "code": 201,
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": '{"orderId": "ord-001", "status": "pending"}',
                }
            ],
        }
    ],
})


# ── helper ────────────────────────────────────────────────────────────────────

def _write(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ── detect + parse ────────────────────────────────────────────────────────────

class TestDetectAndParse:
    def test_detects_level1_txt(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        parser, result, parsed = detect_and_parse(f)
        assert result.valid
        assert parser.format_name == "level-1-txt"
        assert len(parsed.stubs) == 1

    def test_detects_level2_txt(self, tmp_path):
        f = _write(tmp_path, "customer.txt", LEVEL2_TXT)
        parser, result, parsed = detect_and_parse(f)
        assert result.valid
        assert parser.format_name == "level-2-txt"
        assert len(parsed.stubs[0].scenarios) == 2

    def test_detects_openapi_json(self, tmp_path):
        f = _write(tmp_path, "accounts.json", OPENAPI_JSON)
        parser, result, parsed = detect_and_parse(f)
        assert result.valid
        assert parser.format_name == "openapi"
        assert parsed.stubs[0].request.url == "/accounts/{id}"

    def test_detects_postman_collection(self, tmp_path):
        f = _write(tmp_path, "orders.json", POSTMAN_COLLECTION)
        parser, result, parsed = detect_and_parse(f)
        assert result.valid
        assert parser.format_name == "postman-v2.1"

    def test_unknown_format_returns_invalid(self, tmp_path):
        f = _write(tmp_path, "garbage.txt", "this is not any known format at all\n")
        parser, result, parsed = detect_and_parse(f)
        assert parser is None
        assert not result.valid
        assert parsed is None


# ── wiremock mapping generation ───────────────────────────────────────────────

class TestWireMockGeneration:
    def test_level1_produces_one_mapping(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        created = generate_wiremock_mappings(parsed, tmp_path / "out")
        assert len(created) == 1

    def test_level2_produces_two_mappings(self, tmp_path):
        f = _write(tmp_path, "customer.txt", LEVEL2_TXT)
        _, _, parsed = detect_and_parse(f)
        created = generate_wiremock_mappings(parsed, tmp_path / "out")
        assert len(created) == 2

    def test_mapping_method_is_correct(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        generate_wiremock_mappings(parsed, tmp_path / "out")
        mapping = json.loads((tmp_path / "out" / "mappings").glob("*.json").__next__().read_text())
        assert mapping["request"]["method"] == "POST"

    def test_mapping_url_is_correct(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        generate_wiremock_mappings(parsed, tmp_path / "out")
        mapping = json.loads((tmp_path / "out" / "mappings").glob("*.json").__next__().read_text())
        assert mapping["request"]["urlPath"] == "/api/v1/payments"

    def test_mapping_status_is_correct(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        generate_wiremock_mappings(parsed, tmp_path / "out")
        mapping = json.loads((tmp_path / "out" / "mappings").glob("*.json").__next__().read_text())
        assert mapping["response"]["status"] == 200

    def test_mapping_body_contains_expected_json(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        generate_wiremock_mappings(parsed, tmp_path / "out")
        mapping = json.loads((tmp_path / "out" / "mappings").glob("*.json").__next__().read_text())
        assert "pay-001" in mapping["response"]["body"]

    def test_path_param_uses_url_pattern(self, tmp_path):
        f = _write(tmp_path, "customer.txt", LEVEL2_TXT)
        _, _, parsed = detect_and_parse(f)
        generate_wiremock_mappings(parsed, tmp_path / "out")
        mappings = list((tmp_path / "out" / "mappings").glob("*.json"))
        contents = [json.loads(m.read_text()) for m in mappings]
        default = next(m for m in contents if "default" in m["name"].lower())
        assert "urlPattern" in default["request"]

    def test_dynamic_body_gets_response_template_transformer(self, tmp_path):
        f = _write(tmp_path, "customer.txt", LEVEL2_TXT)
        _, _, parsed = detect_and_parse(f)
        generate_wiremock_mappings(parsed, tmp_path / "out")
        mappings = list((tmp_path / "out" / "mappings").glob("*.json"))
        contents = [json.loads(m.read_text()) for m in mappings]
        default = next(m for m in contents if "default" in m["name"].lower())
        assert "response-template" in default["response"].get("transformers", [])

    def test_openapi_multi_status_produces_correct_count(self, tmp_path):
        f = _write(tmp_path, "accounts.json", OPENAPI_JSON)
        _, _, parsed = detect_and_parse(f)
        created = generate_wiremock_mappings(parsed, tmp_path / "out")
        assert len(created) == 2  # 200 + 404


# ── spring boot project generation ───────────────────────────────────────────

class TestSpringBootProjectGeneration:
    def test_all_root_files_created(self, tmp_path):
        (tmp_path / "in").mkdir(exist_ok=True)
        f = _write(tmp_path / "in", "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "payment-api", "Payment API")

        assert (out / "pom.xml").exists()
        assert (out / "Dockerfile").exists()
        assert (out / "docker-compose.yml").exists()
        assert (out / "settings.xml").exists()

    def test_java_source_files_created(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "payment-api", "Payment API")
        java_dir = out / "src/main/java/com/natwest/mockingbird/stubs"
        assert (java_dir / "StubApplication.java").exists()
        assert (java_dir / "WireMockConfig.java").exists()

    def test_application_yml_created(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "payment-api", "Payment API")
        assert (out / "src/main/resources/application.yml").exists()

    def test_mappings_baked_into_jar_resources(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "payment-api", "Payment API")
        jar_mappings = out / "src/main/resources/mappings"
        assert jar_mappings.is_dir()
        assert len(list(jar_mappings.glob("*.json"))) == 1

    def test_pom_project_id_substituted(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "payment-api", "Payment API")
        pom = (out / "pom.xml").read_text()
        assert "payment-api-stub" in pom
        assert "{{project_id}}" not in pom

    def test_pom_project_name_substituted(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "payment-api", "Payment API")
        pom = (out / "pom.xml").read_text()
        assert "Payment API" in pom
        assert "{{project_name}}" not in pom

    def test_auto_derives_project_id_from_stub_name(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out)  # no project_id
        pom = (out / "pom.xml").read_text()
        assert "payment-api-stub" in pom  # derived from stub name "Payment API"

    def test_wiremock_jar_resources_match_mappings_dir(self, tmp_path):
        f = _write(tmp_path, "customer.txt", LEVEL2_TXT)
        _, _, parsed = detect_and_parse(f)
        out = tmp_path / "stub"
        generate_springboot_project(parsed, out, "customer-api", "Customer API")
        mappings_files = set(p.name for p in (out / "mappings").glob("*.json"))
        jar_files = set(p.name for p in (out / "src/main/resources/mappings").glob("*.json"))
        assert mappings_files == jar_files


# ── CLI (sv-gen command) ──────────────────────────────────────────────────────

class TestCLI:
    def _run(self, *args: str) -> object:
        return CliRunner().invoke(main, list(args), catch_exceptions=False)

    def test_version_flag(self):
        result = CliRunner().invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help_flag(self):
        result = CliRunner().invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--input" in result.output
        assert "--output" in result.output
        assert "--dry-run" in result.output
        assert "--mappings-only" in result.output

    def test_dry_run_shows_valid_and_no_files(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        out = tmp_path / "out"
        result = CliRunner().invoke(main, [
            "--input", str(f), "--output", str(out), "--dry-run"
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert "VALID" in result.output
        assert not out.exists()

    def test_mappings_only_creates_only_mappings_dir(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        out = tmp_path / "out"
        result = CliRunner().invoke(main, [
            "--input", str(f), "--output", str(out), "--mappings-only"
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert (out / "mappings").is_dir()
        assert not (out / "pom.xml").exists()
        assert not (out / "Dockerfile").exists()

    def test_full_generate_exits_zero(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        out = tmp_path / "out"
        result = CliRunner().invoke(main, [
            "--input", str(f), "--output", str(out)
        ], catch_exceptions=False)
        assert result.exit_code == 0

    def test_full_generate_creates_spring_boot_project(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        out = tmp_path / "out"
        CliRunner().invoke(main, ["--input", str(f), "--output", str(out)], catch_exceptions=False)
        assert (out / "pom.xml").exists()
        assert (out / "Dockerfile").exists()
        assert (out / "src/main/java/com/natwest/mockingbird/stubs/WireMockConfig.java").exists()

    def test_invalid_file_exits_nonzero(self, tmp_path):
        f = _write(tmp_path, "garbage.txt", "this is not a valid stub file\n")
        out = tmp_path / "out"
        result = CliRunner().invoke(main, ["--input", str(f), "--output", str(out)])
        assert result.exit_code != 0

    def test_output_shows_stub_url(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        out = tmp_path / "out"
        result = CliRunner().invoke(main, ["--input", str(f), "--output", str(out)], catch_exceptions=False)
        assert "localhost:8080" in result.output

    def test_manifest_json_written(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        out = tmp_path / "out"
        CliRunner().invoke(main, ["--input", str(f), "--output", str(out)], catch_exceptions=False)
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["format"] == "level-1-txt"
        assert len(manifest["stubs"]) == 1
        assert manifest["stubs"][0]["method"] == "POST"

    def test_openapi_input_generates_project(self, tmp_path):
        f = _write(tmp_path, "accounts.json", OPENAPI_JSON)
        out = tmp_path / "out"
        result = CliRunner().invoke(main, [
            "--input", str(f), "--output", str(out),
            "--project-id", "accounts-api", "--project-name", "Accounts API"
        ], catch_exceptions=False)
        assert result.exit_code == 0
        assert (out / "pom.xml").exists()
        pom = (out / "pom.xml").read_text()
        assert "accounts-api" in pom

    def test_postman_input_generates_project(self, tmp_path):
        f = _write(tmp_path, "orders.json", POSTMAN_COLLECTION)
        out = tmp_path / "out"
        result = CliRunner().invoke(main, ["--input", str(f), "--output", str(out)], catch_exceptions=False)
        assert result.exit_code == 0
        assert (out / "mappings").is_dir()

    def test_output_shows_format_label(self, tmp_path):
        f = _write(tmp_path, "payment.txt", LEVEL1_TXT)
        out = tmp_path / "out"
        result = CliRunner().invoke(main, ["--input", str(f), "--output", str(out)], catch_exceptions=False)
        assert "level-1-txt" in result.output
