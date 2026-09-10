"""Generates a ready-to-open LoadRunner DevWeb (VuGen) project from parsed
stubs. Phase 2 of automatic NFT script generation (see
docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md) — one script for the whole
project, one named `load.action()` + `load.Transaction` per stub (the
direct DevWeb analogue of "one Thread Group per stub" in the JMeter zip),
one CSV parameter file per stub. Reuses the exact same per-scenario row
data as generator/jmeter.py via generator/nft_common.py for path/body/status
resolution — same real-captured-body reuse, same
synthesized-body-guaranteed-to-match fallback, same conservative
newline-collapsing (see nft_common's module docstring).

Request bodies are NOT embedded in the CSV as a quoted field (unlike the
JMeter generator). A real VuGen open of an early version of this generator's
output failed with "check file format error" on a CSV row whose requestBody
column held a JSON/XML payload containing embedded, RFC4180-doubled quotes
(`""like this""`) — JMeter's CSVDataSet parses that convention fine (proven
in Phase 1's real JMeter runs against XML bodies with the same
quote-heavy shape), but VuGen's CSV reader evidently does not accept it.
Rather than guess at VuGen's exact undocumented quoting rules, each
scenario's body is written to its own plain text file
(`<stub-base>-<scenario-index>.body.txt`, containing the raw payload,
no CSV escaping applied to it at all) and referenced via the SDK's own
documented `bodyPath` WebRequest option instead of `body`. The CSV itself
now only ever holds simple values (a URL path, a file path, a status code)
that never need quoting in practice, sidestepping the whole class of
CSV-quoting risk for the one field that actually needed it.

All data files (CSVs and body .txt files) live flat at the project root,
not in a `data/` subfolder, and are explicitly declared — in both
`ScriptUploadMetadata.xml` and the `.usr` file's `[ManuallyExtraFiles]`
section — rather than left to be discovered implicitly. A real LRE
"upload only runtime files" run silently excluded every `.body.txt` file:
unlike parameters.yml's CSV references (a structured, first-class VuGen
construct any packaging tool can statically discover by reading
parameters.yml itself), a body file's name is only known at *runtime*, as
*data* inside a CSV row (`load.params.X_requestBodyFile`) — there is no
static reference anywhere in main.js or parameters.yml for a packaging
tool to follow. A `data/` subfolder made this worse: files that aren't
statically referenced also weren't being found even when present. The fix
— confirmed working by the user against a real LRE upload — is to flatten
every data file to the project root and list each one explicitly as an
extra file, exactly the way this generator already lists parameters.yml
and rts.yml.

The mandatory/optional VuGen project file set and every static template
below (`.usr`, `default.cfg`, `default.usp`, `tsconfig.json`,
`ScriptUploadMetadata.xml`) were taken verbatim from a real, previously
VuGen-opened reference project (an internal converter tool's own generated
output), not reconstructed from documentation alone — see
docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md §2 for the full source
review. `parameters.yml` and the CSV format follow the official DevWeb
"Parameterize values" documentation field-for-field.

Deliberately NOT generated: `Action.c`/`vuser_init.c`/`vuser_end.c`/
`Bookmarks.xml`/`Breakpoints.xml`/`UserTasks.xml`. These appear in
`ScriptUploadMetadata.xml` at Filter="1" (IDE-only) in the reference
project's own output, but are absent from its actual generated project
folders — VuGen creates them itself on first open when needed. They are
still *listed* in the generated `ScriptUploadMetadata.xml` for parity with
that real, working reference.

Deliberately NOT bundled: the vendor's own `DevWebSdk.d.ts`. It is
Micro Focus/OpenText's proprietary SDK type-definition file; redistributing
a copy inside every generated Mockingbird download is a licensing question
this generator does not decide unilaterally. It is only needed for editor
IntelliSense, never at runtime (the `load` namespace is injected by the
real DevWeb engine regardless of whether this file is present) — the
generated README instead tells the tester to copy their own installation's
copy in if they want it, which needs no license decision at all.

Correlation/extractors are correctly unused, not a missed feature: every
Mockingbird stub is one independent captured endpoint, not a multi-step
chained user journey with a session token to correlate.
"""
from __future__ import annotations

