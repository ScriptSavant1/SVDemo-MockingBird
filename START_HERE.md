# MOCKINGBIRD — PROJECT RESUME DOCUMENT
## Read This First When Starting a New Session

**Last Updated:** 2026-06-19 (Session 9)
**Status:** Phases 1–6 COMPLETE. Phase 7 Sprints 18 + 21 COMPLETE. ~690 tests passing across all services.
**Next Action:** Phase 7 Sprint 22 — Kafka stub engine (Spring Boot + Spring Kafka)

---

## SECTION 1 — What Is Mockingbird (2-Minute Summary)

Mockingbird is a **Service Virtualisation (SV) platform**.

**The problem it solves:**
- The SV team manually creates fake API responses (called "stubs") using paid tools CA LISA and IBM Rational Test Workbench (£100,000+/year in licences)
- Every project team that needs to test their app has to wait for the SV team to do this manually
- It's slow, expensive, and doesn't scale

**What Mockingbird does:**
1. A project team uploads their API spec (any format — text, JSON, Postman, OpenAPI)
2. Mockingbird automatically generates stub code (using WireMock inside Spring Boot)
3. With one click, it deploys that stub to an AWS EC2 server
4. The project team gets back a URL — their fake API is live and handling 10,000+ requests/second
5. When done, they suspend it (saves cost). When needed again, redeploy in 4 minutes — no re-upload needed

**Why build it:**
- Replaces CA LISA + IBM tools (saves £100K+/year)
- SV team of 5 people can ramp down as automation takes over
- 20–30 projects will use it in Year 1

---

## SECTION 2 — Sprint-by-Sprint Build History

### Phase 1 — Parser + Generator CLI (Weeks 1–8) ✅ COMPLETE

| Sprint | What Was Built | Tests |
|--------|---------------|-------|
| Sprint 1 | Level 1/2/3 TXT parsers, JSON parser, WireMock mapping generator, Spring Boot project generator, `sv-gen` CLI | ~60 |
| Sprint 2 | Postman v2.1 parser, OpenAPI 3.x / Swagger 2.x parser | ~50 |
| Sprint 3 | SOAP TXT format, BODY_XPATH match type, namespace-aware XPath | ~34 |
| Sprint 4 | Template bundling (`importlib.resources`), 34 integration tests, CLI packaging | 161 total |

**Phase 1 output:** `sv-gen --input payments-api.yaml --output ./stub` → ready-to-run Spring Boot + WireMock Docker project.

---

### Phase 2 — Dynamic Stubs + SOAP + Stateful Scenarios (Weeks 9–16) ✅ COMPLETE

| Sprint | What Was Built | Tests added |
|--------|---------------|-------------|
| Sprint 5 | Dynamic Handlebars templates (UUIDs, dates, account numbers), all delay types (fixed / random / chunked / lognormal) | 33 |
| Sprint 6 | `STATEFUL` format — multi-step state machine (login → account → transfer), scenario chaining | 82 total |
| Sprint 7 | Namespace-aware XPath, WS-Security (`ConditionalOnProperty`), WSDL serving | 47 |
| Sprint 8 | Fault injection — `CONNECTION_RESET_BY_PEER`, `EMPTY_RESPONSE`, `MALFORMED_RESPONSE_CHUNK` | 61 |

**parser-worker cumulative: ~388 tests passing.**

---

### Phase 3 — Platform Backend (Weeks 17–24) ✅ COMPLETE

| Sprint | What Was Built | Tests added |
|--------|---------------|-------------|
| Sprint 9 | project-service (FastAPI + PostgreSQL + SQLAlchemy 2.0 + Alembic + JWT, 44 tests), auth-service (Node.js 20 + Fastify + bcrypt + JWT, TypeScript strict, 18 tests), Dockerfiles, docker-compose | 62 |
| Sprint 10 | ingestion-service (FastAPI file upload, S3 storage, format auto-detection, presigned URL download), 18 tests | 18 |
| Sprint 11 | SQS job queues: parse-queue → parser-worker consumer, generate-queue → generator-worker consumer. Job trigger + status API in project-service. 19 tests | 19 |
| Sprint 12 | LDAP auth (`ldapts`) in auth-service, Redis session cache (`ioredis`), forced logout propagation. 14 new tests → 32 auth total | 14 |

