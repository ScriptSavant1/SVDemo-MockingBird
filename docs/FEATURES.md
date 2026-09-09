# Mockingbird — Features

Feature-level documentation for behavior that isn't obvious from
`ARCHITECTURE.md`'s system-level view, but that a future session (or a
teammate) needs to understand before touching the relevant code. Organised
by feature area, newest first within each area.

---

## CA LISA / IBM RTWS Capture Parsing

Parses recorded HTTP request/response capture files (`.txt` / `.xml` /
`.json`) into WireMock stubs. Lives in
`services/parser-worker/src/parser_worker/parsers/ca_lisa_parser.py`.

### Two structural variants, one shared pipeline

CA LISA (and hand-authored files following the same shape) export captures
in one of two layouts:

- **Labelled** — explicit section-label lines (`RequestHeader:`,
  `ResponseHeader:`, or a tool-specific custom prefix like
  `AccountInstructionsRequestHeader:`) mark each block.
- **Inline** — no labels at all; a bare `={Method="POST" ...}` block is
  followed directly by the body, and the response is either
  `ResponseHeader={StatusCode=...}` or a bare `={StatusCode=...}` block.

Label **text** is never inspected for classification — a label's role
(request-header / response-header / body) is decided structurally, by what
immediately follows it (a `={Method=` block, a `={StatusCode=` block, or
plain body content). This is what lets the parser survive arbitrary label
naming — CA LISA export-tool customisations, Postman/Bruno-style exports,
hand-authored files — without new code per naming convention.

Both variants converge on one shared builder,
`_build_stub_from_captures` (fed by `_Capture` records from either
`_scan_labelled_captures` + `_resolve_labelled_captures`, or
`_scan_inline_captures`), so "how many captures does this file have, and
how are they paired/differentiated" is answered identically regardless of
which structural variant produced them. An earlier version of the inline
variant only ever looked at the first request/response marker in a file —
anything recorded after it was silently dropped or garbled into the first
capture's body; this is why inline files were fixed at the same time as
the multi-capture work below.

Once paired (request[i] ↔ response[i], up to
`min(len(requests), len(responses))` — a mismatched count is not an error,
the extra capture is just left unpaired), `_build_stub_from_captures`
decides which of three shapes the captured URLs actually form:

1. **All captures share one exact URL** → `_build_same_url_stub` (see
   "Multiple captures at the same URL" below) — the common case.
2. **URLs differ, but only in one path segment, common to every capture**
   (an ID embedded in the path itself) → `_build_url_pattern_stub` (see
   "URL path segment differentiation" below).
3. **URLs differ with no such pattern** (genuinely different, unrelated
   operations that happened to land in one file) →
   `_build_stubs_grouped_by_url`: one `ParsedStub` per distinct URL, each
   still handled by case 1 or 2 for whatever captures share that URL.
   Guarantees no capture is ever silently dropped just because the file as
   a whole doesn't fit one clean shape — an earlier version of this parser
   used the *first* capture's URL for the whole file and discarded every
   other capture's distinct URL entirely, the "only one URL created,
   repeatedly" bug.

### Multiple captures at the same URL

A single operation is often recorded multiple times — the same URL, the
same headers, different payloads (e.g. `POST /accountinstructions` called
once per test customer).

For a stub with more than one paired capture, `_differentiate_bodies`
auto-selects a body field whose value differs across every capture (an
XML leaf element via local-name, or a top-level JSON scalar field) and
builds a WireMock `bodyPatterns` matcher (`matchesXPath` / `matchesJsonPath`)
per scenario — the same manual pattern previously used to fix one-off
same-URL SOAP mapping collisions, now automatic. If no single field reliably
distinguishes every capture, scenarios fall back to `MatchType.ALWAYS` (only
correct for a single capture; multiple ALWAYS-matched scenarios on one stub
will collide in WireMock, so this is a known, accepted limitation rather
than a silent wrong answer).

Headers are also auto-filtered by the same signal: with more than one
capture, only headers whose value is **identical across every capture**
become required-match headers. Correlation/trace IDs (`x-requestid`,
`traceparent`, ...) differ on every real call by design — baking one
captured value in as a required match would mean the resulting stub could
never match a real replay request. No hardcoded list of "known volatile"
header names is needed; the cross-capture comparison finds them
automatically.

### URL path segment differentiation

