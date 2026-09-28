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

## Deployment: `MB-DEP`

Shown on the stub's deployment page ("The last deployment failed") and on
the job. The EC2 instance may or may not exist, depending on the step that
failed.

| Code | Meaning | What to do |
|---|---|---|
| MB-DEP-001 | The GitLab image build couldn't be started (GitLab unreachable, bad token or project). | Check GitLab is up and the deployer's GitLab settings; retry. |
| MB-DEP-002 | The GitLab image build ran but failed. The message gives the pipeline number and its final status. | Open that pipeline in GitLab to see the build log. |
| MB-DEP-003 | Terraform couldn't provision the EC2 instance (subnet, security group, quota, IAM…). | Admin: search the deployer log for the `ref`, which holds the full Terraform output. |
| MB-DEP-004 | The EC2 instance started, but the stub didn't report healthy in time. | Check the instance (`/actuator/health` on port 8081) and its container logs; redeploy. |
| MB-DEP-005 | Suspend: Terraform couldn't remove the EC2 instance. | Admin: check the `ref` in the deployer log; the instance may still be running and costing money. |
| MB-DEP-006 | Microcks (async) deploy: copying or starting it over SSH failed. | Check SSH access to the instance; see the `ref` in the log. |
| MB-DEP-007 | Microcks deploy failed unexpectedly. | Give the `ref` to an admin. |
| MB-DEP-008 | The deployer worker crashed. | Retry; if it repeats, give the `ref` to an admin. |

## Reports: `MB-RPT`

| Code | Meaning | What to do |
|---|---|---|
| MB-RPT-001 | The metrics for the report couldn't be loaded. | Check the stub has been LIVE and producing metrics for the chosen period; retry. |
| MB-RPT-002 | No report could be produced in any format. The job is FAILED. | Give the `ref`s in the job's warnings to an admin. |
| MB-RPT-003 | One format (PDF, Excel or PowerPoint) couldn't be produced. The others are still downloadable. Shown under the report's download buttons. | Use the formats that worked; give the `ref` to an admin if you need the missing one. |
| MB-RPT-004 | The report worker crashed. | Retry; if it repeats, give the `ref` to an admin. |

## AI generation: `MB-AI`

| Code | Meaning | What to do |
|---|---|---|
| MB-AI-001 | Hourly AI-generation limit reached. The message gives the limit. | Try again later. |
| MB-AI-002 | The AI's reply couldn't be turned into a stub spec. | Rephrase the description, with more detail on the endpoints. |
| MB-AI-003 | AI generation isn't available on this server (no API key or package). | Admin: configure the Anthropic API key (Vault). |

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
| MB-REQ-400 | The request isn't valid: a required field is missing (the message names it) or the action isn't allowed in the current state (e.g. generate before upload). |
| MB-REQ-401 | Not signed in, or the session expired. Sign in again. |
| MB-REQ-403 | Your role isn't allowed to do this. |
| MB-REQ-404 | The project, stub or job doesn't exist (or was deleted). |
| MB-REQ-413 | A file is over its size limit. |
| MB-REQ-422 | A field has an invalid value. The message names the field. |

---

## For developers

- **Response shape:** every non-2xx response from every Mockingbird service is
  RFC 7807 Problem JSON plus `code`, and `ref` on unexpected errors. `detail` is
  always one plain-string line:
  `{"type", "title", "status", "code", "detail", "ref"?}`. Python services
  do this in `errors.py` (served as `application/problem+json`); the Node
  services (auth, notification) do it in `src/plugins/errors.ts`.
- **Raise a coded error:** `raise MockingbirdError(413, "MB-UPL-002", "…one line…")`.
  A plain `HTTPException` automatically gets `MB-REQ-<status>`.
- **Upload validation failures** (HTTP 200, `valid: false`) carry
  `error_code` + `error_summary` in the `IngestionResult`, with the full
  `errors` list underneath.
- **Job failures:** `jobs.error_message` holds `"<code> · <message> (ref …)"`,
  built with `parser_worker.error_codes.job_error()`.
- **Where codes are defined:** `parser_worker/error_codes.py` (UPL/GEN),
  `deployer_worker/error_codes.py` (DEP), `reporter_service/error_codes.py` (RPT),
  `ai_service/routers/generate.py` (AI), each service's `errors.py` /
  `errors.ts` (SYS/REQ), and `portal/src/api/client.ts` (NET). Add every new
  code to this page too.
- **Portal:** always show `ApiError.userMessage`. It's built by
  `apiErrorFromResponse()` in `portal/src/api/client.ts`.
- **Never** put exception text, stack traces, file paths or secrets in
  `detail`. Log them under a `ref` instead.

**Coverage (2026-09-28):** every service. The Python APIs (ingestion,
project, metrics, ai) and Node services (auth, notification) share one
response shape. The workers (parser, generator, deployer, reporter) store
coded lines in `jobs.error_message`, and a crashed worker marks its job
FAILED instead of leaving it running. The portal shows `userMessage`
everywhere, plus deployment failure reasons and partial-report warnings.
