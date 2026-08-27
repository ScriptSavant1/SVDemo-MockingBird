"""CA LISA / IBM Rational Test Workbench recorded HTTP capture file parser.

Format is detected purely from file CONTENT — never from filename or client
name. Different capture tools (and different teams' export settings) produce
two structural variants; which client produced a given file is irrelevant to
this parser, and no client name should ever appear in code here.

  Inline variant (no section labels — body appended directly after header block):
    ={Method="POST" URL="/api/..." httpDetails={Version="1.1" httpHeaders={...}}}BODY
    ResponseHeader={StatusCode="200" ...}
    Response..BODY

    Two looser sub-cases also occur:
    - (manually reformatted captures) the outer ={...} block closes early,
      right after URL=, and httpDetails={...} appears as a sibling block
      afterwards instead of nested inside. See _consume_sibling_kv — headers
      are merged in either layout.
    - (some capture tools) the response omits the "ResponseHeader" label
      entirely, exporting a bare ={StatusCode="200" ...}BODY block that is
      structurally identical to a request block except for StatusCode=
      instead of Method=. See _BARE_RESPONSE_RE.

  Labelled variant (explicit section labels):
    12-Jun-2026 13:32:21            ← optional date line — ignored
    RequestHeader:
    ={Method="POST" URL="/api/..." httpDetails={...}}
    Request:
    BODY
    ResponseHeader:
    ={StatusCode="200" ...}
    Response:
    BODY

Body content is opaque to this parser by design: JSON (objects, arrays,
nested/mixed), XML/SOAP (any namespace prefix, repeated sibling elements,
attributes, SOAP Fault bodies), or plain text are all captured verbatim and
passed straight through to the WireMock mapping — no schema is assumed, so
whatever shape the real service returns is what gets replayed. The one
inference this parser does make: if a captured response has no Content-Type
header at all, one is guessed from the body's leading character (see
_infer_content_type) so replayed responses aren't served content-type-less.

Single-file upload:
    Concatenate the request file and the response file into one file.
    The parser splits on the first ResponseHeader= / ResponseHeader: occurrence.

ZIP upload:
    Zip a folder containing *_Request_*.txt and *_Response_*.txt pairs
    (.txt, .json, or .xml — extension doesn't affect detection).
    The detector pairs them automatically by filename pattern.

CA LISA variable substitution:
    %%X-Interaction-Id%%  → WireMock response template {{request.headers.X-Interaction-Id}}
    %%StatusCode%%        → inferred from filename (Error400 → 400, Success → 200)
    %%AnyOtherVar%%       → WireMock response template {{request.headers.AnyOtherVar}}
"""
from __future__ import annotations

import json as _json
import re
from typing import Any, NamedTuple, Optional
from xml.etree import ElementTree as _ET

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