import json
import re

from ..models import MatchType, ParsedFile, ParsedStub
from .nft_common import OUT_OF_SCOPE_NOTE, csv_field, safe_filename, scenario_row

_DEVWEB_OUT_OF_SCOPE_EXTRA = (
    "No correlation/extractors are generated — every Mockingbird stub is one "
    "independent captured endpoint, not a chained multi-step journey with a "
    "session token to correlate. All stubs run as named actions inside one "
    "script sharing one Vuser pool/schedule; independent per-stub TPS scaling "
    "the way separate JMeter Thread Groups allow would need separate scripts, "
    "which this generator does not create."
)

_NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_]+")
_LINE_BREAK_RE = re.compile(r"[\r\n]+")


def _js_block_comment_safe(text: str) -> str:
    """Make arbitrary text safe to embed inside a `/** ... */` block
    comment in generated JavaScript. A stub/project name is user-supplied
    (the upload form's "stub name" field) and is embedded directly into
    main.js's header docblock — an unlucky value containing a literal
    `*/` would prematurely close the comment, leaving the rest of the
    intended comment text as raw, syntactically-invalid JS source
    (verified with a real `node --check` reproduction, not a guess).
    Also strips embedded newlines, which would break the one-line-per-`*`
    docblock formatting."""
    return _LINE_BREAK_RE.sub(" ", text).replace("*/", "* /")


def _js_line_comment_safe(text: str) -> str:
    """Make arbitrary text safe to embed inside a `// ...` line comment.
    A `//` comment only ends at a newline, so the only real risk is an
    embedded newline breaking out into raw source early — a captured URL
    is very unlikely to contain one, but this is cheap insurance for
    "handle all kinds of inputs", not just the inputs seen so far."""
    return _LINE_BREAK_RE.sub(" ", text)


def build_devweb_project_files(parsed: ParsedFile, project_name: str = "") -> dict[str, str]:
    """Build the full DevWeb NFT project as {relative_path: text_content},
    entirely in memory. Returns:

        {
          "main.js": ...,
          "<ScriptName>.usr": ...,
          "default.cfg": ...,
          "default.usp": ...,
          "rts.yml": ...,
          "parameters.yml": ...,
          "tsconfig.json": ...,
          "ScriptUploadMetadata.xml": ...,
          "<stub-base>.csv": ...,             (one per stub; requestPath,requestBodyFile,expectedStatus)
          "<stub-base>-<n>.body.txt": ...,    (one per scenario — see module docstring)
          "README.md": ...,
        }

    Every CSV/body-file name is also listed explicitly in
    ScriptUploadMetadata.xml and the .usr file's [ManuallyExtraFiles] — see
    the module docstring for why that's required, not optional.
    """
    project_label = project_name or (parsed.stubs[0].name if parsed.stubs else "Mockingbird Stub")
    script_name = _script_name(project_label)

    files: dict[str, str] = {}
    actions: list[tuple[str, str]] = []  # (base_name, action_block)
    param_blocks: list[str] = []
    stub_summaries: list[str] = []
    data_filenames: list[str] = []  # every CSV + body.txt — must be declared explicitly, see module docstring

    for index, stub in enumerate(parsed.stubs):
        base = _stub_base_name(stub, index)
        csv_filename = f"{base}.csv"
        csv_rows: list[tuple[str, str, int]] = []  # (path, bodyFilePath, status)
        for scenario_index, scenario in enumerate(stub.scenarios):
            row = scenario_row(stub, scenario)
            body_filename = f"{base}-{scenario_index}.body.txt"
            files[body_filename] = row.body
            data_filenames.append(body_filename)
            csv_rows.append((row.path, body_filename, row.status))
        files[csv_filename] = _build_devweb_csv(csv_rows)
        data_filenames.append(csv_filename)

        actions.append((base, _build_action_block(stub, base, request_id=index + 1)))
        param_blocks.append(_build_param_block(base, csv_filename))
        stub_summaries.append(
            f"- **{stub.name}** — `{stub.request.method.value}` `{stub.request.url}` "
            f"({len(stub.scenarios)} scenario(s), action `{base}`, data file `{csv_filename}`)"
        )

    files["main.js"] = _build_main_js(project_label, actions)
    files[f"{script_name}.usr"] = _build_usr(script_name, [name for name, _ in actions], data_filenames)
    files["default.cfg"] = _DEFAULT_CFG
    files["default.usp"] = _DEFAULT_USP
    files["rts.yml"] = _RTS_YML
    files["parameters.yml"] = _build_parameters_yml(param_blocks)
    files["tsconfig.json"] = _TSCONFIG_JSON
    files["ScriptUploadMetadata.xml"] = _build_upload_metadata(script_name, data_filenames)
    files["README.md"] = _build_readme(project_label, stub_summaries)
    return files