**Backend services live: project-service, auth-service, ingestion-service, parser-worker, generator-worker. ~497 tests total at end of Phase 3.**

---

### Phase 4 — Auto-Deploy (Weeks 25–32) ✅ COMPLETE

| Sprint | What Was Built | Notes |
|--------|---------------|-------|
| Sprint 13 | deployer-worker (Python SQS consumer): Terraform EC2 provisioning, GitLab CI pipeline trigger (Kaniko build → Spring Boot stub image), deployment status tracking, STS AssumeRole for cross-account deploys | deploy-queue consumer, Terraform state in S3 + DynamoDB |

**Full end-to-end flow working: upload spec → parse → generate → deploy → EC2 live with stub URL + API key.**

---

### Phase 5 — Metrics + Reporting (Weeks 33–38) ✅ COMPLETE

| Sprint | What Was Built | Notes |
|--------|---------------|-------|
| Sprint 14 | metrics-service (FastAPI): Prometheus scraper → AWS Timestream, WebSocket live TPS feed (Redis pub/sub), `/api/v1/metrics/{id}/history` REST endpoint returning `MetricHistoryPoint[]` | Port 8005, scrapes `/actuator/prometheus` every 30s |
| Sprint 15 | reporter-service (SQS consumer): PDF (WeasyPrint), Excel (openpyxl), PowerPoint (python-pptx) report generation. Stores output in S3, writes keys to job.result | report-queue consumer |

**All 4 report formats delivered: live dashboard (Phase 6), PDF, Excel, PowerPoint.**

---

### Phase 6 — Self-Service React Portal (Weeks 39–48) ✅ COMPLETE

| Sprint | What Was Built | Notes |
|--------|---------------|-------|
| Sprint 16 | React 18 + TypeScript strict + Vite + Tailwind portal foundation: LoginPage, DashboardPage, ProjectPage, auth store (Zustand), JWT handling, TpsChart (ECharts canvas), WebSocket hook, StatusBadge, Button, Card, layout | 44 portal tests |
| Sprint 17 | Upload flow: drag-and-drop UploadZone, ingestion-service routing (Vite proxy + Nginx), JobStatusPage with polling + progress steps, AiGeneratePage stub, format detection preview | +13 tests |
| Sprint 19 | MetricsHistoryChart (ECharts dual-axis), DeploymentPage 3-tab layout (Overview / Metrics History / Reports), time range picker (1h/6h/24h), PDF/Excel/PPT download via S3 presigned URLs, metrics-service proxy | +9 tests |
| Sprint 20 | Admin panel (user CRUD, role management, active/suspend toggle, reset password, audit log tab), CreateProjectPage, Edit/Archive project (inline modals), `New Project` button, Admin nav link, `AdminRoute` guard, `Modal` component | +11 tests |

**Portal cumulative: 77 tests across 15 test files.**
**project-service cumulative: 96 tests (44 original + 52 added across Sprints 11–20).**

---

### Phase 7 — Kafka + AI-Assisted Generation (Weeks 49–56) — PARTIAL

| Sprint | What Was Built | Status |
|--------|---------------|--------|
| Sprint 18 | ai-service (Python + FastAPI): Claude API integration (`claude-sonnet-4-6`), plain-English description → OpenAPI stub spec generation, generation history DB (SQLite/PostgreSQL), rate limiting. Portal AI Generate page: textarea → spec preview → "Create Stubs" (posts Postman JSON to ingestion-service) | ✅ COMPLETE — 11 tests |
| Sprint 21 | notification-service (Node.js 20 + Fastify): email + Slack + MS Teams webhooks, SQS consumer for EventBridge events, POST /api/v1/notify/send | ✅ COMPLETE — 20 tests |
| Sprint 22 | Kafka stub engine (Spring Boot + Spring Kafka) | ❌ NOT STARTED |
| Sprint 23 | Microcks — AsyncAPI + Avro schema registry | ❌ NOT STARTED |
| Sprint 24 | IBM MQ stub engine (Spring Boot + Spring JMS) | ❌ NOT STARTED |

