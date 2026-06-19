"""Sprint 24 — IBM MQ stub generator tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from parser_worker.generator.mq_springboot import generate_mq_project
from parser_worker.models_mq import MQStubType, ParsedMQFile, ParsedMQStub


# ── helpers ───────────────────────────────────────────────────────────────────

def _consumer_reply(**overrides) -> ParsedMQStub:
    return ParsedMQStub(
        name=overrides.get("name", "payment-reply"),
        type=MQStubType.CONSUMER_REPLY,
        consume_queue=overrides.get("consume_queue", "PAYMENT.REQUEST.QUEUE"),
        produce_queue=overrides.get("produce_queue", "PAYMENT.REPLY.QUEUE"),
        response_body=overrides.get("response_body", '{"status": "PROCESSED"}'),
        response_properties=overrides.get("response_properties", {"JMSType": "PaymentResponse"}),
        delay_ms=overrides.get("delay_ms", 100),
    )


def _producer(**overrides) -> ParsedMQStub:
    return ParsedMQStub(
        name=overrides.get("name", "account-event"),
        type=MQStubType.PRODUCER,
        produce_queue=overrides.get("produce_queue", "ACCOUNT.EVENT.QUEUE"),
        response_body=overrides.get("response_body", '{"eventType": "UPDATE"}'),
    )


def _file(stubs: list[ParsedMQStub]) -> ParsedMQFile:
    return ParsedMQFile(source_file="test.mq.json", stubs=stubs)


@pytest.fixture
def out() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ── pom.xml ───────────────────────────────────────────────────────────────────

def test_pom_contains_project_id(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out, project_id="payments", project_name="Payments API")
    pom = (out / "pom.xml").read_text()
    assert "payments-stub" in pom


def test_pom_contains_project_name(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out, project_name="My MQ Stub")
    pom = (out / "pom.xml").read_text()
    assert "My MQ Stub" in pom


def test_pom_contains_ibm_mq_dependency(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out)
    pom = (out / "pom.xml").read_text()
    assert "mq-jms-spring-boot-starter" in pom


def test_pom_id_auto_derived_from_stub_name(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply(name="account-payments")]), out)
    pom = (out / "pom.xml").read_text()
    assert "account-payments-stub" in pom


# ── stubs.json ────────────────────────────────────────────────────────────────

def test_stubs_json_consumer_reply_fields(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out)
    data = json.loads((out / "src/main/resources/stubs.json").read_text())
    assert len(data["stubs"]) == 1
    stub = data["stubs"][0]
    assert stub["name"] == "payment-reply"
    assert stub["type"] == "CONSUMER_REPLY"
    assert stub["consumeQueue"] == "PAYMENT.REQUEST.QUEUE"
    assert stub["produceQueue"] == "PAYMENT.REPLY.QUEUE"
    assert stub["delayMs"] == 100
    assert stub["responseProperties"] == {"JMSType": "PaymentResponse"}


def test_stubs_json_producer_has_empty_consume_queue(out: Path) -> None:
    generate_mq_project(_file([_producer()]), out)
    data = json.loads((out / "src/main/resources/stubs.json").read_text())
    stub = data["stubs"][0]
    assert stub["type"] == "PRODUCER"
    assert stub["consumeQueue"] == ""


def test_stubs_json_multiple_stubs(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply(), _producer()]), out)
    data = json.loads((out / "src/main/resources/stubs.json").read_text())
    assert len(data["stubs"]) == 2


# ── application.yml ───────────────────────────────────────────────────────────

def test_application_yml_contains_ibm_mq_config(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out)
    yml = (out / "src/main/resources/application.yml").read_text()
    assert "ibm:" in yml
    assert "MQ_QUEUE_MANAGER" in yml
    assert "MQ_HOST" in yml


def test_application_yml_contains_virtual_threads(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out)
    yml = (out / "src/main/resources/application.yml").read_text()
    assert "virtual" in yml


# ── Java source files ─────────────────────────────────────────────────────────

def test_java_source_files_generated(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out)
    java_dir = out / "src/main/java/com/mockingbird/stubs/mq"
    for name in ["MQStubApplication.java", "StubDefinition.java",
                 "StubRegistry.java", "MQStubConsumer.java", "StubController.java"]:
        assert (java_dir / name).exists(), f"Missing: {name}"


# ── infrastructure files ──────────────────────────────────────────────────────

def test_dockerfile_generated(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out, project_id="payments")
    dockerfile = (out / "Dockerfile").read_text()
    assert "payments-stub" in dockerfile
    assert "java" in dockerfile.lower()


def test_settings_xml_generated(out: Path) -> None:
    generate_mq_project(_file([_consumer_reply()]), out)
    settings = (out / "settings.xml").read_text()
    assert "artifactory-mirror" in settings


def test_returns_output_dir(out: Path) -> None:
    result = generate_mq_project(_file([_consumer_reply()]), out)
    assert result == out
