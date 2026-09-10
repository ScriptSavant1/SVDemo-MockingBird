# Phase 2 — Automatic LoadRunner DevWeb (VuGen) Script Generation

**Status: COMPLETE**
**Owner constraint (unchanged from Phase 1):** existing upload → parse → generate →
deploy flow, and the already-shipped Phase 1 `nft-jmeter.zip` endpoint, must not be
touched or put at risk. Everything in this phase is additive.

---

## 1. Confirmed understanding

- **One script, not one-per-stub.** Mirrors the JMeter deliverable exactly: a single
  DevWeb project (one `main.js` + one set of mandatory VuGen files) covers every stub
  in the upload — not a separate VuGen project per stub. This is a deliberate change
  from my earlier proposal (one project per stub); the user corrected this and it is
  now the agreed design.
- **One CSV per stub inside that one script**, same as JMeter's one-CSV-per-Thread-Group.
  Handled correctly per the official parameterization doc (`Parameterize values.pdf`,
  pasted at repo root) and cross-checked against `C:\Workspace\bruno-devweb-converter`'s
  real, VuGen-opened output.
- Delivered as **one zip with two top-level folders**, `jmeter/` and `devweb/`, replacing
  the single-purpose `nft-jmeter.zip` download with a combined one. The existing
  `nft-jmeter.zip` endpoint itself is left in place, untouched (see §3).

## 2. Reference material and what it settled

Three sources, in order of authority:

1. **`Parameterize values.pdf`** (official Micro Focus doc, user-provided) — the
   authoritative spec for `parameters.yml` + CSV format:
   - CSV is plain comma-separated, **header row mandatory**, one column = one parameter.
     No mention of multi-line-quoted-field support anywhere in the spec — since I could
     not get a positive confirmation either way (see §2a), the DevWeb CSV writer will
     apply the same conservative newline-collapsing already proven necessary for
     JMeter's `CSVDataSet` (`generator/jmeter.py`'s `_collapse_body_whitespace`).
   - `parameters.yml` schema confirmed field-for-field: `name`, `type: csv`, `fileName`,
     `columnName`, `nextValue` (`once`|`iteration`|`always`), `nextRow`
     (`sequential`|`random`|`"same as <param>"`|`unique`+`blockSize`), `onEnd: loop`,
     `firstDataRow`.
   - Critically: **`nextRow: "same as <parameter>"`** is the documented mechanism for
     keeping related columns in lockstep on the same row ("useful ... when matching a
     password for a username") — this is exactly what's needed to keep a stub's
     `requestBody`/`expectedStatus` columns synchronized with its `requestPath` column,
     the same guarantee JMeter gets for free from one `CSVDataSet` covering all three
     columns together.
2. **`DevWeb JavaScript SDK.pdf`** (official, user-provided) — confirms the runtime API:
   `load.action(name, async fn)` (supports multiple independently-named actions per
   script, run in registration order or per the Run Logic tree), `new
   load.WebRequest({url, method, headers, body, returnBody, handleHTTPError}).sendSync()`,
   `new load.Transaction(name)` with `.start()`/`.stop(status)`, `load.params.<name>`.
3. **`C:\Workspace\bruno-devweb-converter`** — a previously-built, real, VuGen-opened
   converter (surveyed in full; see prior turn's agent report). Gives the exact mandatory
   file set VuGen needs to open a project at all: `main.js`, `<name>.usr`, `default.cfg`,
   `default.usp`, `rts.yml`, `parameters.yml`, `DevWebSdk.d.ts`, `tsconfig.json`,
   `Action.c`/`vuser_init.c`/`vuser_end.c` stub files, `collection_data*.csv` when there
   are parameters, `ScriptUploadMetadata.xml` for LRE upload. This project's own
   `DevWebSdk.d.ts`/PDF are the vendor's own type definitions, not a reverse-engineered
   guess — corroborates source (2) directly.

### 2a. Open question, flagged rather than silently assumed

The official parameterize-values doc does not state whether multi-line quoted CSV
fields are supported or will corrupt row parsing (the exact failure mode proven for
JMeter in Phase 1). No sample in either reference source contains a multi-line field.
**Decision: apply the same newline-collapsing as JMeter, documented as an assumption
in the generated README**, consistent with "verify, don't assume" — this is the
conservative choice, not a shortcut, since collapsing whitespace never changes
well-formedness of the XML/JSON bodies involved.

## 3. Design

### 3.1 Shared row-extraction logic (behavior-preserving refactor)

`generator/jmeter.py`'s per-scenario row logic (`_Row`, `_scenario_row`,
`_synthesize_minimal_body`, `_collapse_body_whitespace`) is extracted into a new,
shared module — `generator/nft_common.py` — imported by both `jmeter.py` and the new
`devweb.py`. This is a pure extraction, no behavior change; verified by re-running the
full parser-worker suite (672 tests) immediately after the extraction, before any new
DevWeb code is added, so a regression here is caught before it can be blamed on new work.

### 3.2 DevWeb project structure (one script for the whole upload)

```
devweb/
├── main.js                      # one script, N named actions (one per stub)
├── <ProjectName>.usr            # VuGen project manifest
├── default.cfg
├── default.usp
├── rts.yml                      # HOST/PORT as userArguments, mirrors JMX's user-defined vars
├── parameters.yml                # 3 parameter entries per stub, namespaced (see 3.3)
├── DevWebSdk.d.ts                # copied verbatim from the official SDK (vendor artifact)
├── tsconfig.json
├── Action.c / vuser_init.c / vuser_end.c   # empty stubs, VuGen loader requirement
├── ScriptUploadMetadata.xml      # for LRE/PC upload
└── data/
    ├── <stub-1-slug>.csv
    ├── <stub-2-slug>.csv
    └── ...
```

### 3.3 Per-stub naming inside the single script

Since `parameters.yml` is one flat, script-wide list (no per-action scoping the way a
JMeter `CSVDataSet` can be scoped to one Thread Group), parameter names are prefixed
per stub to avoid collisions across stubs with different scenario counts:

```yaml
- name: stub01_requestPath
  type: csv
  fileName: data/stub01-createadviser.csv
  columnName: requestPath
  nextValue: iteration
  nextRow: sequential
  onEnd: loop
- name: stub01_requestBody
  type: csv
  fileName: data/stub01-createadviser.csv
  columnName: requestBody
  nextRow: same as stub01_requestPath   # keeps body/status locked to the same row
  onEnd: loop
- name: stub01_expectedStatus
  type: csv
  fileName: data/stub01-createadviser.csv
  columnName: expectedStatus
  nextRow: same as stub01_requestPath
  onEnd: loop
```

### 3.4 Script shape (one named action per stub)

```javascript
load.WebRequest.defaults.headers = { ... stub's stable required headers ... };

const T_stub01 = new load.Transaction("stub01_CreateAdviser");

load.action("stub01_CreateAdviser", async function () {
  T_stub01.start();
  const url = `http://${load.config.user.args.HOST}:${load.config.user.args.PORT}${load.params.stub01_requestPath}`;
  const response = new load.WebRequest({
    url,
    method: "POST",
    body: load.params.stub01_requestBody,
    returnBody: false,
    handleHTTPError: () => false,   // let an intentionally-non-200 scenario through
  }).sendSync();
  T_stub01.stop(
    response.status == load.params.stub01_expectedStatus
      ? load.TransactionStatus.Passed
      : load.TransactionStatus.Failed
  );
});
```

One `load.action(name, fn)` block per stub, each with its own `Transaction`. This is
the direct DevWeb analogue of "one Thread Group per stub" within a single script — the
honest limitation (flagged, not hidden) is that all actions in one script run on the
same Vuser pool per the script's one Run Logic tree, so independent per-stub TPS
scaling the way separate JMeter Thread Groups allow is not available without splitting
into separate scripts later. Documented in the generated README exactly as the
JMeter WS-Security/fault/Handlebars gaps were documented in Phase 1 — a stated
limitation, not a silent one.

### 3.5 Out of scope (same list as Phase 1, plus one DevWeb-specific item)

SOAP WS-Security auth injection, fault/delay scenario replication, Handlebars-templated
response assertions — unchanged from Phase 1. Additionally: **no correlation/extractors**
— every Mockingbird stub is one independent captured endpoint, not a multi-step chained
user journey with a session token to correlate, so `load.JsonPathExtractor` etc. are
correctly unused, not a missed feature.

### 3.6 Delivery

New endpoint (name TBD, e.g. `GET .../stubs/{id}/nft-scripts.zip`) replacing the
*portal button's* target — the existing `nft-jmeter.zip` endpoint is left in the
codebase exactly as shipped, so nothing that already works can regress. The new
endpoint's zip contains `jmeter/` (unchanged content, produced by the existing
`build_jmeter_test_plan_files`) and `devweb/` (new, from `build_devweb_project_files`)
as sibling top-level folders.

## 4. Verification plan (no VuGen license available in this environment)

Same rigor standard as Phase 1's real-JMeter validation, adapted to what's actually
reachable here:

1. **Unit tests** for `generator/devweb.py` — parameters.yml correctness (3-column
   lockstep via `same as`), CSV correctness/escaping, per-stub naming collision safety,
   all three stub shapes (single-scenario, body-differentiated, URL-segment).
2. **Real-Node.js execution** of the actual generated `main.js` against a small,
   hand-written mock of the documented `load` namespace (`WebRequest`, `Transaction`,
   `params`, `action`, `config.user.args`) built strictly from the SDK PDF's documented
   semantics — run against the same real, already-validated Spring Boot stub-engine
   JARs used for Phase 1's JMeter runs. This proves script correctness, request
   correctness, and CSV row-cycling for real, not just "the JS parses."
3. **Explicitly not verifiable here, flagged honestly**: the literal "opens cleanly in
   VuGen Script Studio" step, since that needs a real VuGen/DevWeb license this
   environment doesn't have. The generated `.usr`/`rts.yml`/`parameters.yml` structure
   is built to match `bruno-devweb-converter`'s real, previously-VuGen-validated output
   field-for-field, which is the strongest substitute evidence available — but this
   should still get a real open-in-VuGen check on the user's side before calling Phase 2
   fully done.
4. Full existing suite (parser-worker + ingestion-service + portal `tsc` + real
   Playwright E2E) re-run at the end, same as Phase 1 — must stay 100% green.

## 5. Progress checklist

- [x] Confirm design with user, get explicit go-ahead to start coding — user corrected
      the initial one-project-per-stub proposal to one script covering all stubs
      (§1); design re-confirmed against the official `Parameterize values.pdf` before
      coding began
- [x] Extract shared row logic from `generator/jmeter.py` into `generator/nft_common.py`
      (behavior-preserving refactor) — full parser-worker suite green (672/672)
      immediately after, before any DevWeb-specific code was added
- [x] `generator/devweb.py` — `build_devweb_project_files(parsed, project_name)`
- [x] Unit tests for `generator/devweb.py` — 18 tests, 100% line coverage of the module
- [x] Node.js mock-`load` harness + real execution against real stub-engine JARs
      (all 3 stub shapes, combined in one script) — see §6
- [x] New combined-zip endpoint — `GET .../stubs/{id}/nft-scripts.zip`
      (`services/ingestion-service/src/ingestion_service/routers/nft.py`)
- [x] ingestion-service endpoint tests — 4 new tests, full suite 38/39 (the 1 failure is
      the pre-existing, unrelated `test_get_presigned_url_for_uploaded_stub`)
- [x] Portal wiring — `ingestionApi.downloadNftScriptsZip`, new Vite proxy rule, the
      "Download NFT Scripts" button now calls `handleDownloadNftScripts` and downloads
      `nft-scripts.zip`
- [x] Real Playwright E2E through the actual UI — `06-download-nft-scripts.spec.ts`
      (replaces the old jmeter-only spec, same button, updated for the combined zip)
- [x] Full existing test suite re-run — parser-worker 690/690, ingestion-service 38/39
      (1 pre-existing unrelated failure), portal `tsc --noEmit` clean, real Playwright
      E2E 26/26
- [x] `docs/FEATURES.md` update
- [x] Final summary to user, including the "please open this in real VuGen to confirm"
      ask from §4.3

*(This section is updated as work completes, same convention as Phase 1.)*

## 6. Real end-to-end verification results

Ran twice: once for the URL-segment (multi-scenario, most parameter-cycling-dependent)
shape alone, then once for all three shapes combined in a single script, matching the
"one script covers every stub" design directly rather than only testing shapes in
isolation.

**Setup**: `generator/springboot.py`'s real `generate_springboot_project` and
`generator/devweb.py`'s `build_devweb_project_files` were called on the *same*
in-memory `ParsedFile`, guaranteeing the real running stub and the generated DevWeb
script describe the same endpoints. The Spring Boot project was built with a real
`mvn package` and run as a real JVM process (WireMock loaded real stub mappings,
confirmed via its own startup log). A ~150-line Node.js harness
(`scratchpad/devweb-verify-all/harness.mjs`, not part of the repo) mocked the `load`
namespace strictly from the documented SDK semantics — `Transaction`, `WebRequest`
(issuing real synchronous HTTP calls via `curl`, matching DevWeb's real blocking
`sendSync()`), and a real `parameters.yml`/CSV reader implementing `nextRow:
sequential` / `"same as <param>"` / `onEnd: loop` — then dynamically imported the
*actual* generated `main.js` and ran it for 3 simulated iterations.

**Bug caught by the harness itself, not the generator**: the first run failed every
transaction. Root cause was traced to the harness's own file-writing step (a Python
`Path.write_text` call had translated `\n` to `\r\n` on Windows) combined with the
harness's CSV parser not stripping trailing `\r` from the last column of each line —
corrupting only the `expectedStatus` key lookup. Fixed by writing raw bytes
(`write_bytes`) in the generation script and normalizing `\r\n`→`\n` in the harness's
CSV parser — confirmed as a harness-only bug, not a `generator/devweb.py` defect,
since the real production endpoint writes into a zip via `zipfile.writestr()`, which
never performs newline translation.

**Result, combined 3-shape run** (`stub00_simple_stub`, `stub01_body_differentiated`,
`stub02_url_segment_stub`, one script, 3 iterations):

```
Distinct URLs hit across 3 iterations: 4 -> http://localhost:8080/api/test,
  http://localhost:8080/api/accounts,
  http://localhost:8080/api/customers/cust-1/profile,
  http://localhost:8080/api/customers/cust-2/profile
