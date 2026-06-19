"""Generates a Spring Boot + Spring Kafka stub project from a ParsedKafkaFile.

Output directory structure:
    output/
    ├── pom.xml                          Maven build (all deps from Artifactory)
    ├── settings.xml                     Artifactory mirror config
    ├── Dockerfile                       Java 21 base image (project_id filled in)
    └── src/main/
        ├── resources/
        │   ├── application.yml          Spring Kafka config (bootstrap servers via env var)
        │   └── stubs.json               Generated from parsed stubs
        └── java/com/mockingbird/stubs/kafka/
            ├── KafkaStubApplication.java
            ├── StubDefinition.java
            ├── StubRegistry.java
            ├── KafkaStubConsumer.java
            └── StubController.java
"""
from __future__ import annotations

import importlib.resources as _pkg
import json
import re
import shutil
from pathlib import Path

from ..models_kafka import KafkaStubType, ParsedKafkaFile

_SAFE_ID_RE = re.compile(r"[^\w-]")

_JAVA_FILES = [
    "KafkaStubApplication.java",
    "StubDefinition.java",
    "StubRegistry.java",
    "KafkaStubConsumer.java",
    "StubController.java",
]


def _kafka_engine_dir() -> Path:
    return Path(str(_pkg.files("parser_worker").joinpath("templates/stub-engine-kafka")))


def generate_kafka_project(
    parsed: ParsedKafkaFile,
    output_dir: Path,
    project_id: str = "",
    project_name: str = "",
) -> Path:
    """Write a complete Spring Boot + Spring Kafka stub project.

    Args:
        parsed:       ParsedKafkaFile produced by KafkaJsonParser.
        output_dir:   Root directory for the generated project.
        project_id:   Short identifier used in artifact ID (e.g., 'payment-kafka').
        project_name: Human-readable name (e.g., 'Payment Kafka Stub').

    Returns:
        output_dir (the generated project root).
    """
    if not project_id:
        project_id = _to_id(parsed.stubs[0].name if parsed.stubs else "kafka-stub")
    if not project_name:
        project_name = parsed.stubs[0].name if parsed.stubs else "Kafka Stub"

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Static files (same for every project)
    _copy("settings.xml", output_dir)

    # 2. pom.xml and Dockerfile — project_id filled in
    _write_from_template("pom.xml", output_dir, {
        "{{project_id}}": project_id,
        "{{project_name}}": project_name,
    })
    _write_from_template("Dockerfile", output_dir, {
        "{{project_id}}": project_id,
    })

    # 3. application.yml — copied unchanged (bootstrap servers come from env var at runtime)
    _copy("src/main/resources/application.yml", output_dir)

    # 4. stubs.json — generated from parsed stubs
    _write_stubs_json(output_dir, parsed)

    # 5. Java source files
    java_pkg = "src/main/java/com/mockingbird/stubs/kafka"
    (output_dir / java_pkg).mkdir(parents=True, exist_ok=True)
    for java_file in _JAVA_FILES:
        _copy(f"{java_pkg}/{java_file}", output_dir)

    return output_dir


def _copy(relative_path: str, output_dir: Path) -> None:
    src = _kafka_engine_dir() / relative_path
    if src.exists():
        dst = output_dir / relative_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _write_from_template(
    relative_path: str, output_dir: Path, replacements: dict[str, str]
) -> None:
    src = _kafka_engine_dir() / relative_path
    if not src.exists():
        return
    content = src.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    dst = output_dir / relative_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")


def _write_stubs_json(output_dir: Path, parsed: ParsedKafkaFile) -> None:
    """Serialise parsed stubs to stubs.json using the Java-side field naming convention."""
    stub_list = []
    for stub in parsed.stubs:
        java_type = (
            "CONSUMER_REPLY"
            if stub.type == KafkaStubType.CONSUMER_REPLY
            else "PRODUCER"
        )
        stub_list.append({
            "name": stub.name,
            "type": java_type,
            "consumeTopic": stub.consume_topic or "",
            "produceTopic": stub.produce_topic,
            "consumerGroup": stub.consumer_group,
            "responseBody": stub.response_body,
            "responseHeaders": stub.response_headers,
            "delayMs": stub.delay_ms,
        })
    resources_dir = output_dir / "src/main/resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    (resources_dir / "stubs.json").write_text(
        json.dumps({"stubs": stub_list}, indent=2), encoding="utf-8"
    )


def _to_id(name: str) -> str:
    return _SAFE_ID_RE.sub("-", name.lower()).strip("-")[:50]