---

## SECTION 3 — What Is Still Pending

### Services Not Yet Built

| Service | What It Does | Sprint |
|---------|-------------|--------|
| notification-service | Email (SMTP), Slack webhook, MS Teams webhook — fires on: stub deployed, deploy failed, report ready, stub suspended | Sprint 21 |
| Kafka stub engine | Spring Boot + Spring Kafka — generates stubs for Kafka message consumers | Sprint 22 |
| Microcks | AsyncAPI + Avro schema registry support for complex async stubs | Sprint 23 |
| IBM MQ stub engine | Spring Boot + Spring JMS for legacy IBM MQ teams | Sprint 24 |

### Features Not Yet Built

| Feature | Notes |
|---------|-------|
| SAML / Europa SSO | Auth Phase 3 — additive to LDAP, Europa-domain users only. Code structure ready in auth-service. |
| Grafana embed in portal | Grafana iframe panel in portal for operational dashboards. Architecture defined, not wired. |
| Production Vault integration | All services currently read secrets from `config/local.env`. Production requires `hvac` (Python) / `spring-vault-core` (Java). Vault endpoint TBC (input I1). |
| CloudWatch → Splunk log forwarding | Structured JSON logs work; Splunk HEC subscription not wired (input I3). |
| AppDynamics Java agent | Agent config placeholder in deployer-worker; agent key TBC (input I4). |
| On-premise deployment path | SSH + Docker via Paramiko architected in deployer-worker; not tested against real on-prem host. |

---

## SECTION 4 — Confirmed Technology Stack

### 4.1 Platform Services (all built)

| Service | Language | Port | Status |
|---------|----------|------|--------|
| auth-service | Node.js 20 + Fastify | 3001 | ✅ Built |
| project-service | Python 3.11 + FastAPI | 8001 | ✅ Built |
| ingestion-service | Python 3.11 + FastAPI | 8003 | ✅ Built |
| ai-service | Python 3.11 + FastAPI | 8004 | ✅ Built |
| metrics-service | Python 3.11 + FastAPI | 8005 | ✅ Built |
| parser-worker | Python 3.11 (SQS consumer) | — | ✅ Built |
| generator-worker | Python 3.11 (SQS consumer) | — | ✅ Built |
| deployer-worker | Python 3.11 (SQS consumer) | — | ✅ Built |
| reporter-service | Python 3.11 (SQS consumer) | — | ✅ Built |
| notification-service | Node.js 20 + Fastify | 3002 | ✅ Built |

### 4.2 Frontend

- React 18 + TypeScript strict + Vite 5
- Tailwind CSS + custom components (Button, Card, Tabs, Modal, StatusBadge, UploadZone)
- Apache ECharts (canvas TPS chart + dual-axis history chart)
- TanStack Query v5 (server state), Zustand (client state)
- WebSocket hook for live TPS via Redis pub/sub
- Vite dev proxy + Nginx production proxy — both configured for all 5 backend services

### 4.3 Stub Engine (per-project EC2)

| Engine | Used When | TPS | Status |
|--------|----------|-----|--------|
| Spring Boot + WireMock (Netty) **PRIMARY** | All REST + SOAP | 12,000–18,000 | ✅ generator-worker produces these |
| Hoverfly (Go) | > 18K TPS only | 18,000–25,000 | Architecture defined, not automated |
| Spring Boot + Spring Kafka | Kafka stubs | async | ❌ Sprint 22 |
| Microcks | AsyncAPI + Avro | async | ❌ Sprint 23 |
| Spring Boot + Spring JMS | IBM MQ | N/A | ❌ Sprint 24 |