All transactions passed: true
PASS
```

- Real requests reached the real stub for all three shapes.
- URL-segment cycling confirmed correct: cust-1 → cust-2 → cust-1 (proves
  `nextRow: sequential` + `onEnd: loop`).
- Body-differentiated stub correctly returned 200 for the Alice variant and 404 for
  the Bob variant on alternating iterations, and **both** were reported
  `TransactionStatus.Passed` — proving `nextRow: "same as <requestPath param>"`
  correctly keeps `requestBody` and `expectedStatus` locked to the same captured row
  as `requestPath`, not just cycling independently.
- Single-scenario stub passed on every iteration as expected.

This is real, not simulated: a real JVM, a real WireMock server, real TCP requests,
and the exact bytes that will ship in `nft-scripts.zip`. What it cannot confirm —
flagged, not hidden — is the literal "opens without error in VuGen Script Studio"
step, which needs the user's own VuGen/DevWeb license.

## 7. Real-VuGen bug report and fix (BUG — found via actual user testing)

The §4.3 gap was closed for real: the user opened a generated project (from real
`Sample_SV_Files/Wealth` data) in real VuGen and hit a genuine error:

```
failed to read file stub00_createadviserpost_request.csv from line 2, check file format error.
```

### Root cause

The failing row's `requestBody` CSV field held the real captured JSON payload with
RFC4180 doubled-quote escaping (`"{ ""email"" : ""joe.doe@doe"" }"`) — the same
escaping convention `generator/jmeter.py` already uses successfully (proven in Phase
1's real JMeter runs against XML bodies with the same quote-heavy shape) and the same
convention `bruno-devweb-converter`'s own `generateCollectionDataCSV()` uses. JMeter's
`CSVDataSet` parses it fine; **VuGen's CSV reader evidently does not accept it** —
every one of the four stubs' CSVs had this shape (JSON quotes for the two JSON stubs,
XML attribute quotes like `version=""1.0""` for the two XML stubs), so this wasn't a
one-off — it would have broken all four sooner or later.

Investigated and ruled out before settling on the real cause: file encoding /
Windows-1252-vs-UTF-8 (a real, documented VuGen quirk found in
`bruno-devweb-converter`'s own `BUGS.md` — BUG-026/027 — but the failing file was
confirmed pure ASCII via a hex dump, no BOM, so not the trigger here). Also searched
for the exact VuGen error text and general CSV-quoting guidance for DevWeb; neither
the official docs nor public discussion gave a definitive answer on VuGen's exact
quoting rules for embedded quotes.

### Fix — sidestep the whole risk class rather than guess at undocumented rules

Rather than gamble on a different quoting convention that might fail differently,
request bodies are no longer embedded in the CSV at all. Each scenario's body is now
written to its own plain file — `data/<stub-base>-<scenario-index>.body.txt`,
containing the raw payload with **no CSV escaping applied to it** — and referenced via
the SDK's own documented `bodyPath` `WebRequest` option (`main.js` now uses
`bodyPath: load.params.X_requestBodyFile` instead of `body: load.params.X_requestBody`).
The CSV itself now only ever holds a URL path, a body-file path, and a status code —
none of which need quoting in real-world use, so the entire class of "does VuGen
accept this quoting convention" risk is removed rather than argued about.
`parameters.yml`'s `requestBody` param/column was renamed to `requestBodyFile`
throughout; the `"nextRow: same as <requestPath param>"` lockstep mechanism is
unchanged and still keeps body-file/status locked to the same captured row as path.

### Verification of the fix

1. **18 → 22 parser-worker unit tests updated/added** for the new CSV shape (path +
   body-file-reference + status only) and per-scenario body files, including a test
   that a body containing both quotes and commas together produces a CSV field with
   zero quote characters in it.
2. **Re-parsed the actual real `Sample_SV_Files/Wealth` files** (zipped, run through
   the real `detect_and_parse`, the same 4 stubs the user's own download produced:
   CreateAdviserPost, GetAdvisers, AccountInstructions ×8, CustomerInstructionsAddressBookPost
   ×29) and confirmed directly: every generated CSV row now contains zero embedded
   quote characters; every `.body.txt` file holds the real captured JSON/XML verbatim,
   including its natural quotes, completely unescaped.
3. **Real end-to-end re-run** against this exact real Wealth data: built and ran the
   real Spring Boot + WireMock stub from the same parsed data, extended the Node.js
   verification harness's `WebRequest` mock to resolve `bodyPath` (reading the
   referenced file relative to the script folder, matching the documented behavior),
   and ran all 4 real stubs for 3 iterations. Result: all 12 transaction calls
   `Passed`, real bodies (the exact JSON with `joe.doe@doe`, the exact XML with
   `xmlns:xsi=` attributes) sent correctly over real HTTP, correct row cycling across
   `AccountInstructions`' 8 scenarios and `CustomerInstructionsAddressBookPost`'s 29.
4. Full suite re-run: parser-worker 694/694, ingestion-service 38/39 (same
   pre-existing, unrelated failure as before).

Still not verifiable in this environment — same gap as §4.3, now narrower: whether
VuGen accepts *this* CSV shape cleanly needs the user's own re-test. Given the fix
removes the exact field type (a quote-and-comma-bearing value) that VuGen's own error
pointed at, this is a well-evidenced fix, not a guess repeated.

## 8. Proactive hardening pass — "different inputs tomorrow"

After the §7 fix, explicitly asked to make sure the generator holds up for input
shapes not yet seen, not just the specific Wealth sample that broke it. Reviewed
`generator/devweb.py` line by line for anywhere raw, user-controlled text gets
embedded into a context with its own syntax rules, then wrote a real, reproducing
test for each risk found before fixing it (not fixed speculatively).

### A real second bug, found and fixed the same way as §7

`main.js`'s header docblock (`/** ... */`) interpolates `project_label` directly —
and `project_label` is the stub name from the upload form, fully user-controlled.
A name containing a literal `*/` prematurely closes the comment, turning the rest of
the intended comment text into raw JS source. **Reproduced for real**:

```
node --check main.js
SyntaxError: Unexpected identifier 'from'
```

Same root issue, smaller blast radius, in the per-stub `// {method} {url}` line
comment: a captured URL containing an embedded newline would break out of a `//`
comment early (line comments only end at a newline). `*/` itself is harmless in a
line comment, only the docblock was at risk from that specific sequence.

