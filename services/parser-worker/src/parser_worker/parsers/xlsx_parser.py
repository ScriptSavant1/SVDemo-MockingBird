"""Mockingbird XLSX stub template parser (Phase 0 — dry-run validator only).

Reads the "mockingbird-stub-template.xlsx" shape: a "Stubs" tab (one row per
API operation) and a "Rules" tab (one row per response scenario for stubs
flagged data-driven), plus a zipped "data/" folder of response bodies and
CSV lookup files referenced from either tab via "file:<name>".

Why this does NOT implement BaseParser (parsers/base.py):
BaseParser.can_handle/validate/parse all take `content: str` — every other
parser's input is a single text file, decoded once by detector.py before any
parser sees it. An xlsx workbook is a binary zip-of-XML container, and this
format always arrives bundled with a whole folder of dependent response/
lookup files (never as one standalone text file) — forcing that shape through
a single `content: str` parameter would mean smuggling bytes and a multi-file
mapping through a string. Dispatched directly from detector.py's ZIP handler
instead, the same way CA LISA's zip-pair path bypasses the text-parser
registry for the same reason (see detector.py's `_detect_and_parse_zip`).

Phase 0 (validator): read-only validation, reporting every finding this
format's first real input (the pilot project) actually surfaced — missing
`file:` references, unfilled template placeholder rows, orphaned/inconsistent
Stubs<->Rules cross-references, missing catch-all rows, suspicious literal-
placeholder leakage, and CSV lookup header sanity.

Phase 1 (this pass — parse_xlsx_zip): builds real ParsedStub/ParsedScenario
objects for every stub that doesn't need the lookup-table engine (Phase 2 —
any Rules row with a Lookup File is skipped here, not misrepresented as a
static match). `Path / Expression` values are trusted VERBATIM as the real
JSONPath/XPath expression — this format's Rules tab asks the sheet author to
write the actual expression (its own placeholder text says "edit: request
field/xpath..."), so no auto-compilation from a bare field name happens here
(unlike CA LISA's _differentiate_bodies, which infers a match condition from
captured bodies because it has no human-authored expression to trust at all).
See the xlsx implementation plan (internal notes, not in this repo) for the full phase plan.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Optional

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from .. import error_codes as ec
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
from .ca_lisa_parser import _URL_SEGMENT_KEY_JOIN, _resolve_variables, _xpath_literal

# ── zip-level format sniffing (called from detector.py) ──────────────────────

REQUIRED_SHEETS = {"Stubs", "Rules"}

# Zip-bomb guard: this format's zips carry a whole data/ folder of response
# bodies, unlike CA LISA's zip path (which only ever reads a handful of
# *_Request_*/*_Response_* text files) — worth a real cap since every entry's
# bytes are read fully into memory before this parser reads a byte.
MAX_ZIP_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200MB
MAX_ZIP_ENTRIES = 2000

# Template placeholder text — the exact literal strings the shipped template
# leaves in every unfilled cell. A row containing these was never edited by
# whoever filled in the sheet; treated as "not usable yet", not as a real
# match condition (see the pilot-project input review, internal notes — this is the single
# biggest gap that review found: 0/176 rows had these replaced).
_PLACEHOLDER_TEXTS = {
    "(edit: request field/xpath that decides this branch)",
    "request matches this case (edit condition)",
    "request matches an error case (edit condition)",
}

# A literal, unresolved %%Token%% leaking into a field that isn't a response
# body (e.g. Response Content-Type = "%%Content-Type%%", a real bug found in
# the pilot sheet's LKP03_InitiateUpdate row) — these fields are never
# run through the %%Token%% -> Handlebars resolution pass Phase 1 applies to
# response bodies, so a literal placeholder here would ship as-is.
_LEGACY_TOKEN_RE = re.compile(r"%%[A-Za-z0-9_\-]+%%")

# A CSV lookup header row whose first cell looks like data, not a column name
# (found live: LKP03.csv's header was "833,action,flow#" — "833" is not a
# plausible column name).
_NUMERIC_LOOKING_RE = re.compile(r"^\d+$")


def sniff_xlsx_zip_entry(zf: zipfile.ZipFile) -> Optional[str]:
    """Return the name of the single .xlsx/.xlsm entry in `zf` that looks
    like a Mockingbird stub template (has both required sheets), or None if
    the zip doesn't contain one. Never raises on a malformed/foreign
    .xlsx/.xlsm — treated as "not this format", letting detector.py fall
    back to the CA LISA path.

    Matches .xlsm too (not just .xlsx) specifically so a macro-enabled
    workbook still gets identified as "this is the xlsx shape" and then
    rejected by check_zip_safety with a clear, specific message — rather
    than silently falling through to an unrelated, confusing "no CA LISA
    capture files found" error.
    """
    candidate_names = [
        n for n in zf.namelist()
        if n.lower().endswith((".xlsx", ".xlsm")) and not n.startswith("__MACOSX")
    ]
    if len(candidate_names) != 1:
        return None

    name = candidate_names[0]
    try:
        raw = zf.read(name)
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True, keep_links=False)
        sheet_names = set(wb.sheetnames)
        wb.close()
    except Exception:
        return None

    return name if REQUIRED_SHEETS.issubset(sheet_names) else None


def check_zip_safety(zf: zipfile.ZipFile) -> Optional[str]:
    """Return an error message if `zf` fails basic zip-bomb / zip-slip / macro
    guards, or None if it's safe to extract in full into memory.

    Deliberately checks metadata (ZipInfo.file_size, .filename) before any
    entry is decompressed — a zip bomb's whole point is that its compressed
    size lies about its decompressed size, so the guard has to work off the
    central directory's declared sizes, not by reading and measuring.
    """
    total_uncompressed = 0
    entry_count = 0
    for info in zf.infolist():
        if info.filename.startswith("__MACOSX"):
            continue
        entry_count += 1
        if entry_count > MAX_ZIP_ENTRIES:
            return f"ZIP contains more than {MAX_ZIP_ENTRIES} entries — rejected as a possible zip bomb."

        # Zip-slip: reject any entry whose name would resolve outside the
        # extraction root. This parser never writes entries to disk by name
        # (everything is read via zf.read() into an in-memory dict, see
        # extract_data_files below), but reject defensively anyway — a
        # filename this shape is never legitimate input from this format.
        if info.filename.startswith("/") or ".." in info.filename.replace("\\", "/").split("/"):
            return f"ZIP entry has an unsafe path and was rejected: {info.filename!r}"

        if info.filename.lower().endswith(".xlsm"):
            return (
                f"ZIP contains a macro-enabled workbook ({info.filename}) — "
                "not accepted. Save as .xlsx (no macros) and re-upload."
            )

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            return (
                f"ZIP's uncompressed contents exceed the "
                f"{MAX_ZIP_UNCOMPRESSED_BYTES // (1024 * 1024)}MB limit — rejected as a possible zip bomb."
            )

    return None


def extract_data_files(zf: zipfile.ZipFile, xlsx_entry_name: str) -> dict[str, bytes]:
    """Read every non-xlsx entry in `zf` into memory, keyed by basename only
    (never by the entry's full path) — so a `file:<name>` reference resolves
    by filename regardless of whether the SV team nested it under `data/` or
    left it at the zip root (see plan §3.1), and so a crafted entry path can
    never influence where these bytes end up (nothing here is ever written
    to a real filesystem path derived from a zip entry name).
    """
    import os

    out: dict[str, bytes] = {}
    for info in zf.infolist():
        if info.filename == xlsx_entry_name or info.filename.startswith("__MACOSX") or info.is_dir():
            continue
        basename = os.path.basename(info.filename)
        if not basename:
            continue
        out[basename] = zf.read(info.filename)
    return out


# ── sheet reading ─────────────────────────────────────────────────────────────

_STUBS_HEADER_ROW = 2
_RULES_HEADER_ROW = 2


@dataclass
class StubRow:
    row: int
    name: str
    protocol: str = ""
    method: str = ""
    url_path: str = ""
    response_status: str = ""
    response_content_type: str = ""
    response_body: str = ""
    data_driven: bool = False


@dataclass
class RuleRow:
    row: int
    stub_name: str
    order: object = None
    scenario: str = ""
    extract_field: str = ""
    extract_from: str = ""
    path_expression: str = ""
    lookup_file: str = ""
    match_on: str = ""
    response_status: str = ""
    response_body: str = ""


def _header_index(ws: Worksheet, header_row: int) -> dict[str, int]:
    """Map header cell text -> 1-indexed column number, so row-reading is
    resilient to the template's columns being reordered in a future
    revision (read by name, never by hardcoded position)."""
    index: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        value = ws.cell(row=header_row, column=col).value
        if isinstance(value, str) and value.strip():
            index[value.strip()] = col
    return index


def _cell(ws: Worksheet, row: int, header_index: dict[str, int], header: str) -> str:
    col = header_index.get(header)
    if col is None:
        return ""
    value = ws.cell(row=row, column=col).value
    return "" if value is None else str(value).strip()


def read_stubs_sheet(ws: Worksheet) -> list[StubRow]:
    idx = _header_index(ws, _STUBS_HEADER_ROW)
    rows: list[StubRow] = []
    for r in range(_STUBS_HEADER_ROW + 1, ws.max_row + 1):
        name = _cell(ws, r, idx, "Stub Name")
        if not name:
            continue
        rows.append(StubRow(
            row=r,
            name=name,
            protocol=_cell(ws, r, idx, "Protocol"),
            method=_cell(ws, r, idx, "Method"),
            url_path=_cell(ws, r, idx, "URL Path"),
            response_status=_cell(ws, r, idx, "Response Status"),
            response_content_type=_cell(ws, r, idx, "Response Content-Type"),
            response_body=_cell(ws, r, idx, "Response Body  (inline, file:<name>, or SEE Rules)")
            or _cell(ws, r, idx, "Response Body"),
            data_driven=_cell(ws, r, idx, "Data-driven?").lower() == "yes",
        ))
    return rows


def read_rules_sheet(ws: Worksheet) -> list[RuleRow]:
    idx = _header_index(ws, _RULES_HEADER_ROW)
    rows: list[RuleRow] = []
    for r in range(_RULES_HEADER_ROW + 1, ws.max_row + 1):
        stub_name = _cell(ws, r, idx, "Stub Name")
        if not stub_name:
            continue
        rows.append(RuleRow(
            row=r,
            stub_name=stub_name,
            order=ws.cell(row=r, column=idx.get("Order", 0)).value if idx.get("Order") else None,
            scenario=_cell(ws, r, idx, "Scenario"),
            extract_field=_cell(ws, r, idx, "Extract Field"),
            extract_from=_cell(ws, r, idx, "Extract From"),
            path_expression=_cell(ws, r, idx, "Path / Expression"),
            lookup_file=_cell(ws, r, idx, "Lookup File"),
            match_on=_cell(ws, r, idx, "Match On"),
            response_status=_cell(ws, r, idx, "Response Status"),
            response_body=_cell(ws, r, idx, "Response Body (file:<name>)")
            or _cell(ws, r, idx, "Response Body"),
        ))
    return rows


def _file_ref(body: str) -> Optional[str]:
    """Return the referenced filename if `body` is a `file:<name>` reference,
    else None (an inline literal body, or a "SEE Rules tab" marker)."""
    body = body.strip()
    if body.lower().startswith("file:"):
        return body[len("file:"):].strip()
    return None


# ── dry-run validator ─────────────────────────────────────────────────────────

def validate_xlsx_zip(xlsx_bytes: bytes, data_files: dict[str, bytes]) -> ValidationResult:
    """Read `xlsx_bytes` as a Mockingbird stub template and cross-check it
    against `data_files` (basename -> bytes, from extract_data_files).

    Returns a ValidationResult whose `errors` are conditions that make the
    file impossible to use at all (unreadable workbook, missing required
    sheets, zero usable stub rows) and whose `warnings` are per-row findings
    that don't block reading the rest of the sheet but would silently produce
    broken or incomplete stubs if not fixed — every category here is
    empirically motivated by a real finding from the pilot project (see
    the pilot-project input review, internal notes), not a speculative checklist.
    """
    errors: list[ValidationError] = []
    warnings: list[str] = []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    except Exception as exc:
        return ValidationResult(
            valid=False,
            format_detected="mockingbird-xlsx-stub-template",
            errors=[ValidationError(message=f"Could not open workbook: {exc}", code=ec.UPL_WORKBOOK_INVALID)],
        )

    missing_sheets = REQUIRED_SHEETS - set(wb.sheetnames)
    if missing_sheets:
        return ValidationResult(
            valid=False,
            format_detected="mockingbird-xlsx-stub-template",
            errors=[ValidationError(message=f"Missing required sheet(s): {sorted(missing_sheets)}", code=ec.UPL_WORKBOOK_INVALID)],
        )

    stub_rows = read_stubs_sheet(wb["Stubs"])
    rule_rows = read_rules_sheet(wb["Rules"])

    if not stub_rows:
        return ValidationResult(
            valid=False,
            format_detected="mockingbird-xlsx-stub-template",
            errors=[ValidationError(message="'Stubs' tab has no stub rows (nothing after the header).", code=ec.UPL_WORKBOOK_INVALID)],
        )

    stub_names = {r.name for r in stub_rows}
    data_driven_names = {r.name for r in stub_rows if r.data_driven}
    rule_stub_names: dict[str, list[RuleRow]] = {}
    for rr in rule_rows:
        rule_stub_names.setdefault(rr.stub_name, []).append(rr)

    # Missing file: references — Stubs tab
    for sr in stub_rows:
        ref = _file_ref(sr.response_body)
        if ref and ref not in data_files:
            errors.append(ValidationError(
                field=f"Stubs!row{sr.row} ({sr.name})",
                message=f"Response body references 'file:{ref}' but that file is not in the uploaded zip.",
                code=ec.UPL_REFERENCED_FILE_MISSING,
                subject=ref,
            ))

    # Missing file: references — Rules tab, + placeholder/leakage checks
    for rr in rule_rows:
        ref = _file_ref(rr.response_body)
        if ref and ref not in data_files:
            errors.append(ValidationError(
                field=f"Rules!row{rr.row} ({rr.stub_name}/{rr.scenario})",
                message=f"Response body references 'file:{ref}' but that file is not in the uploaded zip.",
                code=ec.UPL_REFERENCED_FILE_MISSING,
                subject=ref,
            ))

        if rr.path_expression in _PLACEHOLDER_TEXTS or rr.match_on in _PLACEHOLDER_TEXTS:
            warnings.append(
                f"Rules!row{rr.row} ({rr.stub_name}/{rr.scenario}): 'Path / Expression' / 'Match On' "
                "still contains the template placeholder text — this scenario can never be selected "
                "and will effectively be unreachable until a real match condition is filled in."
            )

        if _LEGACY_TOKEN_RE.search(rr.response_status):
            warnings.append(
                f"Rules!row{rr.row} ({rr.stub_name}/{rr.scenario}): 'Response Status' contains a literal "
                f"'{rr.response_status}' placeholder token — this field is not resolved at generation time, "
                "so it would ship as-is instead of a real status code."
            )

    for sr in stub_rows:
        if _LEGACY_TOKEN_RE.search(sr.response_content_type):
            warnings.append(
                f"Stubs!row{sr.row} ({sr.name}): 'Response Content-Type' contains a literal "
                f"'{sr.response_content_type}' placeholder token instead of a real content type."
            )

    # Cross-reference integrity between Stubs and Rules tabs
    for name in data_driven_names:
        if name not in rule_stub_names:
            warnings.append(
                f"Stubs!{name}: marked 'Data-driven? = Yes' but has no matching rows on the Rules tab — "
                "this stub currently has no response at all."
            )
    for name, rows in rule_stub_names.items():
        if name not in stub_names:
            warnings.append(
                f"Rules tab has {len(rows)} row(s) for '{name}', which does not appear on the Stubs tab at all "
                "(typo in the stub name?)."
            )
        elif name not in data_driven_names:
            warnings.append(
                f"Rules tab has {len(rows)} row(s) for '{name}', but its Stubs row says "
                "'Data-driven? = No' — these Rules rows will be ignored."
            )

    # Missing catch-all per data-driven stub
    for name, rows in rule_stub_names.items():
        has_catch_all = any(rr.match_on.strip().lower() == "always" for rr in rows)
        if not has_catch_all:
            warnings.append(
                f"Rules!{name}: no row with Match On = 'always' (no Default/catch-all) — "
                "a request that doesn't match any listed condition will fall through to WireMock's "
                "generic 404 instead of a deliberate response."
            )

    # CSV lookup header sanity
    checked_csvs: set[str] = set()
    for rr in rule_rows:
        lf = rr.lookup_file.strip()
        if not lf or lf in checked_csvs:
            continue
        checked_csvs.add(lf)
        raw = data_files.get(lf)
        if raw is None:
            continue  # already reported above as a missing file: reference (if referenced) — avoid duplicate noise
        try:
            first_line = raw.decode("utf-8", errors="replace").splitlines()[0]
        except IndexError:
            warnings.append(f"Lookup file '{lf}' is empty.")
            continue
        first_cell = first_line.split(",")[0].strip()
        if _NUMERIC_LOOKING_RE.match(first_cell):
            warnings.append(
                f"Lookup file '{lf}': header row's first cell is '{first_cell}', which looks like data, "
                "not a column name — check row 1 is really a header."
            )

    summary = (
        f"{len(stub_rows)} stub(s), {len(rule_rows)} rule row(s) across {len(rule_stub_names)} "
        f"data-driven stub(s) — {len(errors)} blocking issue(s), {len(warnings)} warning(s)"
    )

    return ValidationResult(
        valid=len(errors) == 0,
        format_detected="mockingbird-xlsx-stub-template",
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


# ── Phase 1: building real ParsedStub/ParsedScenario objects ─────────────────

_SUPPORTED_PROTOCOLS = {"REST", "SOAP"}


def parse_xlsx_zip(
    xlsx_bytes: bytes, data_files: dict[str, bytes], source_name: str
) -> tuple[ParsedFile, list[str]]:
    """Build ParsedStub/ParsedScenario objects from a validated workbook.

    Only ever called after validate_xlsx_zip has confirmed the workbook is at
    least structurally readable (required sheets present, at least one stub
    row) — this function does not re-check that.

    Returns (parsed_file, skip_notes). A row/stub is silently EXCLUDED from
    parsed_file rather than represented with a broken/guessed match condition
    whenever it can't be built correctly — every exclusion is instead recorded
    as a human-readable entry in skip_notes, the same "partial failures become
    warnings" pattern detector.py's CA LISA zip path already uses. Never
    raises on a single bad row; one malformed stub must not block every other
    stub in the same workbook from generating.
    """
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    stub_rows = read_stubs_sheet(wb["Stubs"])
    rule_rows = read_rules_sheet(wb["Rules"])

    rules_by_stub: dict[str, list[RuleRow]] = {}
    for rr in rule_rows:
        rules_by_stub.setdefault(rr.stub_name, []).append(rr)

    stubs: list[ParsedStub] = []
    skip_notes: list[str] = []

    for sr in stub_rows:
        protocol = sr.protocol.strip().upper()
        if protocol and protocol not in _SUPPORTED_PROTOCOLS:
            skip_notes.append(
                f"{sr.name}: protocol '{sr.protocol}' is not REST/SOAP — the xlsx format only covers "
                "REST/SOAP (see the Kafka/MQ JSON formats for those transports). Skipped."
            )
            continue

        try:
            method = HttpMethod(sr.method.strip().upper())
        except ValueError:
            skip_notes.append(f"{sr.name}: unrecognised HTTP method '{sr.method}'. Skipped.")
            continue

        request_spec = ParsedRequestSpec(method=method, url=sr.url_path or "/")

        if not sr.data_driven:
            scenario, reason = _build_static_scenario(sr, data_files, source_name)
            if scenario is None:
                skip_notes.append(f"{sr.name}: {reason} Skipped.")
                continue
            stubs.append(ParsedStub(name=sr.name, request=request_spec, scenarios=[scenario]))
            continue

        rows = rules_by_stub.get(sr.name, [])
        if not rows:
            skip_notes.append(f"{sr.name}: marked data-driven but has no Rules rows. Skipped.")
            continue

        if any(rr.lookup_file.strip() for rr in rows):
            lookup_scenarios, disc_type, disc_field, lookup_notes = _build_lookup_table_scenarios(
                sr.name, rows, data_files, source_name, sr.response_content_type,
            )
            skip_notes.extend(f"{sr.name}: {n}" for n in lookup_notes)
            if not lookup_scenarios:
                skip_notes.append(f"{sr.name}: lookup-table stub produced no usable scenarios. Skipped.")
                continue
            stubs.append(ParsedStub(
                name=sr.name,
                request=request_spec,
                scenarios=lookup_scenarios,
                lookup_discriminator_type=disc_type,
                lookup_discriminator_field=disc_field,
                force_lookup_table=True,
            ))
            continue

        def _order_key(rr: RuleRow) -> float:
            try:
                return float(rr.order)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return float("inf")  # unordered rows sort last, never first

        scenarios: list[ParsedScenario] = []
        for rr in sorted(rows, key=_order_key):
            scenario, reason = _build_rule_scenario(rr, data_files, source_name, sr.response_content_type)
            if scenario is None:
                skip_notes.append(f"{sr.name}/{rr.scenario or f'row{rr.row}'}: {reason} Skipped.")
                continue
            scenarios.append(scenario)

        if not scenarios:
            skip_notes.append(f"{sr.name}: data-driven with no usable scenario rows after filtering. Skipped.")
            continue

        stubs.append(ParsedStub(name=sr.name, request=request_spec, scenarios=scenarios))

    parsed_file = ParsedFile(
        format="mockingbird-xlsx-stub-template",
        source_file=source_name,
        stubs=stubs,
    )
    return parsed_file, skip_notes


def _build_static_scenario(
    sr: StubRow, data_files: dict[str, bytes], source_name: str
) -> tuple[Optional[ParsedScenario], str]:
    body, reason = _resolve_body(sr.response_body, data_files, source_name)
    if body is None:
        return None, reason
    status = _parse_status(sr.response_status)
    if status is None:
        return None, f"'Response Status' ('{sr.response_status}') is not a plain integer."

    headers = _content_type_header(sr.response_content_type)
    return ParsedScenario(
        name="default",
        match=MatchCondition(type=MatchType.ALWAYS),
        status=status,
        response_headers=headers,
        body=body,
    ), ""


def _build_rule_scenario(
    rr: RuleRow, data_files: dict[str, bytes], source_name: str, content_type: str
) -> tuple[Optional[ParsedScenario], str]:
    body, reason = _resolve_body(rr.response_body, data_files, source_name)
    if body is None:
        return None, reason
    status = _parse_status(rr.response_status)
    if status is None:
        return None, f"'Response Status' ('{rr.response_status}') is not a plain integer."

    match_on = rr.match_on.strip().lower()
    if match_on == "always":
        match = MatchCondition(type=MatchType.ALWAYS)
    else:
        if not rr.path_expression or rr.path_expression in _PLACEHOLDER_TEXTS:
            return None, "'Path / Expression' is unfilled (still the template placeholder)."
        try:
            match_type = MatchType(rr.extract_from.strip().lower())
        except ValueError:
            return None, f"'Extract From' ('{rr.extract_from}') is not a recognised match type."
        if match_type not in (MatchType.BODY_JSON_PATH, MatchType.BODY_XPATH):
            return None, f"'Extract From' ('{rr.extract_from}') is not body-json-path/body-xpath."
        match = MatchCondition(type=match_type, value=rr.path_expression)

    headers = _content_type_header(content_type)
    return ParsedScenario(
        name=rr.scenario or f"row{rr.row}",
        match=match,
        status=status,
        response_headers=headers,
        body=body,
    ), ""


def _content_type_header(content_type: str) -> dict[str, str]:
    ct = content_type.strip()
    if not ct or _LEGACY_TOKEN_RE.search(ct):
        return {}
    return {"Content-Type": ct}


def _resolve_body(
    raw: str, data_files: dict[str, bytes], source_name: str
) -> tuple[Optional[str], str]:
    """Resolve a Stubs/Rules "Response Body" cell into real response text.

    Returns (text, "") on success, or (None, reason) when the body can't be
    resolved at all — a missing file: reference (already a hard error from
    validate_xlsx_zip, so this is a second, cheaper line of defence, not the
    first place it's caught) or an empty/SEE-RULES marker cell.
    """
    raw = raw.strip()
    ref = _file_ref(raw)
    if ref is not None:
        content = data_files.get(ref)
        if content is None:
            return None, f"references 'file:{ref}', which is not in the uploaded zip."
        text = content.decode("utf-8", errors="replace")
    elif not raw or raw.upper() == "SEE RULES TAB":
        return None, "has no response body (blank or 'SEE Rules tab' with no matching content)."
    else:
        text = raw

    resolved, _ = _resolve_variables(text, source_name)
    return resolved, ""


def _parse_status(raw: str) -> Optional[int]:
    raw = raw.strip()
    try:
        return int(float(raw))
    except ValueError:
        return None


# ── Phase 2: CSV-driven dynamic lookup routing ────────────────────────────────
#
# A Rules row with a Lookup File isn't a static match condition at all — the
# real routing decision comes from a CSV key->outcome table (LKP01.csv,
# LKP03.csv in the pilot data): each CSV row's key column(s) become a
# composite discriminator value, and its outcome column names WHICH Rules
# row's response applies. This is architecturally different from a normal
# Rules row (see _build_rule_scenario) and from CA LISA's lookup-table stubs
# (ca_lisa_parser._differentiate_bodies always keys either every captured
# scenario or none — never a mix of keyed + a separate unkeyed catch-all).

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")
_TRAILING_DIGITS_RE = re.compile(r"\d+$")


def _normalize_scenario_text(text: str) -> str:
    return _NON_ALNUM_RE.sub("", text.lower())


def _resolve_outcome_label(label: str, scenario_by_norm: dict[str, list["RuleRow"]]) -> Optional["RuleRow"]:
    """Resolve one CSV row's outcome label (e.g. "success", "success1") to
    exactly one named Rules row (Scenario column, e.g. "Success 1"), or None
    if it can't be resolved unambiguously. Never guesses: an ambiguous match
    (real example — LKP03.csv's plain "success" label matches "Success 1",
    "Success 2", AND "Success 4" equally well) returns None rather than
    picking one arbitrarily, because this routes real production traffic —
    a wrong guess here is a live bug, not a cosmetic gap.

    Matching strategy, in order:
      1. Exact match on normalized text (lowercase, non-alphanumeric
         stripped) — "success1" == "Success 1" normalized. Short-circuits:
         if exactly one scenario matches exactly, that wins outright, even
         if OTHER scenarios would also match loosely under step 2 (that
         would otherwise make "success1" wrongly ambiguous against
         "Success 2" purely because both share the stripped core "success").
      2. Only when no exact match exists: compare with trailing digits
         stripped from both sides — label "error" vs scenario "Error 3"
         (normalized "error3", stripped to "error") — handling LKP01's
         plain "success"/"error" CSV labels against differently-numbered
         Rules scenario names.
    """
    norm_label = _normalize_scenario_text(label)
    if not norm_label:
        return None

    exact = scenario_by_norm.get(norm_label, [])
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    label_core = _TRAILING_DIGITS_RE.sub("", norm_label)
    core_matches = [
        rr
        for norm, rows in scenario_by_norm.items()
        for rr in rows
        if _TRAILING_DIGITS_RE.sub("", norm) == label_core
    ]
    return core_matches[0] if len(core_matches) == 1 else None


def _build_lookup_match_condition(
    disc_type: MatchType, field_names: list[str], values: list[str]
) -> MatchCondition:
    """Build a real match condition for the static-mapping FALLBACK path only
    (ingestion-service's "quick wiremock.zip download" with no Java
    extension to run DynamicLookupRequestFilter — see wiremock.py's
    include_lookup_table_stubs=True). The primary path (the Java filter)
    never reads this — it extracts and joins fields itself at request time.

    Combines every field/value pair with a logical AND. Reuses
    ca_lisa_parser._xpath_literal for correct XPath string-literal quoting —
    the same helper _differentiate_bodies already uses for single-field CA
    LISA discriminators, not reimplemented here.
    """
    if disc_type == MatchType.BODY_XPATH:
        # Each field is an independent leaf-element existence check; XPath
        # 1.0 has no single-selector "AND across separate node tests", so
        # this ANDs several //*[...] boolean node-set tests at the top level
        # instead — standard, valid XPath 1.0, and how WireMock's XPath
        # matcher (evaluated as a boolean result) already expects it.
        parts = [
            f"//*[local-name()='{name}' and text()={_xpath_literal(value)}]"
            for name, value in zip(field_names, values)
        ]
        return MatchCondition(type=MatchType.BODY_XPATH, value=" and ".join(parts))

    escaped_pairs = [
        (name, value.replace("\\", "\\\\").replace("'", "\\'"))
        for name, value in zip(field_names, values)
    ]
    expr = "$[?(" + " && ".join(f"@.{name}=='{value}'" for name, value in escaped_pairs) + ")]"
    return MatchCondition(type=MatchType.BODY_JSON_PATH, value=expr)


def _build_lookup_table_scenarios(
    stub_name: str,
    rows: list[RuleRow],
    data_files: dict[str, bytes],
    source_name: str,
    content_type: str,
) -> tuple[list[ParsedScenario], Optional[str], Optional[str], list[str]]:
    """Build CSV-driven lookup-table scenarios for a stub whose Rules rows
    carry a Lookup File.

    Returns (scenarios, discriminator_type, discriminator_field, notes).
    `scenarios` holds both the CSV-keyed scenarios (one per resolvable CSV
    data row — lookup_key set) and the plain always-match Default/catch-all
    row if present among `rows` (lookup_key None) — the latter is what lets
    should_use_lookup_table + wiremock.py's build_wiremock_mappings emit a
    deliberate fallback response for a key the CSV doesn't recognise,
    instead of falling all the way through to WireMock's generic 404.

    Every skip is reported in `notes`, never silent — this builds routing
    for real production traffic, so an unresolvable row must be visible to
    whoever maintains the sheet, not quietly dropped.
    """
    notes: list[str] = []

    lookup_rows = [rr for rr in rows if rr.lookup_file.strip()]
    default_rows = [rr for rr in rows if rr.match_on.strip().lower() == "always"]
    named_rows = [rr for rr in lookup_rows if rr.match_on.strip().lower() != "always"]

    if not lookup_rows:
        return [], None, None, notes

    lookup_files = {rr.lookup_file.strip() for rr in lookup_rows}
    if len(lookup_files) > 1:
        notes.append(f"multiple different Lookup Files referenced ({sorted(lookup_files)}) — expected one per stub. Skipped.")
        return [], None, None, notes
    lookup_file = next(iter(lookup_files))

    extract_froms = {rr.extract_from.strip().lower() for rr in lookup_rows}
    if len(extract_froms) > 1:
        notes.append(f"multiple different 'Extract From' values on Lookup File rows ({sorted(extract_froms)}) — expected one. Skipped.")
        return [], None, None, notes
    try:
        disc_type_enum = MatchType(next(iter(extract_froms)))
    except ValueError:
        notes.append(f"'Extract From' ('{next(iter(extract_froms))}') is not a recognised match type. Skipped.")
        return [], None, None, notes
    if disc_type_enum not in (MatchType.BODY_JSON_PATH, MatchType.BODY_XPATH):
        notes.append(f"'Extract From' ('{disc_type_enum.value}') is not body-json-path/body-xpath — lookup routing needs a body field. Skipped.")
        return [], None, None, notes
    discriminator_type = "xpath" if disc_type_enum == MatchType.BODY_XPATH else "json"

    extract_fields_raw = {rr.extract_field.strip() for rr in lookup_rows if rr.extract_field.strip()}
    if len(extract_fields_raw) != 1:
        notes.append("Lookup File rows must all share exactly one 'Extract Field' value (comma-separated for a composite key). Skipped.")
        return [], None, None, notes
    field_names = [f.strip() for f in next(iter(extract_fields_raw)).split(",") if f.strip()]
    if not field_names:
        notes.append("'Extract Field' is empty on Lookup File rows. Skipped.")
        return [], None, None, notes

    csv_bytes = data_files.get(lookup_file)
    if csv_bytes is None:
        notes.append(f"references Lookup File '{lookup_file}', which is not in the uploaded zip. Skipped.")
        return [], None, None, notes

    csv_rows = [
        row for row in csv.reader(io.StringIO(csv_bytes.decode("utf-8", errors="replace")))
        if any(cell.strip() for cell in row)
    ]
    if len(csv_rows) < 2:
        notes.append(f"Lookup File '{lookup_file}' has no data rows.")
        return [], None, None, notes

    header, *data_rows = csv_rows
    key_column_count = len(header) - 1
    if key_column_count != len(field_names):
        notes.append(
            f"'Extract Field' lists {len(field_names)} field name(s) {field_names} but "
            f"'{lookup_file}' has {key_column_count} key column(s) before its outcome column "
            f"{header[:-1]} — these must match 1:1, in order. Update the sheet's 'Extract Field' "
            f"to comma-separate all {key_column_count} field name(s). Skipped."
        )
        return [], None, None, notes

    scenario_by_norm: dict[str, list[RuleRow]] = {}
    for rr in named_rows:
        scenario_by_norm.setdefault(_normalize_scenario_text(rr.scenario), []).append(rr)

    scenarios: list[ParsedScenario] = []
    for data_row in data_rows:
        if len(data_row) != len(header):
            notes.append(f"Lookup File '{lookup_file}' row {data_row!r} has {len(data_row)} column(s), expected {len(header)}. Skipped.")
            continue
        key_values = [c.strip() for c in data_row[:-1]]
        outcome_label = data_row[-1].strip()

        matched = _resolve_outcome_label(outcome_label, scenario_by_norm)
        if matched is None:
            notes.append(
                f"Lookup File row {key_values + [outcome_label]!r}: outcome '{outcome_label}' did not "
                "resolve to exactly one Rules scenario (no match, or ambiguous against more than one "
                "similarly-named scenario). Skipped."
            )
            continue

        body, reason = _resolve_body(matched.response_body, data_files, source_name)
        if body is None:
            notes.append(f"{matched.scenario or f'row{matched.row}'}: {reason} Skipped (lookup row {key_values!r}).")
            continue
        status = _parse_status(matched.response_status)
        if status is None:
            notes.append(
                f"{matched.scenario or f'row{matched.row}'}: 'Response Status' "
                f"('{matched.response_status}') is not a plain integer. Skipped (lookup row {key_values!r})."
            )
            continue

        scenarios.append(ParsedScenario(
            name=f"{matched.scenario or 'lookup'} ({', '.join(key_values)})",
            match=_build_lookup_match_condition(disc_type_enum, field_names, key_values),
            status=status,
            response_headers=_content_type_header(content_type),
            body=body,
            lookup_key=_URL_SEGMENT_KEY_JOIN.join(key_values),
        ))

    for rr in default_rows:
        scenario, reason = _build_rule_scenario(rr, data_files, source_name, content_type)
        if scenario is None:
            notes.append(f"Default: {reason} Skipped.")
            continue
        scenarios.append(scenario)

    return scenarios, discriminator_type, ",".join(field_names), notes
