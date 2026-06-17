# Mockingbird — Implementation Plan

**Version:** 1.1  
**Last Updated:** 2026-06-14 (Session 2 — Phase 1 Sprint 1 started)  
**Total Duration:** 56 weeks (14 months)

---

## Overview

| Phase | Weeks | Goal | Business Impact |
|-------|-------|------|----------------|
| 1 | 1–8 | Parser + Generator CLI (offline tool) | Automates 60% of manual SV work |
| 2 | 9–16 | Dynamic stubs + SOAP + Stateful | Automates 85% of SV work |
| 3 | 17–24 | Platform backend (FastAPI + DB + SQS) | SV team uses API, eliminates file management |
| 4 | 25–32 | Auto-deploy (Terraform + EC2 + ECR) | Zero manual deployments |
| 5 | 33–38 | Metrics + Reporting | Full management visibility, executive dashboards |
| 6 | 39–48 | Self-service React portal | Any team self-serves; SV team is no longer a bottleneck |
| 7 | 49–56 | Kafka + AI-assisted generation | Industry-leading; unmatched by CA/IBM |

---

## Phase 1 — Parser + Generator CLI (Weeks 1–8)

**Goal:** Build a command-line tool that takes any API spec file and outputs a ready-to-run WireMock project package.

**Demo at end of phase:** `sv-gen --input payments-api.yaml --output ./payments-stubs` → produces runnable WireMock Docker project

### Sprint Breakdown

#### Sprint 1 (Week 1–2): Parser + WireMock Generator — ✅ COMPLETE (2026-06-14)
```
Completed:
  ✅ services/parser-worker/ Python package created
  ✅ pyproject.toml with Pydantic v2, Click, Jinja2 (all from Artifactory)
  ✅ Pydantic models (models.py) — all core data structures
  ✅ BaseParser ABC
  ✅ TxtLevel1Parser — Level 1 simple TXT format (single request/response)
  ✅ TxtLevel2Parser — Level 2 multi-scenario TXT format
  ✅ JsonLevel3Parser — Level 3 full JSON format (dynamic params, faults, delays)
  ✅ Format auto-detector (detector.py)
  ✅ WireMock JSON mapping generator (generator/wiremock.py)
  ✅ sv-gen CLI (cli.py) — --input --output --dry-run flags
  ✅ Full test suite: test_txt_level1.py, test_txt_level2.py, test_wiremock_generator.py
  ✅ stub-engine/Dockerfile — uses confirmed Java 21 base image
  ✅ stub-engine/settings.xml — confirmed Artifactory URL from sample files
  ✅ stub-engine/.gitlab-ci.yml — uses confirmed Kaniko + runner tag + Vault pattern

  ✅ stub-engine/pom.xml — Spring Boot 3.3 + WireMock 3.5 + Prometheus + Spring-WS
  ✅ stub-engine/src/.../StubApplication.java
  ✅ stub-engine/src/.../WireMockConfig.java — Jetty tuned for high TPS, response templating, metrics
  ✅ stub-engine/src/main/resources/application.yml — virtual threads, dual-port (8080 stub / 8081 actuator)
  ✅ stub-engine/docker-compose.yml — for local testing
  ✅ generator/springboot.py — writes full Spring Boot project tree from parsed stubs
  ✅ cli.py updated — sv-gen now outputs complete docker-buildable project

Remaining for Sprint 2:
  ⬜ Postman v2.1 collection parser
  ⬜ OpenAPI 3.x parser  
  ⬜ Integration test: sv-gen --input examples/POST-payment-multi-scenario.txt --output ./test-out && docker compose up

Confirmed technical facts from sample files:
  - GitLab registry: registry.gitlab.internal
  - Artifactory: https://artifactory.internal/artifactory/dws-all-repos
  - Vault (dev): https://vault-dev-pnf.web.deviaas.intenv01.net  namespace=secrets  mount=kv  auth=jwt/gitlab
  - Runner tag: nwg-rosa-sharedrunner-scan
  - CRITICAL: Artifactory NOT accessible from AWS EC2 — all Maven/pip builds in GitLab CI only
```

