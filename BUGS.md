# Mockingbird — Bug Tracker

Track all bugs found during development, testing, and QA.  
Format: one entry per bug, newest at the top.

---

## BUG-021 — Double-deploy allowed: "LIVE" missing from in-flight deployment guard

| Field | Value |
|-------|-------|
| **ID** | BUG-021 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/project-service/src/project_service/routers/deploy.py` |
| **Commit** | (session fix) |

**Description:**  
After BUG-020 made local-dev deployments go directly to LIVE status, clicking Deploy a second time succeeded (returned 202) instead of blocking with 409 Conflict. A duplicate deployment was created for the same stub.

**Root cause:**  
The in-flight guard queried `Deployment.status.in_(["PENDING", "BUILDING", "PROVISIONING"])` — it never included `"LIVE"`. In production with a real deployer-worker, a LIVE deployment was expected to be permanent and not re-deployed without suspending first, but the guard omitted this state.

**Fix:**  
Added `"LIVE"` to the guard: `Deployment.status.in_(["PENDING", "BUILDING", "PROVISIONING", "LIVE"])`. Second deploy now returns 409 with "Suspend it first" message.

---

## BUG-020 — Local dev deploy simulation missing: stubs stuck in PENDING, DeploymentPage/Reports unreachable

| Field | Value |
|-------|-------|
| **ID** | BUG-020 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/project-service/src/project_service/routers/deploy.py` |
| **Commit** | (session fix) |

**Description:**  
In local development (no deployer-worker SQS consumer running), clicking Deploy created a deployment record with `status="PENDING"` that never advanced. The portal showed no "View" button (only appears for LIVE/SUSPENDED deployments). The DeploymentPage, Metrics History tab, and Reports tab were therefore completely inaccessible.

**Root cause:**  
`deploy.py` only handled the SQS path. The `else` branch (no `sqs_deploy_queue_url`) committed the deployment as PENDING with no worker to advance it.

**Fix:**  
Added local dev simulation in the `else` branch: sets `job.status = "DONE"`, `deployment.status = "LIVE"`, `deployment.stub_url = f"http://localhost:8080/stubs/{stub_id}"`, `deployment.deployed_at = now`, and `stub.status = "LIVE"`. Deploy button now immediately transitions to "View" which opens the DeploymentPage with Reports tab accessible.

---

## BUG-019 — `generated_at` not set in generate local-dev inline path

| Field | Value |
|-------|-------|
| **ID** | BUG-019 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/project-service/src/project_service/routers/jobs.py` |
| **Commit** | (session fix) |

**Description:**  
When POST `.../generate` was called and `sqs_parse_queue_url` was not set (local dev), the job ran inline but never set `stub.generated_at`. The Deploy button checks `generated_at is not None` before showing — so stubs generated via the UI generate button in local dev never got a Deploy button.

**Root cause:**  
The local-dev inline path in `jobs.py` set `job.status = "DONE"` and populated `job.result` but forgot `stub.generated_at`.

**Fix:**  
Added `if not stub.generated_at: stub.generated_at = datetime.now(timezone.utc)` in the no-SQS branch.

---

## BUG-018 — `generated_at` never set after WireMock ZIP generation in upload.py

| Field | Value |
|-------|-------|
| **ID** | BUG-018 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/ingestion-service/src/ingestion_service/routers/upload.py` |
| **Commit** | (session fix) |

**Description:**  
File uploads succeeded and WireMock ZIPs were generated inline during upload, but `stub.generated_at` was never written. The `Deploy` button in the portal checks `stub.generated_at is not None` before rendering — so after an upload the Deploy button was always hidden.

**Root cause:**  
`upload.py` called `generate_wiremock_zip()` and stored the result to S3/local storage, but did not update `stub.generated_at` after success.

**Fix:**  
Added `stub.generated_at = datetime.now(timezone.utc)` inside the `try` block, after successful WireMock ZIP storage.

---

## BUG-017 — `StubOut` schema missing `stub_type` field: TYPE column showed "—" in portal

