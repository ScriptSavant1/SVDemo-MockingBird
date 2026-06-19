"""Sprint 23 — AsyncApiParser tests."""
from __future__ import annotations

import json

import pytest

from parser_worker.parsers.asyncapi import AsyncApiParser
from parser_worker.models_asyncapi import ChannelOperation, MessageFormat

# ── fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_YAML = """\
asyncapi: "2.6.0"
info:
  title: Payment Events API
  version: "1.0.0"
channels:
  payment/processed:
    description: Notifies when a payment completes
    subscribe:
      message:
        name: PaymentProcessed
        contentType: application/json
        examples:
          - payload:
              paymentId: PAY-001
              status: PROCESSED
"""

AVRO_YAML = """\
asyncapi: "2.6.0"
info:
  title: Account Events API
  version: "2.0.0"
x-schemaRegistry: http://schema-registry:8081
channels:
  account/updated:
    subscribe:
      message:
        name: AccountUpdated
        contentType: application/vnd.apache.avro+json
  payment/failed:
    publish:
      message:
        name: PaymentFailed
        contentType: application/json
"""

MULTI_CHANNEL_YAML = """\
asyncapi: "2.6.0"
info:
  title: Banking Events
  version: "1.0.0"
channels:
  payments.in:
    publish:
      message:
        name: PaymentRequest
  payments.out:
    subscribe:
      message:
        name: PaymentResponse
"""

OPENAPI_YAML = """\
openapi: "3.0.0"
info:
  title: REST API
  version: "1.0.0"
paths:
  /health:
    get:
      responses:
        "200":
          description: OK
"""

ASYNCAPI_JSON = json.dumps({
    "asyncapi": "2.6.0",
    "info": {"title": "Events", "version": "1.0.0"},
    "channels": {
        "events.out": {
            "subscribe": {
                "message": {"name": "DomainEvent", "contentType": "application/json"}
            }
        }
    }
})


@pytest.fixture
def parser() -> AsyncApiParser:
    return AsyncApiParser()


# ── can_handle ────────────────────────────────────────────────────────────────

def test_can_handle_asyncapi_2x_yaml(parser: AsyncApiParser) -> None:
    assert parser.can_handle(MINIMAL_YAML, "events.yaml") is True


def test_can_handle_asyncapi_2x_json(parser: AsyncApiParser) -> None:
    assert parser.can_handle(ASYNCAPI_JSON, "events.json") is True


def test_can_handle_rejects_openapi(parser: AsyncApiParser) -> None:
    assert parser.can_handle(OPENAPI_YAML, "api.yaml") is False


def test_can_handle_rejects_random_yaml(parser: AsyncApiParser) -> None:
    assert parser.can_handle("name: John\nage: 30\n", "data.yaml") is False


def test_can_handle_rejects_invalid_content(parser: AsyncApiParser) -> None:
    assert parser.can_handle("not: valid: yaml: ::", "x.yaml") is False


# ── validate ──────────────────────────────────────────────────────────────────

def test_validate_minimal_spec_is_valid(parser: AsyncApiParser) -> None:
    result = parser.validate(MINIMAL_YAML)
    assert result.valid is True
    assert "1 AsyncAPI channel" in result.summary


def test_validate_multi_channel_summary(parser: AsyncApiParser) -> None:
    result = parser.validate(MULTI_CHANNEL_YAML)
    assert result.valid is True
    assert "2 AsyncAPI channels" in result.summary


def test_validate_no_channels_invalid(parser: AsyncApiParser) -> None:
    spec = "asyncapi: '2.6.0'\ninfo:\n  title: Test\n  version: '1.0'\nchannels: {}\n"
    result = parser.validate(spec)
    assert result.valid is False
    assert any("channel" in e.message.lower() for e in result.errors)


def test_validate_missing_title_invalid(parser: AsyncApiParser) -> None:
    spec = "asyncapi: '2.6.0'\ninfo:\n  version: '1.0'\nchannels:\n  t:\n    subscribe:\n      message:\n        name: x\n"
    result = parser.validate(spec)
    assert result.valid is False
    assert any("title" in (e.field or "") for e in result.errors)


def test_validate_unsupported_version_invalid(parser: AsyncApiParser) -> None:
    spec = "asyncapi: '1.2.0'\ninfo:\n  title: T\n  version: '1.0'\nchannels:\n  t:\n    subscribe: {}\n"
    result = parser.validate(spec)
    assert result.valid is False
    assert any("1.2.0" in e.message for e in result.errors)


# ── parse ─────────────────────────────────────────────────────────────────────

def test_parse_channel_name(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(MINIMAL_YAML, "events.yaml")
    assert parsed is not None
    assert parsed.channels[0].name == "payment/processed"


def test_parse_subscribe_operation(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(MINIMAL_YAML, "events.yaml")
    assert parsed is not None
    assert parsed.channels[0].operation == ChannelOperation.SUBSCRIBE


def test_parse_publish_operation(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(MULTI_CHANNEL_YAML, "events.yaml")
    assert parsed is not None
    publish_ch = next(c for c in parsed.channels if c.name == "payments.in")
    assert publish_ch.operation == ChannelOperation.PUBLISH


def test_parse_avro_channel_format(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(AVRO_YAML, "avro.yaml")
    assert parsed is not None
    avro_ch = next(c for c in parsed.channels if c.name == "account/updated")
    assert avro_ch.message_format == MessageFormat.AVRO


def test_parse_has_avro_flag_true(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(AVRO_YAML, "avro.yaml")
    assert parsed is not None
    assert parsed.has_avro is True


def test_parse_has_avro_flag_false(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(MINIMAL_YAML, "events.yaml")
    assert parsed is not None
    assert parsed.has_avro is False


def test_parse_schema_registry_url(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(AVRO_YAML, "avro.yaml")
    assert parsed is not None
    assert parsed.schema_registry_url == "http://schema-registry:8081"


def test_parse_example_payload_extracted(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(MINIMAL_YAML, "events.yaml")
    assert parsed is not None
    ch = parsed.channels[0]
    assert ch.example_payload is not None
    assert "PAY-001" in ch.example_payload


def test_parse_asyncapi_version(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(MINIMAL_YAML, "events.yaml")
    assert parsed is not None
    assert parsed.asyncapi_version == "2.6.0"
    assert parsed.version == "1.0.0"


def test_validate_and_parse_returns_none_on_invalid(parser: AsyncApiParser) -> None:
    spec = "asyncapi: '2.6.0'\ninfo:\n  version: '1.0'\nchannels: {}\n"
    result, parsed = parser.validate_and_parse(spec, "bad.yaml")
    assert result.valid is False
    assert parsed is None


def test_parse_json_format(parser: AsyncApiParser) -> None:
    _, parsed = parser.validate_and_parse(ASYNCAPI_JSON, "events.json")
    assert parsed is not None
    assert parsed.title == "Events"
    assert len(parsed.channels) == 1
