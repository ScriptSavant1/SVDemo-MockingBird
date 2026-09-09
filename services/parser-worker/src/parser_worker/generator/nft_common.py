"""Shared per-scenario data resolution for NFT script generation, used by
both generator/jmeter.py (Phase 1) and generator/devweb.py (Phase 2). See
docs/progress/PHASE1_JMETER_NFT_GENERATION.md and
docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md.

Extracted from generator/jmeter.py as a pure, behavior-preserving move —
nothing about how a row/CSV field is built changed when this module was
created; only the tool consuming that data differs (a .jmx for JMeter, a
DevWeb main.js + parameters.yml for VuGen).

Row shape (`requestPath,requestBody,expectedStatus`) and CSV escaping are
identical for both engines: JMeter's CSVDataSet and DevWeb's CSV parameter
files are both plain, header-row, comma-separated files (see the DevWeb
"Parameterize values" doc), so one shared implementation is correct for
both rather than two copies that could drift.

Embedded newlines in a captured/synthesized body are collapsed to a single
space before being written to any CSV field. This was *verified* necessary
for JMeter's CSVDataSet (it reads its file line-by-line before applying
quote/delimiter parsing, so a real embedded newline breaks row parsing even
with quoting enabled). The official DevWeb parameterization doc does not
confirm multi-line quoted fields are safe either, so the same conservative
collapsing is applied for DevWeb too, rather than assuming the two engines'
CSV readers behave differently without evidence. Safe for both XML and
JSON bodies: whitespace between XML tags/tokens is insignificant, and a
raw literal newline inside a JSON string value isn't valid JSON to begin
with (it would already be \\n-escaped in the source text).
"""
from __future__ import annotations

import html
import json
import re

from ..models import MatchType, ParsedScenario, ParsedStub

_SAFE_CHAR_RE = re.compile(r"[^\w\s-]")
_WHITESPACE_RUN_RE = re.compile(r"[\r\n]+\s*")

OUT_OF_SCOPE_NOTE = (
    "SOAP WS-Security auth headers, fault/delay scenario replication, and "
    "assertions on Handlebars-templated ({{...}}) response content are not "
    "generated in this phase."
)


class Row:
    __slots__ = ("path", "body", "status")

    def __init__(self, path: str, body: str, status: int):
        self.path = path
        self.body = body
        self.status = status


def scenario_row(stub: ParsedStub, scenario: ParsedScenario) -> Row:
    path = scenario.url_override or stub.request.url
    body = scenario.captured_request_body or _synthesise_minimal_body(stub, scenario)
    return Row(path=path, body=_collapse_body_whitespace(body), status=scenario.status)


def _synthesise_minimal_body(stub: ParsedStub, scenario: ParsedScenario) -> str:
    """Build a body guaranteed to satisfy this scenario's own match
    condition, for stubs whose source parser didn't record a real request
    body (anything other than CA LISA). Never an arbitrary placeholder —
    always derived from the same match data WireMock itself would check.
    """
    if scenario.match.type == MatchType.BODY_XPATH and stub.lookup_discriminator_field and scenario.lookup_key:
        field = stub.lookup_discriminator_field
        value = _xml_escape_text(scenario.lookup_key)
        return f"<request><{field}>{value}</{field}></request>"
    if scenario.match.type == MatchType.BODY_JSON_PATH and stub.lookup_discriminator_field and scenario.lookup_key:
        return json.dumps({stub.lookup_discriminator_field: scenario.lookup_key})
    # No body-based discriminator (url-segment stubs, or a plain
    # single-scenario stub) — body content doesn't affect matching, so any
    # well-formed placeholder works. Match the captured Content-Type when
    # we have one, to at least send a shape a real backend would expect.
    content_type = next(
        (v for k, v in stub.request.required_headers.items() if k.lower() == "content-type"), ""
    ).lower()
    if "json" in content_type:
        return "{}"
    if "xml" in content_type:
        return "<request/>"
    return ""


def _collapse_body_whitespace(body: str) -> str:
    """Collapse embedded newlines (and the indentation whitespace that
    typically follows one in a pretty-printed capture) to a single space.
    See the module docstring for why this is required for both target
    engines' CSV readers.
    """
    return _WHITESPACE_RUN_RE.sub(" ", body).strip()


def _xml_escape_text(value: str) -> str:
    return html.escape(value, quote=False)


# ── CSV ────────────────────────────────────────────────────────────────────────

CSV_HEADER = "requestPath,requestBody,expectedStatus"


def build_csv(rows: list[Row]) -> str:
    lines = [CSV_HEADER]
    for row in rows:
        lines.append(",".join([
            csv_field(row.path),
            csv_field(row.body),
            csv_field(str(row.status)),
        ]))
    return "\n".join(lines) + "\n"


def csv_field(value: str) -> str:
    """RFC4180-style: always quote, double any embedded quote. Value is
    assumed already single-line (see _collapse_body_whitespace)."""
    return '"' + value.replace('"', '""') + '"'


def safe_filename(name: str) -> str:
    safe = _SAFE_CHAR_RE.sub("", name).strip().replace(" ", "-").lower()
    return safe[:80]
