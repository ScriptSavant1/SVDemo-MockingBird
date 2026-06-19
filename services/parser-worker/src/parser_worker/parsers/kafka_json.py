"""Parser for the Mockingbird Kafka stub spec format (.kafka.json).

Format marker: { "_mockingbird_kafka": "1.0", "stubs": [...] }

Each stub is either:
  consumer-reply  — listens on consume_topic, sends responseBody to produce_topic
  producer        — HTTP trigger fires responseBody onto produce_topic
"""
from __future__ import annotations

import json

from ..models import ValidationError, ValidationResult
from ..models_kafka import KafkaStubType, ParsedKafkaFile, ParsedKafkaStub

_MARKER = "_mockingbird_kafka"
_VALID_TYPES = {t.value for t in KafkaStubType}


class KafkaJsonParser:

    @property
    def format_name(self) -> str:
        return "kafka-json"

    def can_handle(self, content: str, filename: str) -> bool:
        try:
            data = json.loads(content)
            return isinstance(data, dict) and data.get(_MARKER) == "1.0"
        except (json.JSONDecodeError, AttributeError):
            return False

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return ValidationResult(
                valid=False,
                format_detected=self.format_name,
                errors=[ValidationError(message=f"Invalid JSON: {exc}")],
            )

        if data.get(_MARKER) != "1.0":
            errors.append(ValidationError(field=_MARKER, message="Must be '1.0'"))

        stubs = data.get("stubs", [])
        if not stubs:
            errors.append(ValidationError(
                field="stubs", message="At least one stub is required"
            ))

        for i, stub in enumerate(stubs):
            prefix = f"stubs[{i}]"
            if not stub.get("name"):
                errors.append(ValidationError(
                    field=f"{prefix}.name", message="name is required"
                ))
            stub_type = stub.get("type", "")
            if stub_type not in _VALID_TYPES:
                errors.append(ValidationError(
                    field=f"{prefix}.type",
                    message=f"type must be one of {sorted(_VALID_TYPES)}",
                ))
            if not stub.get("produce_topic"):
                errors.append(ValidationError(
                    field=f"{prefix}.produce_topic", message="produce_topic is required"
                ))
            if stub_type == KafkaStubType.CONSUMER_REPLY.value and not stub.get("consume_topic"):
                errors.append(ValidationError(
                    field=f"{prefix}.consume_topic",
                    message="consume_topic is required for consumer-reply stubs",
                ))

        n = len(stubs)
        return ValidationResult(
            valid=len(errors) == 0,
            format_detected=self.format_name,
            errors=errors,
            summary=f"{n} Kafka stub{'s' if n != 1 else ''}",
        )

    def parse(self, content: str, source_file: str) -> ParsedKafkaFile:
        data = json.loads(content)
        stubs: list[ParsedKafkaStub] = []
        for stub in data.get("stubs", []):
            stubs.append(ParsedKafkaStub(
                name=stub["name"],
                description=stub.get("description", ""),
                type=KafkaStubType(stub["type"]),
                consume_topic=stub.get("consume_topic"),
                produce_topic=stub["produce_topic"],
                consumer_group=stub.get("consumer_group", "mockingbird-stub-group"),
                response_body=stub.get("response_body", "{}"),
                response_headers=stub.get("response_headers", {}),
                delay_ms=stub.get("delay_ms", 0),
            ))
        return ParsedKafkaFile(source_file=source_file, stubs=stubs)

    def validate_and_parse(
        self, content: str, source_file: str
    ) -> tuple[ValidationResult, ParsedKafkaFile | None]:
        result = self.validate(content)
        if not result.valid:
            return result, None
        return result, self.parse(content, source_file)