# Inline-variant request: ={Method="VERB" ...
_REQUEST_RE = re.compile(r'=\{Method="(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"')
# Inline-variant response: ResponseHeader={StatusCode=
_INLINE_RESPONSE_RE = re.compile(r'ResponseHeader=\{StatusCode=')
# Inline-variant response, bare sub-form: some capture tools omit the
# "ResponseHeader" label entirely and export just ={StatusCode=...} — a block
# structurally identical to a request block except it carries StatusCode=
# instead of Method=. Distinguish purely by that content, not by any label.
_BARE_RESPONSE_RE = re.compile(r'=\{StatusCode="')
# Labelled-variant response: standalone "ResponseHeader:" label line
_LABELLED_RESPONSE_LABEL_RE = re.compile(r'^ResponseHeader:\s*$', re.MULTILINE)
# Labelled-variant request: standalone "RequestHeader:" label line
_LABELLED_REQUEST_LABEL_RE = re.compile(r'^RequestHeader:\s*$', re.MULTILINE)
# Structural label line: ANY standalone identifier ending in ':' with nothing
# else on the line — e.g. "RequestHeader:", "AccountInstructionsRequestHeader:",
# "Request:", "AccountInstructionResponse:". The label's literal text is
# deliberately never inspected; only what immediately follows it decides its
# role (see _scan_labelled_captures). This is what lets the labelled variant
# survive whatever naming convention a given CA LISA export, Postman/Bruno
# export, or hand-authored file happens to use for its section labels,
# without new code for every naming scheme — as long as the underlying shape
# (a label line, then a "={...}" metadata block, then a body) still holds.
_LABEL_LINE_RE = re.compile(r'^([A-Za-z][A-Za-z0-9_]*):\s*$')
_META_REQUEST_START_RE = re.compile(r'^=\{Method="')
_META_RESPONSE_START_RE = re.compile(r'^=\{StatusCode="')
# CA LISA variable: %%VarName%%  (also catches single-% prefix artefacts like %VarName%%)
_CALISA_VAR_RE = re.compile(r'%{1,2}([A-Za-z][A-Za-z0-9_\-]*)%{1,2}')
# Labelled-variant date header line: "12-Jun-2026 13:32:21"
_DATE_LINE_RE = re.compile(r'^\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}\s*$')
# Status code in filename: Error400, Error500
_FILENAME_ERROR_CODE_RE = re.compile(r'[Ee]rror(\d{3})')
_FILENAME_SUCCESS_RE = re.compile(r'[Ss]uccess|\bOK\b', re.IGNORECASE)
# A top-level "Key=" token — used to detect sibling header fields that follow
# an already-closed block (see _consume_sibling_kv). No \A/^ anchor: matched via
# Pattern.match(text, pos), which already anchors to `pos` on its own — \A would
# instead anchor to absolute index 0 of the whole string and never match at pos > 0.
_TOP_LEVEL_KEY_RE = re.compile(r'([A-Za-z][A-Za-z0-9_\-]*)\s*=\s*')
# Body sniffing for Content-Type inference — SOAP envelopes use varying prefixes
# (soapenv:, soap:, soap12:, SOAP-ENV:, or none with a default xmlns), so match
# structurally on the local name rather than any one prefix.
_SOAP_ENVELOPE_RE = re.compile(r'<(?:[\w.-]+:)?Envelope[\s>]', re.IGNORECASE)


