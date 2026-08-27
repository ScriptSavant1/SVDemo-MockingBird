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