Some operations embed the discriminating value in the **URL path itself**,
not the body — e.g. `POST /customerinstructions/{customerId}/addressbook`,
recorded once per customer with the ID as a literal path segment
(`.../062-2187638988/addressbook`, `.../289-9984361405/addressbook`, ...).
`_detect_url_segment_pattern` finds this shape: given every captured URL for
one operation, split each on `/` and check whether (a) they all have the
same segment count and (b) one or more segment indices vary across every
URL, with the *combination* of values at those indices distinct for every
capture (a reliable per-capture key, not a coincidence). More than one
varying segment is a real case, not just a theoretical one — an operation
like `/accounts/{acctId}/sub/{subId}` with two IDs embedded in the path —
and is handled identically to the one-segment case: each varying segment
becomes its own capture group in the returned regex (e.g.
`/api/accounts/([^/]+)/sub/([^/]+)`), and the per-capture key is every
varying segment's value joined with `_URL_SEGMENT_KEY_JOIN` (an ASCII "unit
separator", chosen because it's vanishingly unlikely to appear in a real
path segment), in left-to-right order. An earlier version only recognised
exactly one varying segment and fell back to `_build_stubs_grouped_by_url`
(one stub per distinct URL) for anything with two or more — not wrong, but
it silently re-created the "many stubs from one operation" problem this
mechanism exists to solve. Any deviation from the shape (different segment
counts, no segment varying at all, a repeated combined key) returns `None`,
and the captures fall through to `_build_stubs_grouped_by_url` (case 3
above) rather than a wrong guess.

`_build_url_pattern_stub` then builds one `ParsedStub` where:
- Each scenario carries its own `url_override` (the exact captured URL) —
  the **static-mapping** generator (`generator/wiremock.py`) uses this
  instead of the stub's shared `request.url` when present, matching that
  scenario with a plain exact `urlPath` and no `bodyPatterns` at all (the
  URL itself already disambiguates every scenario; the URL-pattern regex is
  only needed once the capture count crosses the lookup-table threshold).
