"""Parser for AsyncAPI 2.x / 3.x specs (YAML or JSON).

Detection: top-level "asyncapi" key with a version string starting "2." or "3.".

AsyncAPI 2.x channel structure:
  channels:
    payment/processed:
      subscribe:          # stub produces to this topic
        message:
          name: PaymentProcessed
          contentType: application/json

Avro is detected when any message contentType contains "avro".
Schema registry URL is extracted from x-schemaRegistry or
components.x-schemaRegistry extensions.
"""
from __future__ import annotations

import json
from typing import Any

import yaml

from ..models import ValidationError, ValidationResult
from ..models_asyncapi import (
    ChannelOperation,
    MessageFormat,
    ParsedAsyncApiChannel,
    ParsedAsyncApiFile,
)

_AVRO_CONTENT_TYPES = {
    "application/vnd.apache.avro+json",
    "application/vnd.apache.avro",
    "avro/binary",
}


class AsyncApiParser:

    @property
    def format_name(self) -> str:
        return "asyncapi"

    def can_handle(self, content: str, filename: str) -> bool:
        try:
            data = self._load(content)
            version = str(data.get("asyncapi", ""))
            return bool(version) and (version.startswith("2.") or version.startswith("3."))
        except Exception:
            return False

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []

        try:
            data = self._load(content)
        except Exception as exc:
            return ValidationResult(
                valid=False,
                format_detected=self.format_name,
                errors=[ValidationError(message=f"Cannot parse spec: {exc}")],
            )

        version = str(data.get("asyncapi", ""))
        if not version:
            errors.append(ValidationError(field="asyncapi", message="asyncapi version is required"))
        elif not (version.startswith("2.") or version.startswith("3.")):
            errors.append(ValidationError(
                field="asyncapi",
                message=f"Unsupported AsyncAPI version '{version}' — only 2.x and 3.x are supported",
            ))

        info = data.get("info", {})
        if not info.get("title"):
            errors.append(ValidationError(field="info.title", message="info.title is required"))
        if not info.get("version"):
            errors.append(ValidationError(field="info.version", message="info.version is required"))

        channels = data.get("channels", {})
        if not channels:
            errors.append(ValidationError(field="channels", message="At least one channel is required"))

        n = len(channels) if isinstance(channels, dict) else 0
        return ValidationResult(
            valid=len(errors) == 0,
            format_detected=self.format_name,
            errors=errors,
            summary=f"{n} AsyncAPI channel{'s' if n != 1 else ''}",
        )

    def parse(self, content: str, source_file: str) -> ParsedAsyncApiFile:
        data = self._load(content)

        info = data.get("info", {})
        asyncapi_version = str(data.get("asyncapi", "2.0.0"))
        title = info.get("title", "")
        version = info.get("version", "")
        raw_channels = data.get("channels", {})

        channels: list[ParsedAsyncApiChannel] = []
        has_avro = False

        for name, chan_def in raw_channels.items():
            if not isinstance(chan_def, dict):
                continue

            chan = self._parse_channel_2x(name, chan_def)
            if chan.message_format == MessageFormat.AVRO:
                has_avro = True
            channels.append(chan)

        schema_registry_url = (
            data.get("x-schemaRegistry")
            or data.get("x-schema-registry-url")
            or (data.get("components") or {}).get("x-schemaRegistry")
        )

        return ParsedAsyncApiFile(
            source_file=source_file,
            title=title,
            version=version,
            asyncapi_version=asyncapi_version,
            channels=channels,
            has_avro=has_avro,
            schema_registry_url=schema_registry_url,
        )

    def validate_and_parse(
        self, content: str, source_file: str
    ) -> tuple[ValidationResult, ParsedAsyncApiFile | None]:
        result = self.validate(content)
        if not result.valid:
            return result, None
        return result, self.parse(content, source_file)

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load(content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return yaml.safe_load(content) or {}

    @staticmethod
    def _parse_channel_2x(name: str, chan_def: dict) -> ParsedAsyncApiChannel:
        description = chan_def.get("description", "")

        # Determine operation: subscribe = stub produces, publish = stub consumes
        if "subscribe" in chan_def:
            operation = ChannelOperation.SUBSCRIBE
            msg_def = (chan_def.get("subscribe") or {}).get("message", {})
        else:
            operation = ChannelOperation.PUBLISH
            msg_def = (chan_def.get("publish") or {}).get("message", {})

        message_name = msg_def.get("name", "")
        content_type = (
            msg_def.get("contentType")
            or chan_def.get("subscribe", {}).get("message", {}).get("contentType", "application/json")
            if "subscribe" in chan_def
            else msg_def.get("contentType", "application/json")
        )

        msg_format = MessageFormat.JSON
        if any(ct in content_type.lower() for ct in ("avro", "vnd.apache")):
            msg_format = MessageFormat.AVRO

        # Extract a single example payload if available
        example_payload: str | None = None
        examples = msg_def.get("examples", [])
        if examples and isinstance(examples, list):
            payload = examples[0].get("payload")
            if payload is not None:
                example_payload = json.dumps(payload) if not isinstance(payload, str) else payload

        return ParsedAsyncApiChannel(
            name=name,
            description=description,
            operation=operation,
            message_name=message_name,
            content_type=content_type,
            message_format=msg_format,
            example_payload=example_payload,
        )