#### Sprint 2 (Week 3–4): OpenAPI + Postman Parsers
```
Tasks:
  - OpenAPI 3.x parser:
      - Resolves $ref references (inline)
      - Extracts: method, path, params, request body, response body + headers
      - Generates synthetic examples from schema when no example provided
      - Handles allOf/oneOf/anyOf
  - Swagger 2.x parser (same output format as OpenAPI 3.x)
  - Postman Collection v2.1 parser:
      - Recursive folder traversal
      - Variable replacement: {{baseUrl}} → placeholder
      - Pre-request script hints extraction
  - Unit tests with real banking API fixtures for each parser

Deliverable: Parsers returning List[ParsedEndpoint] for each format
```

#### Sprint 3 (Week 5–6): HAR + Raw + CSV Parsers + WireMock Generator
```
Tasks:
  - HAR file parser (browser traffic recordings)
  - Raw HTTP request+response pair parser (plain text format)
  - CSV / Excel parser (request-response pair table)
  - WireMock 3.x mapping generator (static stubs):
      - URL pattern matching (path params as regex)
      - Method + header matching
      - Exact response body from parsed example
      - Correct status code and response headers
      - Generates UUID per stub
      - WireMock metadata (name, created timestamp)

Deliverable: End-to-end: upload any spec → List[WireMockMapping JSON]
```

#### Sprint 4 (Week 7–8): Project Packager + CLI + Tests
```
Tasks:
  - Project packager:
      - Takes List[WireMockMapping] → complete WireMock project directory
      - Generates: Dockerfile, docker-compose.yml, prometheus.yml, start.sh
      - WireMock JVM flags for high TPS in Dockerfile
      - Outputs ZIP bytes or writes to local directory
  - CLI tool (`sv-gen`):
      - `sv-gen --input spec.yaml --output ./project --type openapi`
      - `sv-gen --input collection.json --output ./project --type postman`
      - `sv-gen --input service.wsdl --output ./project --type wsdl`
      - Auto-detects type if --type omitted
  - Integration test: real OpenAPI spec → docker build → docker run → curl stubs → 200 OK
  - README with installation and usage instructions
  - GitLab CI pipeline: lint + test on every commit

Deliverable: Working CLI. Can be demoed to SV team.
```

### Phase 1 Dependencies
- Python 3.11 dev environment
- Docker Desktop (local testing)
- GitLab repo created with CI runner configured
- Sample API specs from SV team (banking examples: payments, accounts, cards)

### Phase 1 Definition of Done
- [ ] CLI generates valid WireMock project from: OpenAPI, Postman, HAR, Raw, CSV
- [ ] WireMock starts from generated Dockerfile with no errors
- [ ] Stubs return correct responses when called via curl
- [ ] Test coverage > 80% on parser and generator modules
- [ ] CI pipeline passes on every commit

---

## Phase 2 — Dynamic Stubs + SOAP + Stateful (Weeks 9–16)

**Goal:** Extend the generator to handle all stub types: dynamic data, SOAP, conditional logic, stateful scenarios.

### Sprint 5–6 (Week 9–12): Dynamic Data + SOAP
```
Tasks:
  - Data rules engine:
      Field name pattern detection (accountNumber → NUMERIC 10 digits)
      Handlebars template generation for WireMock response-template transformer
      Client override rules via config file
      Faker integration for UK-specific data (IBAN, sort code, postcode, phone)
  - WSDL 1.1/2.0 parser:
      Parse operations, input/output message schemas
      XSD type resolution
      Generate XML request/response examples
      SOAP envelope wrapping (1.1 and 1.2)
  - SOAP WireMock mapping generator:
      SOAPAction header matching
      XPath body matching on operation name
      Full SOAP envelope in response body
      Content-Type: text/xml

Deliverable: `sv-gen --input service.wsdl` produces SOAP stubs that respond to real SOAPAction calls
```

