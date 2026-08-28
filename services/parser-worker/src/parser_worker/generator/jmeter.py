"""Generates a ready-to-run Apache JMeter test plan from parsed stubs.

Phase 1 of automatic NFT script generation (see
docs/progress/PHASE1_JMETER_NFT_GENERATION.md) — JMeter only. This is a
pure reader over the same ParsedFile/ParsedStub/ParsedScenario data every
other generator (wiremock.py, lookup_table.py, springboot.py) already
consumes; nothing here changes how a file is parsed or how a stub's own
mappings are built, and no existing generator's output is affected by this
module existing.

One Thread Group per ParsedStub, one CSV data file per stub, columns
`requestPath,requestBody,expectedStatus` — the same shape regardless of
how many scenarios a stub has (1 row for a single-scenario stub, N rows
for a multi-capture one) so there is exactly one code path to get right,
not several branches for different scenario counts.

Request bodies:
    scenario.captured_request_body when the source parser recorded one
    (CA LISA captures always do); otherwise a synthesised minimal body
    that is *guaranteed* to satisfy the stub's own match condition (see
    _synthesise_minimal_body) — never an arbitrary placeholder that might
    fail to match. Embedded newlines are collapsed to a single space
    before being written to the CSV: JMeter's CSVDataSet reads its file
    line-by-line *before* applying quote/delimiter parsing, so a
    multi-line field would be split across malformed rows even with
    "Allow quoted data?" enabled — a real, verified JMeter limitation, not
    a guess. Collapsing newlines is safe for both XML and JSON (see
    _collapse_body_whitespace's docstring).

Explicitly out of scope for Phase 1 (flagged in the generated README, not
silently dropped): SOAP WS-Security auth headers, fault/delay scenario
replication, response-body assertions on Handlebars-templated content.
"""
from __future__ import annotations

import html
import json
import re

from ..models import MatchType, ParsedFile, ParsedScenario, ParsedStub

_SAFE_CHAR_RE = re.compile(r"[^\w\s-]")
_WHITESPACE_RUN_RE = re.compile(r"[\r\n]+\s*")

_OUT_OF_SCOPE_NOTE = (
    "SOAP WS-Security auth headers, fault/delay scenario replication, and "
    "assertions on Handlebars-templated ({{...}}) response content are not "
    "generated in this phase."
)


def build_jmeter_test_plan_files(parsed: ParsedFile, project_name: str = "") -> dict[str, str]:
    """Build the full NFT script package as {relative_path: text_content},
    entirely in memory — no filesystem access, matching the same
    in-memory-first pattern generator/springboot.py already uses.

    Returns:
        {
          "test-plan.jmx": ...,
          "data/<stub-slug>.csv": ...,   (one per stub)
          "README.md": ...,
        }
    """
    project_label = project_name or (parsed.stubs[0].name if parsed.stubs else "Mockingbird Stub")

    files: dict[str, str] = {}
    thread_groups_xml: list[str] = []
    stub_summaries: list[str] = []

    for index, stub in enumerate(parsed.stubs):
        slug = _safe_filename(stub.name) or f"stub-{index}"
        csv_filename = f"{slug}.csv"
        rows = [_scenario_row(stub, scenario) for scenario in stub.scenarios]
        files[f"data/{csv_filename}"] = _build_csv(rows)
        thread_groups_xml.append(_build_thread_group_xml(stub, csv_filename, index))
        stub_summaries.append(
            f"- **{html.escape(stub.name)}** — `{stub.request.method.value}` "
            f"`{html.escape(stub.request.url)}` ({len(stub.scenarios)} scenario(s), "
            f"data file `data/{csv_filename}`)"
        )

    files["test-plan.jmx"] = _JMX_TEMPLATE.format(
        test_plan_name=_esc(f"{project_label} — NFT Test Plan"),
        thread_groups="\n".join(thread_groups_xml),
    )
    files["README.md"] = _build_readme(project_label, stub_summaries)
    return files


# ── per-scenario data resolution ──────────────────────────────────────────────