# ── CSV (path + body-file-reference + status only — see module docstring) ──────

_DEVWEB_CSV_HEADER = "requestPath,requestBodyFile,expectedStatus"


def _build_devweb_csv(rows: list[tuple[str, str, int]]) -> str:
    lines = [_DEVWEB_CSV_HEADER]
    for path, body_filename, status in rows:
        lines.append(",".join([csv_field(path), csv_field(body_filename), csv_field(str(status))]))
    return "\n".join(lines) + "\n"


# ── naming ─────────────────────────────────────────────────────────────────────

def _stub_base_name(stub: ParsedStub, index: int) -> str:
    """A name that is simultaneously a valid JS identifier suffix, a safe
    filename, and a parameters.yml parameter-name prefix — namespaced per
    stub (stub00_, stub01_, ...) since parameters.yml is one flat,
    script-wide list with no per-action scoping, unlike a JMeter
    CSVDataSet which can be scoped to just one Thread Group."""
    slug = (safe_filename(stub.name) or "stub").replace("-", "_")
    return f"stub{index:02d}_{slug}"


def _script_name(project_label: str) -> str:
    """VuGen's own convention for a .usr filename, e.g.
    'Regular_Expression_Extractor_Test.usr' — spaces/punctuation collapsed
    to single underscores, matching the real reference project's output.
    Capped at 80 chars, same as safe_filename, so an unusually long project
    name can't push a generated path over Windows' MAX_PATH once combined
    with the zip's folder nesting."""
    name = _NON_IDENTIFIER_RE.sub("_", project_label).strip("_")[:80]
    return name or "Mockingbird_NFT_Script"


# ── main.js ──────────────────────────────────────────────────────────────────────

def _build_action_block(stub: ParsedStub, base: str, request_id: int) -> str:
    """request_id becomes the WebRequest's `id` — used by VuGen to
    generate the matching snapshot file for the Replay view (see the SDK
    docs' `id` option: "The ID used to generate the corresponding
    snapshot file."). Sequential across the whole script, 1-based,
    matching the real reference converter's own generated output, which
    numbers every request this way."""
    method = stub.request.method.value
    headers_js = json.dumps(stub.request.required_headers, indent=6) if stub.request.required_headers else "{}"
    url_comment = _js_line_comment_safe(stub.request.url)
    return f"""    T_{base}.start();
    // {method} {url_comment}
    const response_{base} = new load.WebRequest({{
      id: {request_id},
      url: `http://${{load.config.user.args["HOST"]}}:${{load.config.user.args["PORT"]}}${{load.params.{base}_requestPath}}`,
      method: "{method}",
      headers: {headers_js},
      bodyPath: load.params.{base}_requestBodyFile,
      returnBody: false,
      handleHTTPError: () => false,
    }}).sendSync();
    // CSV values are always strings, so response.status (a number) is
    // compared with == deliberately, not === — this is an intentional
    // loose comparison, not an oversight.
    T_{base}.stop(
      response_{base}.status == load.params.{base}_expectedStatus
        ? load.TransactionStatus.Passed
        : load.TransactionStatus.Failed
    );"""