### Sprint 7–8 (Week 13–16): Conditional Logic + Stateful Scenarios
```
Tasks:
  - Conditional response generator:
      WireMock priority mapping (two stubs, priority 1 checked first)
      Python transformer layer for complex conditions
  - Stateful scenario generator:
      WireMock Scenario state machine
      Multi-step: login → get account → transfer → verify balance
  - Request field echo (JSONPath extraction in Handlebars)
  - Multiple responses per endpoint (round-robin / random)
  - Response delays: fixed, random range, progressive
  - Fault injection: timeout, 500 error, partial response, network reset
  - Data-driven from CSV: lookup customer by ID from file

Deliverable: Full Phase 2 demo to SV team using real project examples
```

---

## Phase 3 — Platform Backend (Weeks 17–24)

**Goal:** Wrap the CLI logic in a production FastAPI + PostgreSQL + SQS platform API.

### Sprint 9–10 (Week 17–20): Core API + Database
```
Tasks:
  - FastAPI application setup:
      CORS, JWT middleware, request logging, correlation IDs
      Global exception handler (RFC 7807 Problem JSON)
      OpenAPI docs at /docs
  - PostgreSQL schema + Alembic migrations:
      projects, stubs, deployments, users, audit_log, jobs tables
  - Project CRUD API (/projects)
  - Stub CRUD API (/stubs)
  - File upload endpoint (/upload — multipart, saves to S3)
  - Auth endpoints (/auth/login, /auth/refresh, /auth/logout)
  - JWT + RBAC implementation (Admin / SV_Team / ProjectOwner / Viewer)
  - Audit logging middleware (every mutation → audit_log)

Deliverable: Platform API running locally with Swagger UI; CRUD working
```

### Sprint 11–12 (Week 21–24): SQS Job Queue + Workers
```
Tasks:
  - SQS setup: parse-queue, generate-queue, deploy-queue, report-queue, DLQ
  - Refactor CLI parsers into SQS consumer workers (parser-worker)
  - Refactor CLI generators into SQS consumer workers (generator-worker)
  - Job status tracking in PostgreSQL (QUEUED → RUNNING → SUCCESS/FAILED)
  - Exponential backoff retry (3 attempts max before DLQ)
  - API endpoints: /generate (trigger), /jobs/{id} (status polling)
  - WebSocket endpoint: /ws/jobs/{id} (live status updates)
  - Integration tests with localstack (local AWS SQS emulation)

Deliverable: Upload file via API → async parse → async generate → poll job status
```

---

## Phase 4 — Auto-Deploy (Weeks 25–32)

**Goal:** One-click deploy from portal to a live EC2 stub server.

### Sprint 13–14 (Week 25–28): Terraform Modules
```
Tasks:
  - Terraform module: sv-ec2-instance
      EC2 instance, security group, IAM role, EBS volume
      user_data.sh: install Docker, pull ECR image, run container
      Health check on :8080/__admin/health
  - Terraform module: ecs-service (for platform services)
  - Environment configs: dev/test/prod with Terragrunt
  - Remote state: S3 backend + DynamoDB lock
  - GitLab CI Terraform job: plan on MR, apply on merge to main
  - Test: terraform plan produces valid plan for test environment

Deliverable: `terraform apply` deploys WireMock on EC2 manually
```

### Sprint 15–16 (Week 29–32): Deployer Service + ECR Pipeline
```
Tasks:
  - deployer-worker:
      Build Docker image from generated project (boto3 + subprocess)
      Tag + push to ECR
      Run Terraform (subprocess with timeout)
      Poll health check (retry 60 times, 5s interval)
      Update PostgreSQL: stub_url, ec2_instance_id, status=LIVE
      Generate firewall documentation PDF → S3
      Emit EventBridge: stub.deployed
  - Deploy API endpoints: /deploy (trigger), /deployments/{id} (status)
  - Rollback: /deployments/{id}/rollback (re-deploy previous ECR image)
  - Zero-downtime redeploy: new EC2 spun up, DNS switched, old terminated
  - Notification: email/Slack on deploy complete with stub URL
  - End-to-end test: upload OpenAPI → generate → deploy → stub returns 200

Deliverable: Full automated deploy from API call. No manual steps.
```

---

## Phase 5 — Metrics + Reporting (Weeks 33–38)

**Goal:** Management-grade real-time and historical dashboards and reports.