class _Row:
    __slots__ = ("path", "body", "status")

    def __init__(self, path: str, body: str, status: int):
        self.path = path
        self.body = body
        self.status = status


def _scenario_row(stub: ParsedStub, scenario: ParsedScenario) -> _Row:
    path = scenario.url_override or stub.request.url
    body = scenario.captured_request_body or _synthesise_minimal_body(stub, scenario)
    return _Row(path=path, body=_collapse_body_whitespace(body), status=scenario.status)


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
    See the module docstring for why this is required for correctness
    against a real JMeter CSVDataSet, and why it's safe for both XML and
    JSON bodies.
    """
    return _WHITESPACE_RUN_RE.sub(" ", body).strip()


# ── CSV ────────────────────────────────────────────────────────────────────────

_CSV_HEADER = "requestPath,requestBody,expectedStatus"


def _build_csv(rows: list[_Row]) -> str:
    lines = [_CSV_HEADER]
    for row in rows:
        lines.append(",".join([
            _csv_field(row.path),
            _csv_field(row.body),
            _csv_field(str(row.status)),
        ]))
    return "\n".join(lines) + "\n"


def _csv_field(value: str) -> str:
    """RFC4180-style: always quote, double any embedded quote. Value is
    assumed already single-line (see _collapse_body_whitespace) — see the
    module docstring for why a real embedded newline would break JMeter's
    CSVDataSet even with correct quoting."""
    return '"' + value.replace('"', '""') + '"'


# ── JMX rendering ──────────────────────────────────────────────────────────────

def _build_thread_group_xml(stub: ParsedStub, csv_filename: str, index: int) -> str:
    method = stub.request.method.value
    header_manager_xml = _build_header_manager_xml(stub.request.required_headers)
    thread_group_name = _esc(f"{stub.name} ({method})")

    return _THREAD_GROUP_TEMPLATE.format(
        index=index,
        thread_group_name=thread_group_name,
        csv_filename=_esc(csv_filename),
        method=_esc(method),
        header_manager=header_manager_xml,
    )


def _build_header_manager_xml(headers: dict[str, str]) -> str:
    if not headers:
        return "          <collectionProp name=\"HeaderManager.headers\"/>\n"
    entries = "\n".join(
        f'            <elementProp name="" elementType="Header">\n'
        f'              <stringProp name="Header.name">{_esc(name)}</stringProp>\n'
        f'              <stringProp name="Header.value">{_esc(value)}</stringProp>\n'
        f'            </elementProp>'
        for name, value in headers.items()
    )
    return f'          <collectionProp name="HeaderManager.headers">\n{entries}\n          </collectionProp>\n'


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _xml_escape_text(value: str) -> str:
    return html.escape(value, quote=False)


def _safe_filename(name: str) -> str:
    safe = _SAFE_CHAR_RE.sub("", name).strip().replace(" ", "-").lower()
    return safe[:80]


# ── README ─────────────────────────────────────────────────────────────────────

def _build_readme(project_label: str, stub_summaries: list[str]) -> str:
    stub_list = "\n".join(stub_summaries) if stub_summaries else "- (no stubs in this project)"
    return f"""# NFT Test Plan — {project_label}

Generated automatically from this project's parsed stub data. Open
`test-plan.jmx` in Apache JMeter (5.x) and set the `HOST` / `PORT` user
defined variables (Test Plan level) to your running stub-engine's address
— the default stub port is `8080`.

## What's in here