| Field | Value |
|-------|-------|
| **ID** | BUG-017 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/project-service/src/project_service/schemas.py` |
| **Commit** | (session fix) |

**Description:**  
The TYPE column in the Stubs table always showed "—". The frontend `Stub` TypeScript type expected a `stub_type` field. The API response contained only `format`.

**Root cause:**  
`StubOut` Pydantic schema had no `stub_type` field. The frontend mapped `stub.stub_type` for the TYPE column display; receiving `undefined` caused the "—" fallback to render.

**Fix:**  
Added a Pydantic v2 `@computed_field` property `stub_type` on `StubOut` returning `self.format`. This adds `stub_type` to serialised JSON without modifying the DB schema.

---

## BUG-016 — `Stub` ORM model missing `status` column: Deploy/Download ZIP buttons never rendered

| Field | Value |
|-------|-------|
| **ID** | BUG-016 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | Critical |
| **File** | `services/project-service/src/project_service/models.py`, `services/ingestion-service/src/ingestion_service/models.py`, Alembic migration `003_add_stub_status.py` |
| **Commit** | (session fix) |

**Description:**  
The Deploy button and Download ZIP button were completely missing from the project detail page. The STATUS column showed "—" for every stub.

**Root cause:**  
The `Stub` SQLAlchemy model had no `status` column. The `StubOut` Pydantic schema therefore had no `status` field. The frontend `Stub` type expected `status: StubStatus` — receiving `undefined` caused all conditional button renders (`status === "READY" → show Deploy`, etc.) to evaluate as `false`. No buttons rendered for any stub.

**Fix:**  
1. Added `status: Mapped[str] = mapped_column(String(20), nullable=False, default="READY")` to both `Stub` models (project-service and ingestion-service).  
2. Added Alembic migration `003_add_stub_status.py` with `server_default="READY"` and a backfill of `generated_at` for stubs that already had a `source_file_key`.  
3. Added `status: str` field to `StubOut`.  
4. Ran `alembic stamp 002` + `alembic upgrade head` to apply migration to existing DB.

---

## BUG-015 — Admin role `<td>` anchored regex never matched because `<select>` text contains all options

| Field | Value |
|-------|-------|
| **ID** | BUG-015 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | Medium |
| **File** | `portal/e2e/real/04-admin.spec.ts` |
| **Commit** | 5f57c94 |

**Description:**  
The Playwright test `"created user appears with correct role"` used `page.locator('td').filter({ hasText: /^SV_TEAM$/ })` to find the role cell. It never matched. The test always timed out.

**Root cause:**  
The role column renders a `<select>` element containing ALL four roles as `<option>` elements. The innerText of the `<td>` is therefore `"ADMIN SV_TEAM PROJECT_OWNER VIEWER"`, not `"SV_TEAM"`. The anchored regex `^SV_TEAM$` cannot match multi-option text.

**Fix:**  
Changed to find the row by username, then assert `toHaveValue('SV_TEAM')` on the row's `<select>`:
```typescript
const svUserRow = page.locator('tr').filter({ hasText: 'sv.user' });
await expect(svUserRow.locator('select')).toHaveValue('SV_TEAM');
```

---

## BUG-014 — Playwright strict mode violation: `getByText` matched username in header span + table cells

| Field | Value |
|-------|-------|
| **ID** | BUG-014 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | Medium |
| **File** | `portal/e2e/real/04-admin.spec.ts` |
| **Commit** | 5f57c94 |

**Description:**  
`page.getByText("sv.admin")` matched 3 elements: the header user-info `<span>`, the username `<td>`, and the email `<td>`. Playwright strict mode threw "resolved to 2 elements" and the test failed.

**Root cause:**  
`getByText` searches the entire page without scoping to a specific element type.

**Fix:**  
Changed to `page.locator('td').filter({ hasText: 'sv.admin' }).first()` to scope to table cells only.

---

## BUG-013 — Playwright strict mode violation on upload/generate button

| Field | Value |
|-------|-------|
| **ID** | BUG-013 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | Medium |
| **File** | `portal/e2e/real/02-projects.spec.ts` |
| **Commit** | 5f57c94 |

**Description:**  
`await expect(page.getByRole('link', { name: /upload/i }).or(page.getByRole('button', { name: /upload/i }))).toBeVisible()` threw "strict mode violation: resolved to 2 elements" — the project detail page has both a nav link and an action button matching "upload".

**Root cause:**  
`.or()` chains two separate locators that each match elements; when both are present simultaneously, the combined locator has 2+ elements.

**Fix:**  
Added `.first()` before `.toBeVisible()`.

---

## BUG-012 — `wiremock_generator.py` accessed non-existent `ParsedRequestSpec` fields

| Field | Value |
|-------|-------|
| **ID** | BUG-012 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/ingestion-service/src/ingestion_service/wiremock_generator.py` |
| **Commit** | 5f57c94 |