### Sprint 17–18 (Week 33–36): Metrics Pipeline
```
Tasks:
  - Prometheus scraping from WireMock /metrics (every 30s via SQS scheduled event)
  - Parse WireMock Prometheus format:
      wiremock_requests_total, wiremock_request_duration_seconds
  - Write to AWS Timestream (project_id, path, method, status tags)
  - Calculate: current TPS (delta / 30s), rolling P50/P90/P95/P99
  - Redis pub/sub: publish TPS update to channel metrics:{project_id}
  - WebSocket: stream Redis pub/sub to browser clients
  - Metrics query API: /metrics/{project_id}?start=&end=&resolution=
  - Grafana dashboards: per-project TPS, latency heatmap, error rate

Deliverable: Live TPS chart in portal showing real stub traffic
```

### Sprint 19 (Week 37–38): Report Generator
```
Tasks:
  - Executive Summary PDF: branded, charts, license savings calc
  - Project Report PDF: per-endpoint TPS, latency table, deployment history
  - Platform Audit report: all user actions from audit_log
  - Cost Report: EC2 hours × instance type rate vs CA/IBM equivalent
  - Excel export: raw data via openpyxl
  - Email scheduler: daily/weekly/monthly via SQS scheduled events
  - S3 presigned URL: 7-day report sharing link
  - Report API: /reports/generate, /reports/{id}/download

Deliverable: Admin can generate Executive Summary PDF for CTO
```

---

## Phase 6 — Self-Service React Portal (Weeks 39–48)

**Goal:** Beautiful, modern web UI where any project team can self-serve without SV team involvement.

### Sprint 20–21 (Week 39–42): Portal Scaffold + Auth + Projects
```
Tasks:
  - React 18 + Vite + TypeScript + Tailwind + shadcn/ui project setup
  - API client: typed fetch wrapper with TanStack Query
  - Auth: JWT via httpOnly cookies, SSO redirect flow
  - Role-based rendering (show/hide nav items by role)
  - Login page, Dashboard, Project list, Create project
  - File upload with drag-and-drop + progress indicator
  - Format detection preview component
  - Error boundaries on all pages, loading skeletons

Deliverable: Login → dashboard → create project → upload file
```

### Sprint 22–23 (Week 43–46): Stub Management + Deploy UI
```
Tasks:
  - Endpoint preview table with inline editing
  - Stub editor: full-screen modal, WireMock JSON editor (Monaco Editor)
  - Data rules panel (alongside stub editor)
  - Generate button with live job status (WebSocket progress)
  - Stub library: list, search, enable/disable, bulk operations
  - Deploy page: one-click deploy with confirmation modal
  - Deploy status: live WebSocket progress steps
  - Deployment history + rollback button

Deliverable: Complete generate → deploy flow in portal
```

### Sprint 24–25 (Week 47–48): Metrics Dashboard + Reports + Admin
```
Tasks:
  - Live TPS dashboard: ECharts real-time line chart (WebSocket)
  - Historical metrics: switch to 1h/24h/7d/30d (REST API + Timestream)
  - Per-endpoint breakdown table
  - Reports page: generate, download, share
  - Admin panel: user management, platform overview, dead-letter queue
  - Grafana embedded dashboards (iframe with auth pass-through)
  - Dark mode support
  - Responsive layout (desktop + tablet)
  - Playwright E2E tests for all main flows

Deliverable: Complete self-service portal. SV team no longer a bottleneck.
```

---

## Phase 7 — Kafka + AI (Weeks 49–56)

**Goal:** Complete async protocol support and AI-assisted stub generation.

### Sprint 26–27 (Week 49–52): Microcks + Kafka
```
Tasks:
  - AsyncAPI parser (Kafka topic definitions)
  - Microcks integration: generate Kafka stub configs
  - Microcks deployer: EC2 + Kafka broker (Docker Compose)
  - Kafka message production simulation
  - Kafka consumption simulation (consumer group stubs)
  - Test with real Kafka client

Deliverable: Kafka topic stubs deployed via same portal flow
```

