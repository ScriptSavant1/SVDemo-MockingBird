"""CA LISA / IBM Rational Test Workbench recorded HTTP capture file parser.

Supports two recording variants that CA LISA / IBM RTWS produce:

  ESP variant (no section labels — body appended directly after header block):
    ={Method="POST" URL="/api/..." httpDetails={Version="1.1" httpHeaders={...}}}BODY
    ResponseHeader={StatusCode="200" ...}
    Response..BODY

  Wealth / labelled variant (explicit section labels):
    12-Jun-2026 13:32:21            ← optional date line — ignored
    RequestHeader:
    ={Method="POST" URL="/api/..." httpDetails={...}}
    Request:
    BODY
    ResponseHeader:
    ={StatusCode="200" ...}
    Response:
    BODY

Single-file upload:
    Concatenate the request file and the response file into one file.
    The parser splits on the first ResponseHeader= / ResponseHeader: occurrence.

ZIP upload:
    Zip a folder containing *_Request_*.txt and *_Response_*.txt pairs.
    The detector pairs them automatically by filename pattern.

CA LISA variable substitution:
    %%X-Interaction-Id%%  → WireMock response template {{request.headers.X-Interaction-Id}}
    %%StatusCode%%        → inferred from filename (Error400 → 400, Success → 200)
    %%AnyOtherVar%%       → WireMock response template {{request.headers.AnyOtherVar}}
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..models import (
    HttpMethod,
    MatchCondition,
    MatchType,
    ParsedFile,
    ParsedRequestSpec,
    ParsedScenario,
    ParsedStub,
    ValidationError,
    ValidationResult,
)
from .base import BaseParser

# ── detection patterns ────────────────────────────────────────────────────────

# ESP request: ={Method="VERB" ...
_REQUEST_RE = re.compile(r'=\{Method="(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"')
# ESP response: ResponseHeader={StatusCode=
_ESP_RESPONSE_RE = re.compile(r'ResponseHeader=\{StatusCode=')
# Wealth response: standalone "ResponseHeader:" label line
_WEALTH_RESPONSE_LABEL_RE = re.compile(r'^ResponseHeader:\s*$', re.MULTILINE)
# Wealth request: standalone "RequestHeader:" label line
_WEALTH_REQUEST_LABEL_RE = re.compile(r'^RequestHeader:\s*$', re.MULTILINE)
# CA LISA variable: %%VarName%%  (also catches single-% prefix artefacts like %VarName%%)
_CALISA_VAR_RE = re.compile(r'%{1,2}([A-Za-z][A-Za-z0-9_\-]*)%{1,2}')
# Wealth date header line: "12-Jun-2026 13:32:21"
_DATE_LINE_RE = re.compile(r'^\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}\s*$')
# Status code in filename: Error400, Error500
_FILENAME_ERROR_CODE_RE = re.compile(r'[Ee]rror(\d{3})')
_FILENAME_SUCCESS_RE = re.compile(r'[Ss]uccess|\bOK\b', re.IGNORECASE)


class CALISAParser(BaseParser):
    """Parses CA LISA / IBM RTWS recorded HTTP capture files into WireMock stubs."""

    @property
    def format_name(self) -> str:
        return "ca-lisa-http-pair"

    def can_handle(self, content: str, filename: str) -> bool:
        return bool(
            _REQUEST_RE.search(content)
            or _ESP_RESPONSE_RE.search(content)
            or _WEALTH_RESPONSE_LABEL_RE.search(content)
        )

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []

        has_request = bool(_REQUEST_RE.search(content))
        has_response = bool(
            _ESP_RESPONSE_RE.search(content)
            or _WEALTH_RESPONSE_LABEL_RE.search(content)
        )

        if not has_request and not has_response:
            errors.append(ValidationError(
                message="No CA LISA HTTP capture content found. "
                        "File must contain a request (={Method=) or response (ResponseHeader=) block.",
            ))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        if not has_request:
            errors.append(ValidationError(
                message="Response file detected but no request block found. "
                        "Combine request and response files into one file before uploading.",
            ))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        if not has_response:
            errors.append(ValidationError(
                message="Request file detected but no response block found. "
                        "Combine request and response files into one file before uploading.",
            ))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

        try:
            stubs = _parse_ca_lisa_content(content, "validate")
            stub_count = len(stubs)
            scenario_count = sum(len(s.scenarios) for s in stubs)
            return ValidationResult(
                valid=True,
                format_detected=self.format_name,
                summary=(
                    f"{stub_count} stub(s) · {scenario_count} scenario(s) "
                    f"detected from CA LISA HTTP capture"
                ),
            )
        except Exception as exc:
            errors.append(ValidationError(message=f"Parse error: {exc}"))
            return ValidationResult(valid=False, format_detected=self.format_name, errors=errors)

    def parse(self, content: str, source_file: str) -> ParsedFile:
        stubs = _parse_ca_lisa_content(content, source_file)
        return ParsedFile(format=self.format_name, source_file=source_file, stubs=stubs)


# ── public helper for ZIP pairing (used by detector) ─────────────────────────

def parse_ca_lisa_pair(
    request_content: str,
    response_content: str,
    request_filename: str,
    response_filename: str,
) -> ParsedStub:
    """Build a single ParsedStub from separate request and response file contents.

    Called by the ZIP handler in detector.py after pairing files by filename.
    """
    combined = request_content.rstrip() + "\n" + response_content
    stubs = _parse_ca_lisa_content(combined, request_filename, hint_filename=response_filename)
    if not stubs:
        raise ValueError(
            f"No stub could be built from pair: {request_filename} + {response_filename}"
        )
    return stubs[0]


# ── internal: top-level dispatch ──────────────────────────────────────────────

def _parse_ca_lisa_content(
    content: str,
    source_name: str,
    hint_filename: str = "",
) -> list[ParsedStub]:
    """Parse combined request+response CA LISA content into ParsedStubs."""
    variant = _detect_variant(content)
    if variant == "wealth":
        return _parse_wealth_content(content, source_name, hint_filename)
    return _parse_esp_content(content, source_name, hint_filename)


def _detect_variant(content: str) -> str:
    """Return 'wealth' if content uses section labels; 'esp' otherwise."""
    if _WEALTH_REQUEST_LABEL_RE.search(content) or _WEALTH_RESPONSE_LABEL_RE.search(content):
        return "wealth"
    return "esp"


# ── Wealth variant ────────────────────────────────────────────────────────────

def _parse_wealth_content(
    content: str, source_name: str, hint_filename: str
) -> list[ParsedStub]:
    """Parse the labelled (Wealth) CA LISA format."""
    lines = content.splitlines()

    req_label_idx: Optional[int] = None
    resp_label_idx: Optional[int] = None

    for i, line in enumerate(lines):
        s = line.strip()
        if s == "RequestHeader:" and req_label_idx is None:
            req_label_idx = i
        elif s == "ResponseHeader:":
            resp_label_idx = i
            break

    if req_label_idx is None:
        raise ValueError("No 'RequestHeader:' label found in Wealth-format CA LISA file")
    if resp_label_idx is None:
        raise ValueError(
            "No 'ResponseHeader:' label found. "
            "Combine request and response files into one file before uploading."
        )

    req_block_text, req_body = _extract_wealth_section(
        lines, req_label_idx, "Request:", end_line=resp_label_idx
    )
    resp_block_text, resp_body = _extract_wealth_section(
        lines, resp_label_idx, "Response:"
    )

    req_parsed = _parse_kvblock(req_block_text)
    resp_parsed = _parse_kvblock(resp_block_text)

    method_str = req_parsed.get("Method", "GET")
    url = req_parsed.get("URL", "/")

    req_headers = _extract_http_headers(req_parsed)
    resp_headers = _extract_http_headers(resp_parsed)

    raw_status = str(resp_parsed.get("StatusCode", "200"))
    status_code = _infer_status_code(raw_status, hint_filename or source_name)

    # Resolve CA LISA variables in response body and headers
    resolved_body, uses_template = _resolve_variables(resp_body or "", hint_filename or source_name)
    resolved_headers = {
        k: _resolve_variables(v, hint_filename or source_name)[0]
        for k, v in resp_headers.items()
    }
    if any(
        _resolve_variables(v, hint_filename or source_name)[1]
        for v in resp_headers.values()
    ):
        uses_template = True

    stub_name = _stub_name_from_source(source_name)

    scenario = ParsedScenario(
        name="default",
        match=MatchCondition(type=MatchType.ALWAYS),
        status=status_code,
        response_headers=resolved_headers,
        body=resolved_body or None,
    )
    stub = ParsedStub(
        name=stub_name,
        request=ParsedRequestSpec(
            method=HttpMethod(method_str.upper()),
            url=url,
            required_headers=_filter_request_headers(req_headers),
        ),
        scenarios=[scenario],
    )
    return [stub]


def _extract_wealth_section(
    lines: list[str],
    label_idx: int,
    body_label: str,
    end_line: Optional[int] = None,
) -> tuple[str, str]:
    """Extract the CA LISA block text and the body from a labelled section.

    CA LISA Wealth format often omits the outer closing brace of the ={...}
    block, so brace-depth counting is unreliable.  Instead we use the body
    section label (e.g. "Request:" or "Response:") as the hard boundary
    between the header block and the body.

    Returns (block_text, body_text).
    """
    limit = end_line if end_line is not None else len(lines)
    section_lines = lines[label_idx + 1 : limit]

    # Find the body label ("Request:" or "Response:") within this section
    body_label_key = body_label.rstrip(":")
    body_label_idx: Optional[int] = None
    for i, line in enumerate(section_lines):
        if line.strip() == f"{body_label_key}:":
            body_label_idx = i
            break

    if body_label_idx is not None:
        # Block = everything before the body label, skipping blank and date lines
        block_lines = [
            l for l in section_lines[:body_label_idx]
            if l.strip() and not _DATE_LINE_RE.match(l.strip())
        ]
        body_lines = section_lines[body_label_idx + 1 :]
    else:
        # No body label — entire section is the header block; no body
        block_lines = [
            l for l in section_lines
            if l.strip() and not _DATE_LINE_RE.match(l.strip())
        ]
        body_lines = []

    block_text = "\n".join(block_lines).strip()
    if block_text.startswith("="):
        block_text = block_text[1:].strip()

    body = "\n".join(body_lines).strip()
    return block_text, body


# ── ESP variant ───────────────────────────────────────────────────────────────

def _parse_esp_content(
    content: str, source_name: str, hint_filename: str
) -> list[ParsedStub]:
    """Parse the raw (ESP) CA LISA format.

    Splits on ResponseHeader= to separate request and response sections.
    Multiple pairs in one file (e.g., from ZIP concatenation) are each parsed.
    """
    # Split into request-part and response-part on "ResponseHeader="
    split_match = re.search(r'(?=ResponseHeader=\{)', content)
    if split_match is None:
        raise ValueError(
            "Cannot find 'ResponseHeader={' in ESP-format CA LISA content. "
            "Make sure the response file is concatenated after the request file."
        )

    request_part = content[: split_match.start()]
    response_part = content[split_match.start() :]

    # Parse request
    method, url, req_headers, req_body = _parse_esp_request(request_part)

    # Parse response
    status_code, resp_headers, resp_body = _parse_esp_response(
        response_part, hint_filename or source_name
    )

    resolved_body, uses_template = _resolve_variables(resp_body, hint_filename or source_name)
    resolved_headers = {
        k: _resolve_variables(v, hint_filename or source_name)[0]
        for k, v in resp_headers.items()
    }
    if any(
        _resolve_variables(v, hint_filename or source_name)[1]
        for v in resp_headers.values()
    ):
        uses_template = True

    stub_name = _stub_name_from_source(source_name)

    scenario = ParsedScenario(
        name="default",
        match=MatchCondition(type=MatchType.ALWAYS),
        status=status_code,
        response_headers=resolved_headers,
        body=resolved_body or None,
    )
    stub = ParsedStub(
        name=stub_name,
        request=ParsedRequestSpec(
            method=HttpMethod(method.upper()),
            url=url,
            required_headers=_filter_request_headers(req_headers),
        ),
        scenarios=[scenario],
    )
    return [stub]


def _parse_esp_request(text: str) -> tuple[str, str, dict[str, str], str]:
    """Return (method, url, request_headers, request_body) from ESP request text."""
    text = text.strip()

    # Strip leading = before the block
    if text.startswith("="):
        text = text[1:].lstrip()

    if not text.startswith("{"):
        raise ValueError("ESP request: expected '{' after '='")

    block_end = _find_block_end(text, 0)
    block_text = text[:block_end]
    body = text[block_end:].strip()

    parsed = _parse_kvblock(block_text)
    method = parsed.get("Method", "GET")
    url = parsed.get("URL", "/")
    headers = _extract_http_headers(parsed)
    return method, url, headers, body


def _parse_esp_response(
    text: str, filename_hint: str
) -> tuple[int, dict[str, str], str]:
    """Return (status_code, response_headers, response_body) from ESP response text."""
    text = text.strip()

    # ResponseHeader={...}
    if not text.startswith("ResponseHeader="):
        raise ValueError("ESP response: expected 'ResponseHeader={' at start")

    brace_start = text.index("{")
    block_end = _find_block_end(text, brace_start)
    block_text = text[brace_start:block_end]
    parsed = _parse_kvblock(block_text)

    raw_status = str(parsed.get("StatusCode", "200"))
    status_code = _infer_status_code(raw_status, filename_hint)
    headers = _extract_http_headers(parsed)

    # Body follows "Response.." or plain newline after block
    after_block = text[block_end:].strip()
    if after_block.startswith("Response.."):
        body = after_block[len("Response..") :].strip()
    elif after_block.startswith("Response:"):
        body = after_block[len("Response:") :].strip()
    else:
        body = after_block.strip()

    return status_code, headers, body


# ── CA LISA header parser ─────────────────────────────────────────────────────

def _find_block_end(text: str, start: int) -> int:
    """Return the index AFTER the closing '}' of the block starting at text[start].

    Correctly skips braces and curly-braces inside quoted strings so that
    nested CA LISA blocks and JSON body content are not confused.
    """
    depth = 0
    in_string = False
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    return n


def _parse_kvblock(text: str) -> dict[str, Any]:
    """Parse a CA LISA key=value block.

    Handles:
      Method="POST"              → {"Method": "POST"}
      httpDetails={Version="1.1"} → {"httpDetails": {"Version": "1.1"}}
    """
    text = text.strip()
    if text.startswith("{"):
        # Strip outer braces. CA LISA sometimes omits the matching closing brace
        # (e.g. Wealth format outer block), so only strip closing } when it actually
        # closes the opening { (using _find_block_end rather than just checking endswith).
        close = _find_block_end(text, 0)
        if close == len(text):
            text = text[1:-1]  # proper {…}
        else:
            text = text[1:]    # unclosed — just strip the leading {

    result: dict[str, Any] = {}
    i = 0
    n = len(text)

    while i < n:
        # Skip whitespace
        while i < n and text[i] in " \t\n\r":
            i += 1
        if i >= n:
            break

        # Read key (everything up to '=')
        key_start = i
        while i < n and text[i] not in "= \t\n\r":
            i += 1
        key = text[key_start:i].strip()

        # Skip whitespace then expect '='
        while i < n and text[i] in " \t\n\r":
            i += 1
        if i >= n or text[i] != "=":
            # Not a key=value pair — skip token
            while i < n and text[i] not in " \t\n\r":
                i += 1
            continue
        i += 1  # consume '='

        if i >= n:
            break

        # Read value
        if text[i] == '"':
            i += 1
            val_start = i
            while i < n and text[i] != '"':
                i += 1
            value: Any = text[val_start:i]
            if i < n:
                i += 1
        elif text[i] == "{":
            block_end = _find_block_end(text, i)
            value = _parse_kvblock(text[i:block_end])
            i = block_end
        else:
            val_start = i
            while i < n and text[i] not in " \t\n\r":
                i += 1
            value = text[val_start:i]

        if key:
            result[key] = value

    return result


def _extract_http_headers(parsed_block: dict[str, Any]) -> dict[str, str]:
    """Pull flat httpHeaders dict out of a parsed CA LISA block."""
    http_details = parsed_block.get("httpDetails", {})
    if not isinstance(http_details, dict):
        return {}
    http_headers = http_details.get("httpHeaders", {})
    if not isinstance(http_headers, dict):
        return {}
    return {k: str(v) for k, v in http_headers.items()}


_SKIP_REQUEST_HEADERS = frozenset({
    "Host", "Connection", "Content-Length", "Accept", "User-Agent",
    "Accept-Encoding", "dws-correlation-id",
})


def _filter_request_headers(headers: dict[str, str]) -> dict[str, str]:
    """Keep only headers that are meaningful for WireMock request matching.

    Drops infrastructure headers (Host, Content-Length, etc.) that vary
    across environments and would cause false negatives in matching.
    """
    return {
        k: v
        for k, v in headers.items()
        if k not in _SKIP_REQUEST_HEADERS and v  # drop empty values too
    }


# ── CA LISA variable resolution ───────────────────────────────────────────────

_STATUS_CODE_VAR = re.compile(r'^%{1,2}StatusCode%{1,2}$', re.IGNORECASE)


def _resolve_variables(text: str, filename_hint: str) -> tuple[str, bool]:
    """Replace CA LISA %%Var%% placeholders with WireMock Handlebars equivalents.

    Returns (resolved_text, uses_response_template).
    %%StatusCode%% is NOT replaced (handled separately in status code inference).
    %%X-Interaction-Id%% → {{request.headers.X-Interaction-Id}}
    """
    uses_template = False

    def replace(m: re.Match) -> str:  # type: ignore[type-arg]
        nonlocal uses_template
        var_name = m.group(1)
        if _STATUS_CODE_VAR.match(m.group(0)):
            return m.group(0)  # leave as-is; resolved by _infer_status_code
        uses_template = True
        return f"{{{{request.headers.{var_name}}}}}"

    resolved = _CALISA_VAR_RE.sub(replace, text)
    return resolved, uses_template


def _infer_status_code(raw_status: str, filename_hint: str) -> int:
    """Resolve a CA LISA status code value.

    If raw_status is a plain number → use it.
    If it is %%StatusCode%% → infer from filename:
        Error400 → 400, Error500 → 500, Success/OK → 200, Error (no code) → 400.
    """
    if raw_status.isdigit():
        return int(raw_status)

    # CA LISA variable — infer from filename
    m = _FILENAME_ERROR_CODE_RE.search(filename_hint)
    if m:
        return int(m.group(1))
    if _FILENAME_SUCCESS_RE.search(filename_hint):
        return 200
    if re.search(r'[Ee]rror|[Ff]ail', filename_hint):
        return 400
    # Default: 200
    return 200


# ── misc helpers ──────────────────────────────────────────────────────────────

def _stub_name_from_source(source: str) -> str:
    """Derive a human-readable stub name from the source filename."""
    import os
    name = os.path.basename(source)
    # Strip extensions and timestamp suffixes like _20260610_100059
    name = re.sub(r'_\d{8}_\d{6}', '', name)
    name = re.sub(r'\.(txt|zip)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[_\-]+', ' ', name).strip()
    return name or "CA LISA Stub"
