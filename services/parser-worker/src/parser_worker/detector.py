"""Auto-detects which parser to use for a given file.

Supports:
  Text files:  all registered BaseParser implementations (can_handle check)
  ZIP files:   CA LISA HTTP pair archives (request+response file pairs)
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from .models import ParsedFile, ValidationError, ValidationResult
from .parsers import (
    BaseParser,
    CALISAParser,
    JsonLevel3Parser,
    OpenApiParser,
    PostmanParser,
    SoapTxtParser,
    StatefulTxtParser,
    TxtLevel1Parser,
    TxtLevel2Parser,
)
from .parsers.ca_lisa_parser import parse_ca_lisa_pair

_PARSERS: list[BaseParser] = [
    JsonLevel3Parser(),    # Mockingbird native JSON — before generic OpenAPI
    PostmanParser(),       # Postman v2.1 collections
    OpenApiParser(),       # OpenAPI 3.x / Swagger 2.0 (JSON or YAML)
    SoapTxtParser(),       # SOAP: "--- MOCKINGBIRD v1.0 SOAP ---"
    StatefulTxtParser(),   # Stateful: "--- MOCKINGBIRD v1.0 STATEFUL ---"
    TxtLevel2Parser(),     # TXT multi-scenario (SCENARIO blocks)
    TxtLevel1Parser(),     # TXT single-response (RESPONSE block)
    CALISAParser(),        # CA LISA / IBM RTWS HTTP capture files
]

# Kafka, AsyncAPI, and MQ parsers return their own model types (ParsedKafkaFile etc.)
# and are registered separately in the SQS worker flow, not the upload flow.


def detect_parser(content: str, filename: str) -> BaseParser | None:
    """Return the first parser that can handle this content, or None."""
    for parser in _PARSERS:
        if parser.can_handle(content, filename):
            return parser
    return None


def detect_and_parse(file_path: Path) -> tuple[BaseParser | None, object, object]:
    """Read a file, detect its format, validate, and parse.

    Returns (parser, validation_result, parsed_file_or_None).

    For ZIP files: expects CA LISA request+response file pairs inside the archive.
    For text files: uses the registered parser list (can_handle check).
    """
    # ZIP files — CA LISA archive with request+response pairs
    if file_path.suffix.lower() == ".zip":
        return _detect_and_parse_zip(file_path)

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(message=f"Could not read file: {exc}")],
        )
        return None, result, None

    parser = detect_parser(content, file_path.name)

    if parser is None:
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(
                message=(
                    "File format not recognised. Supported formats: "
                    "Mockingbird TXT (Level 1 / Level 2 / Stateful / SOAP), "
                    "Postman v2.1 collection, OpenAPI / Swagger, "
                    "CA LISA HTTP capture (.txt pair or .zip), "
                    "Mockingbird JSON (native format)."
                )
            )],
        )
        return None, result, None

    validation_result, parsed_file = parser.validate_and_parse(content, str(file_path))
    return parser, validation_result, parsed_file


# ── ZIP / CA LISA pair handling ───────────────────────────────────────────────

# Filename patterns to classify CA LISA files inside a ZIP
_REQUEST_FILE_RE = re.compile(r'[_\-]?[Rr]equest[_\-]?', re.IGNORECASE)
_RESPONSE_FILE_RE = re.compile(r'[_\-]?[Rr]esponse[_\-]?', re.IGNORECASE)
# Timestamp suffix: _20260610_100059
_TIMESTAMP_RE = re.compile(r'_(\d{8}_\d{6})')


def _detect_and_parse_zip(
    file_path: Path,
) -> tuple[BaseParser | None, ValidationResult, ParsedFile | None]:
    """Handle ZIP archives containing CA LISA HTTP capture file pairs.

    Pairs are matched by:
      1. Shared timestamp in filename (_20260610_100059)
      2. Shared prefix after stripping _Request_ / _Response_
    Returns a ParsedFile containing one stub per matched pair.
    """
    parser = CALISAParser()

    if not zipfile.is_zipfile(file_path):
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(message="File has .zip extension but is not a valid ZIP archive.")],
        )
        return None, result, None

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            txt_files = [
                n for n in zf.namelist()
                if n.lower().endswith(".txt") and not n.startswith("__MACOSX")
            ]

            if not txt_files:
                result = ValidationResult(
                    valid=False,
                    errors=[ValidationError(
                        message="ZIP contains no .txt files. "
                                "Expected CA LISA *_Request_*.txt and *_Response_*.txt files."
                    )],
                )
                return None, result, None

            # Read all text files
            file_contents: dict[str, str] = {}
            for name in txt_files:
                raw = zf.read(name)
                file_contents[name] = raw.decode("utf-8", errors="replace")

    except Exception as exc:
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(message=f"Could not read ZIP: {exc}")],
        )
        return None, result, None

    # Classify into request / response groups
    request_files: dict[str, str] = {}   # name → content
    response_files: dict[str, str] = {}

    for name, content in file_contents.items():
        basename = Path(name).name
        if _REQUEST_FILE_RE.search(basename):
            request_files[name] = content
        elif _RESPONSE_FILE_RE.search(basename):
            response_files[name] = content
        else:
            # Fallback: detect from content
            from .parsers.ca_lisa_parser import _REQUEST_RE, _ESP_RESPONSE_RE, _WEALTH_RESPONSE_LABEL_RE
            if _REQUEST_RE.search(content):
                request_files[name] = content
            elif _ESP_RESPONSE_RE.search(content) or _WEALTH_RESPONSE_LABEL_RE.search(content):
                response_files[name] = content

    if not request_files:
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(
                message="No request files found in ZIP. "
                        "Expected filenames containing 'Request' (e.g., *_Request_*.txt)."
            )],
        )
        return None, result, None

    if not response_files:
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(
                message="No response files found in ZIP. "
                        "Expected filenames containing 'Response' (e.g., *_Response_*.txt)."
            )],
        )
        return None, result, None

    # Pair requests to responses
    pairs = _pair_files(request_files, response_files)

    if not pairs:
        result = ValidationResult(
            valid=False,
            errors=[ValidationError(
                message="Could not match request files to response files in ZIP. "
                        "Files should share a timestamp suffix or name prefix."
            )],
        )
        return None, result, None

    # Parse each pair
    stubs = []
    errors: list[ValidationError] = []
    for req_name, resp_name in pairs:
        try:
            stub = parse_ca_lisa_pair(
                request_content=request_files[req_name],
                response_content=response_files[resp_name],
                request_filename=Path(req_name).name,
                response_filename=Path(resp_name).name,
            )
            stubs.append(stub)
        except Exception as exc:
            errors.append(ValidationError(
                message=f"Pair ({Path(req_name).name} + {Path(resp_name).name}): {exc}"
            ))

    if not stubs:
        result = ValidationResult(
            valid=False,
            format_detected=parser.format_name,
            errors=errors,
        )
        return parser, result, None

    warnings = [str(e) for e in errors]  # partial failures become warnings
    result = ValidationResult(
        valid=True,
        format_detected=parser.format_name,
        summary=f"{len(stubs)} stub(s) from {len(pairs)} CA LISA pair(s) in ZIP",
        warnings=warnings,
    )
    parsed_file = ParsedFile(
        format=parser.format_name,
        source_file=str(file_path),
        stubs=stubs,
    )
    return parser, result, parsed_file


def _pair_files(
    request_files: dict[str, str],
    response_files: dict[str, str],
) -> list[tuple[str, str]]:
    """Return list of (request_name, response_name) pairs.

    Matching strategy (in order):
      1. Shared timestamp suffix in filename (_20260610_100059)
      2. Longest common prefix after stripping _Request / _Response
      3. One-to-one if there is exactly one request and one response
    """
    pairs: list[tuple[str, str]] = []
    unmatched_responses = set(response_files.keys())

    for req_name in request_files:
        req_base = Path(req_name).name
        matched = False

        # Strategy 1: match by exact timestamp suffix (_YYYYMMDD_HHMMSS)
        ts_match = _TIMESTAMP_RE.search(req_base)
        if ts_match:
            ts = ts_match.group(1)
            for resp_name in list(unmatched_responses):
                if ts in Path(resp_name).name:
                    pairs.append((req_name, resp_name))
                    unmatched_responses.discard(resp_name)
                    matched = True
                    break

        if not matched:
            # Strategy 2: longest common filename prefix (after stripping Request/Response tokens).
            # Handles CA LISA files where request and response timestamps differ by a second.
            req_stripped = _REQUEST_FILE_RE.sub("", req_base).lower()
            best_match: str | None = None
            best_score = 0
            for resp_name in unmatched_responses:
                resp_stripped = _RESPONSE_FILE_RE.sub("", Path(resp_name).name).lower()
                score = _common_prefix_length(req_stripped, resp_stripped)
                if score > best_score:
                    best_score = score
                    best_match = resp_name
            if best_match and best_score >= 4:
                pairs.append((req_name, best_match))
                unmatched_responses.discard(best_match)

    # Strategy 3: one-to-one fallback
    if not pairs and len(request_files) == 1 and len(response_files) == 1:
        pairs.append((
            next(iter(request_files)),
            next(iter(response_files)),
        ))

    return pairs


def _common_prefix_length(a: str, b: str) -> int:
    length = min(len(a), len(b))
    for i in range(length):
        if a[i] != b[i]:
            return i
    return length
