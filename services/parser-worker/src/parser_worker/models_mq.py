"""Pydantic models for IBM MQ stub specs (Sprint 24)."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MQStubType(str, Enum):
    CONSUMER_REPLY = "consumer-reply"
    """Listen on consume_queue; send responseBody to produce_queue."""

    PRODUCER = "producer"
    """HTTP POST /api/stubs/{name}/trigger → put responseBody onto produce_queue."""


class ParsedMQStub(BaseModel):
    name: str
    description: str = ""
    type: MQStubType
    consume_queue: Optional[str] = None
    """Required for CONSUMER_REPLY; absent for PRODUCER."""
    produce_queue: str
    """Destination queue for response (CONSUMER_REPLY) or trigger message (PRODUCER)."""
    response_body: str = "{}"
    response_properties: dict[str, str] = Field(default_factory=dict)
    """JMS message properties set on outbound messages (e.g. JMSType, CorrelationID)."""
    delay_ms: int = 0


class ParsedMQFile(BaseModel):
    format: str = "mq-json"
    source_file: str
    stubs: list[ParsedMQStub]