**Key Spring Boot config (already generated by generator-worker):**
```yaml
spring.threads.virtual.enabled: true   # Java 21 virtual threads
server.http2.enabled: true
server.compression.enabled: true
# JVM: -Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10
# EC2: c6i.2xlarge (8 vCPU, 16GB)
```

### 4.4 Data Stores

| Store | Technology | Notes |
|-------|-----------|-------|
| Primary DB | PostgreSQL 15 on AWS RDS (Multi-AZ, eu-west-2) | SQLAlchemy 2.0 + psycopg2 |
| Object storage | AWS S3 (eu-west-2 + eu-west-1 replica) | Spec files, stub packages, reports |
| Cache / sessions | AWS ElastiCache Redis 7 | JWT sessions, WebSocket pub/sub, rate limiting |
| Time-series metrics | AWS Timestream | TPS, latency, error rates (written by metrics-service) |
| Job queue | AWS SQS | parse / generate / deploy / report queues + DLQ |
| Events | AWS EventBridge | Cross-service domain events (`mockingbird.{service}`) |
| Container images | GitLab Container Registry | URL: TBC (input C1) |
| Secrets | HashiCorp Vault (primary) | Endpoint TBC (input I1) — currently using local.env |

### 4.5 Infrastructure

| Area | Decision |
|------|---------|
| AWS Regions | eu-west-2 (London, PRIMARY) + eu-west-1 (Ireland, DR) |
| Platform hosting | Single EC2 t3.2xlarge + Docker Compose (all 10 services + PostgreSQL + Redis) |
| Stub EC2 | c6i.2xlarge per project (1 per project) |
| Deployment targets | (A) Mockingbird AWS account via Terraform, (B) Client AWS via STS AssumeRole, (C) On-prem via SSH + Docker |
| CI/CD | GitLab CI/CD self-hosted, AWS-hosted Kubernetes runners |
| Docker builds | Kaniko (NOT Docker-in-Docker) |
| IaC state | Terraform remote state in S3 + DynamoDB lock |

### 4.6 Authentication — Three Phases

| Phase | Method | Status |
|-------|--------|--------|
| Phase 1 (local) | Admin-created credentials, bcrypt, JWT | ✅ Built and working |
| Phase 2 (LDAP) | `ldapts` library, group-to-role mapping, Redis session cache | ✅ Built — needs LDAP endpoint (input I5) |
| Phase 3 (SAML) | Europa SSO, additive to LDAP | ❌ Not built — Sprint 21+ |

---

## SECTION 5 — Pending Inputs (What We Still Need From You)

### 🔴 CRITICAL — Needed to connect to real infrastructure

| # | What | Why |
|---|------|-----|
| **C1** | GitLab Container Registry exact URL | Every `docker push/pull` in deployer-worker uses this |
| **C2** | Artifactory base URLs: Maven, PyPI, npm, Docker mirror | All production builds use Artifactory — currently using public registries in dev |

*(C3 resolved — PostgreSQL confirmed, in use)*

### 🟡 IMPORTANT — Needed to wire up existing enterprise tools

| # | What | Why |
|---|------|-----|
| **I1** | HashiCorp Vault endpoint URL + auth method (AppRole / Kubernetes / Token) | All services currently read secrets from `config/local.env`. Production needs Vault. |
| **I2** | mTLS (client cert) or server-side TLS only on stub EC2? | Nginx config on every stub EC2 |
| **I3** | Splunk HEC (HTTP Event Collector) endpoint URL + token | Log forwarding from CloudWatch → Splunk |
| **I4** | AppDynamics agent key + controller hostname | APM Java agent in stub containers |
| **I5** | LDAP server hostname, port, base DN, bind service account | LDAP auth is coded and tested — just needs endpoint |

### 🟢 USEFUL — Needed before production rollout to users