class CALISAParser(BaseParser):
    """Parses CA LISA / IBM RTWS recorded HTTP capture files into WireMock stubs."""

    @property
    def format_name(self) -> str:
        return "ca-lisa-http-pair"

    def can_handle(self, content: str, filename: str) -> bool:
        return bool(
            _REQUEST_RE.search(content)
            or _INLINE_RESPONSE_RE.search(content)
            or _BARE_RESPONSE_RE.search(content)
            or _LABELLED_RESPONSE_LABEL_RE.search(content)
        )

    def validate(self, content: str) -> ValidationResult:
        errors: list[ValidationError] = []

        has_request = bool(_REQUEST_RE.search(content))
        has_response = bool(
            _INLINE_RESPONSE_RE.search(content)
            or _BARE_RESPONSE_RE.search(content)
            or _LABELLED_RESPONSE_LABEL_RE.search(content)
        )

        if not has_request and not has_response:
            errors.append(ValidationError(
                message="No CA LISA HTTP capture content found. "
                        "File must contain a request (={Method=) or response "
                        "(ResponseHeader={ or a bare ={StatusCode=) block.",
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
    if variant == "labelled":
        return _parse_labelled_content(content, source_name, hint_filename)
    return _parse_inline_content(content, source_name, hint_filename)


def _detect_variant(content: str) -> str:
    """Return 'labelled' if content uses section labels; 'inline' otherwise."""
    if _scan_labelled_captures(content.splitlines()):
        return "labelled"
    return "inline"


# ── labelled variant ──────────────────────────────────────────────────────────

def _scan_labelled_captures(lines: list[str]) -> list[dict]:
    """Walk labelled-variant content and extract every request/response capture,
    in document order — regardless of what the section-label lines are
    literally named. A label line's role is decided purely by what
    immediately follows it: a "={Method=" block starts a new request
    capture, a "={StatusCode=" block starts a new response capture, and any
    other label line encountered while a capture is open is that capture's
    body label (its own text is irrelevant and simply consumed).

    Handles any number of captures — one file may contain several
    request/response pairs recorded at the same URL (e.g. re-runs of the
    same operation with different payloads); each becomes its own entry
    here in the order it appears, later paired up by _parse_labelled_content.

    Returns a list of {"type": "request"|"response", "block": str, "body": str}.
    """
    captures: list[dict] = []
    current: Optional[dict] = None
    current_body_start: Optional[int] = None
    n = len(lines)

    def _next_nonblank(idx: int) -> Optional[str]:
        j = idx + 1
        while j < n and not lines[j].strip():
            j += 1
        return lines[j].strip() if j < n else None

    def _finish_body(end_idx: int) -> str:
        assert current_body_start is not None
        body_lines = lines[current_body_start:end_idx]
        while body_lines and (
            not body_lines[-1].strip() or _DATE_LINE_RE.match(body_lines[-1].strip())
        ):
            body_lines = body_lines[:-1]
        return "\n".join(body_lines).strip()

    def _finish_current(end_idx: int) -> None:
        if current is None:
            return
        current["body"] = _finish_body(end_idx) if current_body_start is not None else ""
        block_text = "\n".join(current.pop("block_lines")).strip()
        if block_text.startswith("="):
            block_text = block_text[1:].strip()
        current["block"] = block_text
        captures.append(current)

    i = 0
    while i < n:
        stripped = lines[i].strip()
        m = _LABEL_LINE_RE.match(stripped)
        if m:
            peek = _next_nonblank(i)
            if peek and _META_REQUEST_START_RE.match(peek):
                _finish_current(i)
                current = {"type": "request", "block_lines": []}
                current_body_start = None
            elif peek and _META_RESPONSE_START_RE.match(peek):
                _finish_current(i)
                current = {"type": "response", "block_lines": []}
                current_body_start = None
            elif current is not None and current_body_start is None:
                # Body label for the currently open capture — header block
                # text ends here, body starts on the next line.
                current_body_start = i + 1
            i += 1
            continue
        if current is not None and current_body_start is None:
            if stripped and not _DATE_LINE_RE.match(stripped):
                current["block_lines"].append(lines[i])
        i += 1

    _finish_current(n)
    return captures


class _Capture(NamedTuple):
    """One fully-resolved request or response capture, in the shape both
    CA LISA structural variants converge on before _build_stub_from_captures
    — the one place multi-capture pairing, header-stability filtering,
    same-URL differentiation, and lookup-table field population happen, so
    neither variant can silently diverge in how it handles "many captures
    at one URL" (see module docstring and _build_stub_from_captures).
    """
    type: str                       # "request" | "response"
    method: Optional[str]           # request only
    url: Optional[str]              # request only
    status: Optional[int]           # response only — already resolved via _infer_status_code
    headers: dict[str, str]
    body: str


def _parse_labelled_content(
    content: str, source_name: str, hint_filename: str
) -> list[ParsedStub]:
    """Parse the labelled CA LISA format (explicit *Header: sections)."""
    raw = _scan_labelled_captures(content.splitlines())
    captures = _resolve_labelled_captures(raw, hint_filename, source_name)
    return _build_stub_from_captures(captures, source_name, hint_filename)


def _resolve_labelled_captures(
    raw: list[dict], hint_filename: str, source_name: str
) -> list[_Capture]:
    """Turn _scan_labelled_captures' raw {"type","block","body"} dicts into
    fully-resolved _Capture records. Kept separate from scanning because
    _detect_variant calls _scan_labelled_captures without knowing the
    target filename yet (needed here only for %%StatusCode%% inference)."""
    resolved: list[_Capture] = []
    for c in raw:
        parsed = _parse_kvblock(c["block"])
        headers = _extract_http_headers(parsed)
        if c["type"] == "request":
            resolved.append(_Capture(
                "request", parsed.get("Method", "GET"), parsed.get("URL", "/"),
                None, headers, c["body"],
            ))
        else:
            raw_status = str(parsed.get("StatusCode", "200"))
            status = _infer_status_code(raw_status, hint_filename or source_name)
            resolved.append(_Capture("response", None, None, status, headers, c["body"]))
    return resolved


def _build_stub_from_captures(
    captures: list[_Capture], source_name: str, hint_filename: str
) -> list[ParsedStub]:
    """Build the final ParsedStub(s) from a flat, already-resolved list of
    request/response captures, in document order — shared by both CA LISA
    structural variants (labelled and inline) so "one file has many
    captures of one operation" is handled identically no matter which
    section-label convention (or lack of one) produced them.

    Captures are matched request[i] <-> response[i] in document order, up
    to min(len(requests), len(responses)). What happens next depends on
    whether the captured URLs actually agree:

      - All captures share one exact URL (the common case: same operation,
        different payload) -> _build_same_url_stub. A request-body field
        differentiates scenarios (see _differentiate_bodies).
      - URLs differ, but only in one path segment across every capture
        (e.g. an account/customer ID embedded in the path itself, like
        "/accounts/{id}/addressbook") -> _build_url_pattern_stub. The URL
        segment itself differentiates scenarios — no body inspection
        needed. An earlier version of this parser used the FIRST capture's
        URL for the whole stub and silently discarded every other
        capture's distinct URL entirely.
      - URLs differ with no such single-segment pattern (genuinely
        different, unrelated endpoints happening to share one file) ->
        _build_stubs_grouped_by_url: one ParsedStub per distinct URL, each
        still handled by whichever of the above two cases applies to the
        captures sharing that URL. Nothing is ever silently dropped.
    """
    requests = [c for c in captures if c.type == "request"]
    responses = [c for c in captures if c.type == "response"]

    if not requests:
        raise ValueError("No request section found in CA LISA content")
    if not responses:
        raise ValueError(
            "No response section found. "
            "Combine request and response files into one file before uploading."
        )

    pair_count = min(len(requests), len(responses))
    requests, responses = requests[:pair_count], responses[:pair_count]

    distinct_urls = {r.url for r in requests}
    if len(distinct_urls) == 1:
        return [_build_same_url_stub(requests, responses, source_name, hint_filename)]

    url_pattern_result = _detect_url_segment_pattern([r.url or "/" for r in requests])
    if url_pattern_result is not None:
        pattern, values = url_pattern_result
        return [_build_url_pattern_stub(requests, responses, pattern, values, source_name, hint_filename)]

    return _build_stubs_grouped_by_url(requests, responses, source_name, hint_filename)


def _build_same_url_stub(
    requests: list[_Capture], responses: list[_Capture], source_name: str, hint_filename: str
) -> ParsedStub:
    """One or more captures, all recorded at the identical URL — the
    common case. A single request-body field differentiates scenarios when
    there's more than one (see _differentiate_bodies); that same field also
    becomes the stub's dynamic lookup-table discriminator once the capture
    count crosses generator/lookup_table.py's threshold.
    """
    pair_count = len(requests)
    method_str = requests[0].method or "GET"
    url = requests[0].url or "/"

    required_headers = _stable_required_headers(requests)

    req_bodies = [r.body for r in requests]
    diff = _differentiate_bodies(req_bodies) if pair_count > 1 else _no_differentiation(1)

    scenarios: list[ParsedScenario] = []
    for i in range(pair_count):
        resolved_body, resolved_headers = _resolve_response(responses[i], source_name, hint_filename)
        match = diff.conditions[i] or MatchCondition(type=MatchType.ALWAYS)
        scenario_name = "default" if pair_count == 1 else f"variant-{i + 1}"

        scenarios.append(ParsedScenario(
            name=scenario_name,
            match=match,
            status=responses[i].status or 200,
            response_headers=resolved_headers,
            body=resolved_body or None,
            lookup_key=diff.values[i],
        ))

    return ParsedStub(
        name=_stub_name_from_source(source_name),
        request=ParsedRequestSpec(
            method=HttpMethod(method_str.upper()),
            url=url,
            required_headers=required_headers,
        ),
        scenarios=scenarios,
        lookup_discriminator_type=diff.discriminator_type,
        lookup_discriminator_field=diff.discriminator_field,
    )


def _build_url_pattern_stub(
    requests: list[_Capture],
    responses: list[_Capture],
    url_pattern: str,
    url_values: list[str],
    source_name: str,
    hint_filename: str,
) -> ParsedStub:
    """Captures recorded at URLs that differ in exactly one path segment
    (an ID embedded in the path — see _detect_url_segment_pattern). Each
    scenario gets its own exact url_override (so the static-mapping path,
    below generator/lookup_table.py's threshold, needs no body inspection
    at all — the URL itself already disambiguates every scenario via plain
    WireMock exact-urlPath matching). The stub's own request.url carries
    the regex pattern, for the lookup-table path once the capture count
    crosses that threshold.
    """
    pair_count = len(requests)
    method_str = requests[0].method or "GET"
    required_headers = _stable_required_headers(requests)

    scenarios: list[ParsedScenario] = []
    for i in range(pair_count):
        resolved_body, resolved_headers = _resolve_response(responses[i], source_name, hint_filename)
        scenarios.append(ParsedScenario(
            name=f"variant-{i + 1}",
            match=MatchCondition(type=MatchType.ALWAYS),
            status=responses[i].status or 200,
            response_headers=resolved_headers,
            body=resolved_body or None,
            lookup_key=url_values[i],
            url_override=requests[i].url,
        ))

    return ParsedStub(
        name=_stub_name_from_source(source_name),
        request=ParsedRequestSpec(
            method=HttpMethod(method_str.upper()),
            url=url_pattern,
            required_headers=required_headers,
        ),
        scenarios=scenarios,
        lookup_discriminator_type="url-segment",
        lookup_url_pattern=url_pattern,
    )


def _build_stubs_grouped_by_url(
    requests: list[_Capture], responses: list[_Capture], source_name: str, hint_filename: str
) -> list[ParsedStub]:
    """Fallback when captured URLs differ with no single-segment pattern
    common to all of them: group captures by their exact URL and build one
    stub per distinct URL (via _build_same_url_stub, so multiple captures
    sharing one of those URLs still get body-based differentiation).
    Guarantees no capture is ever silently dropped just because the parser
    couldn't find a clean shared shape across the whole file.
    """
    by_url: dict[str, tuple[list[_Capture], list[_Capture]]] = {}
    for req, resp in zip(requests, responses):
        url = req.url or "/"
        by_url.setdefault(url, ([], []))
        group_requests, group_responses = by_url[url]
        group_requests.append(req)
        group_responses.append(resp)

    return [
        _build_same_url_stub(group_requests, group_responses, source_name, hint_filename)
        for group_requests, group_responses in by_url.values()
    ]


def _stable_required_headers(requests: list[_Capture]) -> dict[str, str]:
    """Headers that are identical across every capture — see
    _build_same_url_stub's docstring for why volatile per-call headers
    (correlation/trace IDs) must never become a required match condition."""
    req_headers_list = [r.headers for r in requests]
    if len(req_headers_list) > 1:
        first = req_headers_list[0]
        stable_headers = {
            k: v for k, v in first.items()
            if all(h.get(k) == v for h in req_headers_list[1:])
        }
    else:
        stable_headers = req_headers_list[0]
    return _filter_request_headers(stable_headers)


def _resolve_response(
    response: _Capture, source_name: str, hint_filename: str
) -> tuple[Optional[str], dict[str, str]]:
    """Resolve one response capture's %%Var%% placeholders (body + headers)
    and ensure a Content-Type is present. Shared by every stub-building
    path so response resolution can never drift between them."""
    resolved_body, _ = _resolve_variables(response.body or "", hint_filename or source_name)
    resolved_headers = {
        k: _resolve_variables(v, hint_filename or source_name)[0]
        for k, v in response.headers.items()
    }
    resolved_headers = _ensure_content_type(resolved_headers, resolved_body or "")
    return resolved_body or None, resolved_headers


def _detect_url_segment_pattern(urls: list[str]) -> Optional[tuple[str, list[str]]]:
    """Given N captured URLs for what looks like one operation, find a
    single path segment that varies across every one of them (e.g. an
    account/customer ID embedded in the path, not just the query string or
    body) and return (wiremock_url_regex, [segment value per url]) in the
    same order as `urls`.

    Returns None when the URLs don't share the same segment count, when
    more than one segment varies, or when the varying segment's values
    aren't all distinct (not a reliable per-capture discriminator) — the
    caller falls back to grouping by exact URL in that case, never to
    silently picking one URL and discarding the rest.
    """
    split = [u.split("/") for u in urls]
    if len({len(s) for s in split}) != 1:
        return None
    n_segments = len(split[0])

    varying_indices = [i for i in range(n_segments) if len({s[i] for s in split}) > 1]
    if len(varying_indices) != 1:
        return None
    idx = varying_indices[0]

    values = [s[idx] for s in split]
    if len(set(values)) != len(values):
        return None
    if any(not v for v in values):  # an empty segment (e.g. a trailing "//") isn't a real ID
        return None

    template = split[0]
    # The varying segment is a capturing group — DynamicLookupRequestFilter
    # extracts the discriminator value via group(1) when routing by URL
    # pattern instead of by body content.
    pattern = "/".join(
        "([^/]+)" if i == idx else re.escape(segment)
        for i, segment in enumerate(template)
    )
    return pattern, values


# ── same-URL body differentiation ─────────────────────────────────────────────

def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _xml_leaf_values(body: str) -> dict[str, str]:
    """Map {leaf-element-local-name: text} for a captured XML body.

    Uses local-name so namespace prefixes (soapenv:, ns2:, none at all,
    ...) don't matter. Duplicate leaf names within one body are skipped —
    ambiguous as a discriminator. Returns {} if the body isn't valid XML.
    """
    try:
        root = _ET.fromstring(body)
    except Exception:
        return {}
    values: dict[str, str] = {}
    seen_twice: set[str] = set()
    for el in root.iter():
        if len(el) == 0 and el.text and el.text.strip():
            name = _local_name(el.tag)
            if name in values:
                seen_twice.add(name)
            else:
                values[name] = el.text.strip()
    for name in seen_twice:
        values.pop(name, None)
    return values


def _json_leaf_values(body: str) -> dict[str, str]:
    """Map {top-level-key: value} for a captured JSON body's scalar fields.

    Restricted to top-level keys (not nested paths) so the JSONPath filter
    built in _differentiate_bodies stays a simple, always-correct
    "$[?(@.key=='value')]" expression. Returns {} if not valid JSON or the
    top level isn't an object.
    """
    try:
        data = _json.loads(body)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        k: str(v) for k, v in data.items()
        if isinstance(v, (str, int, float, bool)) and v not in (None, "")
    }


def _xpath_literal(value: str) -> str:
    """Build an XPath 1.0 string literal for `value` (no escape mechanism in
    XPath 1.0, so pick whichever quote character isn't already in the value,
    or fall back to concat() when it contains both)."""
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


class _Differentiation(NamedTuple):
    """Result of _differentiate_bodies: per-body MatchCondition for the
    static-mapping generator, plus the raw discriminator field name/type/
    values for generator/lookup_table.py to build a lookup table from
    instead, when the capture count crosses LOOKUP_TABLE_THRESHOLD. Both
    consumers are built from the same chosen field so they can never
    disagree about which field actually distinguishes these captures.
    """
    conditions: list[Optional[MatchCondition]]
    discriminator_type: Optional[str]   # "xpath" | "json"
    discriminator_field: Optional[str]
    values: list[Optional[str]]         # per-body raw discriminator value


def _no_differentiation(n: int) -> _Differentiation:
    return _Differentiation([None] * n, None, None, [None] * n)


def _differentiate_bodies(bodies: list[str]) -> _Differentiation:
    """Given N request bodies captured for the same method+URL, find a body
    field whose value differs across every capture — the same manual
    pattern used earlier for same-URL SOAP collisions, applied
    automatically — and return both a per-body MatchCondition (for the
    static-mapping generator) and the raw field name/type/values (for the
    lookup-table generator). Returns an all-None _Differentiation when no
    reliable single-field differentiator exists (mixed/unparseable bodies,
    or no field both present everywhere and distinct everywhere).
    """
    if len(bodies) < 2:
        return _no_differentiation(len(bodies))

    stripped = [b.lstrip() for b in bodies]
    is_xml = all(s.startswith("<") for s in stripped)
    is_json = all(s[:1] in "{[" for s in stripped)

    if is_xml:
        per_body = [_xml_leaf_values(b) for b in bodies]
    elif is_json:
        per_body = [_json_leaf_values(b) for b in bodies]
    else:
        return _no_differentiation(len(bodies))

    if any(not m for m in per_body):
        return _no_differentiation(len(bodies))

    common_keys = set(per_body[0])
    for m in per_body[1:]:
        common_keys &= set(m)

    chosen_key: Optional[str] = None
    for key in per_body[0]:  # preserve document order of the first body
        if key not in common_keys:
            continue
        values = [m[key] for m in per_body]
        if len(set(values)) == len(values):  # every capture has a distinct value
            chosen_key = key
            break

    if chosen_key is None:
        return _no_differentiation(len(bodies))

    conditions: list[Optional[MatchCondition]] = []
    raw_values: list[Optional[str]] = []
    for m in per_body:
        value = m[chosen_key]
        raw_values.append(value)
        if is_xml:
            xpath = f"//*[local-name()='{chosen_key}' and text()={_xpath_literal(value)}]"
            conditions.append(MatchCondition(type=MatchType.BODY_XPATH, value=xpath))
        else:
            escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            jsonpath = f"$[?(@.{chosen_key}=='{escaped}')]"
            conditions.append(MatchCondition(type=MatchType.BODY_JSON_PATH, value=jsonpath))
    return _Differentiation(
        conditions=conditions,
        discriminator_type="xpath" if is_xml else "json",
        discriminator_field=chosen_key,
        values=raw_values,
    )


# ── inline variant ────────────────────────────────────────────────────────────

def _parse_inline_content(
    content: str, source_name: str, hint_filename: str
) -> list[ParsedStub]:
    """Parse the inline (unlabelled) CA LISA format.

    Scans for every "={Method=" (request) and "ResponseHeader={StatusCode=" /
    bare "={StatusCode=" (response) marker in document order — one file may
    hold a single pair, or several same-URL captures back to back (repeated
    calls to the same operation with different payloads, or several
    ZIP-paired pairs concatenated together); each becomes its own capture,
    fed through the same _build_stub_from_captures multi-capture pairing and
    same-URL differentiation the labelled variant uses. An earlier version
    of this parser only ever looked at the first request/response marker and
    silently dropped or garbled anything recorded after it — this way
    inline-variant files get the identical treatment labelled-variant files
    already did.
    """
    captures = _scan_inline_captures(content, hint_filename, source_name)
    return _build_stub_from_captures(captures, source_name, hint_filename)


def _scan_inline_captures(
    content: str, hint_filename: str, source_name: str
) -> list[_Capture]:
    """Split inline-variant content into every request/response capture it
    contains, in document order, and fully resolve each via the existing
    single-block parsers (_parse_inline_request / _parse_inline_response) —
    this only adds the segmentation those two never needed to do themselves.
    """
    n = len(content)

    def _next_marker(start: int) -> Optional[tuple[int, str, int]]:
        # Searching the three patterns independently and taking the
        # earliest start (rather than one combined regex) sidesteps overlap:
        # _BARE_RESPONSE_RE also matches the "={StatusCode=" tail of
        # "ResponseHeader={StatusCode=", but that occurrence is always later
        # than _INLINE_RESPONSE_RE's match on the same text, so the minimum
        # still picks the correct (earlier) marker when a "ResponseHeader="
        # label is present. Returns (start, kind, match_end) — callers must
        # resume their next search from match_end, not start+1, or
        # _BARE_RESPONSE_RE re-matches its own tail inside the marker just
        # found and wrongly truncates that capture's segment.
        best: Optional[tuple[int, str, int]] = None
        for pattern, kind in (
            (_REQUEST_RE, "request"),
            (_INLINE_RESPONSE_RE, "response"),
            (_BARE_RESPONSE_RE, "response"),
        ):
            m = pattern.search(content, start)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), kind, m.end())
        return best

    captures: list[_Capture] = []
    marker = _next_marker(0)
    if marker is None:
        raise ValueError(
            "Cannot find a request (={Method=) or response ('ResponseHeader={' "
            "or a bare '={StatusCode=') block in inline-variant CA LISA content."
        )

    while marker is not None:
        marker_pos, capture_type, marker_end = marker
        nxt = _next_marker(marker_end)
        end = nxt[0] if nxt else n
        segment = content[marker_pos:end]

        if capture_type == "request":
            method, url, headers, body = _parse_inline_request(segment)
            captures.append(_Capture("request", method, url, None, headers, body))
        else:
            status, headers, body = _parse_inline_response(segment, hint_filename or source_name)
            captures.append(_Capture("response", None, None, status, headers, body))

        marker = nxt

    return captures