**Description:**  
`GET /projects/{id}/stubs/{stubId}/wiremock.zip` returned HTTP 500. Error: `AttributeError: 'ParsedRequestSpec' object has no attribute 'url_path'`.

**Root cause:**  
`_build_request_pattern()` referenced `req.url_path`, `req.url_pattern`, `req.headers`, and `req.query_params`. The actual `ParsedRequestSpec` model (in `parser_worker.models`) only has `url` and `required_headers`.

**Fix:**  
Rewrote `_build_request_pattern` to use `req.url` (splitting on `?` to extract query params) and `req.required_headers`.

---

## BUG-011 — `wiremock_generator.py` imported `ParsedScenario` from wrong module

| Field | Value |
|-------|-------|
| **ID** | BUG-011 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/ingestion-service/src/ingestion_service/wiremock_generator.py` |
| **Commit** | 5f57c94 |

**Description:**  
First invocation of the ZIP download endpoint raised `ImportError: cannot import name 'ParsedScenario' from 'parser_worker.parsers.base'`.

**Root cause:**  
`ParsedScenario`, `ParsedStub`, and `ParsedFile` live in `parser_worker.models`, not `parser_worker.parsers.base`.

**Fix:**  
Changed import to `from parser_worker.models import ParsedFile, ParsedScenario, ParsedStub`.

---

## BUG-010 — JWT secret mismatch: ingestion-service read clean secret from .env while auth-service used trailing-space secret from env var

| Field | Value |
|-------|-------|
| **ID** | BUG-010 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | Critical |
| **File** | `scripts/start-services.ps1`, `services/ingestion-service/.env` |
| **Commit** | 5f57c94 |

**Description:**  
All ingestion-service upload requests returned HTTP 401 "Invalid or expired token" even with a valid token from auth-service.

**Root cause:**  
cmd.exe `set VAR=value && next` includes the trailing space before `&&` in the variable value. auth-service and project-service were started with `set JWT_SECRET=mockingbird-local-dev-jwt-2026 &&` → secret stored as `"mockingbird-local-dev-jwt-2026 "` (trailing space). Ingestion-service was started without the `set` command; pydantic-settings v2 read the secret from `.env` file and strips trailing whitespace → `"mockingbird-local-dev-jwt-2026"` (no space). HMAC-SHA256 signatures do not match.

**Fix:**  
Set ingestion-service to use the same unquoted `set jwt_secret=$jwtSecret` form in `start-services.ps1` so all three services share the identical secret string (trailing space included).

---

## BUG-009 — cmd.exe `set VAR=value &&` includes trailing space in variable value

| Field | Value |
|-------|-------|
| **ID** | BUG-009 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `scripts/start-services.ps1` |
| **Commit** | 5f57c94 |

**Description:**  
`set local_storage_path=C:/path/uploads && uvicorn ...` set the variable to `"C:/path/uploads "` (trailing space). The ingestion-service resolved upload paths as `"C:\\path\\uploads \\stubs"` — a path with a literal space before `\stubs`. File writes failed with a path-not-found error.

**Root cause:**  
cmd.exe `set` treats everything between `=` and the next `&&` (including the space before `&&`) as the variable value.

**Fix:**  
Use quoted syntax `set "VAR=value"` for all variables except `jwt_secret` (which intentionally carries a trailing space for consistency with auth-service). Example: `set "local_storage_path=./uploads"`.

---

## BUG-008 — `Set-Content -Encoding UTF8` writes UTF-8 BOM, causing CA LISA parse failure

| Field | Value |
|-------|-------|
| **ID** | BUG-008 |
| **Found** | 2026-06-22 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `Sample_SV_Files/ESP/combined_request_response.txt` |
| **Commit** | 5f57c94 |

**Description:**  
The combined CA LISA request+response file always failed validation with `Parse error: ESP request: expected '{' after '='`. First bytes were `0xEF 0xBB 0xBF` (UTF-8 BOM) instead of `0x3D 0x7B` (`={`).

**Root cause:**  
PowerShell 5.1 `Set-Content -Encoding UTF8` and `[System.IO.File]::WriteAllText(path, content, [System.Text.Encoding]::UTF8)` both write a UTF-8 BOM. The CA LISA parser reads the file as bytes and expects the first byte to be `=` (0x3D). The BOM prefix `0xEF 0xBB 0xBF` breaks the parser immediately.

**Fix:**  
Used `[System.IO.File]::WriteAllBytes` with raw `Uint8Array` concatenation (request bytes + `0x0A` newline + response bytes) to produce a BOM-free binary file. Verified first bytes are `0x3D 0x7B` (`={`).

---

## BUG-007 — Upload fixture mocked wrong generate endpoint URL

| Field | Value |
|-------|-------|
| **ID** | BUG-007 |
| **Found** | 2026-06-21 |
| **Status** | FIXED |
| **Severity** | Medium |
| **File** | `portal/e2e/upload.spec.ts` |
| **Commit** | 9f7eda7 |

**Description:**  
The `mockUpload` fixture mocked `**/api/v1/projects/${projectId}/generate` but the actual `projectsApi.generate()` call sends to `/api/v1/projects/${projectId}/stubs/${stubId}/generate` (includes `/stubs/<id>`). The route was never matched, so the generate step timed out.

**Root cause:**  
Fixture written without first checking `projectsApi.generate` URL in `portal/src/api/projects.ts`.

**Fix:**  
Changed route pattern to `**/api/v1/projects/${projectId}/stubs/*/generate` (glob `*` matches the stub ID segment).

---

## BUG-006 — Playwright `waitForURL` regex matched full URL string, not path

| Field | Value |
|-------|-------|
| **ID** | BUG-006 |
| **Found** | 2026-06-21 |
| **Status** | FIXED |
| **Severity** | Medium |
| **File** | `portal/e2e/fixtures.ts` |
| **Commit** | 9f7eda7 |

**Description:**  
`page.waitForURL(/^\/((?!login).)*$/)` always timed out after login. The regex starts with `^/` but Playwright passes the **full URL string** (`http://localhost:3000/`) to `waitForURL`, not just the path. The regex could never match.

**Root cause:**  
Playwright's `waitForURL` works against the full URL. Regex assumed it would receive only the pathname.

**Fix:**  
Changed to a predicate function: `page.waitForURL((url) => !url.pathname.includes("login"))`.

---

## BUG-005 — API client showed "Session expired" on failed login (no token present)

| Field | Value |
|-------|-------|
| **ID** | BUG-005 |
| **Found** | 2026-06-21 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `portal/src/api/client.ts` |
| **Commit** | 9f7eda7 |

**Description:**  
All 401 responses from any endpoint triggered `logout()` and surfaced the hardcoded message "Session expired — please log in again". When the login endpoint itself returned 401 (wrong password), the user saw "Session expired" instead of "Invalid username or password".

**Root cause:**  
The 401 handler did not check whether there was an existing token in the auth store. The login endpoint legitimately returns 401 on bad credentials, but there is no session to expire at that point.

**Fix:**  
Added `const hasToken = !!useAuthStore.getState().token`. If no token → read `detail` from the 401 response body and surface it. If token exists → call `logout()` + show "Session expired".

---

## BUG-004 — Zustand auth store lost state on `page.goto()` in Playwright (no sessionStorage persistence)

| Field | Value |
|-------|-------|
| **ID** | BUG-004 |
| **Found** | 2026-06-21 |
| **Status** | FIXED |
| **Severity** | High |
| **Files** | `portal/src/store/auth.ts`, all Playwright E2E tests on protected routes |
| **Commit** | 9f7eda7 |

**Description:**  
After `loginAs()` completed (auth state in Zustand memory, page at `/`), calling `page.goto("/projects/new")` caused a full page reload. Zustand's in-memory store reset to `isAuthenticated: false`. ProtectedRoute redirected to `/login`, so no elements on the protected page were ever rendered. All 13 create-project and upload tests timed out.

**Root cause:**  
The Zustand auth store used no persistence middleware — state was purely in-memory and reset on any hard navigation.

**Fix:**  
Added `persist` middleware with `createJSONStorage(() => sessionStorage)`. Auth state now survives within the same browser tab. Playwright tests can call `page.goto()` on protected routes after `loginAs()`. Also better UX — users do not lose their session if they accidentally refresh.

---

## BUG-003 — CA LISA ZIP pairing: `else: continue` blocked fallback from timestamp → prefix strategy

| Field | Value |
|-------|-------|
| **ID** | BUG-003 |
| **Found** | 2026-06-21 |
| **Status** | FIXED |
| **Severity** | High |
| **File** | `services/parser-worker/src/parser_worker/detector.py` |
| **Commit** | 1d4dac0 |

**Description:**  
When parsing a ZIP archive with ESP-format CA LISA files, only 1 stub was returned instead of 2. The ESP files have timestamps that differ by 1 second between request (`_100912`) and response (`_100911`). Strategy 1 (exact timestamp match) found the timestamp in the request filename but found no response with the same timestamp, then hit `else: continue` (Python for-else on the response loop), which jumped to the next request and never tried Strategy 2 (longest common prefix).

**Root cause:**  
`for response in responses: ... else: continue` is Python's for-else pattern — the `else` runs when the loop finishes WITHOUT a `break`. Combined with `continue` at the outer level, it completely skipped prefix matching when timestamp matching produced no hit.

**Fix:**  
Replaced the for-else pattern with a `matched = False` flag. Strategy 2 (prefix matching) now always runs as fallback when Strategy 1 produces no match.

---

## BUG-002 — CA LISA Wealth format: brace-counting consumed request body as header block

| Field | Value |
|-------|-------|
| **ID** | BUG-002 |
| **Found** | 2026-06-21 |
| **Status** | FIXED |
| **Severity** | Critical |
| **File** | `services/parser-worker/src/parser_worker/parsers/ca_lisa_parser.py` |
| **Commit** | 1d4dac0 |

**Description:**  
The Wealth variant was parsed with method `GET` instead of `POST`. The request body was silently lost. The `_extract_wealth_section` function used brace-depth counting to find the end of the `={Method="POST" ...}` block, but the outer `={...}` block in Wealth files is **never properly closed** (the closing `}` is absent). Brace counting ran past the entire request block, consuming the JSON body as "header block text". Then `_parse_kvblock` received the JSON body starting with `{` as if it were a nested block and misread `{Method` as the key name instead of `Method`. `result.get("Method", "GET")` returned the default.

**Root cause:**  
CA LISA Wealth format has a structural quirk: the outer `={...}` key=value block is always missing its closing `}`. Brace counting is not a valid parsing strategy for this format.

**Fix (two-part):**
1. Rewrote `_extract_wealth_section` to use the section label (`Request:` / `Response:`) as a hard block boundary instead of brace counting.
2. Changed `_parse_kvblock` to use `_find_block_end()` (which handles quoted strings correctly) to detect whether `{...}` is properly closed; if unclosed, strips just the leading `{` without requiring a matching `}`.

---

## BUG-001 — Test file used wrong `parents` depth to locate sample files

| Field | Value |
|-------|-------|
| **ID** | BUG-001 |
| **Found** | 2026-06-21 |
| **Status** | FIXED |
| **Severity** | Low |
| **File** | `services/parser-worker/tests/test_ca_lisa_parser.py` |
| **Commit** | 1d4dac0 |

**Description:**  
`_REPO_ROOT = Path(__file__).parents[4]` pointed to `C:\Workspace` (one level above the repo root `C:\Workspace\Mockingbird`). All file-based tests that used `_REPO_ROOT / "Sample_SV_Files" / ...` failed with `FileNotFoundError`.

**Root cause:**  
Wrong depth count. The test file is at depth 3 from the repo root: `services/parser-worker/tests/test_ca_lisa_parser.py` → parents[3] = repo root.

**Fix:**  
Changed to `parents[3]`.

---

## How to add a new bug

Copy the template below and fill in the fields. Add at the **top** of this file (newest first).

```markdown
## BUG-NNN — Short title

| Field | Value |
|-------|-------|
| **ID** | BUG-NNN |
| **Found** | YYYY-MM-DD |
| **Status** | OPEN / IN PROGRESS / FIXED / WONT FIX |
| **Severity** | Critical / High / Medium / Low |
| **File** | path/to/file.py |
| **Commit** | (commit hash when fixed, or blank) |

**Description:**  
What went wrong and what the user/test observed.

**Root cause:**  
Why it happened.

**Fix:**  
What was changed.
```