| # | What | Why |
|---|------|-----|
| **U1** | Branding assets: logo (PNG/SVG), brand hex colours, PowerPoint template | PDF and PPT reports use placeholder styling — need your organisation's branding |
| **U2** | Internal CA certificate for HTTPS | Stub EC2 HTTPS without browser warnings |
| **U3** | Confirm: on-premise Linux servers as deployment targets? Which teams? | On-prem path architected but not tested |
| **U4** | Any existing WireMock JSON mappings teams have already created? | Platform can import them directly |
| **U5** | LDAP bind credentials (service account username + password) | Stored in Vault, consumed by auth-service |

---

## SECTION 6 — File Map

```
c:\Workspace\Mockingbird\
│
├── START_HERE.md                    ← YOU ARE HERE — read every session
├── CLAUDE.md                        ← AI reference (tech decisions, conventions)
├── SV_Platform_Master_Guide.md      ← Original full requirements + prompt library
│
├── config/
│   └── example.env                  ← All configurable env vars (URLs, keys, ports)
│                                       Copy to local.env (gitignored) for dev
│
├── services/
│   ├── docker-compose.yml           ← All 9 services + PostgreSQL + Redis
│   ├── auth-service/                ← Node.js 20 + Fastify (port 3001)
│   ├── project-service/             ← Python FastAPI (port 8001) — 96 tests
│   ├── ingestion-service/           ← Python FastAPI (port 8003) — 18 tests
│   ├── ai-service/                  ← Python FastAPI (port 8004) — 11 tests
│   ├── metrics-service/             ← Python FastAPI (port 8005)
│   ├── parser-worker/               ← Python SQS consumer — ~388 tests
│   ├── generator-worker/            ← Python SQS consumer
│   ├── deployer-worker/             ← Python SQS consumer (Terraform + GitLab CI)
│   └── reporter-service/            ← Python SQS consumer (PDF + Excel + PPT)
│
├── portal/                          ← React 18 + TypeScript (port 3000) — 77 tests
│   ├── src/
│   │   ├── api/                     ← client.ts, projects.ts, admin.ts, ai.ts, metrics.ts
│   │   ├── pages/                   ← Login, Dashboard, Project, Deployment, Upload,
│   │   │                               JobStatus, AiGenerate, CreateProject, Admin
│   │   ├── components/              ← Layout, ProtectedRoute, AdminRoute, StatusBadge,
│   │   │                               TpsChart, MetricsHistoryChart, UploadZone,
│   │   │                               JobProgress, Tabs, Modal
│   │   ├── hooks/                   ← useMetricsWS (WebSocket live TPS)
│   │   └── store/                   ← auth.ts (Zustand)
│   ├── tests/                       ← 15 test files (Vitest + Testing Library)
│   ├── vite.config.ts               ← Dev proxy for all 5 backend services
│   └── nginx.conf                   ← Production proxy (same routing as Vite proxy)
│
└── docs/
    ├── ARCHITECTURE.md
    ├── USER_FLOWS.md
    ├── TECH_STACK.md
    ├── IMPLEMENTATION_PLAN.md
    ├── DEPLOYMENT_ARCHITECTURE.md
    ├── SV_EXPERT_REVIEW.md
    ├── DECISIONS_LOG.md
    └── FINAL_ARCHITECTURE.md
```

---

## SECTION 7 — How to Resume

### Sprint Status (complete reference)