def _parse_inline_request(text: str) -> tuple[str, str, dict[str, str], str]:
    """Return (method, url, request_headers, request_body) from inline-variant request text."""
    text = text.strip()

    # Strip leading = before the block
    if text.startswith("="):
        text = text[1:].lstrip()

    if not text.startswith("{"):
        raise ValueError("Inline-variant request: expected '{' after '='")

    block_end = _find_block_end(text, 0)
    block_text = text[:block_end]

    parsed = _parse_kvblock(block_text)
    block_end = _consume_sibling_kv(text, block_end, parsed)
    body = text[block_end:].strip()

    method = parsed.get("Method", "GET")
    url = parsed.get("URL", "/")
    headers = _extract_http_headers(parsed)
    return method, url, headers, body


def _parse_inline_response(
    text: str, filename_hint: str
) -> tuple[int, dict[str, str], str]:
    """Return (status_code, response_headers, response_body) from inline-variant response text.

    Accepts both sub-forms: labelled "ResponseHeader={...}" and the bare
    "={StatusCode=...}" block some tools export with no label at all.
    """
    text = text.strip()

    if not (text.startswith("ResponseHeader=") or text.startswith("=")):
        raise ValueError(
            "Inline-variant response: expected 'ResponseHeader={' or a bare '={StatusCode=' at start"
        )

    brace_start = text.index("{")
    block_end = _find_block_end(text, brace_start)
    block_text = text[brace_start:block_end]
    parsed = _parse_kvblock(block_text)
    block_end = _consume_sibling_kv(text, block_end, parsed)

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


