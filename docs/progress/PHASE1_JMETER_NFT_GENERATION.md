# Phase 1 — Automatic JMeter NFT Script Generation

**Status: COMPLETE**
**Started:** 2026-08-27
**Owner constraint (user's explicit instruction, verbatim intent):** existing
upload → parse → generate → deploy flow must not be touched, disturbed, or
risked in any way. Everything in this phase is additive-only.

---

## 1. What this is

Every stub Mockingbird generates already has everything a JMeter test needs
— method, URL (or URL pattern), required headers, and (via the dynamic
lookup-table work) exactly which field/segment differentiates each captured
scenario. This phase adds a second, independent download next to the
existing "Download Stub Project" button: a ready-to-run `.jmx` test plan
(plus its CSV data files) generated automatically from the same parsed
data — no NFT tester has to hand-write a script for the common case.

**Scope for Phase 1 (JMeter only, explicitly excludes LoadRunner/DevWeb —
that's a later, separate phase if this one proves out):**
- One `.jmx` per project download, one JMeter Thread Group per stub.
- Covers every stub shape the parser already produces: single scenario, a
  stub with N same-URL body-differentiated scenarios, and a stub with N
  URL-segment-differentiated scenarios (see `docs/FEATURES.md`).
- Correct required headers, correct method, correct URL/URL pattern,
  correct expected status per scenario (not hardcoded to 200 — different
  scenarios can carry different captured status codes).
- Explicitly **out of scope for Phase 1** (documented in the generated
  README, not silently ignored): SOAP WS-Security auth injection,
  fault/delay scenario replication, Handlebars-templated response
  assertions. These are real gaps to flag, not corners to quietly cut.

---

## 2. Impact analysis — what does and doesn't change

### Touched (existing, working code)
| File | Change | Why it's safe |
|------|--------|----------------|
| `services/parser-worker/src/parser_worker/models.py` | Add `ParsedScenario.captured_request_body: Optional[str] = None` | Purely additive optional field, default `None`. No existing code reads or depends on its absence. Every existing test constructs `ParsedScenario` without it and keeps working unchanged. |
| `services/parser-worker/src/parser_worker/parsers/ca_lisa_parser.py` | Populate the new field from data *already held* in `_Capture.body` inside `_build_same_url_stub` / `_build_url_pattern_stub` / `_build_stubs_grouped_by_url` | Read-only use of data those functions already have in scope; nothing about matching, differentiation, or stub structure changes. Full 653-test suite re-run after, expect 653 passed. |
| `services/ingestion-service/src/ingestion_service/routers/upload.py` or a new sibling router | Register one new `GET` route | New route only — the existing `POST /upload`, `GET /wiremock.zip`, `GET /stub-engine.zip` handlers are not modified. |
| `portal/vite.config.ts` | Add one new proxy rule for the new endpoint path | Same pattern as the two existing ingestion-service proxy rules; doesn't reorder or touch the existing ones. |
| `portal/src/api/ingestion.ts` | Add one new `downloadJmeterZip` function | Additive export; existing exports unchanged. |
| `portal/src/pages/ProjectPage.tsx` | Add one new `Button` next to the existing "Download Stub Project" button | Same conditional block (`stub.status === "READY" && !!stub.generated_at`), one more sibling button. No existing button's condition/handler changes. |

### New (nothing else depends on these existing)
- `services/parser-worker/src/parser_worker/generator/jmeter.py` — the generator itself.
- `services/parser-worker/tests/test_jmeter_generator.py`
- `services/ingestion-service/src/ingestion_service/routers/nft.py` (new router, kept separate from `upload.py` rather than growing that file further)
- `services/ingestion-service/tests/test_nft.py`
- This progress doc.

### Explicitly NOT touched
`detector.py`, `CALISAParser` parsing/detection logic, `generator/wiremock.py`
mapping construction, `generator/lookup_table.py`, `generator/springboot.py`,
`DynamicLookupRequestFilter.java`, the upload endpoint's existing steps 1–8,
the portal upload flow, batch pairing logic. Verified by: full existing test
suite passes unchanged before any new endpoint/UI work begins, and again at
the end.

---

## 3. Design

### 3.1 Data source (no new analysis — reuse what exists)

For each `ParsedStub`, per scenario `i`:
- `method = stub.request.method.value`
- `path = scenario.url_override or stub.request.url` — the exact literal
  path to call (mirrors `generator/wiremock.py`'s own `_build_mapping`
  logic for the same reason: `stub.request.url` is a *regex pattern*, not
  a literal, for URL-segment stubs).
- `body = scenario.captured_request_body or _synthesize_minimal_body(stub, scenario)`
  — real captured request body when available (CA LISA-sourced stubs,
  via the new field above); otherwise a synthesized minimal body that is
  *guaranteed to satisfy the stub's own match condition*:
  - body-differentiated (xpath): `<root><{field}>{value}</{field}></root>`
  - body-differentiated (json): `{"{field}": "{value}"}`
  - url-segment or no discriminator: a trivial placeholder (`{}` for
    JSON content types, `<request/>` for XML, empty otherwise) — body
    content doesn't affect matching in these cases.
- `expected_status = scenario.status` — never hardcoded.
- `required_headers = stub.request.required_headers` — same for every
  scenario of one stub (that's already guaranteed by
  `_stable_required_headers`).

### 3.1.1 Verified JMeter constraint: CSV fields must stay single-line

Checked against real JMeter documentation/community reports before
committing to the CSV design (not assumed): JMeter's `CSVDataSet` reads its
file **line-by-line first**, then applies quote/delimiter parsing to each
already-split line — so a captured request body's embedded newlines would
split it across multiple malformed "rows" even with `quotedData=true`,
regardless of proper RFC4180 quoting. This is a real, documented JMeter
limitation (line-based reader, not a full multi-line-aware CSV parser),
not something a correct `.jmx` file could work around with a different
setting.

**Fix**: every CSV field (`requestBody` in particular) has its embedded
`\r\n`/`\n` collapsed to a single space before being written, keeping the
field on one physical line. Safe for both formats we generate against:
whitespace between XML tags/tokens is insignificant, and JSON can't
contain a raw literal newline inside a string value at all (it would
already be `\n`-escaped in the source text) — so this never changes
whether the body is well-formed, only its exact original formatting.
Documented in the generated README so nobody is surprised the payload
isn't byte-identical to the original capture.

### 3.2 One CSV per stub, one Thread Group per stub

Uniform shape regardless of scenario count (1 row for a single-scenario
stub, N rows otherwise) — one code path to get right and test, not several
conditionals. CSV columns: `requestPath,requestBody,expectedStatus`.
Thread Group: CSV Data Set Config (scoped to that group, `recycle=true`) →
Header Manager (the stable required headers) → one HTTP Sampler using
`${requestPath}` / `${requestBody}` → a Response Assertion on
`${expectedStatus}`.

### 3.3 Delivery

New endpoint `GET /api/v1/projects/{project_id}/stubs/{stub_id}/nft-jmeter.zip`
(ingestion-service), generated on demand at download time — **not** at
upload time, so the upload path's performance (BUG-034) gains zero
additional work and zero additional failure surface. Mirrors the existing
"regenerate on demand from the stored source file" fallback already used by
`wiremock.zip`. Zip contains `test-plan.jmx`, one `data/<stub-slug>.csv`
per stub, and a `README.md` explaining prerequisites, how to point
`HOST`/`PORT` at a running stub, and the explicit out-of-scope list from
§1.

---

## 4. Progress log

- [x] Model + parser change (`captured_request_body`), full test suite green (655/655)
- [x] `generator/jmeter.py` — one CSV per stub (`requestPath,requestBody,expectedStatus`), one Thread Group per stub, real captured request bodies when available, synthesized-but-match-guaranteed bodies otherwise
- [x] Verified (not assumed) a real JMeter CSVDataSet constraint before finalizing the CSV design: embedded newlines break row parsing even with quoted data enabled, because the file is read line-by-line before quote/delimiter parsing runs. Fixed by collapsing embedded newlines to spaces in generated CSV fields — see §3.1.1.
- [x] Real JMeter install (Apache JMeter 5.6.3, downloaded fresh, matches the `.jmx`'s declared `jmeter="5.6.3"` version) + three full real end-to-end runs, JMeter non-GUI mode against a real running Mockingbird stub-engine jar (not a mock, not just XML validation):
  - Single-scenario stub (CreateAdviser, JSON): 25/25 requests, 0 errors, all HTTP 200.
  - Body-differentiated multi-scenario stub (AccountInstructions, 8 scenarios, XML): 25/25 requests, 0 errors, all HTTP 200 — confirms `captured_request_body` + per-row XPath-matching bodies work correctly against the real stub.
  - URL-segment-differentiated multi-scenario stub (AddressBook, 29 scenarios via the dynamic lookup-table engine): 25/25 requests, 0 errors, all HTTP 200, confirmed different customer IDs actually appear in the request URL per row (real parameterization, not a fixed URL).
  - All three: `success=true` for every JTL row, zero `failureMessage` entries, confirmed via direct inspection of `results.jtl`, not just the console summary line.
- [x] Formal pytest unit tests for `generator/jmeter.py` (CSV escaping, XML well-formedness, all three scenario shapes, synthesized-body correctness) — 17/17 passing, parser-worker suite 672/672 green
- [x] ingestion-service endpoint + tests — `routers/nft.py` (`GET /api/v1/projects/{project_id}/stubs/{stub_id}/nft-jmeter.zip`), on-demand generation from stored source (local storage direct path, S3 via a temp-dir download+cleanup), covers both local-storage and S3-backed storage. `tests/test_nft.py`: 4/4 passing (valid zip contents, unknown stub 404, unknown project 404, works immediately post-upload without requiring generate/deploy first). Full ingestion-service suite re-run: 34/35 passing — the 1 failure (`test_get_presigned_url_for_uploaded_stub`) is **pre-existing**, confirmed unrelated to this work by re-running it with all NFT changes stashed out (fails identically either way).
- [x] Portal wiring — `ingestionApi.downloadJmeterZip` (`portal/src/api/ingestion.ts`), new proxy rule in `portal/vite.config.ts` (same pattern as the existing `stub-engine.zip`/`wiremock.zip` rules, ordered before the generic `/api/v1` catch-all), `handleDownloadJmeterScripts` + "Download NFT Scripts" button in `ProjectPage.tsx` as a sibling to the existing "Download Stub Project" button (same `stub.status === "READY" && !!stub.generated_at` block, no existing button's condition/handler touched). `tsc --noEmit` clean.
- [x] Real Playwright E2E — `portal/e2e/real/06-download-nft-jmeter.spec.ts`: real login, real project creation, real file upload through the actual UI, real click of the "Download NFT Scripts" button, real downloaded ZIP parsed with `jszip` (added as a portal devDependency) and asserted well-formed (`test-plan.jmx`, `data/*.csv`, `README.md`, correct JMeter XML markers, correct CSV header). Full real E2E suite re-run: **26/26 passing**, including all 5 pre-existing real E2E specs — zero regressions in login, project management, upload-and-generate, admin, or the existing wiremock.zip download flow.
- [x] Full existing test suite re-run — parser-worker (672/672), ingestion-service (34/35 — the 1 failure is the pre-existing, unrelated `test_get_presigned_url_for_uploaded_stub`, confirmed to fail identically with this phase's changes stashed out), portal `tsc --noEmit` clean, full real Playwright suite 26/26.
- [x] `docs/FEATURES.md` update — new "Automatic JMeter NFT Script Generation (Phase 1)" section added. No new bugs found this phase, so `BUGS.md` is unchanged.
- [x] Final summary given to user.

**Status: COMPLETE.**

*(This section is updated as work completes.)*