def _build_main_js(project_label: str, actions: list[tuple[str, str]]) -> str:
    transactions = (
        "\n".join(f'const T_{base} = new load.Transaction("{base}");' for base, _ in actions)
        or "// (no stubs in this project)"
    )
    action_blocks = (
        "\n\n".join(f'load.action("{base}", async function () {{\n{block}\n}});' for base, block in actions)
        or "// (no stubs in this project)"
    )

    safe_label = _js_block_comment_safe(project_label)
    return f"""/**
 * Mockingbird NFT Test Script — {safe_label}
 * Auto-generated from this project's parsed stub data (Phase 2 — DevWeb).
 * One named action + one Transaction per stub, one CSV parameter file per
 * stub (see parameters.yml and *.csv). See README.md for setup and
 * scope notes.
 */

// ── Transaction objects — declared once at module level so they are
// available inside every action() without re-allocating per iteration ──
{transactions}

{action_blocks}
"""


# ── parameters.yml ─────────────────────────────────────────────────────────────

def _build_param_block(base: str, csv_filename: str) -> str:
    # nextValue is present on every entry, including the "same as" ones,
    # even though the docs describe it as "ignored" there — the vendor's
    # own example YAML in that same doc, and the real reference
    # converter's own generated output, both still include it on "same
    # as" rows. A real VuGen run confirmed this isn't optional: omitting
    # it produced "nextValue getter was not defined" at script
    # initialization — the field must be present even where its value
    # doesn't affect row selection.
    return f"""  - name: {base}_requestPath
    type: csv
    fileName: {csv_filename}
    columnName: requestPath
    nextValue: iteration
    nextRow: sequential
    onEnd: loop
  - name: {base}_requestBodyFile
    type: csv
    fileName: {csv_filename}
    columnName: requestBodyFile
    nextValue: iteration
    nextRow: same as {base}_requestPath
    onEnd: loop
  - name: {base}_expectedStatus
    type: csv
    fileName: {csv_filename}
    columnName: expectedStatus
    nextValue: iteration
    nextRow: same as {base}_requestPath
    onEnd: loop"""


def _build_parameters_yml(param_blocks: list[str]) -> str:
    body = "\n".join(param_blocks) if param_blocks else ""
    return f"""# Parameters Configuration
# Auto-generated by Mockingbird from this project's parsed stub data.
# nextValue: iteration = a fresh row is read every iteration (matches
# JMeter's recycle=true CSVDataSet behavior in the sibling jmeter/ folder).
# requestBodyFile/expectedStatus use "nextRow: same as <requestPath param>"
# so all three columns always advance together, staying on the same
# captured scenario's row — the documented mechanism for exactly this (see
# the official DevWeb "Parameterize values" doc's username/password
# example). requestBodyFile holds a *path* to a .body.txt file, not the
# body itself — see the generator module's docstring for why.
parameters:
{body}
"""


# ── static VuGen project files ────────────────────────────────────────────────
# Verbatim from a real, previously VuGen-opened reference project — see the
# module docstring and docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md §2.

_DEFAULT_CFG = """[General]
AutomaticTransactions=0
AutomaticTransactionsPerFunc=0
ContinueOnError=0
XlBridgeTimeout=120
DefaultRunLogic=default.usp
Encoding=UTF8

[Iterations]
NumOfIterations=1
IterationPace=IterationASAP
StartEvery=60
RandomMin=60
RandomMax=90

[Log]
AutoLog=0
AutoLogBufferSize=1
IncludeEnvInfo=0
LogDetail=1
LogOptions=LogExtended
MsgClassData=0
MsgClassFull=0
MsgClassParameters=0
PrintTimeStamp=0

[ThinkTime]
Factor=1
Limit=1
LimitFlag=0
Options=NOTHINK
"""