**Fix**: two small sanitizers — `_js_block_comment_safe()` (strips newlines, breaks
up `*/` into `* /`) applied to `project_label`, and `_js_line_comment_safe()` (strips
newlines) applied to the captured URL in each stub's comment line. Neither changes
the *values* used for the actual HTTP request (path/body/headers still come from the
real captured data via `load.params`/`bodyPath`) — only the human-readable comment
text is touched, so nothing about request correctness changes.

### Also fixed while auditing

- `_script_name()` (the `.usr` filename) had no length cap, unlike `safe_filename()`'s
  existing 80-char cap for CSV/body-file names — an unusually long project name could
  push a generated path over Windows' `MAX_PATH` once combined with zip folder
  nesting. Capped at 80 chars for consistency.

### Checked and confirmed already safe (no change needed)

- `generator/jmeter.py` — every user-controlled value already goes through `_esc()`
  (proper XML attribute escaping) before embedding into the `.jmx`; the same class of
  injection isn't possible there. Confirmed by reading every call site, not assumed.
- Header values embedded in `main.js` — built via `json.dumps(...)`, which correctly
  escapes quotes/backslashes/control characters for a JS object literal, and defaults
  to `ensure_ascii=True` (all non-ASCII automatically escaped to `\uXXXX`), so header
  content was never actually at risk — verified with a test using a header value
  containing quotes, backslashes, and tabs together.