| Phase | Sprint | Deliverable | Status |
|-------|--------|------------|--------|
| 1 | 1 | TXT/JSON parsers, WireMock generator, Spring Boot generator, sv-gen CLI | ✅ |
| 1 | 2 | Postman v2.1 parser, OpenAPI 3.x/Swagger 2.x parser | ✅ |
| 1 | 3 | SOAP TXT format, BODY_XPATH match type | ✅ |
| 1 | 4 | Template bundling, 34 integration tests, CLI packaging | ✅ |
| 2 | 5 | Dynamic Handlebars, all delay types | ✅ |
| 2 | 6 | Stateful format, state machine scenarios | ✅ |
| 2 | 7 | Namespace XPath, WS-Security, WSDL serving | ✅ |
| 2 | 8 | Fault injection (3 WireMock fault types) | ✅ |
| 3 | 9 | project-service + auth-service + DB + Docker | ✅ |
| 3 | 10 | ingestion-service (upload, S3, format detect) | ✅ |
| 3 | 11 | SQS queues, parser-worker consumer, generator-worker consumer | ✅ |
| 3 | 12 | LDAP auth, Redis session cache, forced logout | ✅ |
| 4 | 13 | deployer-worker — Terraform EC2 + GitLab CI per project | ✅ |
| 5 | 14 | metrics-service — Prometheus → Timestream + WebSocket | ✅ |
| 5 | 15 | reporter-service — PDF + Excel + PowerPoint | ✅ |
| 6 | 16 | React portal foundation — Login, Dashboard, Project, TPS chart | ✅ |
| 6 | 17 | Upload flow, job polling, ingestion routing | ✅ |
| 7 | 18 | ai-service (Claude API), portal AI Generate page | ✅ |
| 6 | 19 | Metrics history chart, Reports tab, presigned URL downloads | ✅ |
| 6 | 20 | Admin panel, Create/Edit/Archive project, Modal component | ✅ |
| 7 | 21 | notification-service (email + Slack + MS Teams) | ✅ |
| 7 | 22 | Kafka stub engine (Spring Boot + Spring Kafka) | ❌ Next |
| 7 | 23 | Microcks — AsyncAPI + Avro | ❌ |
| 7 | 24 | IBM MQ stub engine (Spring Boot + Spring JMS) | ❌ |

### Test Count Summary

| Service | Tests | Confirmed |
|---------|-------|-----------|
| parser-worker | ~388 | ✅ |
| project-service | 96 | ✅ |
| auth-service | 32 | ✅ |
| ingestion-service | 18 | ✅ |
| generator-worker | 3 | ✅ |
| ai-service | 11 | ✅ |
| notification-service | 20 | ✅ |
| portal | 77 | ✅ |
| deployer-worker + metrics-service + reporter-service | ~50 | estimated |
| **Total** | **~690** | |

### Platform Architecture (CONFIRMED — do not change)

**Single EC2 t3.2xlarge + Docker Compose** for the platform.
All 10 services + PostgreSQL + Redis on one machine. Stub EC2s (c6i.2xlarge) always separate — one per project.
If platform goes down: portal unavailable, but all deployed stubs keep running at full TPS.

### Starting a New Claude Session

**Step 1:** Open VS Code in `c:\Workspace\Mockingbird`

**Step 2:** Copy-paste this prompt:

```
Read START_HERE.md and CLAUDE.md. Resume Mockingbird.

Phases 1–6 complete. Phase 7 Sprints 18 + 21 complete. ~690 tests passing.
Start Phase 7 Sprint 22 — Kafka stub engine (Spring Boot + Spring Kafka, generator-worker
extension to produce Kafka consumer stub projects, basic consumer + producer stub support).
```

**To start a specific sprint instead:**

```
Read START_HERE.md and CLAUDE.md. Resume Mockingbird. Start Phase 7 Sprint [N].
```

---

## SECTION 8 — The Complete User Journey

