# Mockingbird — Bug Tracker

Track all bugs found during development, testing, and QA.  
Format: one entry per bug, newest at the top.

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
