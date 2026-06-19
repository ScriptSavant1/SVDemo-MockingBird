"""Pydantic models for Kafka stub specs (Sprint 22)."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class KafkaStubType(str, Enum):
    CONSUMER_REPLY = "consumer-reply"
    """Consume from topic A, produce response to topic B."""

    PRODUCER = "producer"
    """HTTP POST /api/stubs/{name}/trigger → publish message to topic."""


class ParsedKafkaStub(BaseModel):
    name: str
    description: str = ""
    type: KafkaStubType
    consume_topic: Optional[str] = None
    """Required for CONSUMER_REPLY; absent for PRODUCER."""
    produce_topic: str
    consumer_group: str = "mockingbird-stub-group"
    response_body: str = "{}"
    response_headers: dict[str, str] = Field(default_factory=dict)
    delay_ms: int = 0


class ParsedKafkaFile(BaseModel):
    format: str = "kafka-json"
    source_file: str
    stubs: list[ParsedKafkaStub]
