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

### Multiple captures at the same URL

A single operation is often recorded multiple times — the same URL, the
same headers, different payloads (e.g. `POST /accountinstructions` called
once per test customer). All captures matching that shape, in document
order, are paired: request[i] ↔ response[i], up to
`min(len(requests), len(responses))` — a mismatched count (a stray extra
response with no corresponding request, or vice versa) is not an error,
the extra capture is just left unpaired.

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
