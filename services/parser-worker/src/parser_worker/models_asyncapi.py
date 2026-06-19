"""Pydantic models for AsyncAPI stub specs (Sprint 23)."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ChannelOperation(str, Enum):
    SUBSCRIBE = "subscribe"
    """Stub produces messages onto this channel (consumers subscribe to our output)."""

    PUBLISH = "publish"
    """Stub consumes messages from this channel (producers publish to us)."""


class MessageFormat(str, Enum):
    JSON = "json"
    AVRO = "avro"
    BINARY = "binary"


class ParsedAsyncApiChannel(BaseModel):
    name: str
    description: str = ""
    operation: ChannelOperation
    message_name: str = ""
    content_type: str = "application/json"
    message_format: MessageFormat = MessageFormat.JSON
    example_payload: Optional[str] = None


class ParsedAsyncApiFile(BaseModel):
    format: str = "asyncapi"
    source_file: str
    title: str
    version: str
    """Value from info.version — the API version, not the AsyncAPI spec version."""

    asyncapi_version: str
    """The AsyncAPI spec version, e.g. '2.6.0' or '3.0.0'."""

    channels: list[ParsedAsyncApiChannel]
    has_avro: bool = False
    schema_registry_url: Optional[str] = None
