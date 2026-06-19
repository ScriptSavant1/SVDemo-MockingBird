"""Sprint 22 — Kafka stub generator tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from parser_worker.generator.kafka_springboot import generate_kafka_project
from parser_worker.models_kafka import KafkaStubType, ParsedKafkaFile, ParsedKafkaStub


# ── helpers ───────────────────────────────────────────────────────────────────

def _consumer_reply(**overrides) -> ParsedKafkaStub:
    return ParsedKafkaStub(
        name=overrides.get("name", "payment-reply"),
        type=KafkaStubType.CONSUMER_REPLY,
        consume_topic=overrides.get("consume_topic", "payments.requests"),
        produce_topic=overrides.get("produce_topic", "payments.responses"),
        consumer_group=overrides.get("consumer_group", "payment-group"),
        response_body=overrides.get("response_body", '{"status": "PROCESSED"}'),
        response_headers=overrides.get("response_headers", {"X-Event-Type": "PaymentResponse"}),
        delay_ms=overrides.get("delay_ms", 100),
    )


def _producer(**overrides) -> ParsedKafkaStub:
    return ParsedKafkaStub(
        name=overrides.get("name", "account-event"),
        type=KafkaStubType.PRODUCER,
        produce_topic=overrides.get("produce_topic", "accounts.events"),
        response_body=overrides.get("response_body", '{"eventType": "UPDATE"}'),
    )


def _file(stubs: list[ParsedKafkaStub]) -> ParsedKafkaFile:
    return ParsedKafkaFile(source_file="test.kafka.json", stubs=stubs)


@pytest.fixture
def out() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ── pom.xml ───────────────────────────────────────────────────────────────────

def test_pom_contains_project_id(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out, project_id="payments", project_name="Payments API")
    pom = (out / "pom.xml").read_text()
    assert "payments-stub" in pom


def test_pom_contains_project_name(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out, project_name="My Kafka Stub")
    pom = (out / "pom.xml").read_text()
    assert "My Kafka Stub" in pom


def test_pom_contains_spring_kafka_dependency(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out)
    pom = (out / "pom.xml").read_text()
    assert "spring-kafka" in pom


def test_pom_id_auto_derived_from_stub_name(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply(name="account-updates")]), out)
    pom = (out / "pom.xml").read_text()
    assert "account-updates-stub" in pom


# ── stubs.json ────────────────────────────────────────────────────────────────

def test_stubs_json_consumer_reply_fields(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out)
    data = json.loads((out / "src/main/resources/stubs.json").read_text())
    assert len(data["stubs"]) == 1
    stub = data["stubs"][0]
    assert stub["name"] == "payment-reply"
    assert stub["type"] == "CONSUMER_REPLY"
    assert stub["consumeTopic"] == "payments.requests"
    assert stub["produceTopic"] == "payments.responses"
    assert stub["delayMs"] == 100
    assert stub["responseHeaders"] == {"X-Event-Type": "PaymentResponse"}


def test_stubs_json_producer_has_empty_consume_topic(out: Path) -> None:
    generate_kafka_project(_file([_producer()]), out)
    data = json.loads((out / "src/main/resources/stubs.json").read_text())
    stub = data["stubs"][0]
    assert stub["type"] == "PRODUCER"
    assert stub["consumeTopic"] == ""


def test_stubs_json_multiple_stubs(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply(), _producer()]), out)
    data = json.loads((out / "src/main/resources/stubs.json").read_text())
    assert len(data["stubs"]) == 2


# ── application.yml ───────────────────────────────────────────────────────────

def test_application_yml_contains_bootstrap_servers_config(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out)
    yml = (out / "src/main/resources/application.yml").read_text()
    assert "KAFKA_BOOTSTRAP_SERVERS" in yml
    assert "spring.kafka" in yml or "bootstrap-servers" in yml


# ── Java source files ─────────────────────────────────────────────────────────

def test_java_source_files_generated(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out)
    java_dir = out / "src/main/java/com/mockingbird/stubs/kafka"
    for name in ["KafkaStubApplication.java", "StubDefinition.java",
                 "StubRegistry.java", "KafkaStubConsumer.java", "StubController.java"]:
        assert (java_dir / name).exists(), f"Missing: {name}"


# ── infrastructure files ──────────────────────────────────────────────────────

def test_dockerfile_generated(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out, project_id="payments")
    dockerfile = (out / "Dockerfile").read_text()
    assert "payments-stub" in dockerfile
    assert "java" in dockerfile.lower()


def test_settings_xml_generated(out: Path) -> None:
    generate_kafka_project(_file([_consumer_reply()]), out)
    settings = (out / "settings.xml").read_text()
    assert "artifactory-mirror" in settings