_DEFAULT_USP = """[Profile Actions]
MercIniTreeFather=""
MercIniTreeSectionName="Profile Actions"
Profile Actions name=Main

[RunLogicEndRoot]
MercIniTreeFather=""
MercIniTreeSectionName="RunLogicEndRoot"
MercIniTreeSons=""
Name="End"
RunLogicActionOrder=""
RunLogicActionType="VuserEnd"
RunLogicNumOfIterations="1"
RunLogicObjectKind="Group"
RunLogicRunMode="Sequential"

[RunLogicErrorHandlerRoot]
MercIniTreeFather=""
MercIniTreeSectionName="RunLogicErrorHandlerRoot"
MercIniTreeSons="vuser_errorhandler"
Name="ErrorHandler"
RunLogicActionOrder="vuser_errorhandler"
RunLogicActionType="VuserErrorHandler"
RunLogicNumOfIterations="1"
RunLogicObjectKind="Group"
RunLogicRunMode="Sequential"

[RunLogicErrorHandlerRoot:vuser_errorhandler]
MercIniTreeFather="RunLogicErrorHandlerRoot"
MercIniTreeSectionName="vuser_errorhandler"
Name="vuser_errorhandler"
RunLogicActionType="VuserErrorHandler"
RunLogicObjectKind="Action"

[RunLogicInitRoot]
MercIniTreeFather=""
MercIniTreeSectionName="RunLogicInitRoot"
MercIniTreeSons=""
Name="Init"
RunLogicActionOrder=""
RunLogicActionType="VuserInit"
RunLogicNumOfIterations="1"
RunLogicObjectKind="Group"
RunLogicRunMode="Sequential"

[RunLogicRunRoot]
MercIniTreeFather=""
MercIniTreeSectionName="RunLogicRunRoot"
MercIniTreeSons="Main"
Name="Run"
RunLogicActionOrder="Main"
RunLogicActionType="VuserRun"
RunLogicAfterPaceMax="90"
RunLogicAfterPaceMin="60"
RunLogicNumOfIterations="1"
RunLogicObjectKind="Group"
RunLogicPaceConstAfterTime="60"
RunLogicPaceConstTime="60"
RunLogicPaceType="Asap"
RunLogicRandomPaceMax="90"
RunLogicRandomPaceMin="60"
RunLogicRunMode="Sequential"

[RunLogicRunRoot:Main]
MercIniTreeFather="RunLogicRunRoot"
MercIniTreeSectionName="Main"
Name="Main"
RunLogicActionType="VuserRun"
RunLogicObjectKind="Action"
"""

_RTS_YML = """httpConnection:
  maxPersistentConnectionsPerHost: 6
  maxConnectedHosts: 30
  maxRedirectDepth: 10
  keepAliveTimeout: 60
  connectTimeout: 120
  abruptClose: false
  requestTimeout: 120
  canonicalHeaderEntries: true
dns:
  bypassSystem: false
  ttl: 600
grpc:
  connectTimeout: 120
  keepAliveTime: 0
  maxRecvMsgSize: 0
  maxSendMsgSize: 0
proxy:
  usePAC: false
  pacAddress: ''
  useProxy: false
  proxyServer: ''
  proxyDomain: ''
  proxyUser: ''
  proxyPassword: ''
  proxyAuthenticationType: ''
  excludedHosts: []
ssl:
  disableHTTP2: false
  ignoreBadCertificate: false
  tlsMaxVersion: tls12
  enableHTTP3: false
replay:
  simulateNewUser: true
  saveSnapshots: always
  snapshotBodySizeLimit: 100
  useCache: false
  enableDynatrace: false
  resourceHttpErrorAsWarning: true
  enableIntegratedAuthentication: true
  multiIP: none
vts:
  useProxy: false
  proxyServer: ''
  proxyUser: ''
  proxyPassword: ''
  portInQueryString: false
  httpPort: 80
  httpsPort: 443
  ignoreBadCertificate: false
encryption:
  keyLocation: ''
vuserLogger:
  errorBufferSize: 4096
  logMode: full
  logLevel: trace
  traceRequestFlowDetails:
    - headers
    - body
  showInConsole: true
flow:
  enabled: false
  initialize: {}
  run: {}
  finalize: {}
thinkTime:
  type: asRecorded
  limit: -1
  arguments: {}
openTelemetry:
  enabled: false
  collector: ''
  enableTLS: false
  tlsCertificate: ''
  authenticationHeader: ''
  vusersRate: 100
userArguments:
  HOST: "localhost"
  PORT: "8080"
"""