### Sprint 28–29 (Week 53–56): AI-Assisted Generation
```
Tasks:
  - ai-service: FastAPI wrapper around Anthropic Claude API
  - "Describe your API" → Claude claude-sonnet-4-6 → OpenAPI JSON → standard parse flow
  - Pattern detector: analyse existing stub responses → suggest data rules
  - "AI Suggest Rules" button in stub editor (uses Claude claude-haiku-4-5)
  - Anomaly detection: flag stubs with unusual response patterns
  - Portal: AI assistant panel in stub editor

Deliverable: User describes API in plain English → working stubs in < 2 minutes
```

---

## Critical Path & Dependencies

```
Phase 1 (CLI) ──────────────────────────────────────────▶ Phase 2 (Dynamic)
                                                              │
                                                              ▼
                                               Phase 3 (Platform API + SQS)
                                                              │
                                                ┌────────────┴───────────┐
                                                ▼                        ▼
                                      Phase 4 (Deploy)         Phase 5 (Metrics)
                                                │                        │
                                                └────────────┬───────────┘
                                                             ▼
                                                   Phase 6 (Portal UI)
                                                             │
                                                             ▼
                                                   Phase 7 (Kafka + AI)
```

**Phases 4 and 5 can run in parallel** (different team members) once Phase 3 is complete.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| WireMock can't reach 10K TPS target | Medium | High | Benchmark early in Phase 1; Hoverfly is fallback |
| Firewall rules delay EC2 access | High | Medium | Agree CIDR ranges with infra team before Phase 4 |
| SOAP WSDL parsing edge cases (complex schemas) | Medium | Medium | Collect 10 real WSDLs in Phase 1 to test against |
| GitLab runner access to AWS (ECR/Terraform) | Medium | High | IAM roles for GitLab runner established in Phase 1 |
| Bank AD SAML integration complexity | Medium | Low | Fallback to local user accounts in Phase 3; SSO added later |
| Timestream costs at high query volume | Low | Medium | CloudWatch as fallback; use read-replica for reports |
| SQS message ordering (deploy jobs) | Low | Medium | Use FIFO queue for deploy-queue |

---

## Team Recommendations

### Phase 1–2 (MVP): Solo or 2-person
- 1 x Platform Engineer (Python, AWS) — parsers, generators, CLI
- Optional: 1 x SV SME part-time (validates generated stubs against CA/IBM output)

### Phase 3–4 (Backend platform): 2–3 people
- 1 x Python Backend Engineer (FastAPI, SQS, Terraform)
- 1 x Infrastructure Engineer (Terraform, AWS, GitLab CI)
- 1 x SV SME (validation, user acceptance)

### Phase 5–6 (Full platform): 4–5 people
- 1 x React Frontend Engineer (TypeScript, shadcn/ui, ECharts)
- 1 x Python Backend Engineer
- 1 x Infrastructure Engineer
- 1 x SV SME / QA

### Phase 7 (AI + Kafka): 3–4 people
- 1 x Python Backend (AI integration, Anthropic SDK)
- 1 x Kafka/async specialist
- 1 x Frontend Engineer
- 1 x SV SME (validates AI output quality)

---

## Quick Wins (Done in Week 1)

Before writing any production code, these can be demoed to stakeholders:

1. **Manual WireMock demo**: Start WireMock Docker locally, hand-create 2 stubs → show to SV team. Proves the engine works without any code.

2. **Parse OpenAPI spec manually**: Run `python -c "import yaml; print(yaml.safe_load(open('payments.yaml')))"` on a real spec — shows what data the parser will extract.

3. **Cost calculation**: Show EC2 costs vs CA LISA license. c6i.xlarge × 10 projects = £1,200/month vs £100,000/year license. Business case in 5 minutes.

---

## Milestone Summary

| Milestone | Target Week | Deliverable |
|-----------|------------|-------------|
| M1: CLI MVP | Week 8 | `sv-gen` CLI works for all input formats |
| M2: Dynamic + SOAP | Week 16 | 85% of stub types automated |
| M3: Platform API | Week 24 | REST API + DB + SQS fully working |
| M4: Auto-deploy | Week 32 | One API call deploys to live EC2 |
| M5: Reporting | Week 38 | Executive PDF report for CTO demo |
| M6: Portal | Week 48 | Any team self-serves via web portal |
| M7: AI | Week 56 | Plain English → stubs in < 2 minutes |
