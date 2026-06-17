"""Tests for the OpenAPI 3.x / Swagger 2.0 parser."""
from __future__ import annotations

import json

import pytest

from parser_worker.parsers.openapi import OpenApiParser

PARSER = OpenApiParser()

# ── fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_OPENAPI3 = {
    "openapi": "3.0.3",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/customers/{id}": {
            "get": {
                "summary": "Get Customer",
                "responses": {
                    "200": {
                        "description": "Customer found",
                        "content": {
                            "application/json": {
                                "example": {"id": "123", "name": "John Smith"}
                            }
                        },
                    }
                },
            }
        }
    },
}

OPENAPI3_MULTI_RESPONSE = {
    "openapi": "3.0.3",
    "info": {"title": "Payment API", "version": "1.0.0"},
    "paths": {
        "/payments": {
            "post": {
                "summary": "Create Payment",
                "responses": {
                    "200": {
                        "description": "Payment accepted",
                        "content": {
                            "application/json": {
                                "example": {"id": "pay-001", "status": "accepted"}
                            }
                        },
                    },
                    "400": {
                        "description": "Bad request",
                        "content": {
                            "application/json": {"example": {"error": "Invalid request"}}
                        },
                    },
                    "402": {
                        "description": "Insufficient funds",
                        "content": {
                            "application/json": {"example": {"error": "Insufficient funds"}}
                        },
                    },
                },
            }
        }
    },
}

SWAGGER2_SPEC = {
    "swagger": "2.0",
    "info": {"title": "Swagger API", "version": "1.0"},
    "paths": {
        "/accounts/{id}": {
            "get": {
                "summary": "Get Account",
                "responses": {
                    "200": {
                        "description": "Account",
                        "examples": {
                            "application/json": {"id": "acc-001", "balance": 1000}
                        },
                    }
                },
            }
        }
    },
}

OPENAPI3_YAML = """\
openapi: "3.0.3"
info:
  title: YAML API
  version: "1.0.0"
paths:
  /items:
    get:
      summary: List items
      responses:
        "200":
          description: OK
          content:
            application/json:
              example:
                items:
                  - id: "1"
                    name: Widget
"""


# ── can_handle ────────────────────────────────────────────────────────────────

class TestCanHandle:
    def test_accepts_openapi3_json(self):
        assert PARSER.can_handle(json.dumps(MINIMAL_OPENAPI3), "api.json")

    def test_accepts_swagger2_json(self):
        assert PARSER.can_handle(json.dumps(SWAGGER2_SPEC), "api.json")

    def test_accepts_openapi3_yaml(self):
        assert PARSER.can_handle(OPENAPI3_YAML, "api.yaml")

    def test_rejects_mockingbird_txt(self):
        assert not PARSER.can_handle("--- MOCKINGBIRD v1.0 ---\n", "file.txt")

    def test_rejects_plain_json(self):
        assert not PARSER.can_handle('{"key": "value"}', "data.json")

    def test_rejects_invalid_yaml(self):
        assert not PARSER.can_handle("this is: not: valid: yaml: {{{{", "api.yaml")


# ── validate ──────────────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_openapi3(self):
        result = PARSER.validate(json.dumps(MINIMAL_OPENAPI3))
        assert result.valid
        assert "1 endpoint" in result.summary
        assert "OpenAPI 3.0.3" in result.summary

    def test_valid_swagger2(self):
        result = PARSER.validate(json.dumps(SWAGGER2_SPEC))
        assert result.valid
        assert "Swagger 2.0" in result.summary

    def test_valid_yaml(self):
        result = PARSER.validate(OPENAPI3_YAML)
        assert result.valid

    def test_counts_multiple_endpoints(self):
        data = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/a": {"get": {"summary": "A", "responses": {"200": {"description": "OK"}}}},
                "/b": {"post": {"summary": "B", "responses": {"201": {"description": "Created"}}}},
            },
        }
        result = PARSER.validate(json.dumps(data))
        assert result.valid
        assert "2 endpoint" in result.summary

    def test_invalid_missing_paths(self):
        data = {"openapi": "3.0.3", "info": {"title": "T", "version": "1"}}
        result = PARSER.validate(json.dumps(data))
        assert not result.valid
        assert any("paths" in e.message for e in result.errors)

    def test_invalid_no_http_operations(self):
        data = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {"/x": {"parameters": []}},
        }
        result = PARSER.validate(json.dumps(data))
        assert not result.valid

    def test_invalid_missing_version_field(self):
        result = PARSER.validate('{"paths": {"/x": {}}}')
        assert not result.valid

    def test_invalid_unparseable_content(self):
        result = PARSER.validate("this is plain text, not JSON or YAML")
        assert not result.valid