_TSCONFIG_JSON = """{
  "compilerOptions": {
    "noEmit": true,
    "jsx": "preserve",
    "allowJs": true,
    "lib": [
      "es2020"
    ],
    "module": "commonjs",
    "moduleResolution": "node",
    "target": "es2020"
  },
  "files": [
    "DevWebSdk.d.ts"
  ],
  "include": [
    "./*.js"
  ],
  "exclude": [
    "*.d.ts"
  ]
}
"""


def _build_usr(script_name: str, transaction_names: list[str], data_filenames: list[str]) -> str:
    tx_order = "__*delimiter*__".join(transaction_names)
    # Every CSV/body.txt file is listed here too, not just in
    # ScriptUploadMetadata.xml — a real LRE "upload only runtime files"
    # run only picked up files declared as extras in one of these two
    # places; a body file referenced only indirectly through CSV row data
    # was invisible to that packaging step otherwise. See module docstring.
    manual_extras_section = (
        "\n[ManuallyExtraFiles]\n" + "".join(f"{name}=\n" for name in data_filenames)
        if data_filenames
        else ""
    )
    return f"""[General]
Type=DevWeb
DefaultCfg=default.cfg
MajorVersion=25
MinorVersion=3
ParameterFile=
GlobalParameterFile=
RunType=DevWeb
NewFunctionHeader=1
ActionLogicExt=action_logic
LastActiveAction=Main
ScriptLanguage=JavaScript
Encoding=UTF8
DevelopTool=Vugen
LastModifyVer=25.3.0.0
ActiveTypes=DevWeb
AdditionalTypes=DevWeb
GenerateTypes=DevWeb
ParamLeftBrace={{
ParamRightBrace=}}
LastCodeGenerationVer=
DisableRegenerate=0
Description=
ScriptLocale=en-GB

[ExtraFiles]
parameters.yml=
rts.yml=

[Actions]
Main=main.js

[Recorded Actions]
Main=0

[Interpreters]
Main=DevWeb

[RunLogicFiles]
Default Profile=default.usp

[Modified Actions]
Main=0

[Replayed Actions]
Main=0

[TransactionsOrder]
Order={tx_order}

[StateManagement]
LastReplayStatus=0

[ActiveReplay]
LastReplayedRunName=
ActiveRunName=
{manual_extras_section}"""