def _consume_sibling_kv(text: str, start: int, parsed: dict[str, Any]) -> int:
    """Absorb additional top-level Key="value" / Key={...} tokens after `start`,
    merging them into `parsed`. Returns the index where the real body begins.

    Most CA LISA captures nest everything (httpDetails, MessageType, etc.) inside
    one well-formed block, so _find_block_end's first match already covers the
    whole header and this is a no-op. Some captures — seen in manually reformatted
    SOAP/XML files — close that outer block early (right after URL=) and emit
    httpDetails (and therefore httpHeaders / SOAPAction) as a separate sibling
    block instead of nesting it. Without this, those siblings get silently
    swallowed into what looks like the body, and headers like SOAPAction — often
    the only thing distinguishing SOAP operations sharing one URL — go missing.
    """
    i = start
    n = len(text)
    while True:
        j = i
        while j < n and text[j] in " \t\n\r}":
            j += 1
        m = _TOP_LEVEL_KEY_RE.match(text, j)
        if not m:
            return j
        key = m.group(1)
        val_start = m.end()
        if val_start < n and text[val_start] == "{":
            block_end = _find_block_end(text, val_start)
            parsed[key] = _parse_kvblock(text[val_start:block_end])
            i = block_end
        elif val_start < n and text[val_start] == '"':
            end_quote = text.find('"', val_start + 1)
            if end_quote == -1:
                return j
            parsed[key] = text[val_start + 1 : end_quote]
            i = end_quote + 1
        else:
            return j