# ── parse ─────────────────────────────────────────────────────────────────────

class TestParse:
    def test_extracts_path_and_method(self):
        parsed = PARSER.parse(json.dumps(MINIMAL_OPENAPI3), "api.json")
        assert len(parsed.stubs) == 1
        stub = parsed.stubs[0]
        assert stub.request.method.value == "GET"
        assert stub.request.url == "/customers/{id}"

    def test_stub_name_from_summary(self):
        parsed = PARSER.parse(json.dumps(MINIMAL_OPENAPI3), "api.json")
        assert parsed.stubs[0].name == "Get Customer"

    def test_extracts_inline_example_as_body(self):
        parsed = PARSER.parse(json.dumps(MINIMAL_OPENAPI3), "api.json")
        stub = parsed.stubs[0]
        assert stub.scenarios[0].status == 200
        assert "John Smith" in stub.scenarios[0].body

    def test_content_type_header_set_from_content_key(self):
        parsed = PARSER.parse(json.dumps(MINIMAL_OPENAPI3), "api.json")
        assert parsed.stubs[0].scenarios[0].response_headers.get("Content-Type") == "application/json"

    def test_2xx_is_first_scenario_for_multi_response(self):
        parsed = PARSER.parse(json.dumps(OPENAPI3_MULTI_RESPONSE), "api.json")
        assert parsed.stubs[0].scenarios[0].status == 200

    def test_non_2xx_placed_after_2xx(self):
        parsed = PARSER.parse(json.dumps(OPENAPI3_MULTI_RESPONSE), "api.json")
        statuses = [s.status for s in parsed.stubs[0].scenarios]
        assert statuses[0] == 200
        assert set(statuses[1:]) == {400, 402}

    def test_all_scenarios_use_always_match(self):
        parsed = PARSER.parse(json.dumps(OPENAPI3_MULTI_RESPONSE), "api.json")
        for scenario in parsed.stubs[0].scenarios:
            assert scenario.match.type.value == "always"

    def test_swagger2_extracts_example_body(self):
        parsed = PARSER.parse(json.dumps(SWAGGER2_SPEC), "api.json")
        stub = parsed.stubs[0]
        assert stub.request.url == "/accounts/{id}"
        assert "acc-001" in stub.scenarios[0].body

    def test_generates_body_from_schema_when_no_example(self):
        data = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/items": {
                    "get": {
                        "summary": "List",
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "string"},
                                                "count": {"type": "integer"},
                                            },
                                        }
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }
        parsed = PARSER.parse(json.dumps(data), "api.json")
        body = json.loads(parsed.stubs[0].scenarios[0].body)
        assert "id" in body
        assert "count" in body

    def test_parses_yaml_input(self):
        parsed = PARSER.parse(OPENAPI3_YAML, "api.yaml")
        assert len(parsed.stubs) == 1
        assert parsed.stubs[0].request.url == "/items"
        assert parsed.stubs[0].scenarios[0].status == 200

    def test_multiple_paths_produce_multiple_stubs(self):
        data = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/a": {"get": {"summary": "A", "responses": {"200": {"description": "OK"}}}},
                "/b": {"post": {"summary": "B", "responses": {"201": {"description": "Created"}}}},
                "/c": {"delete": {"summary": "C", "responses": {"204": {"description": "No content"}}}},
            },
        }
        parsed = PARSER.parse(json.dumps(data), "api.json")
        assert len(parsed.stubs) == 3

    def test_resolves_ref_to_component_schema(self):
        data = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {
                "schemas": {
                    "Customer": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    }
                }
            },
            "paths": {
                "/customers/{id}": {
                    "get": {
                        "summary": "Get",
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Customer"}
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }
        parsed = PARSER.parse(json.dumps(data), "api.json")
        body = json.loads(parsed.stubs[0].scenarios[0].body)
        assert "id" in body
        assert "name" in body

    def test_uses_named_example_when_no_inline_example(self):
        data = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/orders": {
                    "get": {
                        "summary": "Get Orders",
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "examples": {
                                            "sample": {
                                                "value": {"orderId": "ord-001", "total": 99.99}
                                            }
                                        }
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }
        parsed = PARSER.parse(json.dumps(data), "api.json")
        body = json.loads(parsed.stubs[0].scenarios[0].body)
        assert body["orderId"] == "ord-001"