def _build_upload_metadata(script_name: str, data_filenames: list[str]) -> str:
    # Filter="2" (uploaded + visible) matches parameters.yml/rts.yml —
    # every one of these is genuinely needed at runtime, not IDE-only.
    # Listed explicitly rather than left for LRE's packaging step to
    # discover on its own — see module docstring for why that discovery
    # doesn't work for body.txt files.
    data_entries = "".join(f'    <FileEntry Name="{name}" Filter="2" />\n' for name in data_filenames)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<VugenScriptMetadata>
  <ScriptName>{script_name}</ScriptName>
  <Protocol>DevWeb</Protocol>
  <ActionFiles>
    <FileEntry Name="main.js" Filter="2" />
  </ActionFiles>
  <GeneralFiles>
    <FileEntry Name="{script_name}.usr" Filter="4" />
    <FileEntry Name="default.cfg" Filter="4" />
    <FileEntry Name="default.usp" Filter="4" />
    <FileEntry Name="parameters.yml" Filter="2" />
    <FileEntry Name="rts.yml" Filter="2" />
{data_entries}    <FileEntry Name="Action.c" Filter="1" />
    <FileEntry Name="Bookmarks.xml" Filter="1" />
    <FileEntry Name="Breakpoints.xml" Filter="1" />
    <FileEntry Name="DevWebSdk.d.ts" Filter="1" />
    <FileEntry Name="ScriptUploadMetadata.xml" Filter="1" />
    <FileEntry Name="tsconfig.json" Filter="1" />
    <FileEntry Name="UserTasks.xml" Filter="1" />
    <FileEntry Name="vuser_end.c" Filter="1" />
    <FileEntry Name="vuser_init.c" Filter="1" />
  </GeneralFiles>
</VugenScriptMetadata>
"""


# ── README ─────────────────────────────────────────────────────────────────────

def _build_readme(project_label: str, stub_summaries: list[str]) -> str:
    stub_list = "\n".join(stub_summaries) if stub_summaries else "- (no stubs in this project)"
    return f"""# NFT Test Script (DevWeb / VuGen) — {project_label}

Generated automatically from this project's parsed stub data. Open the
`.usr` file in this folder with LoadRunner Developer / VuGen to load it as
a DevWeb project.

## Before you open it

- Set `HOST` / `PORT` in `rts.yml`'s `userArguments` (currently
  `localhost` / `8080`) to your running stub-engine's address.
- **DevWebSdk.d.ts is not included** — it's Micro Focus/OpenText's own SDK
  type-definition file, not something Mockingbird redistributes. Copy your
  local DevWeb/VuGen installation's copy into this folder if you want
  editor IntelliSense; the script itself runs correctly without it (the
  `load` namespace is injected by the real DevWeb engine at runtime,
  regardless of whether this file is present).

## What's in here

- `main.js` — one script, one named `load.action()` + `load.Transaction`
  per stub below.
- `*.csv` + `parameters.yml` — one CSV per stub (flat at the project root,
  not in a subfolder — see below), one row per captured scenario:
  `requestPath,requestBodyFile,expectedStatus`. `requestBodyFile` points at
  a `<stub>-<n>.body.txt` file holding that scenario's real captured
  payload (or a minimal payload synthesised to satisfy that scenario's own
  match rule when no capture was recorded) — sent via the SDK's `bodyPath`
  option rather than embedding the body in the CSV, since a real VuGen open
  failed on a CSV field containing an RFC4180-quoted JSON/XML payload
  (VuGen's CSV reader does not accept the same doubled-quote convention
  JMeter's CSVDataSet does). Embedded newlines in a body file are collapsed
  to single spaces (the same conservative precaution proven necessary for
  the sibling JMeter CSVDataSet — see that folder's README).
- Every CSV and `.body.txt` file is listed explicitly in
  `ScriptUploadMetadata.xml` and in this `.usr` file's `[ManuallyExtraFiles]`
  section, and lives flat at the project root rather than in a subfolder —
  a real LRE "upload only runtime files" run silently dropped `.body.txt`
  files otherwise, since a body file's name is only known at runtime (as
  data inside a CSV row), not statically discoverable by a packaging tool
  the way parameters.yml's own CSV references are.
- `<ScriptName>.usr`, `default.cfg`, `default.usp`, `tsconfig.json`,
  `ScriptUploadMetadata.xml` — VuGen project files.

## Stubs in this script

{stub_list}

## Out of scope for this generation (Phase 2)

{OUT_OF_SCOPE_NOTE}

{_DEVWEB_OUT_OF_SCOPE_EXTRA}
"""