- Body content — never interpolated into `main.js`'s JS source at all, in either the
  old or new design; it only ever flows through as a `load.params...`/`bodyPath`
  reference, so arbitrary body content (including embedded `*/`, quotes, unicode) was
  never a JS-injection risk, only ever a CSV-escaping risk (§7).

### New test coverage (8 tests, all passing with real `node --check`)

Project/stub name containing `*/`; captured URL containing a raw newline; a stub name
and body full of real unicode (`François Müller`, `£`/`€` symbols, Japanese
characters) — generation must not crash and must still produce valid JS regardless of
what VuGen's own file-encoding assumptions turn out to be, a question still open per
§7; apostrophes in names (`O'Brien's`); all five common HTTP methods; a project/stub
name close to 600 characters (confirms the new cap holds and output stays valid);
a stub name that's pure punctuation (confirms the existing `"stub"` fallback still
produces valid, non-empty identifiers); a header value combining quotes, backslashes,
and tabs.

### Re-verification

Full parser-worker suite: 702/702 (694 + 8 new). Re-ran the real
`Sample_SV_Files/Wealth` data through the hardened generator end-to-end
(`detect_and_parse` → `build_devweb_project_files` → real `node --check`) — still
clean, confirming the hardening pass didn't regress the §7 fix.

### What's still open, flagged not hidden