- `test-plan.jmx` — one Thread Group per stub below.
- `data/*.csv` — one row per captured scenario: `requestPath,requestBody,expectedStatus`.
  Request bodies are the real captured payload when the source file recorded
  one, otherwise a minimal payload synthesised to satisfy that scenario's own
  match rule. Embedded newlines are collapsed to single spaces (a JMeter
  CSVDataSet limitation, not a formatting choice — see the mapping
  generator's comments if you want the exact original capture).

## Stubs in this test plan

{stub_list}

## Defaults (tune before a real load test)

Each Thread Group starts at 5 threads / 5s ramp-up / 5 loops, cycling
through its CSV data (`recycle=true`). These are safe, small starting
values for a first smoke run — not tuned for your actual TPS target.

## Out of scope for this generation (Phase 1)

{_OUT_OF_SCOPE_NOTE}
"""


# ── XML templates ──────────────────────────────────────────────────────────────
# Hand-validated structure: built from a JMX confirmed to load correctly
# and produce a real, matching HTTP request against a real running stub
# (see docs/progress/PHASE1_JMETER_NFT_GENERATION.md's testing log).

_JMX_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="{test_plan_name}" enabled="true">
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments">
          <elementProp name="HOST" elementType="Argument">
            <stringProp name="Argument.name">HOST</stringProp>
            <stringProp name="Argument.value">localhost</stringProp>
          </elementProp>
          <elementProp name="PORT" elementType="Argument">
            <stringProp name="Argument.name">PORT</stringProp>
            <stringProp name="Argument.value">8080</stringProp>
          </elementProp>
        </collectionProp>
      </elementProp>
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <stringProp name="TestPlan.user_define_classpath"></stringProp>
    </TestPlan>
    <hashTree>
{thread_groups}
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_THREAD_GROUP_TEMPLATE = """      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="{thread_group_name}" enabled="true">
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
          <boolProp name="LoopController.continue_forever">false</boolProp>
          <intProp name="LoopController.loops">5</intProp>
        </elementProp>
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">5</stringProp>
        <boolProp name="ThreadGroup.scheduler">false</boolProp>
        <stringProp name="ThreadGroup.duration"></stringProp>
        <stringProp name="ThreadGroup.delay"></stringProp>
      </ThreadGroup>
      <hashTree>

        <CSVDataSet guiclass="TestBeanGUI" testclass="CSVDataSet" testname="Data ({csv_filename})" enabled="true">
          <stringProp name="filename">data/{csv_filename}</stringProp>
          <stringProp name="fileEncoding">UTF-8</stringProp>
          <stringProp name="variableNames">requestPath,requestBody,expectedStatus</stringProp>
          <boolProp name="ignoreFirstLine">true</boolProp>
          <stringProp name="delimiter">,</stringProp>
          <boolProp name="quotedData">true</boolProp>
          <boolProp name="recycle">true</boolProp>
          <boolProp name="stopThread">false</boolProp>
          <stringProp name="shareMode">shareMode.group</stringProp>
        </CSVDataSet>
        <hashTree/>

        <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Required Headers" enabled="true">
{header_manager}        </HeaderManager>
        <hashTree/>

        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{method} ${{requestPath}}" enabled="true">
          <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
            <collectionProp name="Arguments.arguments">
              <elementProp name="" elementType="HTTPArgument">
                <boolProp name="HTTPArgument.always_encode">false</boolProp>
                <stringProp name="Argument.value">${{requestBody}}</stringProp>
                <stringProp name="Argument.metadata">=</stringProp>
              </elementProp>
            </collectionProp>
          </elementProp>
          <stringProp name="HTTPSampler.domain">${{HOST}}</stringProp>
          <stringProp name="HTTPSampler.port">${{PORT}}</stringProp>
          <stringProp name="HTTPSampler.protocol">http</stringProp>
          <stringProp name="HTTPSampler.path">${{requestPath}}</stringProp>
          <stringProp name="HTTPSampler.method">{method}</stringProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          <stringProp name="HTTPSampler.connect_timeout">5000</stringProp>
          <stringProp name="HTTPSampler.response_timeout">10000</stringProp>
        </HTTPSamplerProxy>
        <hashTree>

          <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="Status matches expectedStatus" enabled="true">
            <collectionProp name="Asserion.test_strings">
              <stringProp name="49586">${{expectedStatus}}</stringProp>
            </collectionProp>
            <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
            <boolProp name="Assertion.assume_success">false</boolProp>
            <intProp name="Assertion.test_type">8</intProp>
          </ResponseAssertion>
          <hashTree/>

        </hashTree>
      </hashTree>
"""
