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
    """True if `stub` was parsed with a same-URL discriminator (see
    ca_lisa_parser._differentiate_bodies) and has enough captured variants
    to make the lookup-table engine worthwhile instead of one static
    WireMock mapping per scenario."""
    return (
        stub.lookup_discriminator_field is not None
        and len(stub.scenarios) > LOOKUP_TABLE_THRESHOLD
        and all(s.lookup_key is not None for s in stub.scenarios)
    )


def generate_lookup_tables(parsed: ParsedFile, output_dir: Path) -> list[Path]:
    """Write one lookup-table JSON file per qualifying stub into
    src/main/resources/lookup-tables/ (loaded at startup by
    DynamicLookupRequestFilter). Returns the created file paths — empty
    when no stub in `parsed` crosses LOOKUP_TABLE_THRESHOLD.
    """
    created: list[Path] = []
    tables_dir = output_dir / "lookup-tables"
    for stub in parsed.stubs:
        if not should_use_lookup_table(stub):
            continue
        tables_dir.mkdir(parents=True, exist_ok=True)
        path = tables_dir / f"{_safe_filename(stub.name)}.json"
        path.write_text(
            json.dumps(_build_table(stub), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        created.append(path)
    return created


def _build_table(stub: ParsedStub) -> dict:
    return {
        "method": stub.request.method.value,
        "urlPath": stub.request.url,
        "requiredHeaders": {
            k: v for k, v in stub.request.required_headers.items() if v != "*"
        },
        "discriminatorType": stub.lookup_discriminator_type,
        "discriminatorField": stub.lookup_discriminator_field,
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
