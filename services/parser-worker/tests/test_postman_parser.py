"""Tests for the Postman v2.1 parser."""
from __future__ import annotations

import json

import pytest

from parser_worker.parsers.postman import PostmanParser

PARSER = PostmanParser()

# ── fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_COLLECTION = {
    "info": {
        "_postman_id": "abc-123",
        "name": "Test Collection",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [
        {
            "name": "Get Customer",
            "request": {"method": "GET", "url": "/api/v1/customers/123", "header": []},
            "response": [],
        }
    ],
}

COLLECTION_WITH_RESPONSES = {
    "info": {
        "name": "Payment API",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [
        {
            "name": "Make Payment",
            "request": {
                "method": "POST",
                "url": "/api/v1/payments",
                "header": [{"key": "Content-Type", "value": "application/json"}],
            },
            "response": [
                {
                    "name": "Payment Accepted",
                    "code": 200,
                    "status": "OK",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": '{"id": "pay-001", "status": "accepted"}',
                },
                {
                    "name": "Insufficient Funds",
                    "code": 402,
                    "status": "Payment Required",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": '{"error": "Insufficient funds"}',
                },
            ],
        }
    ],
}


# ── can_handle ────────────────────────────────────────────────────────────────

class TestCanHandle:
    def test_accepts_v21_collection(self):
        assert PARSER.can_handle(json.dumps(MINIMAL_COLLECTION), "collection.json")

    def test_rejects_v20_schema(self):
        data = {
            **MINIMAL_COLLECTION,
            "info": {
                **MINIMAL_COLLECTION["info"],
                "schema": "https://schema.getpostman.com/json/collection/v2.0.0/collection.json",
            },
        }
        assert not PARSER.can_handle(json.dumps(data), "collection.json")

    def test_rejects_mockingbird_txt(self):
        assert not PARSER.can_handle("--- MOCKINGBIRD v1.0 ---\n", "file.txt")

    def test_rejects_plain_json_without_postman_schema(self):
        assert not PARSER.can_handle('{"key": "value"}', "data.json")

    def test_rejects_missing_item_array(self):
        data = {
            "info": {"schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}
        }
        assert not PARSER.can_handle(json.dumps(data), "collection.json")


# ── validate ──────────────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_minimal_collection(self):
        result = PARSER.validate(json.dumps(MINIMAL_COLLECTION))
        assert result.valid
        assert "1 endpoint" in result.summary

    def test_warns_when_no_saved_responses(self):
        result = PARSER.validate(json.dumps(MINIMAL_COLLECTION))
        assert result.valid
        assert len(result.warnings) == 1
        assert "saved responses" in result.warnings[0].lower()

    def test_no_warning_when_responses_present(self):
        result = PARSER.validate(json.dumps(COLLECTION_WITH_RESPONSES))
        assert result.valid
        assert not result.warnings

    def test_summary_counts_responses(self):
        result = PARSER.validate(json.dumps(COLLECTION_WITH_RESPONSES))
        assert "2 saved response" in result.summary

    def test_invalid_when_item_array_empty(self):
        data = {
            "info": {"schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
            "item": [],
        }
        result = PARSER.validate(json.dumps(data))
        assert not result.valid

    def test_invalid_json(self):
        result = PARSER.validate("not json {{{")
        assert not result.valid
        assert any("JSON" in e.message for e in result.errors)

    def test_invalid_wrong_schema_version(self):
        data = {
            "info": {"schema": "https://schema.getpostman.com/json/collection/v2.0.0/collection.json"},
            "item": [{"name": "x", "request": {"method": "GET", "url": "/x"}, "response": []}],
        }
        result = PARSER.validate(json.dumps(data))
        assert not result.valid


# ── parse ─────────────────────────────────────────────────────────────────────

class TestParse:
    def test_extracts_method_and_url_from_string(self):
        parsed = PARSER.parse(json.dumps(MINIMAL_COLLECTION), "test.json")
        assert len(parsed.stubs) == 1
        stub = parsed.stubs[0]
        assert stub.request.method.value == "GET"
        assert stub.request.url == "/api/v1/customers/123"

    def test_stub_name_from_item_name(self):
        parsed = PARSER.parse(json.dumps(MINIMAL_COLLECTION), "test.json")
        assert parsed.stubs[0].name == "Get Customer"

    def test_url_object_with_raw_field(self):
        data = {
            **MINIMAL_COLLECTION,
            "item": [{
                "name": "Get Item",
                "request": {
                    "method": "GET",
                    "url": {"raw": "{{baseUrl}}/api/v1/items/{{id}}", "path": ["api", "v1", "items", "{{id}}"]},
                    "header": [],
                },
                "response": [],
            }],
        }
        parsed = PARSER.parse(json.dumps(data), "test.json")
        assert parsed.stubs[0].request.url == "/api/v1/items/{id}"

    def test_converts_postman_double_braces_to_wiremock_single(self):
        data = {
            **MINIMAL_COLLECTION,
            "item": [{
                "name": "Get Customer",
                "request": {"method": "GET", "url": "/api/v1/customers/{{customerId}}", "header": []},
                "response": [],
            }],
        }
        parsed = PARSER.parse(json.dumps(data), "test.json")
        assert parsed.stubs[0].request.url == "/api/v1/customers/{customerId}"

    def test_strips_https_host_from_url(self):
        data = {
            **MINIMAL_COLLECTION,
            "item": [{
                "name": "Call",
                "request": {"method": "GET", "url": "https://api.example.com/v1/orders", "header": []},
                "response": [],
            }],
        }
        parsed = PARSER.parse(json.dumps(data), "test.json")
        assert parsed.stubs[0].request.url == "/v1/orders"

    def test_default_200_scenario_when_no_saved_responses(self):
        parsed = PARSER.parse(json.dumps(MINIMAL_COLLECTION), "test.json")
        stub = parsed.stubs[0]
        assert len(stub.scenarios) == 1
        assert stub.scenarios[0].status == 200
        assert stub.scenarios[0].match.type.value == "always"

    def test_scenarios_from_saved_responses(self):
        parsed = PARSER.parse(json.dumps(COLLECTION_WITH_RESPONSES), "test.json")
        stub = parsed.stubs[0]
        assert len(stub.scenarios) == 2

    def test_2xx_is_first_scenario_highest_priority(self):
        parsed = PARSER.parse(json.dumps(COLLECTION_WITH_RESPONSES), "test.json")
        assert parsed.stubs[0].scenarios[0].status == 200

    def test_non_2xx_is_after_2xx(self):
        parsed = PARSER.parse(json.dumps(COLLECTION_WITH_RESPONSES), "test.json")
        assert parsed.stubs[0].scenarios[1].status == 402

    def test_scenario_body_preserved(self):
        parsed = PARSER.parse(json.dumps(COLLECTION_WITH_RESPONSES), "test.json")
        assert "accepted" in parsed.stubs[0].scenarios[0].body

    def test_scenario_response_headers_preserved(self):
        parsed = PARSER.parse(json.dumps(COLLECTION_WITH_RESPONSES), "test.json")
        assert parsed.stubs[0].scenarios[0].response_headers.get("Content-Type") == "application/json"

    def test_flattens_nested_folders(self):
        data = {
            "info": {"schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
            "item": [
                {
                    "name": "Customer Folder",
                    "item": [
                        {
                            "name": "Get Customer",
                            "request": {"method": "GET", "url": "/api/v1/customers", "header": []},
                            "response": [],
                        },
                        {
                            "name": "Inner Folder",
                            "item": [{
                                "name": "Nested Request",
                                "request": {"method": "POST", "url": "/api/v1/orders", "header": []},
                                "response": [],
                            }],
                        },
                    ],
                }
            ],
        }
        parsed = PARSER.parse(json.dumps(data), "test.json")
        assert len(parsed.stubs) == 2

    def test_skips_disabled_headers(self):
        data = {
            **MINIMAL_COLLECTION,
            "item": [{
                "name": "Get Item",
                "request": {
                    "method": "GET",
                    "url": "/api/v1/items",
                    "header": [
                        {"key": "Authorization", "value": "Bearer token", "disabled": True},
                        {"key": "Accept", "value": "application/json"},
                    ],
                },
                "response": [],
            }],
        }
        parsed = PARSER.parse(json.dumps(data), "test.json")
        stub = parsed.stubs[0]
        assert "Authorization" not in stub.request.required_headers
        assert stub.request.required_headers.get("Accept") == "application/json"

    def test_skips_headers_with_postman_variables(self):
        data = {
            **MINIMAL_COLLECTION,
            "item": [{
                "name": "Call",
                "request": {
                    "method": "GET",
                    "url": "/api/v1/items",
                    "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
                },
                "response": [],
            }],
        }
        parsed = PARSER.parse(json.dumps(data), "test.json")
        assert "Authorization" not in parsed.stubs[0].request.required_headers