Whether VuGen's CSV/parameter-file reader assumes UTF-8 or Windows-1252 for non-ASCII
content remains unconfirmed — reasoned through in detail (the modern DevWeb execution
engine is Node.js-based per the SDK docs' own repeated references to Node.js Buffers,
which points toward UTF-8, versus `bruno-devweb-converter`'s documented BUG-026/027
where VuGen's *legacy IDE editor* specifically reads `.c` files as Windows-1252 — a
different subsystem), but genuinely not verifiable without a live VuGen test against
non-ASCII input. None of the current real sample data exercises this path yet. If a
future real dataset with accented names or currency symbols produces garbled (not
necessarily broken) characters when opened in VuGen, that confirms the Windows-1252
theory and the fix would be switching CSV/body-file writes to `cp1252` — flagging this
now rather than silently assuming UTF-8 is correct.

## 9. Second real-VuGen round: two more findings, both fixed

The §7 fix was re-tested by the user in real VuGen against real Wealth data and got
past the CSV parsing error, surfacing two further issues — real progress, not a
repeat of the same bug.

### 9a. `nextValue getter was not defined` at script initialization

```
Error (-227755): error loading parameters from yml file nextValue getter was not
defined map[columnName:requestBodyFile fileName:data/stub00_accountinstructions_
request.csv name:stub00_accountinstructions_request_requestBodyFile nextRow:same
as stub00_accountinstructions_request_requestPath onEnd:loop type:csv]
```

**Root cause — a misreading of the official doc, not a guess this time.** The
"Parameterize values" doc states `nextValue` is *ignored* when `nextRow: "same as
<param>"` is used, and `_build_param_block` omitted the field entirely on the
`requestBodyFile`/`expectedStatus` entries on that basis. But "ignored" meant ignored
*in row selection*, not optional in the YAML — the real parser still requires the key
to be present. This was checkable in hindsight: the vendor's own example YAML in that
same doc, and `bruno-devweb-converter`'s real, previously-VuGen-validated
`parameters.yml` output (both reviewed back in §2, but not re-checked closely enough
against this specific field) **both always include `nextValue: iteration` even on
`same as` rows** — the evidence was already sitting in the reference material.

**Fix**: `nextValue: iteration` added to every parameter block unconditionally,
including the `same as` ones. One line changed per block, no structural change.

### 9b. Missing `id` on every `WebRequest`

