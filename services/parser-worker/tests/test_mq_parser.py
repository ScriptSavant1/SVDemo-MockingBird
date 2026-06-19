"""Sprint 24 — MQJsonParser tests."""
from __future__ import annotations

import json

import pytest

from parser_worker.parsers.mq_json import MQJsonParser
from parser_worker.models_mq import MQStubType

# ── fixtures ──────────────────────────────────────────────────────────────────

CONSUMER_REPLY_DOC = {
    "_mockingbird_mq": "1.0",
    "stubs": [
        {
            "name": "payment-reply",
            "type": "consumer-reply",
            "consume_queue": "PAYMENT.REQUEST.QUEUE",
            "produce_queue": "PAYMENT.REPLY.QUEUE",
            "response_body": '{"status": "PROCESSED", "paymentId": "PAY-001"}',
            "response_properties": {"JMSType": "PaymentResponse"},
            "delay_ms": 100,
        }
    ],
}

PRODUCER_DOC = {
    "_mockingbird_mq": "1.0",
    "stubs": [
        {
            "name": "account-event",
            "type": "producer",
            "produce_queue": "ACCOUNT.EVENT.QUEUE",
            "response_body": '{"eventType": "ACCOUNT_UPDATED"}',
        }
    ],
}

MULTI_STUB_DOC = {
    "_mockingbird_mq": "1.0",
    "stubs": [
        {
            "name": "payment-reply",
            "type": "consumer-reply",
            "consume_queue": "PAYMENT.IN",
            "produce_queue": "PAYMENT.OUT",
        },
        {
            "name": "account-trigger",
            "type": "producer",
            "produce_queue": "ACCOUNT.EVENTS",
        },
    ],
}


@pytest.fixture
def parser() -> MQJsonParser:
    return MQJsonParser()


# ── can_handle ────────────────────────────────────────────────────────────────

def test_can_handle_valid_mq_doc(parser: MQJsonParser) -> None:
    assert parser.can_handle(json.dumps(CONSUMER_REPLY_DOC), "stubs.mq.json") is True


def test_can_handle_rejects_kafka_format(parser: MQJsonParser) -> None:
    kafka = {"_mockingbird_kafka": "1.0", "stubs": []}
    assert parser.can_handle(json.dumps(kafka), "stubs.kafka.json") is False


def test_can_handle_rejects_wiremock_format(parser: MQJsonParser) -> None:
    wiremock = {"_mockingbird": "1.0", "request": {"method": "GET"}}
    assert parser.can_handle(json.dumps(wiremock), "stubs.json") is False


def test_can_handle_rejects_invalid_json(parser: MQJsonParser) -> None:
    assert parser.can_handle("not { valid json", "stubs.mq.json") is False


def test_can_handle_rejects_wrong_version(parser: MQJsonParser) -> None:
    doc = {**CONSUMER_REPLY_DOC, "_mockingbird_mq": "2.0"}
    assert parser.can_handle(json.dumps(doc), "x.mq.json") is False


# ── validate ──────────────────────────────────────────────────────────────────

def test_validate_consumer_reply_is_valid(parser: MQJsonParser) -> None:
    result = parser.validate(json.dumps(CONSUMER_REPLY_DOC))
    assert result.valid is True
    assert "1 MQ stub" in result.summary


def test_validate_producer_is_valid(parser: MQJsonParser) -> None:
    result = parser.validate(json.dumps(PRODUCER_DOC))
    assert result.valid is True


def test_validate_multi_stub_summary(parser: MQJsonParser) -> None:
    result = parser.validate(json.dumps(MULTI_STUB_DOC))
    assert result.valid is True
    assert "2 MQ stubs" in result.summary


def test_validate_empty_stubs_list_is_invalid(parser: MQJsonParser) -> None:
    doc = {"_mockingbird_mq": "1.0", "stubs": []}
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("At least one stub" in e.message for e in result.errors)


def test_validate_consumer_reply_missing_consume_queue(parser: MQJsonParser) -> None:
    doc = {
        "_mockingbird_mq": "1.0",
        "stubs": [{"name": "x", "type": "consumer-reply", "produce_queue": "OUT.QUEUE"}],
    }
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("consume_queue" in (e.field or "") for e in result.errors)


def test_validate_missing_produce_queue_is_invalid(parser: MQJsonParser) -> None:
    doc = {
        "_mockingbird_mq": "1.0",
        "stubs": [{"name": "x", "type": "producer"}],
    }
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("produce_queue" in (e.field or "") for e in result.errors)


def test_validate_unknown_stub_type_is_invalid(parser: MQJsonParser) -> None:
    doc = {
        "_mockingbird_mq": "1.0",
        "stubs": [{"name": "x", "type": "broadcast", "produce_queue": "Q"}],
    }
    result = parser.validate(json.dumps(doc))
    assert result.valid is False
    assert any("type" in (e.field or "") for e in result.errors)


# ── parse ─────────────────────────────────────────────────────────────────────

def test_parse_consumer_reply_fields(parser: MQJsonParser) -> None:
    result, parsed = parser.validate_and_parse(json.dumps(CONSUMER_REPLY_DOC), "stubs.mq.json")
    assert result.valid is True
    assert parsed is not None
    stub = parsed.stubs[0]
    assert stub.name == "payment-reply"
    assert stub.type == MQStubType.CONSUMER_REPLY
    assert stub.consume_queue == "PAYMENT.REQUEST.QUEUE"
    assert stub.produce_queue == "PAYMENT.REPLY.QUEUE"
    assert stub.delay_ms == 100
    assert stub.response_properties == {"JMSType": "PaymentResponse"}


def test_parse_producer_stub_has_no_consume_queue(parser: MQJsonParser) -> None:
    result, parsed = parser.validate_and_parse(json.dumps(PRODUCER_DOC), "stubs.mq.json")
    assert result.valid is True
    assert parsed is not None
    stub = parsed.stubs[0]
    assert stub.type == MQStubType.PRODUCER
    assert stub.consume_queue is None
    assert stub.produce_queue == "ACCOUNT.EVENT.QUEUE"


def test_parse_defaults_applied(parser: MQJsonParser) -> None:
    doc = {
        "_mockingbird_mq": "1.0",
        "stubs": [{"name": "minimal", "type": "producer", "produce_queue": "EVENTS.OUT"}],
    }
    _, parsed = parser.validate_and_parse(json.dumps(doc), "minimal.mq.json")
    assert parsed is not None
    stub = parsed.stubs[0]
    assert stub.delay_ms == 0
    assert stub.response_body == "{}"
    assert stub.response_properties == {}


def test_parse_multi_stub_doc(parser: MQJsonParser) -> None:
    _, parsed = parser.validate_and_parse(json.dumps(MULTI_STUB_DOC), "multi.mq.json")
    assert parsed is not None
    assert len(parsed.stubs) == 2
    assert parsed.stubs[0].type == MQStubType.CONSUMER_REPLY
    assert parsed.stubs[1].type == MQStubType.PRODUCER


def test_validate_and_parse_returns_none_on_invalid(parser: MQJsonParser) -> None:
    doc = {"_mockingbird_mq": "1.0", "stubs": []}
    result, parsed = parser.validate_and_parse(json.dumps(doc), "bad.mq.json")
    assert result.valid is False
    assert parsed is None
