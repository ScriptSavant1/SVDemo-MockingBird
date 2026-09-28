# Mockingbird Error Codes

Every error the portal shows is **one line**: `<code> · <what went wrong>`,
for example:

```
MB-UPL-004 · Referenced file is missing from the upload: SVC03_..._s8_response.xml
```

Use this page to look up what a code means and what to do about it. Codes
never change meaning once they have shipped. New codes are added, and old
ones are never renumbered or reused.

**`(ref a1b2c3d4)`** appears only on unexpected server errors. It is a
reference into the server log, where the full technical detail is recorded.
Give it to whoever runs Mockingbird. The detail itself (stack trace, file
paths) is never shown in the portal.

---

## Upload & validation: `MB-UPL`

Returned when you upload a spec. The upload is rejected and nothing is
created. Fix the file and upload again.

| Code | Meaning | What to do |
|---|---|---|
| MB-UPL-001 | The uploaded file is empty. | Check you picked the right file and it has content. |
| MB-UPL-002 | The upload is bigger than the size limit. | Split it, or ask an admin to raise `max_upload_bytes`. |
| MB-UPL-003 | The file's format isn't recognised. | Use a supported format: Mockingbird TXT/JSON, Postman v2.1, OpenAPI, CA LISA capture, or the xlsx stub template. |
| MB-UPL-004 | The xlsx template references response/lookup files (`file:<name>`) that weren't in the upload. The message names them. | Add the named files to `data/` and select them in the same upload, or fix the `file:` names in the workbook. |
| MB-UPL-005 | The archive was rejected for safety: macro-enabled workbook (`.xlsm`), too many or too large entries, or an unsafe path. | Save the workbook as `.xlsx`; keep the package under 2,000 files and 200 MB. |
| MB-UPL-006 | The protocol isn't HTTP, HTTPS or BOTH. | Pick one of the three on the Upload page. |
| MB-UPL-007 | Problem with the TLS certificate, key or CA bundle (mismatch, only one of the pair supplied, or mTLS without a CA bundle). | Upload the certificate and its matching private key together; add a CA bundle for mTLS. |
| MB-UPL-008 | The spec was recognised but has content errors. The message shows the first one. | Fix the reported line or field; open *Details* for the full list. |
| MB-UPL-009 | A CA LISA ZIP's request and response files couldn't be matched. | Name files with `Request`/`Response` and a shared timestamp or prefix. |
| MB-UPL-010 | The file couldn't be read (corrupt ZIP, unreadable encoding). | Re-export or re-zip the file. |
| MB-UPL-011 | The xlsx workbook is unusable: can't be opened, missing the `Stubs`/`Rules` sheets, no stub rows, or no row could be built. | Start from the official template; check *Warnings* for why rows were skipped. |

## Generation: `MB-GEN`

Stub generation happens after the upload is accepted. When `MB-GEN-001` or
`MB-GEN-002` appears as an upload **warning**, the upload itself still
succeeded. `MB-GEN-003` appears on the job page as the job's failure reason.

| Code | Meaning | What to do |
|---|---|---|
| MB-GEN-001 | The Spring Boot stub project couldn't be generated; *Download Stub Project* won't work. | Re-upload. If it repeats, give the `ref` to an admin. |
| MB-GEN-002 | The WireMock mappings couldn't be pre-generated. | Re-upload. If it repeats, give the `ref` to an admin. |
| MB-GEN-003 | A background worker crashed while parsing or generating. | Retry. If it repeats, give the `ref` to an admin. |

## Server & connection: `MB-SYS`, `MB-NET`

| Code | Meaning | What to do |
|---|---|---|
| MB-SYS-001 | Unexpected server error. | Retry. If it repeats, give the `ref` to an admin. |
| MB-SYS-002 | The server is missing a software component; the message names it (e.g. `openpyxl`). | **Admin:** reinstall the named service's dependencies, e.g. `venv\Scripts\python.exe -m pip install -e ..\parser-worker` in `services\ingestion-service`. |
| MB-NET-001 | The portal can't reach the server at all. | Check your connection and that the services are running. |
| MB-NET-002 | The server answered with an error but no details, usually a service that is down or restarting. | Wait a moment and retry; if it persists, check the service is running. |

## General request errors: `MB-REQ-<HTTP status>`

When nothing more specific applies, the code is the HTTP status. The
message is still specific, for example `MB-REQ-404 · Project … not found`.

| Code | Meaning |
|---|---|
| MB-REQ-400 | The request isn't valid in the current state (e.g. generate before upload). |
| MB-REQ-401 | Not signed in, or the session expired. Sign in again. |
| MB-REQ-403 | Your role isn't allowed to do this. |
| MB-REQ-404 | The project, stub or job doesn't exist (or was deleted). |
| MB-REQ-413 | A file is over its size limit. |
| MB-REQ-422 | A field has an invalid value. The message names the field. |

---

## For developers

- **Response shape** (every non-2xx response from a service that uses
  `errors.py`, which today is ingestion-service and project-service): RFC 7807
  Problem JSON plus `code`, and `ref` on unexpected errors. `detail` is always
  one plain-string line:
  `{"type", "title", "status", "code", "detail", "ref"?}`, served as
  `application/problem+json`.
- **Raise a coded error:** `raise MockingbirdError(413, "MB-UPL-002", "…one line…")`.
  A plain `HTTPException` automatically gets `MB-REQ-<status>`.
- **Upload validation failures** (HTTP 200, `valid: false`) carry
  `error_code` + `error_summary` in the `IngestionResult`, with the full
  `errors` list underneath.
- **Job failures:** `jobs.error_message` holds `"<code> · <message> (ref …)"`,
  built with `parser_worker.error_codes.job_error()`.
- **Where codes are defined:** `services/parser-worker/src/parser_worker/error_codes.py`
  (UPL/GEN) and `errors.py` in each service (SYS/REQ). The portal's
  MB-NET codes are in `portal/src/api/client.ts`. Add every new code here too.
- **Portal:** always show `ApiError.userMessage`. It's built by
  `apiErrorFromResponse()` in `portal/src/api/client.ts`.
- **Never** put exception text, stack traces, file paths or secrets in
  `detail`. Log them under a `ref` instead.

**Coverage today (phase 1, 2026-09-28):** upload and generate: ingestion-service,
project-service, parser-worker, generator-worker, and the portal's Upload page.
**Phase 2 (not done yet):** deployer-worker, metrics, reporter, ai-service,
auth-service and notification-service (Node), and switching the remaining
portal pages from `err.detail` to `err.userMessage`.
