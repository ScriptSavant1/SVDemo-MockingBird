# Stub Engine HTTPS / mTLS Support

Status: **Implemented 2026-09-10, corrected to per-stub 2026-09-11.**
Corresponds to pending item **I2** in [DECISIONS_LOG.md](DECISIONS_LOG.md).

## 2026-09-11 revision: protocol/cert moved from project to stub

The 2026-09-10 version of this feature put protocol/cert config on the
**project**. The user caught that this was architecturally wrong: each
**stub**, not each project, is the actual deployable unit — deployer-worker
builds a separate Docker image and provisions a separate EC2 instance *per
stub*. A project-level setting forced every stub in a project to share one
protocol, which doesn't match real usage — a team adds stubs to a project
over time (a batch of services now, more later), sometimes wanting HTTP for
one and HTTPS for another.

**What changed**:
- The six TLS columns moved from `projects` to `stubs` (migration
  `006_move_tls_config_to_stubs.py` — the 005 project-level columns were
  dropped outright, not left as dead weight, since nothing in production
  depended on them yet).
- **Set at upload time, not at project create/edit time.** The protocol
  selector + TLS panel now live on the Upload Spec page
  (`portal/src/pages/UploadPage.tsx`) — the same multipart request that
  creates the stub (`POST /stubs/upload`, ingestion-service) carries
  `protocol`, `mtls_enabled`, and optionally `server_cert`/`server_key`/
  `ca_bundle` files. This also eliminated the two-step upload-then-PATCH
  dance the 09-10 design needed for the project-create case (no
  chicken-and-egg problem: ingestion-service already creates the `Stub`
  row itself, in the same request, so it always has a `stub_id` to key the
  cert's S3 path off before the row is even inserted).
- **Updating a stub's cert/protocol *later*** (swap an expiring cert, turn
  HTTPS on for a stub that predates this feature) is a separate small
  affordance: a per-stub "TLS settings" action on the project page, backed
  by `POST /stubs/{stub_id}/tls-cert` (ingestion-service, re-upload a cert —
  updates the stub row directly) and `PUT /stubs/{stub_id}/tls-config`
  (project-service, change protocol/mtls_enabled without necessarily
  re-uploading files).
- Create/Edit Project went back to exactly what they were before this
  feature existed — no protocol concept at the project level at all now.
- Everything below this point (nginx placement, entrypoint.sh, deploy-time
  port publishing, performance tuning) is **unchanged** — only which DB
  row/service owns the setting moved, not how the stub engine itself
  serves HTTPS.

The rest of this document (below) describes the 09-10 design as originally
written; where it says "project," read "stub" — kept as-is for the
historical record rather than rewritten, since the "Implementation notes"
section already captures what's actually true today.

## Problem