def _parse_kvblock(text: str) -> dict[str, Any]:
    """Parse a CA LISA key=value block.

    Handles:
      Method="POST"              → {"Method": "POST"}
      httpDetails={Version="1.1"} → {"httpDetails": {"Version": "1.1"}}
    """
    text = text.strip()
    if text.startswith("{"):
        # Strip outer braces. CA LISA sometimes omits the matching closing brace
        # (e.g. the labelled variant's outer block), so only strip closing } when it actually
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


# ── content-type inference ────────────────────────────────────────────────────

def _infer_content_type(body: str) -> Optional[str]:
    """Guess a Content-Type from a response body when the capture recorded none.

    Some captures (hand-trimmed or minimal exports) omit headers entirely,
    including Content-Type. Without it, WireMock serves the replayed body with
    no Content-Type header at all, which trips up strict clients on both
    sides: REST clients expecting application/json, and SOAP clients expecting
    text/xml or application/soap+xml. This only fires when nothing was
    captured — an explicit Content-Type header always wins.

    Structural sniff only (leading character / root element), same principle
    as the rest of this parser: no assumption about which client, service, or
    schema produced the body — just "does this look like JSON or XML".
    """
    stripped = body.lstrip()
    if not stripped:
        return None
    if stripped[0] in "{[":
        return "application/json"
    if stripped.startswith("<"):
        if _SOAP_ENVELOPE_RE.search(stripped):
            return "text/xml;charset=utf-8"
        return "application/xml"
    return None


def _ensure_content_type(headers: dict[str, str], body: str) -> dict[str, str]:
    """Add an inferred Content-Type to `headers` if one wasn't captured."""
    if not body or any(k.lower() == "content-type" for k in headers):
        return headers
    inferred = _infer_content_type(body)
    if not inferred:
        return headers
    return {**headers, "Content-Type": inferred}


# ── misc helpers ──────────────────────────────────────────────────────────────

def _stub_name_from_source(source: str) -> str:
    """Derive a human-readable stub name from the source filename."""
    import os
    name = os.path.basename(source)
    # Strip extensions and timestamp suffixes like _20260610_100059
    name = re.sub(r'_\d{8}_\d{6}', '', name)
    name = re.sub(r'\.(txt|json|xml|zip)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[_\-]+', ' ', name).strip()
    return name or "CA LISA Stub"