- The stub's own `request.url` / `lookup_url_pattern` carries the regex
  pattern, `lookup_discriminator_type` is `"url-segment"` (no
  `lookup_discriminator_field` — there's no body field to name), and each
  scenario's `lookup_key` is that capture's (possibly composite) segment key.

For the **lookup-table** path (see "Dynamic Lookup-Table Engine" below),
`DynamicLookupRequestFilter` holds URL-pattern routes as a separate list
from exact-URL routes: an incoming request first checks the exact-URL
`HashMap` (unchanged), and only if that misses does it scan the (typically
very small — one per distinct path-templated operation project-wide) list
of compiled `Pattern`s for one whose method matches and whose regex fully
matches the request path; on a match, `joinCaptureGroups` joins every
capture group the regex matched (one per varying segment) with the same
`URL_SEGMENT_KEY_JOIN` character used on the Python side, reconstructing
the exact composite key — **no body parsing at all** for this route kind,
regardless of how many segments vary.

### HTTP method is part of an operation's identity, not just its URL

Captures are split by method *before* any URL-shape decision runs — a file
recording both `GET /accounts/123` and `POST /accounts/123` (a REST
resource that legitimately supports more than one verb) must never merge
those into one stub. A stub has exactly one `request.method`; merging would
fix it to whichever capture happened to appear first in the file and make
every capture of the other method permanently unreachable (verified live —
this was a real bug, not a hypothetical one, before the fix). When one
source file produces more than one stub this way (or via the
"unrelated-URLs" fallback above), each stub's name is disambiguated with
its method and URL — otherwise their generated mapping/lookup-table files
collide on disk (`_safe_filename(stub.name, ...)` would produce the same
path for more than one stub, and the later one silently overwrites the
earlier one's file in the generator's output — also a real, verified bug
before the fix).

### Content-first file classification (ZIP / batch upload)

`detector.py`'s ZIP handler and the portal's client-side
`httpCapturePairing.ts` both classify a file as request/response by
**content** first (does it contain a `={Method=` or `={StatusCode=` marker,
searched independently of any label text), falling back to filename
substring matching only when content is ambiguous. A real CA LISA export
tool does not always name a file consistently with what it contains — a
file named `..._Request.txt` containing pure response data has been
observed live — so filename-first classification silently misroutes files
exactly like that.

---

## Dynamic Lookup-Table Engine

`services/parser-worker/src/parser_worker/generator/lookup_table.py` +
`DynamicLookupRequestFilter.java`.

### Why this exists

Real-world CA LISA exports can record dozens to hundreds of distinct
variants of one operation, all at the same URL (see "Multiple captures at
the same URL" above). Below roughly a dozen variants, WireMock's normal
static-mapping approach — one JSON file per captured scenario, matched
sequentially by WireMock in priority order — is simple, inspectable via
WireMock's own admin UI, and fast: WireMock comfortably serves 10K+ TPS
with mapping counts in the hundreds, especially with this project's
Java 21 virtual threads. Above that, two costs start to matter:

1. **File-count sprawl** — hundreds of near-duplicate mapping files per
   operation are painful to review/version, especially multiplied across
   many operations in one project.
2. **Matching cost** — WireMock evaluates a request against mappings
   sharing a URL sequentially until one matches; for N same-URL mappings
   using XPath/JSONPath `bodyPatterns`, that's worst-case O(N) pattern
   evaluations per request.

### Design

Above `LOOKUP_TABLE_THRESHOLD` (currently 15; see
`generator/lookup_table.py`) same-URL captures for one stub, the generator
switches from N static mapping files to:

- **One data file** (`src/main/resources/lookup-tables/<stub>.json`) —
  method, URL, required (stable) headers, the discriminator field/type
  (`xpath` | `json`, the same field `_differentiate_bodies` already
  selected), and one entry per capture (`key`, `status`, `headers`, `body`).
- **`DynamicLookupRequestFilter`** — a `StubRequestFilterV2` registered into
  WireMock's own request pipeline (`WireMockConfig.java`, the same
  mechanism `WsSecurityRequestFilter` already used), loaded once at JVM
  startup into a plain immutable `Map<routeKey, LookupRoute>`. For a
  request matching a registered route (and its required headers), it
  extracts the discriminator value from the body — XML via a streaming
  StAX reader that stops at the first matching leaf element, JSON via
  Jackson's streaming parser scanning only top-level fields; neither builds
  a full DOM/tree — and answers directly with `RequestFilterAction.stopWith(...)`,
  **before WireMock's own stub-matching ever runs**. No `StubMapping` is
  ever registered for these routes; they don't appear in WireMock's
  `Loaded N stub mappings` count, only in this filter's own
  `DynamicLookupRequestFilter: loaded N route(s), M total entries` line.

An unrecognised discriminator value, or a request missing a required
header, is **not** intercepted — the filter calls
`RequestFilterAction.continueWith(request)` and lets WireMock's normal "no
mapping matched" response apply, rather than fabricating a response for
data it was never given.

Performance/lifecycle properties, since this sits directly on the request
path: the lookup map is built once and never mutated afterwards, so reads
need no locking; both parsing factories (`XMLInputFactory`, `JsonFactory`)
are stateless configuration holders safe to share across threads —
creating a reader/parser from either doesn't mutate the factory — so there
is no per-request or per-thread allocation for them. Verified with 2,000
concurrent requests across 64 threads, all correct (no cross-talk from the
shared factories).

### Two independent mapping-generation paths, one shared source

`generator/wiremock.py`'s `build_wiremock_mappings(parsed, include_lookup_table_stubs=False)`
is the single place WireMock mapping **content** is built — the full Spring
Boot project generator and `ingestion-service`'s plain `wiremock.zip`
quick-download both call it, so they can never disagree about what a
mapping contains (this used to not be true: `ingestion-service` had its own
independent, simpler mapping builder with no `bodyPatterns` support at all,
so a same-URL multi-capture stub would silently collide in that download
even after the full Spring Boot project handled it correctly).

`include_lookup_table_stubs` exists because the two products need opposite
behavior at the threshold: the full Spring Boot project has
`DynamicLookupRequestFilter` available and should skip static mappings for
a qualifying stub (`include_lookup_table_stubs=False`, the default); the
plain `wiremock.zip` is just JSON files with no accompanying Java code, so
it has nothing to hand a high-variant stub off to and must always emit
static mappings regardless of the threshold (`include_lookup_table_stubs=True`).

### Generation is fully in-memory

`generator/springboot.py`'s `build_springboot_project_files` builds the
entire Spring Boot project (templates, `pom.xml`, setup guide HTML,
mapping files, lookup tables) as `{relative_path: bytes}` with zero
filesystem writes beyond reading the bundled (read-only) templates.
`generate_springboot_project` (disk) and `generate_springboot_project_zip`
(ZIP bytes, used directly by `ingestion-service`'s upload handler) are thin
wrappers around it. This replaced a pattern where the upload handler wrote
every generated file to a real temp directory, read them all back with
`rglob` to build a ZIP, then deleted the directory — real disk I/O for
every one of potentially hundreds of generated files, on every single
upload, purely to immediately re-read and discard them.

---

## Batch Upload Grouping (Portal)

`portal/src/pages/UploadPage.tsx`. Two modes when uploading multiple files:

- **Combined** (default, recommended) — every selected file is zipped
  as-is and sent to the backend's existing ZIP-upload pairing
  (`detector.py`'s `_detect_and_parse_zip` / `_pair_files`), which matches
  request/response halves and folds every endpoint into one `Stub` record.
- **Separate** — files are paired client-side
  (`portal/src/lib/httpCapturePairing.ts`, kept in lockstep with the
  Python `_pair_files` — same regexes, same scoring, same strategy order)
  and each pair (or standalone file) becomes its own upload, its own `Stub`.

Both paths now classify request-vs-response by content before filename,
matching the backend fix above (see "Content-first file classification").

---

## Automatic JMeter NFT Script Generation (Phase 1)

`services/parser-worker/src/parser_worker/generator/jmeter.py` +
`services/ingestion-service/src/ingestion_service/routers/nft.py` +
`portal/src/api/ingestion.ts` (`downloadJmeterZip`) + the "Download NFT
Scripts" button on the project page. See
`docs/progress/PHASE1_JMETER_NFT_GENERATION.md` for the full impact
analysis and testing record.

### Why this exists

Every stub Mockingbird generates already carries everything a JMeter test
needs — method, URL (or URL pattern), required headers, and, via the
dynamic lookup-table/URL-segment work above, exactly which field or path
segment differentiates each captured scenario. NFT testers previously had
to hand-write a JMeter script per stub from scratch. This feature generates
one automatically, as a **separate download** from the stub engine
project, so the two artifacts (stub + test plan) can be grabbed
independently.

### Scope (Phase 1 — JMeter only)

One `.jmx` per download, one Thread Group per stub, covering every stub
shape the parser produces: single-scenario, same-URL body-differentiated,
and URL-segment-differentiated. Correct method, URL/URL pattern, required
headers, and expected status per scenario (never hardcoded to 200).
**Explicitly out of scope**, and stated in the generated `README.md` rather
than silently skipped: SOAP WS-Security auth injection, fault/delay
scenario replication, and assertions on Handlebars-templated response
content. LoadRunner DevWeb scripts are a deliberately separate, later
phase — not attempted here.

### Design

For each `ParsedStub`, per scenario: `path = scenario.url_override or
stub.request.url` (mirrors `generator/wiremock.py`'s own logic — for
URL-segment stubs, `stub.request.url` is a regex pattern, not a literal);
`body = scenario.captured_request_body or _synthesize_minimal_body(...)`
— a new optional `ParsedScenario.captured_request_body` field (populated
by the CA LISA parser from data it already holds) supplies a real captured
request body when available, otherwise a minimal body is synthesized that
is *guaranteed to satisfy the stub's own match condition* (e.g.
`<root><field>value</field></root>` for an XPath discriminator, `{"field":
"value"}` for a JSONPath one); `expected_status = scenario.status`, never
hardcoded.

**Verified JMeter constraint** (checked against real JMeter
documentation/community reports, not assumed): `CSVDataSet` reads its file
line-by-line *before* applying quote/delimiter parsing, so a captured
request body's embedded newlines would corrupt row parsing even with
`quotedData=true`. Fixed by collapsing embedded newlines to a single space
in every generated CSV field — safe for both XML (whitespace between tags
is insignificant) and JSON (a raw literal newline inside a string value
isn't valid JSON to begin with).

One CSV per stub (`requestPath,requestBody,expectedStatus`, one row per
scenario), one Thread Group per stub (`CSVDataSet` → `HeaderManager` → one
`HTTPSamplerProxy` using `${requestPath}`/`${requestBody}` → a
`ResponseAssertion` on `${expectedStatus}`), delivered via
`GET /api/v1/projects/{project_id}/stubs/{stub_id}/nft-jmeter.zip`
(ingestion-service), generated **on demand at download time**, never at
upload time — this adds zero work/risk to the upload path (see BUG-034),
mirroring the "regenerate from stored source" fallback `wiremock.zip`
already uses, generalized to also work when the source is stored in S3
(not just local storage).

### Testing

Generator logic: 17 parser-worker unit tests (CSV escaping/round-trip,
XML well-formedness, all three scenario shapes, synthesized-body
correctness, newline-collapsing) plus three real, non-GUI Apache JMeter
5.6.3 runs against real running stub-engine JARs — one per scenario shape
— each 25/25 requests successful, 0 errors, all expected status codes,
confirmed by inspecting `results.jtl` directly rather than trusting the
console summary line. Endpoint: 4 ingestion-service tests (valid ZIP
contents, unknown stub, unknown project, works immediately post-upload
without requiring a separate generate/deploy step). Delivery: a real
Playwright E2E that logs in, creates a project, uploads a real sample file
through the actual UI, clicks the real "Download NFT Scripts" button, and
parses the downloaded ZIP — run alongside the full existing real E2E suite,
no regressions (this test now covers the combined zip from Phase 2 below).

---

## Automatic LoadRunner DevWeb (VuGen) Script Generation (Phase 2)

`services/parser-worker/src/parser_worker/generator/devweb.py` +
`services/parser-worker/src/parser_worker/generator/nft_common.py` (shared
with `generator/jmeter.py` above) + the combined
`GET .../stubs/{stub_id}/nft-scripts.zip` endpoint. See
`docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md` for the full design
rationale and testing record.

### Why this exists, and the key design decision

Phase 1 covered JMeter; this phase adds LoadRunner DevWeb (VuGen) as a
second NFT tool, delivered in the **same** download as one combined zip
with `jmeter/` and `devweb/` top-level folders (the existing
`nft-jmeter.zip` endpoint is untouched, kept for anything already
depending on it). Per explicit direction: **one DevWeb script covers every
stub** in the project — not one VuGen project per stub — mirroring
JMeter's "one test plan, one Thread Group per stub" shape. The DevWeb
analogue of a Thread Group is a named `load.action()` + `load.Transaction`
pair; one CSV parameter file per stub, since DevWeb's `parameters.yml` is
one flat, script-wide list with no per-action scoping the way a JMeter
`CSVDataSet` can be scoped to a single Thread Group — parameter names are
therefore namespaced per stub (`stub00_<slug>_requestPath`, ...) to avoid
collisions.

### Reused, not duplicated

`generator/jmeter.py`'s per-scenario row logic (`_Row`→`Row`,
`scenario_row`, body synthesis, the same newline-collapsing safeguard) was
extracted into `generator/nft_common.py` in a behavior-preserving refactor
(verified via the full parser-worker suite before any DevWeb-specific code
was added) and is now imported by both generators — one shared
implementation of "what a scenario's path/body/status resolve to," not two
copies that could drift.

### The VuGen project format is copied from a real, working reference

The mandatory/optional file set and every static template (`.usr`,
`default.cfg`, `default.usp`, `tsconfig.json`, `ScriptUploadMetadata.xml`)
were taken verbatim from a real, previously VuGen-opened project (an
internal converter tool's own generated output), not reconstructed from
documentation alone. `parameters.yml` follows the official DevWeb
"Parameterize values" documentation field-for-field, including
`nextRow: "same as <param>"` to keep a stub's `requestBodyFile`/
`expectedStatus` columns locked to the same row as its `requestPath` — the
documented mechanism for exactly this (the official doc's own example is
keeping a password locked to its username).

**Request bodies are not embedded in the CSV** (unlike JMeter, whose
`CSVDataSet` handles RFC4180-doubled-quote-escaped JSON/XML bodies fine —
proven in Phase 1's real JMeter runs). A real VuGen open of an early
version of this generator's output, using real `Sample_SV_Files/Wealth`
data, failed with `check file format error` on exactly that: a CSV field
holding a JSON/XML payload with doubled internal quotes. VuGen's CSV
reader does not accept the same convention JMeter's does. Fixed by moving
each scenario's body out of the CSV entirely, into its own plain file
(`data/<stub>-<n>.body.txt`, raw payload, no CSV escaping at all) and
referencing it via the SDK's own documented `bodyPath` `WebRequest` option
instead of `body` — the CSV now only ever holds a path, a body-file path,
and a status code, none of which need quoting in practice, removing the
entire risk class rather than guessing at a different quoting convention.
See `docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md` §7 for the full
root-cause writeup and re-verification against the real Wealth data that
originally triggered it.

Deliberately **not** bundled: the vendor's own `DevWebSdk.d.ts`. It's
Micro Focus/OpenText's proprietary SDK type-definition file — redistributing
a copy in every generated download is a licensing question this generator
does not decide unilaterally. It's only needed for editor IntelliSense,
never at runtime (the `load` namespace is injected by the real DevWeb
engine regardless of whether the file is present); the generated README
tells the tester to copy their own installation's copy in if they want it.

Also deliberately out of scope, and stated in the generated README rather
than hidden: no correlation/extractors (every Mockingbird stub is one
independent captured endpoint, not a chained multi-step journey with a
session token to correlate), and all stubs sharing one script means they
share one Vuser pool/schedule — independent per-stub TPS scaling the way
separate JMeter Thread Groups allow would need separate scripts, which
this generator does not create.

### Testing

22 parser-worker unit tests: output shape, real JS syntax validity (via
`node --check` on the actual generated `main.js`, not string matching),
XML well-formedness of `ScriptUploadMetadata.xml`, `parameters.yml`
namespacing/collision-safety and `"same as"` row-locking, per-scenario body
files (including a test that a body containing both quotes and commas
produces a CSV field with zero quote characters in it), and the same three
scenario shapes covered for JMeter (shared logic). Beyond unit tests: real
end-to-end execution — the actual generated `main.js` run under real
Node.js against a hand-built mock of the `load` namespace (built strictly
from the official SDK docs: `Transaction`, `WebRequest` via real
synchronous HTTP calls with `bodyPath` file resolution, a real
`parameters.yml`/CSV reader implementing `nextRow: sequential`/`"same as"`/
`onEnd: loop`), replayed against the same real Spring Boot + WireMock
stub-engine JARs used for Phase 1's JMeter validation — once for all three
scenario shapes combined in one script, and again against the real
`Sample_SV_Files/Wealth` data that originally surfaced the CSV-quoting bug
above. Result: correct URL cycling across iterations (proving row-cycling
and looping), correct body/status lockstep via `"same as"`, and correct
pass/fail transaction status for both a 200 and a 404 scenario. Endpoint:
4 ingestion-service tests for `nft-scripts.zip` (both folders present and
well-formed, 404s, works immediately post-upload). Delivery: the real
Playwright E2E above now also asserts the `devweb/` folder's contents.
Not independently verifiable in this environment and flagged rather than
assumed: the literal "opens cleanly in VuGen Script Studio" step, which
needs a real VuGen/DevWeb license to confirm on the user's side.

### Hardening pass for inputs not yet seen

Auditing `generator/devweb.py` for anywhere raw, user-controlled text (stub
names, captured URLs) is embedded somewhere with its own syntax rules
turned up a second real bug, reproduced with a real `node --check` before
fixing it: a project/stub name containing a literal `*/` prematurely
closes `main.js`'s header docblock comment, corrupting the rest of the
file into invalid JS. Fixed with two small sanitizers applied only to
comment text (never to the actual request data). 8 new tests cover this
plus unicode content, apostrophes, all common HTTP methods, very long
names, and punctuation-only names — all validated with real `node
--check`, not string matching. Full writeup, including what's still open
(a possible UTF-8-vs-Windows-1252 question for non-ASCII content, reasoned
through but not yet exercised by any real sample data) in
`docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md` §8.

### Second real-VuGen round — two more fixes

Re-tested by the user in real VuGen after §7's fix, which got further and surfaced
two more issues, both fixed: (1) `parameters.yml` entries using `nextRow: "same as
<param>"` omitted `nextValue` on the theory that the doc calls it "ignored" there —
real VuGen's parser requires the key present regardless (`nextValue getter was not
defined`); the vendor's own example YAML and the reference converter's real output
both always include it, which should have been caught the first time. (2) Every
`WebRequest` was missing the `id` field the reference converter's real output always
sets (used by VuGen for Replay-view snapshot mapping) — added, 1-based and sequential
across the script. See `docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md` §9.
