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


def should_use_lookup_table(stub: ParsedStub) -> bool:
    """True if `stub` was parsed with a discriminator — a same-URL body
    field (ca_lisa_parser._differentiate_bodies) or a varying URL path
    segment (ca_lisa_parser._detect_url_segment_pattern) — and has enough
    captured variants to make the lookup-table engine worthwhile instead of
    one static WireMock mapping per scenario."""
    has_discriminator = stub.lookup_discriminator_field is not None or stub.lookup_url_pattern is not None
    return (
        has_discriminator
        and len(stub.scenarios) > LOOKUP_TABLE_THRESHOLD
        and all(s.lookup_key is not None for s in stub.scenarios)
    )


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
    # Exactly one of urlPath/urlPattern is non-null: url-segment stubs match
    # any concrete URL fitting the shape via a regex (the discriminator IS
    # the matched segment, no body inspection needed); body-discriminated
    # stubs match one exact URL and extract the discriminator from the body.
    is_url_segment = stub.lookup_discriminator_type == "url-segment"
    return {
        "method": stub.request.method.value,
        "urlPath": None if is_url_segment else stub.request.url,
        "urlPattern": stub.lookup_url_pattern if is_url_segment else None,
        "requiredHeaders": {
            k: v for k, v in stub.request.required_headers.items() if v != "*"
        },
        "discriminatorType": stub.lookup_discriminator_type,
        "discriminatorField": None if is_url_segment else stub.lookup_discriminator_field,
        "entries": [
            {
                "key": scenario.lookup_key,
                "status": scenario.status,
                "headers": scenario.response_headers,
                "body": scenario.body,
            }
            for scenario in stub.scenarios
        ],
    }


def _safe_filename(stub_name: str) -> str:
    safe = _SAFE_CHAR_RE.sub("", stub_name).strip().replace(" ", "_").lower()
    return safe[:100] or "stub"
