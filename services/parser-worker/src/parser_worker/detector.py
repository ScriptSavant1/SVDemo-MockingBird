"""Auto-detects which parser to use for a given file."""
from __future__ import annotations

from pathlib import Path

from .parsers import (
    BaseParser, JsonLevel3Parser, OpenApiParser, PostmanParser,
    SoapTxtParser, StatefulTxtParser, TxtLevel1Parser, TxtLevel2Parser,
)

_PARSERS: list[BaseParser] = [
    JsonLevel3Parser(),    # Mockingbird native JSON — checked before generic OpenAPI
    PostmanParser(),       # Postman v2.1 collections
    OpenApiParser(),       # OpenAPI 3.x / Swagger 2.0 (JSON or YAML)
    SoapTxtParser(),       # SOAP: "--- MOCKINGBIRD v1.0 SOAP ---"
    StatefulTxtParser(),   # Stateful: "--- MOCKINGBIRD v1.0 STATEFUL ---"
    TxtLevel2Parser(),     # TXT multi-scenario (SCENARIO blocks)
    TxtLevel1Parser(),     # TXT single-response (RESPONSE block)
]


def detect_parser(content: str, filename: str) -> BaseParser | None:
    """Return the first parser that can handle this content, or None."""
    for parser in _PARSERS:
        if parser.can_handle(content, filename):
            return parser
    return None


def detect_and_parse(file_path: Path) -> tuple[BaseParser | None, object, object]:
    """Read a file, detect its format, validate, and parse.

    Returns (parser, validation_result, parsed_file_or_None).
    If format cannot be detected, parser is None and validation_result has valid=False.
    """
    from .models import ValidationError, ValidationResult

    content = file_path.read_text(encoding="utf-8")
    parser = detect_parser(content, file_path.name)

    if parser is None:
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(
                message=(
                    "File format not recognised. "
                    "Expected '--- MOCKINGBIRD v1.0 ---' at top of file (TXT formats) "
                    "or a JSON object with '_mockingbird: 1.0' (JSON format)."
                )
            )],
        )
        return None, result, None

    validation_result, parsed_file = parser.validate_and_parse(content, str(file_path))
    return parser, validation_result, parsed_file