Stub engines currently only serve plain HTTP on port 8080
([WireMockConfig.java](../services/parser-worker/src/parser_worker/templates/stub-engine/src/main/java/com/mockingbird/stubs/WireMockConfig.java),
[Dockerfile](../services/parser-worker/src/parser_worker/templates/stub-engine/Dockerfile)
only `EXPOSE 8080`). Some consuming teams expect HTTPS (optionally with
client-certificate/mTLS auth) on port 443 instead. Both must be supported —
this is a per-project opt-in, not a global switch, so existing HTTP-only
projects are unaffected (Non-Breaking Change Rule #4 in CLAUDE.md).

## Chosen approach: nginx TLS-termination sidecar

nginx terminates TLS (and, when mTLS is enabled, verifies the client
certificate) on port 443 and reverse-proxies plaintext to WireMock on
`localhost:8080`, which is left completely unchanged. Rejected alternative:
WireMock-native HTTPS (`.httpsPort()`/keystore config directly in
`WireMockConfiguration`) — would need the JVM to bind a privileged port
(root, or `setcap` on the `java` binary, or an iptables NAT workaround), and
mixes TLS/cert concerns into the same process tuned for 10K+ TPS. nginx
keeps that tuning untouched and is the standard, already-familiar tool for
this job.

## Confirmed UX

**1. Protocol selector on the project form** (create + edit) — project-level,
not per-stub, since all stubs in a project serve the same consuming team:
- `HTTP` (default — today's behavior, zero friction for existing projects)
- `HTTPS`
- `HTTP + HTTPS` (both ports live simultaneously — useful during a
  migration window)

**2. When HTTPS/Both is selected, a "TLS Certificate" panel appears:**
- **Auto-generate (default, pre-selected)** — self-signed cert generated
  automatically, zero input. This is the *only* path built and tested in
  this first pass (confirmed 2026-09-10 — no real internal-CA certs
  available yet to test the upload path against).
- **Upload your own** (server cert + private key, PEM) — UI and backend
  storage plumbing built now, but only exercised against self-signed test
  files until real org certs are available. Treat as untested-with-real-CA
  when this ships.

**3. "Require client certificate (mutual TLS)" checkbox** — shown once
HTTPS is selected, independent of the cert path above. Included in this
first pass (confirmed 2026-09-10). Reveals a CA bundle upload used to
validate incoming client certs; self-signed CA is fine for initial testing
here too.

**4. Validation at upload time**: check cert/key match and expiry with
`openssl` server-side before accepting — fail fast with a clear error.

## Data model

New fields, on a separate `project_tls_config` table (1:1 with `Project`)
rather than columns bolted onto `projects` — keeps the migration
expand-only and the core table unchanged for the common HTTP-only case:
- `project_id` (FK)
- `protocol`: `HTTP` | `HTTPS` | `BOTH`
- `mtls_enabled`: bool
- `cert_source`: `AUTO_GENERATED` | `UPLOADED`
- S3 keys for: server cert, server private key, CA bundle (nullable unless
  uploaded / mTLS)
- `created_at` / `updated_at`

## Service-by-service changes

1. **project-service**: new `project_tls_config` table + migration;
   `ProjectCreate`/`ProjectUpdate` schemas gain `protocol`/`mtls_enabled`.
2. **portal**: protocol selector + conditional TLS panel on the project
   create/edit form; file inputs for upload path.
3. **ingestion-service**: new multipart upload endpoint for cert/key/CA
   bundle, mirroring the existing spec-file upload path; runs the
   `openssl` cert/key-match + expiry validation before accepting.
4. **parser-worker generator**: conditionally emits `nginx.conf` (with
   `ssl_verify_client on` + `ssl_client_certificate` when mTLS is enabled)
   and adds `EXPOSE 443` + an entrypoint that runs both nginx and the
   Spring Boot jar, only when `protocol != HTTP`. When `cert_source ==
   AUTO_GENERATED`, the entrypoint script generates a self-signed cert on
   first boot if one isn't already present.
5. **deployer-worker**: pulls the uploaded cert/key/CA bundle from S3 onto
   the EC2 alongside the stub artifact, when `cert_source == UPLOADED`.
6. **terraform/stub-ec2**: no change to the module itself (security group
   is passed in as a variable) — whoever owns the SG needs to open 443
   inbound for `HTTPS`/`BOTH` projects; call this out in deploy docs.

## Implementation notes (2026-09-10)

What actually shipped differs from the plan above in a few small,
deliberate ways:

- **Data model**: the six TLS fields (`protocol`, `mtls_enabled`,
  `tls_cert_source`, `tls_cert_s3_key`, `tls_key_s3_key`,
  `tls_ca_bundle_s3_key`) live directly as columns on `stubs` (migration
  `006_move_tls_config_to_stubs.py`, superseding `005`'s project-level
  columns — see the 2026-09-11 revision section above) rather than a
  separate table — at this project's actual scale a join table added
  complexity without a real benefit, and it still follows the
  add-columns-with-defaults expand-only rule for `stubs`. `StubOut` never
  returns the raw S3 key strings, only `has_uploaded_cert`/`has_ca_bundle`
  booleans (see `schemas.py` — `Field(exclude=True)` + `@computed_field`).
  S3 keys use the same `stubs/{project_id}/{stub_id}/...` convention as
  every other stub artifact (source file, generated zip, WireMock
  mappings) — `stubs/{project_id}/{stub_id}/tls/server.crt.pem` etc.
- **Cert validation** uses the Python `cryptography` library directly
  (`ingestion-service/routers/tls.py`), not an `openssl` subprocess —
  avoids any command-injection surface entirely, and the library was
  already an installed dependency.
- **nginx placement**: runs *inside the same container* as the Spring
  Boot jar (one process each, supervised by `entrypoint.sh`), not as a
  separate sidecar container. The real deploy path
  (`terraform/stub-ec2/main.tf`) is a single `docker run` per EC2 instance
  with no orchestrator to place a second container next to it, so
  packaging nginx into the one image is what keeps that a one-container
  operation. If either process dies, the container exits non-zero and
  `--restart unless-stopped` (already set) restarts both cleanly.
- **Deploy-time, not generate-time, protocol switch**: which protocol
  actually runs is read from `STUB_PROTOCOL` at container startup, not
  baked into the image. `nginx.conf`/`entrypoint.sh` are generated into
  *every* project unconditionally (harmless on HTTP-only — nginx just
  never starts), so a project's protocol can change on redeploy without
  regenerating the stub. Only `mtls_enabled` is baked in at generate time
  (it changes nginx.conf's `ssl_verify_client` directive content).
- **Port publishing is protocol-strict**: an HTTPS-only project does
  **not** publish 8080 on the host at all — only 443 — so HTTPS can't be
  silently bypassed. `BOTH` publishes both. Actuator (8081) is always
  published regardless of protocol (this also fixed a pre-existing bug:
  the health-check poller was hitting port 8080 for `/actuator/health`,
  which is actually served on 8081 — see `deployer-worker/health.py` vs
  `application.yml`).
- **nginx.conf performance tuning**: TLS session cache + upstream
  keepalive (avoids a fresh handshake and a fresh loopback TCP connection
  per request), `worker_processes auto`, `reuseport`, AES-NI-friendly
  cipher list — see the file itself for the full rationale in comments.

**Tested**: project-service (105 tests), ingestion-service (50/51, one
pre-existing unrelated failure), generator-worker (3), deployer-worker (24,
including a dedicated HTTPS-deploy test asserting the port mapping and
`https://` stub_url), parser-worker (709), portal (`tsc` clean, vitest
93/94 with the same one pre-existing unrelated failure).

**Not yet done / explicitly out of scope for this pass**:
- No real end-to-end test against an actual uploaded (non-self-signed)
  certificate — the upload/validation path is built and unit-tested with
  freshly-generated test certs, but nobody has run it against a real
  internal-CA cert yet (ties to pending item **U2**).
- The security group `443` inbound rule itself is not managed by this
  repo (the SG is passed in as a Terraform variable) — whoever owns it
  needs to open 443 for any project using `HTTPS`/`BOTH`.
- The EC2 IAM instance profile needs `s3:GetObject` added for the TLS
  object keys when `tls_cert_source = UPLOADED` — noted in
  `terraform/stub-ec2/variables.tf`'s `iam_instance_profile` description,
  not applied automatically.
- No real-world HTTPS load test has been run yet to confirm the "small,
  single-digit-percentage" TLS-termination overhead assumption at actual
  10K+ TPS on a c6i.2xlarge — the nginx config is tuned for it, but
  unverified under real load.
