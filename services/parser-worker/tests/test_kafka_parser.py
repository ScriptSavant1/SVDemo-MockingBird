"""Sprint 22 — KafkaJsonParser tests."""
from __future__ import annotations

import json

import pytest

from parser_worker.parsers.kafka_json import KafkaJsonParser
from parser_worker.models_kafka import KafkaStubType

# ── fixtures ──────────────────────────────────────────────────────────────────

CONSUMER_REPLY_DOC = {
    "_mockingbird_kafka": "1.0",
    "stubs": [
        {
            "name": "payment-reply",
            "type": "consumer-reply",
            "consume_topic": "payments.requests",
            "produce_topic": "payments.responses",
            "consumer_group": "payment-stub-group",
            "response_body": '{"status": "PROCESSED", "paymentId": "PAY-001"}',
            "response_headers": {"X-Event-Type": "PaymentResponse"},
            "delay_ms": 50,
        }
    ],
}

PRODUCER_DOC = {
    "_mockingbird_kafka": "1.0",
    "stubs": [
        {
            "name": "account-event",
            "type": "producer",
            "produce_topic": "accounts.events",
            "response_body": '{"eventType": "ACCOUNT_UPDATED", "accountId": "ACC-001"}',
        }
    ],
}

MULTI_STUB_DOC = {
    "_mockingbird_kafka": "1.0",
    "stubs": [
        {
            "name": "payment-reply",
            "type": "consumer-reply",
            "consume_topic": "payments.in",
            "produce_topic": "payments.out",
        },
        {
            "name": "account-trigger",
            "type": "producer",
            "produce_topic": "accounts.events",
        },
    ],
}


@pytest.fixture
def parser() -> KafkaJsonParser:
    return KafkaJsonParser()


# ── can_handle ────────────────────────────────────────────────────────────────

def test_can_handle_valid_kafka_doc(parser: KafkaJsonParser) -> None:
    assert parser.can_handle(json.dumps(CONSUMER_REPLY_DOC), "stubs.kafka.json") is True


def test_can_handle_rejects_wiremock_format(parser: KafkaJsonParser) -> None:
    wiremock = {"_mockingbird": "1.0", "request": {"method": "GET", "url": "/health"}}
    assert parser.can_handle(json.dumps(wiremock), "stubs.json") is False


def test_can_handle_rejects_invalid_json(parser: KafkaJsonParser) -> None:
    assert parser.can_handle("not { valid json", "stubs.kafka.json") is False


def test_can_handle_rejects_wrong_version(parser: KafkaJsonParser) -> None:
    doc = {**CONSUMER_REPLY_DOC, "_mockingbird_kafka": "2.0"}
    assert parser.can_handle(json.dumps(doc), "x.kafka.json") is False


# ── validate ──────────────────────────────────────────────────────────────────

def test_validate_consumer_reply_is_valid(parser: KafkaJsonParser) -> None:
    result = parser.validate(json.dumps(CONSUMER_REPLY_DOC))
    assert result.valid is True
    assert "1 Kafka stub" in result.summary


def test_validate_producer_is_valid(parser: KafkaJsonParser) -> None:
    result = parser.validate(json.dumps(PRODUCER_DOC))
    assert result.valid is True


def test_validate_multi_stub_summary(parser: KafkaJsonParser) -> None:
    result = parser.validate(json.dumps(MULTI_STUB_DOC))
    assert result.valid is True
    assert "2 Kafka stubs" in result.summary


def test_validate_empty_stubs_list_is_invalid(parser: KafkaJsonParser) -> None:
    doc = {"_mockingbird_kafka": "1.0", "stubs": []}
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("At least one stub" in e.message for e in result.errors)


def test_validate_consumer_reply_missing_consume_topic(parser: KafkaJsonParser) -> None:
    doc = {
        "_mockingbird_kafka": "1.0",
        "stubs": [{"name": "x", "type": "consumer-reply", "produce_topic": "out.topic"}],
    }
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("consume_topic" in (e.field or "") for e in result.errors)


def test_validate_missing_produce_topic_is_invalid(parser: KafkaJsonParser) -> None:
    doc = {
        "_mockingbird_kafka": "1.0",
        "stubs": [{"name": "x", "type": "producer"}],
    }
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("produce_topic" in (e.field or "") for e in result.errors)


def test_validate_unknown_stub_type_is_invalid(parser: KafkaJsonParser) -> None:
    doc = {
        "_mockingbird_kafka": "1.0",
        "stubs": [{"name": "x", "type": "fire-and-forget", "produce_topic": "t"}],
    }
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("type" in (e.field or "") for e in result.errors)


# ── parse ─────────────────────────────────────────────────────────────────────

def test_parse_consumer_reply_fields(parser: KafkaJsonParser) -> None:
    result, parsed = parser.validate_and_parse(json.dumps(CONSUMER_REPLY_DOC), "stubs.kafka.json")
    assert result.valid is True
    assert parsed is not None
    stub = parsed.stubs[0]
    assert stub.name == "payment-reply"
    assert stub.type == KafkaStubType.CONSUMER_REPLY
    assert stub.consume_topic == "payments.requests"
    assert stub.produce_topic == "payments.responses"
    assert stub.consumer_group == "payment-stub-group"
    assert stub.delay_ms == 50
    assert stub.response_headers == {"X-Event-Type": "PaymentResponse"}


def test_parse_producer_stub_has_no_consume_topic(parser: KafkaJsonParser) -> None:
    result, parsed = parser.validate_and_parse(json.dumps(PRODUCER_DOC), "stubs.kafka.json")
    assert result.valid is True
    assert parsed is not None
    stub = parsed.stubs[0]
    assert stub.type == KafkaStubType.PRODUCER
    assert stub.consume_topic is None
    assert stub.produce_topic == "accounts.events"


def test_parse_defaults_applied(parser: KafkaJsonParser) -> None:
    doc = {
        "_mockingbird_kafka": "1.0",
        "stubs": [{"name": "minimal", "type": "producer", "produce_topic": "events.out"}],
    }
    _, parsed = parser.validate_and_parse(json.dumps(doc), "minimal.kafka.json")
    assert parsed is not None
    stub = parsed.stubs[0]
    assert stub.consumer_group == "mockingbird-stub-group"
    assert stub.delay_ms == 0
    assert stub.response_body == "{}"
    assert stub.response_headers == {}


def test_parse_multi_stub_doc(parser: KafkaJsonParser) -> None:
    _, parsed = parser.validate_and_parse(json.dumps(MULTI_STUB_DOC), "multi.kafka.json")
    assert parsed is not None
    assert len(parsed.stubs) == 2
    assert parsed.stubs[0].type == KafkaStubType.CONSUMER_REPLY
    assert parsed.stubs[1].type == KafkaStubType.PRODUCER


def test_validate_and_parse_returns_none_on_invalid(parser: KafkaJsonParser) -> None:
    doc = {"_mockingbird_kafka": "1.0", "stubs": []}
    result, parsed = parser.validate_and_parse(json.dumps(doc), "bad.kafka.json")
    assert result.valid is False
    assert parsed is None
