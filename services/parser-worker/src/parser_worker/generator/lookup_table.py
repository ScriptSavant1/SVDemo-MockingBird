"""Generates a dynamic lookup-table data file for a CA LISA stub whose
same-URL capture count is large enough that WireMock's normal per-scenario
static JSON mapping approach (see generator/wiremock.py) stops being the
right tool.

Static per-capture mappings are simple, human-inspectable in WireMock's
admin UI, and perform fine up to real scale — WireMock comfortably matches
hundreds of same-URL mappings well within a 10K+ TPS target, and nothing
here changes that path. This module only kicks in once one recorded
operation has more captured variants than LOOKUP_TABLE_THRESHOLD, where
WireMock's sequential per-mapping match evaluation (worst case O(N) XPath/
JSONPath evaluations per request, for N mappings sharing a URL) starts to
show up as real per-request cost. Past that point, a single generic route
backed by an O(1) in-memory hashmap lookup (DynamicLookupRequestFilter.java,
registered into WireMock's own request pipeline the same way
WsSecurityRequestFilter already is) scales to any capture count at constant
per-request cost.

The two generators are mutually exclusive per stub — see
generator/wiremock.py's build_wiremock_mappings, which skips any stub this
module claims (should_use_lookup_table) so a stub is never represented both
ways at once.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..models import ParsedFile, ParsedStub

# Real-world CA LISA exports of one operation with dozens to hundreds of
# recorded variants are exactly the case this exists for (see the "84
# services from one operation" report that prompted this module). Below
# this count, static per-capture mappings are simpler and just as fast.
LOOKUP_TABLE_THRESHOLD = 15

_SAFE_CHAR_RE = re.compile(r"[^\w\s-]")
# Same pattern generator/wiremock.py's _apply_url_matcher already uses for
# "{brand}"-style path templates — duplicated here rather than imported
# because wiremock.py imports should_use_lookup_table FROM this module, and
# importing back would be circular. One-line regex; not worth a refactor to
# dedupe.
_PATH_PARAM_RE = re.compile(r'\{(\w+)\}')


def should_use_lookup_table(stub: ParsedStub) -> bool:
    """True if `stub` was parsed with a discriminator — a same-URL body
    field (ca_lisa_parser._differentiate_bodies) or a varying URL path
    segment (ca_lisa_parser._detect_url_segment_pattern) — and either has
    enough captured variants to make the lookup-table engine worthwhile
    instead of one static WireMock mapping per scenario, or was explicitly
    authored as a keyed lookup regardless of count (ParsedStub.force_lookup_table
    — xlsx CSV-backed lookups only, see models.py).

    Only scenarios that actually carry a lookup_key count towards the
    threshold and become lookup-table entries (see _build_table). A stub can
    mix keyed scenarios with a plain always-match catch-all in the same
    scenario list — e.g. an xlsx stub with two CSV-driven scenarios plus one
    Default row — unlike CA LISA-sourced stubs, which are always all-keyed
    or none (see ca_lisa_parser._differentiate_bodies: it returns a value
    for every capture or none at all, never a mix). generator/wiremock.py's
    build_wiremock_mappings still emits that catch-all as a normal static
    mapping — the two generators aren't mutually exclusive at the
    scenario level, only at the "which scenarios does each one own" level.
    """
    keyed_scenarios = [s for s in stub.scenarios if s.lookup_key is not None]
    has_discriminator = stub.lookup_discriminator_field is not None or stub.lookup_url_pattern is not None
    if not has_discriminator or not keyed_scenarios:
        return False
    return stub.force_lookup_table or len(keyed_scenarios) > LOOKUP_TABLE_THRESHOLD


def build_lookup_table_files(parsed: ParsedFile) -> dict[str, str]:
    """Build every qualifying stub's lookup table as
    {"lookup-tables/<name>.json": <json text>}, entirely in memory — no
    filesystem access. Empty when no stub in `parsed` crosses
    LOOKUP_TABLE_THRESHOLD.
    """
    return {
        f"lookup-tables/{_safe_filename(stub.name)}.json": json.dumps(
            _build_table(stub), indent=2, ensure_ascii=False
        )
        for stub in parsed.stubs
        if should_use_lookup_table(stub)
    }


def generate_lookup_tables(parsed: ParsedFile, output_dir: Path) -> list[Path]:
    """Write one lookup-table JSON file per qualifying stub into
    src/main/resources/lookup-tables/ (loaded at startup by
    DynamicLookupRequestFilter). Returns the created file paths.

    Thin wrapper around build_lookup_table_files for callers that need real
    files (e.g. a local `mvn package` / CLI workflow) — a hot upload path
    that just needs the bytes for a ZIP should call build_lookup_table_files
    directly instead and skip the disk round-trip entirely.
    """
    created: list[Path] = []
    for relative_path, content in build_lookup_table_files(parsed).items():
        path = output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return created


def _build_table(stub: ParsedStub) -> dict:
    # url-segment stubs match any concrete URL fitting the shape via a
    # regex — the discriminator IS the matched segment, no body inspection.
    #
    # Body-discriminated stubs normally match one exact, literal URL and
    # extract the discriminator from the body — but an xlsx stub can ALSO
    # carry a "{brand}"-style templated URL alongside a body discriminator
    # (e.g. LKP01: "/{brand}/ACCTSVC120/01" + a "bban" body field) —
    # two independent things a real request varies (the brand segment AND
    # the bban value), not the url-segment case (where the URL's own varying
    # segment IS the whole discriminator). Found live: without this check,
    # such a stub's urlPath in the table is the LITERAL, un-substituted
    # "{brand}" string, which can never equal any real request's resolved
    # path — DynamicLookupRequestFilter's exact-URL HashMap lookup misses
    # on every single request, and it silently, permanently falls through
    # to WireMock's static Default mapping instead of ever consulting the
    # lookup table at all. Caught only by actually deploying and curling a
    # generated stub, not by any unit test against the Python objects alone.
    is_url_segment = stub.lookup_discriminator_type == "url-segment"
    has_url_template = not is_url_segment and bool(_PATH_PARAM_RE.search(stub.request.url))
    url_pattern = (
        stub.lookup_url_pattern if is_url_segment
        else _PATH_PARAM_RE.sub(r'[^/]+', stub.request.url) if has_url_template
        else None
    )
    return {
        "method": stub.request.method.value,
        "urlPath": None if (is_url_segment or has_url_template) else stub.request.url,
        "urlPattern": url_pattern,
        "requiredHeaders": {
            k: v for k, v in stub.request.required_headers.items() if v != "*"
        },
        "discriminatorType": stub.lookup_discriminator_type,
        # May be a single field name or a comma-separated composite list
        # (xlsx only) — DynamicLookupRequestFilter.java splits on "," itself,
        # nothing here needs to know the difference. Still set even when this
        # route is a templated-URL pattern route (has_url_template) — that's
        # exactly the signal the Java side uses to tell "pattern route whose
        # discriminator comes from the body" apart from "pattern route whose
        # discriminator IS the matched URL segment" (url-segment stubs, where
        # this stays None).
        "discriminatorField": None if is_url_segment else stub.lookup_discriminator_field,
        "entries": [
            {
                "key": scenario.lookup_key,
                "status": scenario.status,
                "headers": scenario.response_headers,
                "body": scenario.body,
            }
            for scenario in stub.scenarios
            # Only keyed scenarios become table entries — an unkeyed
            # catch-all (xlsx Default row) is handled by wiremock.py as a
            # normal static mapping instead (see should_use_lookup_table).
            if scenario.lookup_key is not None
        ],
    }


def _safe_filename(stub_name: str) -> str:
    safe = _SAFE_CHAR_RE.sub("", stub_name).strip().replace(" ", "_").lower()
    return safe[:100] or "stub"