```
1. ADMIN logs in → Admin panel:
   Creates user accounts, assigns roles (SV_TEAM, PROJECT_OWNER, VIEWER)
   Views audit log of all actions

2. PROJECT OWNER logs in → Dashboard:
   Clicks "New Project" → fills name, team, environment, expected TPS
   Project created in DRAFT state

3. PROJECT OWNER uploads spec:
   Drags in: payments-api.yaml (or .txt file with raw HTTP request+response)
   Or: clicks "Generate with AI" → types plain English → Claude generates spec → auto-uploads
   Platform detects format automatically → ingestion-service validates → stores in S3

4. PARSE + GENERATE (background, ~60 seconds):
   parser-worker reads SQS → parses spec → stores stub definitions
   generator-worker reads SQS → generates WireMock JSON mappings + Spring Boot project
   Portal job progress bar shows steps

5. PROJECT OWNER clicks "Deploy":
   deployer-worker reads SQS → triggers GitLab CI (Kaniko builds Docker image)
   Terraform provisions EC2 (c6i.2xlarge), EC2 pulls image from GitLab registry
   ~4 minutes → status: LIVE
   Portal shows: stub URL + API key

6. TEST TEAM calls the stub:
   POST https://10.x.x.x:8080/payments/domestic
   ← WireMock returns fake response at 10,000–18,000 TPS

7. MONITOR (real-time):
   Portal Overview tab: live TPS / latency / error rate via WebSocket
   Portal History tab: 1h / 6h / 24h chart from Timestream
   Portal Reports tab: "Generate Report" → PDF + Excel + PPT download

8. RELEASE SHIPS → "Suspend":
   EC2 terminated (saves £200/month per stub)
   All stubs PRESERVED in PostgreSQL + S3

9. NEXT RELEASE → "Redeploy":
   Same stubs, new EC2, live in 4 minutes
   No re-upload, no re-generation needed
```

---

## SECTION 9 — Key Architecture Decisions (Final — Do Not Re-Discuss)

| Decision | Choice | Reason |
|----------|--------|--------|
| Stub engine | Spring Boot + WireMock embedded (NOT standalone JAR) | Artifactory compatibility, 12K–18K TPS, Spring-WS for SOAP |
| Java version | OpenJDK 21 | Virtual threads — essential for TPS target |
| Docker builds | Kaniko (NOT Docker-in-Docker) | k8s runners, no privileged containers — bank security policy |
| Container registry | GitLab Container Registry (NOT ECR) | Organisation already uses GitLab |
| Database | PostgreSQL (NOT MS SQL) | Zero licence cost |
| Secrets | HashiCorp Vault (NOT just AWS Secrets Manager) | Team already uses Vault aggressively |
| Job queue | AWS SQS | Fully managed, no ops overhead |
| EC2 provisioning | Terraform inside deployer-worker ECS task | No manual CAB, no GitLab round-trip for infra |
| Cross-account deploy | AWS STS AssumeRole → client's `MockingbirdDeployerRole` | Standard AWS pattern, no VPN |
| Stub persistence | Always PostgreSQL + S3 (never only on EC2) | Terminate EC2, redeploy anytime, no data loss |
| Platform hosting | Single EC2 t3.2xlarge + Docker Compose | Simple ops, Year 2 ECS migration is days not months |
| Logs | Splunk via CloudWatch subscription | Existing Splunk — no new tool |
| APM | AppDynamics Java agent | Existing AppDynamics — no new tool |
| AWS Region | eu-west-2 (London) primary | UK data residency for banking |

---

## SECTION 10 — Coding Conventions (Apply Everywhere)

- **Python**: type hints on every function, Pydantic v2 models, no `Any`, PEP 8
- **TypeScript**: strict mode, no `any`, functional components, named exports
- **API errors**: RFC 7807 Problem JSON (`type`, `title`, `status`, `detail`)
- **DB columns**: snake_case, UUID primary keys, `created_at` + `updated_at` on all tables
- **SQS messages**: `{job_id, type, payload, created_at, project_id}`
- **EventBridge**: `source: "mockingbird.{service}"`, `detail-type: "{Entity}.{Action}"`
- **Secrets**: NEVER in code or env vars — always HashiCorp Vault (local.env for dev only, gitignored)
- **Tests**: one test file per source file, fixtures not hardcoded values, no mocking DB in integration tests
- **Comments**: only when WHY is non-obvious — never explain WHAT

---

*Document updated: 2026-06-19 — reflects Session 9 completion (Sprints 13–20 added)*
