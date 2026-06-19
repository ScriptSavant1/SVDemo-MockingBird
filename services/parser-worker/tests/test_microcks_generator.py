"""Sprint 23 — Microcks docker-compose generator tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from parser_worker.generator.microcks import generate_microcks_config
from parser_worker.models_asyncapi import (
    ChannelOperation,
    MessageFormat,
    ParsedAsyncApiChannel,
    ParsedAsyncApiFile,
)

# ── helpers ───────────────────────────────────────────────────────────────────

_RAW_SPEC = """\
asyncapi: "2.6.0"
info:
  title: Payment Events
  version: "1.0.0"
channels:
  payment/processed:
    subscribe:
      message:
        name: PaymentProcessed
"""

_AVRO_SPEC = """\
asyncapi: "2.6.0"
info:
  title: Account Events
  version: "1.0.0"
x-schemaRegistry: http://schema-registry:8081
channels:
  account/updated:
    subscribe:
      message:
        contentType: application/vnd.apache.avro+json
"""


def _parsed_file(has_avro: bool = False, schema_registry_url: str | None = None) -> ParsedAsyncApiFile:
    ch = ParsedAsyncApiChannel(
        name="payment/processed",
        operation=ChannelOperation.SUBSCRIBE,
        message_name="PaymentProcessed",
        message_format=MessageFormat.AVRO if has_avro else MessageFormat.JSON,
    )
    return ParsedAsyncApiFile(
        source_file="events.yaml",
        title="Payment Events",
        version="1.0.0",
        asyncapi_version="2.6.0",
        channels=[ch],
        has_avro=has_avro,
        schema_registry_url=schema_registry_url,
    )


@pytest.fixture
def out() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ── file presence ─────────────────────────────────────────────────────────────

def test_docker_compose_file_created(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    assert (out / "docker-compose.microcks.yml").exists()


def test_asyncapi_spec_file_written(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    written = (out / "asyncapi.yaml").read_text()
    assert written == _RAW_SPEC


def test_env_file_created(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    assert (out / ".env.microcks").exists()


def test_output_dir_created_if_absent(out: Path) -> None:
    nested = out / "sub" / "dir"
    generate_microcks_config(_parsed_file(), _RAW_SPEC, nested)
    assert nested.exists()


# ── docker-compose content ────────────────────────────────────────────────────

def test_compose_contains_microcks_image(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    content = (out / "docker-compose.microcks.yml").read_text()
    assert "microcks-uber" in content


def test_compose_contains_kafka_env_var(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    content = (out / "docker-compose.microcks.yml").read_text()
    assert "KAFKA_BOOTSTRAP_SERVERS" in content


def test_compose_contains_schema_registry_env(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    content = (out / "docker-compose.microcks.yml").read_text()
    assert "SCHEMA_REGISTRY_URL" in content


def test_compose_has_healthcheck(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    content = (out / "docker-compose.microcks.yml").read_text()
    assert "healthcheck" in content
    assert "/api/health" in content


def test_compose_exposes_port_8080(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    content = (out / "docker-compose.microcks.yml").read_text()
    assert "8080" in content


def test_project_id_in_container_name(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out, project_id="payments")
    content = (out / "docker-compose.microcks.yml").read_text()
    assert "microcks-payments" in content


def test_project_id_auto_derived_from_title(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    content = (out / "docker-compose.microcks.yml").read_text()
    assert "payment-events" in content or "microcks-payment" in content


# ── .env.microcks content ─────────────────────────────────────────────────────

def test_env_file_contains_kafka_servers(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    env = (out / ".env.microcks").read_text()
    assert "KAFKA_BOOTSTRAP_SERVERS" in env


def test_env_file_contains_schema_registry(out: Path) -> None:
    generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    env = (out / ".env.microcks").read_text()
    assert "SCHEMA_REGISTRY_URL" in env


def test_returns_output_dir(out: Path) -> None:
    result = generate_microcks_config(_parsed_file(), _RAW_SPEC, out)
    assert result == out