The user asked directly why every request wasn't carrying an `id`. Checking the
reference converter's own real output again: every `WebRequest` there has a
sequential `"id"` (used by VuGen to generate the matching snapshot file for the
Replay view — documented in the SDK: *"The ID used to generate the corresponding
snapshot file"*). This generator never carried that over — a real parity gap, not a
deliberate omission.

**Fix**: `id: <n>` added as the first property of every generated `WebRequest`,
1-based and sequential across the whole script (stub index + 1) — matching the
reference converter's own numbering convention. Currently 1:1 with stub order since
each stub still produces exactly one request per action; documented as such so a
future multi-request-per-action design doesn't silently reuse stale IDs.

### Verification

5 new/updated parser-worker tests: every parameter block (including `same as` ones)
has `nextValue` present; single- and multi-stub scripts get correct sequential `id`s.
Full suite: parser-worker 705/705, ingestion-service 38/39 (same pre-existing
unrelated failure). Re-generated the real `Sample_SV_Files/Wealth` project end-to-end
and confirmed directly in the output: every `parameters.yml` block now has
`nextValue: iteration`, and `main.js`'s four requests carry `id: 1` through `id: 4`.

## 10. Third real round: `data/` subfolder broke LRE's "runtime files only" upload

The user reported: uploading only "runtime files" to LRE (not a full script upload)
silently dropped every `.body.txt` file — "unable to find the .txt files" at replay
time — and worked around it themselves by (a) flattening every CSV/body file out of
`data/` into the project root, and (b) manually adding each `.body.txt` file to the
`.usr` file's `[ManuallyExtraFiles]` section, e.g. `stub00_createadviserpost_request
-0.body.txt=`.

**Root cause.** `parameters.yml`'s CSV references (`fileName: ...`) are a structured,
first-class VuGen construct — any packaging tool can discover which CSVs are needed
just by reading `parameters.yml` itself. A `bodyPath` value, by contrast, is *data
inside a CSV row*, only known at runtime — there's no static reference anywhere in
`main.js` or `parameters.yml` for a "runtime files only" packaging step to follow.
Nothing in the generated project declared these files as needed, so they were
invisible to that packaging step. Keeping them in a `data/` subfolder made the same
underlying problem worse rather than causing it.

**Fix — replicates the user's own confirmed-working manual fix exactly, generalized:**
- Every CSV and `.body.txt` file now lives flat at the project root, not under `data/`.
- Every one is listed explicitly in `ScriptUploadMetadata.xml`'s `<GeneralFiles>`
  with `Filter="2"` (matching `parameters.yml`/`rts.yml`'s "uploaded + needed at
  runtime" classification), rather than only appearing in a CSV's own content.
- Every one is also listed in the `.usr` file's `[ManuallyExtraFiles]` section — the
  same section, and the same fix, the user had already found and applied by hand.
  Matches the reference converter's own behavior of omitting the section entirely
  when there's nothing to list (verified with a zero-stub test), rather than
  emitting an empty header.

### Verification

4 new parser-worker tests (every data file declared in `[ManuallyExtraFiles]`;
`ScriptUploadMetadata.xml` lists every data file at `Filter="2"`; files are flat, not
in a subfolder; the empty-project case omits `[ManuallyExtraFiles]` entirely) — 37/37
devweb tests, full suite 709/709. Re-generated the real `Sample_SV_Files/Wealth`
project end-to-end and confirmed the output byte-for-byte matches the shape of the
user's own manual fix: all 46 files flat at project root, all 42 CSV/body files
listed in both `ScriptUploadMetadata.xml` (`Filter="2"`) and `.usr`'s
`[ManuallyExtraFiles]`. Real `node --check` on the regenerated `main.js` still passes
(this change is file-layout-only; request logic is untouched).

**Side finding, fixed while re-running the full real E2E suite for this change**: the
earlier port-migration commit (3000→3010, 3001→3002) had missed several hardcoded
`localhost:3000`/`:3001` references — `portal/playwright.config.ts`,
`portal/playwright.real.config.ts`, `portal/e2e/real/05-download-stub.spec.ts`, and
`portal/e2e/manual-ui-audit.ts` — which broke the real E2E suite (`ECONNREFUSED
::1:3001`) until corrected here. `scripts/start-services.ps1`,
`scripts/seed-users.ps1`, `setup.ps1`, and `portal/playwright.screenshots.config.ts`
still have the same stale references and were intentionally left alone (out of scope
for this fix) — flagged here rather than silently left for someone to trip over.
