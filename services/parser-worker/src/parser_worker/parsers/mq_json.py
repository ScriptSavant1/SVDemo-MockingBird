"""Parser for the Mockingbird IBM MQ stub spec format (.mq.json).

Format marker: { "_mockingbird_mq": "1.0", "stubs": [...] }

Each stub is either:
  consumer-reply  — listens on consume_queue, puts responseBody onto produce_queue
  producer        — HTTP POST /api/stubs/{name}/trigger fires responseBody onto produce_queue
"""
from __future__ import annotations

import json

from ..models import ValidationError, ValidationResult
from ..models_mq import MQStubType, ParsedMQFile, ParsedMQStub

_MARKER = "_mockingbird_mq"
_VALID_TYPES = {t.value for t in MQStubType}


class MQJsonParser:

    @property
    def format_name(self) -> str:
        return "mq-json"

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
            if not stub.get("produce_queue"):
                errors.append(ValidationError(
                    field=f"{prefix}.produce_queue", message="produce_queue is required"
                ))
            if stub_type == MQStubType.CONSUMER_REPLY.value and not stub.get("consume_queue"):
                errors.append(ValidationError(
                    field=f"{prefix}.consume_queue",
                    message="consume_queue is required for consumer-reply stubs",
                ))

        n = len(stubs)
        return ValidationResult(
            valid=len(errors) == 0,
            format_detected=self.format_name,
            errors=errors,
            summary=f"{n} MQ stub{'s' if n != 1 else ''}",
        )

    def parse(self, content: str, source_file: str) -> ParsedMQFile:
        data = json.loads(content)
        stubs: list[ParsedMQStub] = []
        for stub in data.get("stubs", []):
            stubs.append(ParsedMQStub(
                name=stub["name"],
                description=stub.get("description", ""),
                type=MQStubType(stub["type"]),
                consume_queue=stub.get("consume_queue"),
                produce_queue=stub["produce_queue"],
                response_body=stub.get("response_body", "{}"),
                response_properties=stub.get("response_properties", {}),
                delay_ms=stub.get("delay_ms", 0),
            ))
        return ParsedMQFile(source_file=source_file, stubs=stubs)

    def validate_and_parse(
        self, content: str, source_file: str
    ) -> tuple[ValidationResult, ParsedMQFile | None]:
        result = self.validate(content)
        if not result.valid:
            return result, None
        return result, self.parse(content, source_file)
