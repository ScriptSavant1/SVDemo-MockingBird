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

from ..models import ParsedFile, ParsedStub
from .nft_common import OUT_OF_SCOPE_NOTE, build_csv, safe_filename, scenario_row


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
        slug = safe_filename(stub.name) or f"stub-{index}"
        csv_filename = f"{slug}.csv"
        rows = [scenario_row(stub, scenario) for scenario in stub.scenarios]
        files[f"data/{csv_filename}"] = build_csv(rows)
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

{OUT_OF_SCOPE_NOTE}
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
