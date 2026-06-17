# MOCKINGBIRD — PROJECT RESUME DOCUMENT
## Read This First When Starting a New Session

**Last Updated:** 2026-06-17 (Session 5)  
**Status:** Phase 2 COMPLETE (384 tests). Phase 3 Sprint 9 COMPLETE — project-service (FastAPI + PostgreSQL, 44 tests), auth-service (Fastify + bcrypt + JWT, 18 tests), Dockerfiles, Alembic migrations, docker-compose.  
**Next Action:** Phase 3 Sprint 10 — ingestion-service (file upload, format auto-detection, S3 storage)

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

## SECTION 2 — Current Status

| Item | Status |
|------|--------|
| Requirements gathering | ✅ Complete |
| Architecture design | ✅ Complete |
| Technology decisions | ✅ Complete |
| User flow design | ✅ Complete |
| Deployment architecture | ✅ Complete |
| Expert SV review | ✅ Complete |
| All decisions documented | ✅ Complete |
| Standard input format files | ✅ Complete (Session 2) |
| Documentation standards defined | ✅ Complete (Session 2) |
| Phase 1 Sprint 1 | ✅ Complete — TXT + JSON parsers, WireMock generator, Spring Boot generator, sv-gen CLI |
| Phase 1 Sprint 2 | ✅ Complete — Postman v2.1 parser, OpenAPI 3.x / Swagger 2.x parser |
| Phase 1 Sprint 3 | ✅ Complete — SOAP input format, BODY_XPATH match type, 127 total tests |
| Phase 1 Sprint 4 | ✅ Complete — CLI packaging (importlib.resources), 34 integration tests, 161 total |
| Phase 2 Sprint 5 | ✅ Complete — dynamic Handlebars, all delay types (fixed/random/chunked/lognormal), 33 tests |
| Phase 2 Sprint 6 | ✅ Complete — stateful `STATEFUL` format, state machine (Started→Authenticated→TransferPending), 82 tests |
| Phase 2 Sprint 7 | ✅ Complete — namespace-aware XPath, WS-Security (ConditionalOnProperty), WSDL serving, 47 tests |
| Phase 2 Sprint 8 | ✅ Complete — fault injection (CONNECTION_RESET_BY_PEER, EMPTY_RESPONSE, MALFORMED_RESPONSE_CHUNK), 61 tests |
| Phase 3 Sprint 9 | ✅ Complete — project-service FastAPI+PostgreSQL (44 tests), auth-service Fastify+bcrypt+JWT (18 tests), Dockerfiles, Alembic migration, docker-compose |
| Phase 3 Sprints 10–12 | ❌ Not started — ingestion-service, SQS workers, LDAP |
| Phase 4–7 | ❌ Not started |

**Phase 1 + Phase 2 fully complete. Phase 3 Sprint 9 complete. 446 tests passing. `sv-gen` CLI fully packaged.**

---

## SECTION 3 — Confirmed Technology Stack (Every Decision)

### 3.1 Platform Backend (the Mockingbird tool itself)

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.11 | All packages from your organisation PyPI mirror (Artifactory) |
| API framework | FastAPI + Pydantic v2 | Auto-generates Swagger docs at /docs |
| Auth service | Node.js 20 + Fastify | LDAP first, SAML Europa SSO later |
| Job queue | AWS SQS | parse-queue, generate-queue, deploy-queue, report-queue, DLQ |
| Domain events | AWS EventBridge | Cross-service events (stub.deployed, project.created) |
| Container platform | AWS ECS Fargate | Serverless containers — no EC2 to manage for platform |
| CI/CD | GitLab CI/CD (self-hosted) | AWS-hosted Kubernetes runners |
| Docker builds | Kaniko (NOT Docker-in-Docker) | Required for k8s runners, rootless, bank-safe |
| Container registry | GitLab Container Registry | NOT AWS ECR. URL to confirm. |
| IaC | Terraform | Runs inside deployer-worker ECS task via IAM role |

### 3.2 Frontend (the web portal users see)

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | React 18 + TypeScript strict | Vite for builds |
| Components | shadcn/ui + Tailwind CSS | Accessible, no vendor lock-in |
| Live charts | Apache ECharts | Canvas-based, handles 10K+ data points at 60fps |
| Operational dashboards | Grafana (embedded iframe) | Reads from Prometheus/Timestream |
| Server state | TanStack Query v5 | Caching, revalidation |
| Client state | Zustand | Lightweight, no Redux |
| Real-time TPS | WebSocket → Redis pub/sub | Live dashboard updates every second |

### 3.3 Stub Engine (what runs on EC2 per project)

| Engine | Used When | TPS | Notes |
|--------|----------|-----|-------|
| **Spring Boot + WireMock (Netty) — PRIMARY** | All REST + SOAP stubs | **12,000–18,000 TPS** | Java 21 virtual threads. All JARs from Artifactory |
| Hoverfly (Go) | Only if > 18K TPS needed | 18,000–25,000 TPS | Fewer features, pure throughput |
| Spring Boot + Spring Kafka | Simple Kafka stubs (Phase 4+) | Messages/sec | Artifactory-friendly |
| Microcks | Complex AsyncAPI + Avro (Phase 4+) | Async | Kafka with schema registry |
| Spring Boot + Spring JMS | IBM MQ (Phase 4+) | N/A | Legacy systems |

**Key Spring Boot config for 10K+ TPS:**
```yaml
spring.threads.virtual.enabled: true   # Java 21 virtual threads (game changer)
server.http2.enabled: true              # HTTP/2 multiplexing
server.compression.enabled: true        # gzip — reduces bandwidth 70-80%
# JVM: -Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10
# EC2: c6i.2xlarge (8 vCPU, 16GB) — achieves 10K+ TPS confirmed
```

### 3.4 Data Stores

| Store | Technology | What It Holds |
|-------|-----------|--------------|
| Primary DB | **PostgreSQL 15 on AWS RDS** (Multi-AZ, eu-west-2) | Projects, stubs, users, deployments, jobs, audit_log |
| Object storage | AWS S3 | Uploaded spec files, generated stub packages, reports |
| Cache / sessions | AWS ElastiCache Redis 7 | API cache, JWT sessions, rate limiting, WebSocket pub/sub |
| Time-series metrics | AWS Timestream | TPS over time, latency percentiles, error rates per stub |
| Secrets | **HashiCorp Vault (PRIMARY)** | DB password, GitLab tokens, LDAP creds, SSH keys |

> **Why PostgreSQL not MS SQL:** Many organisations use MS SQL/Oracle centrally. But Mockingbird's mission is £0 licence cost — MS SQL requires a paid licence. PostgreSQL is free. If your organisation mandates MS SQL for all apps, SQLAlchemy supports it with zero code changes.

### 3.5 Infrastructure

| Area | Decision |
|------|---------|
| AWS Regions | **eu-west-2 (London) PRIMARY** + eu-west-1 (Ireland) DR/overflow |
| Platform containers | AWS ECS Fargate (no EC2 management) |
| Stub servers | AWS EC2 per project (c6i.2xlarge for 10K+ TPS) |
| Stub deployment target options | (A) Mockingbird's own AWS account, (B) Client's own AWS account via STS AssumeRole, (C) On-premise via SSH + Direct Connect |
| On-premise connectivity | AWS Direct Connect exists between on-premise and AWS |
| DNS | AWS Route 53 |
| CDN | AWS CloudFront → S3 (React portal) |
| EC2 provisioning | Terraform runs inside ECS deployer-worker task (IAM role, no manual steps) |

### 3.6 Monitoring & Observability

| Concern | Tool | How |
|---------|------|-----|
| Application logs | **Splunk** (existing) | Structured JSON → CloudWatch Logs → Splunk HEC subscription |
| APM / tracing | **AppDynamics** (existing) | Java agent injected into Spring Boot stub containers |
| AWS alarms | CloudWatch | SQS depth, ECS task health, RDS CPU |
| Live TPS dashboards | Grafana (embedded in portal) | Reads Prometheus metrics from stub engines → Timestream |
| Stub metrics collection | Prometheus scrapes Spring Boot Actuator `/actuator/prometheus` every 30s | |

### 3.7 Authentication (Three Phases)

| Phase | Method | When |
|-------|--------|------|
| Phase 1 (Weeks 1–16) | Local admin-created credentials (bcrypt) | During development — no external dependency |
| Phase 2 (Weeks 17–32) | **LDAP** — network login | `memberOf: CN=SV-Team,OU=Groups,DC=company,DC=com` → ADMIN role |
| Phase 3 (Weeks 39+) | **SAML — Europa SSO** (additive, LDAP still works) | For Europa-domain users |

**LDAP role mapping:**
```
CN=SV-Team   → ADMIN
CN=SV-Users  → SV_TEAM
CN={project} → PROJECT_OWNER
(any auth'd)  → VIEWER
```

### 3.8 Reports (All Four Formats Required)

| Format | Library | Audience |
|--------|---------|---------|
| Live Dashboard | React + ECharts + WebSocket + Grafana | Everyone — real-time TPS, latency |
| PDF | WeasyPrint (Python) | Management, CTO — branded |
| Excel | openpyxl (Python) | Finance, analysts — raw data |
| PowerPoint | python-pptx (Python) | Management presentations — branded template |

---

## SECTION 4 — What We Know About the Organisation's Setup

| Topic | Confirmed Answer |
|-------|----------------|
| Artifactory | YES — internal mirror for Maven, PyPI, npm, Docker. URL: TBC |
| Java version | OpenJDK 21 ✅ (virtual threads available) |
| Container registry | GitLab Container Registry (NOT ECR). Exact URL: TBC (user checking Monday) |
| GitLab | Self-hosted. AWS-hosted Kubernetes runners |
| Docker builds in CI | Kaniko (k8s runners, no DinD) |
| SSO | SSO only for Europa users. LDAP for all others. LDAP first |
| Direct Connect | YES — AWS ↔ on-premise connectivity exists |
| EC2 approval | Automated via Terraform (no manual CAB needed for Mockingbird) |
| Database standard | MS SQL + Oracle (centrally managed) BUT Mockingbird uses PostgreSQL |
| Secrets | HashiCorp Vault (aggressively used) + AWS Secrets Manager |
| Monitoring | DX APM, AppDynamics, Splunk, Elasticsearch, CloudWatch |
| Projects Year 1 | 20–30 projects |
| Stubs per project | Mostly 1 (occasionally 2) |
| TPS requirement | 10,000+ TPS per stub (met by Spring Boot Netty + c6i.2xlarge) |
| Input formats | Raw .txt (PRIMARY), .json, Postman v2.1 (with saved responses) |
| Response size | No restriction — any size. Compression auto-enabled. Warning shown if > bandwidth |
| Slow response sim | YES — needed. Fixed/random/progressive/chunked dribble |
| Conditional responses | YES — needed. 200/400/404/500/fault injection via WireMock priority mappings |
| Kafka / IBM MQ | Deferred to Phase 4+ |
| SV team size | 5 people today → plan to ramp down as automation completes |
| On-premise deployment | Maybe needed — architecture supports it (Phase 4) |
| Report formats | PDF + Excel + PowerPoint + Live Dashboard (ALL four) |
| Branding | YES — all reports must use your organisation's logo/colours/template |
| LDAP group format | `memberOf: CN=SV-Team,OU=Groups,DC=company,DC=com` |

---

## SECTION 5 — Pending Inputs (What We Still Need)

### 🔴 CRITICAL — Needed Before Writing Phase 1 Code

| # | What We Need | Why It's Blocking |
|---|-------------|------------------|
| **C1** | GitLab Container Registry exact URL | Every `docker push` and `docker pull` command in CI uses this |
| **C2** | Artifactory base URLs: Maven (`https://artifactory.internal/...`), PyPI, npm, Docker mirror | Every `pom.xml`, `requirements.txt`, `package.json` uses these |
| **C3** | Is PostgreSQL acceptable, or does your organisation mandate MS SQL for ALL new applications? | Determines entire DB setup before any table is created |

### 🟡 IMPORTANT — Needed Before Phase 2–3 (Weeks 9–24)

| # | What We Need | Why |
|---|-------------|-----|
| **I1** | HashiCorp Vault endpoint URL + auth method (AppRole? Kubernetes auth? Token?) | Secrets integration in all services |
| **I2** | mTLS (client presents certificate to stub) or server-side TLS only? | Nginx config on every stub EC2 |
| **I3** | Splunk HEC (HTTP Event Collector) endpoint URL + token | Log forwarding from CloudWatch |
| **I4** | AppDynamics agent key / controller hostname | APM agent in stub containers |
| **I5** | LDAP server hostname, port, base DN, bind account | Auth service Phase 2 |

### 🟢 USEFUL — Needed Before Phase 5–6 (Weeks 33–48)

| # | What We Need | Why |
|---|-------------|-----|
| **U1** | Branding assets: logo (PNG/SVG), brand colours (hex), fonts, PowerPoint template | PDF and PPT report generation |
| **U2** | Internal CA certificate for HTTPS on stub servers | SSL setup without browser warnings |
| **U3** | Confirm: are on-premise Linux servers expected as deployment targets? Which teams? | Phase 4 scope |
| **U4** | Any existing WireMock JSON mappings that teams have already created manually? | Platform should be able to import them |
| **U5** | LDAP bind credentials (service account username + password) | Stored in Vault, used by auth-service |

---

## SECTION 6 — File Map (What Each Document Contains)

```
c:\Workspace\Mockingbird\
│
├── START_HERE.md                    ← YOU ARE HERE — read this first every session
│
├── CLAUDE.md                        ← AI reference (Claude reads this for context)
│
├── SV_Platform_Master_Guide.md      ← Original full requirements + prompt library
│                                       (prompt templates for each implementation phase)
│
└── docs/
    ├── ARCHITECTURE.md              ← System architecture + AWS infrastructure diagrams
    │                                   Microservices layout, data flows, security model
    │
    ├── USER_FLOWS.md                ← Step-by-step user journeys
    │                                   Upload → Generate → Deploy → Monitor → Report
    │
    ├── TECH_STACK.md                ← Every technology choice with rationale
    │                                   "Why Spring Boot and not standalone WireMock"
    │                                   "Why PostgreSQL and not MS SQL"
    │
    ├── IMPLEMENTATION_PLAN.md       ← 7-phase roadmap, sprint breakdown for Phase 1
    │                                   Risk register, team recommendations
    │
    ├── DEPLOYMENT_ARCHITECTURE.md   ← Multi-account deployment (SV account, client account, on-prem)
    │                                   Project lifecycle (LIVE → SUSPEND → REDEPLOY without re-upload)
    │
    ├── SV_EXPERT_REVIEW.md          ← Deep technical SV review
    │                                   TPS benchmarks, WireMock vs Spring Boot analysis
    │                                   Non-breaking change patterns, Kafka strategy
    │
    ├── DECISIONS_LOG.md             ← Every confirmed decision + what's still pending
    │                                   Chronological record of all answers from project team
    │
    ├── FINAL_ARCHITECTURE.md        ← Consolidated final architecture (most up-to-date)
    │                                   EC2 provisioning flow, stub engine details, auth phases
    │
    ├── DOCUMENTATION_STANDARDS.md  ← How docs work in this project
    │                                   What is auto-generated vs AI-maintained vs manual
    │
    └── input-formats/               ← Standard input file formats for client teams
        ├── GUIDE.md                 ← Complete guide — which format to use + step-by-step
        ├── templates/
        │   ├── level-1-simple.txt         ← Simplest format — single request/response
        │   ├── level-2-multi-scenario.txt ← Multiple scenarios (200/404/500)
        │   └── level-3-full.json          ← Full control — dynamic params, delays, faults
        └── examples/
            ├── GET-customer-simple.txt         ← Filled Level 1 example (REST GET)
            ├── POST-payment-multi-scenario.txt ← Filled Level 2 example (REST POST + 5 scenarios)
            ├── customer-api-full.json          ← Filled Level 3 example (dynamic + delays + faults)
            └── customer-soap.txt              ← SOAP XML stub example
```

---

## SECTION 7 — How to Resume (Exact Steps)

### Current Status (as of 2026-06-17)

| Phase | Sprint | Status |
|-------|--------|--------|
| Phase 1 Sprint 1 | TXT + JSON parsers, WireMock generator, Spring Boot generator, sv-gen CLI | ✅ COMPLETE |
| Phase 1 Sprint 2 | Postman v2.1 parser, OpenAPI 3.x / Swagger 2.x parser | ✅ COMPLETE |
| Phase 1 Sprint 3 | SOAP TXT format, BODY_XPATH match type, 127 tests | ✅ COMPLETE |
| Phase 1 Sprint 4 | Template bundling (importlib.resources), 34 integration tests, 161 total | ✅ COMPLETE |
| Phase 2 Sprint 7 | Namespace-aware XPath, WS-Security, WSDL serving, 47 tests | ✅ COMPLETE |
| Phase 2 Sprint 8 | Fault injection — all 3 WireMock fault types, all 4 TXT parsers, 61 tests | ✅ COMPLETE |
| Phase 3 Sprint 9 | project-service (FastAPI CRUD + PostgreSQL ORM + JWT auth, 44 tests), auth-service (Fastify + bcrypt + JWT, TypeScript strict, 18 tests), Dockerfiles, Alembic migrations 001, docker-compose.yml | ✅ COMPLETE |
| Phase 3 Sprint 10 | ingestion-service (file upload, format auto-detection, S3) | ❌ Not started |
| Phase 3 Sprint 11 | SQS job queues (parse-queue → parser-worker as service) | ❌ Not started |
| Phase 3 Sprint 12 | LDAP auth + Redis session cache | ❌ Not started |
| Phase 4–7 | Auto-deploy, metrics, portal, Kafka + AI | ❌ Not started |

### Platform Architecture Decision (CONFIRMED)

**Option A: Single EC2 + Docker Compose** — this is what we will build.

All 10 platform services + PostgreSQL + Redis run on one EC2 (t3.2xlarge). Docker Compose manages them.  
Stub EC2s (c6i.2xlarge) are always separate — one per project.  
If platform machine goes down: portal unavailable, but all deployed stubs keep running at full TPS.  
Year 2 if scale demands it: services are already containerised — moving to ECS takes days, not months.

### Starting a New Claude Session

**Step 1:** Open VS Code in `c:\Workspace\Mockingbird`

**Step 2:** Copy-paste this exactly:

```
Read START_HERE.md and CLAUDE.md. Resume Mockingbird.
Phase 1 + Phase 2 + Phase 3 Sprint 9 fully complete (446 tests total). Start Phase 3 Sprint 10 — ingestion-service (file upload, format auto-detection, S3 storage).
```

**That is all. No other inputs needed. Claude will continue immediately.**

### If You Want to Jump to a Different Point

```
Read START_HERE.md and CLAUDE.md. Resume Mockingbird. Start Phase [N] Sprint [N].
```

---

### Phase 1 — What Gets Built First (Weeks 1–8)

Phase 1 is a **command-line tool** (no UI, no database, no AWS). It takes any API spec file and outputs a ready-to-run WireMock Docker project.

```
INPUT:  payments-api.yaml (OpenAPI 3.0 file)
                │
                ▼
    sv-gen --input payments-api.yaml --output ./payments-stub
                │
                ▼
OUTPUT: payments-stub/
          ├── mappings/
          │     ├── POST_payments_domestic.json   (WireMock mapping)
          │     └── GET_payments_{id}.json        (WireMock mapping with 200 + 404)
          ├── Dockerfile                          (Spring Boot app)
          ├── pom.xml                             (all deps from Artifactory)
          ├── docker-compose.yml
          └── src/main/java/MockingbirdStubApp.java
                │
                ▼
    docker-compose up → stubs live on localhost:8080
    curl http://localhost:8080/payments/domestic → fake response
```

**Phase 1 Sprint Plan:**

| Sprint | Weeks | Deliverable | Status |
|--------|-------|------------|--------|
| Sprint 1 | 1–2 | Level 1/2/3 TXT parsers, JSON parser, WireMock generator, Spring Boot project generator, sv-gen CLI | ✅ COMPLETE |
| Sprint 2 | 3–4 | Postman v2.1 parser + OpenAPI 3.x / Swagger 2.x parser | ✅ COMPLETE |
| Sprint 3 | 5–6 | SOAP TXT format, BODY_XPATH match type, 127 tests | ✅ COMPLETE |
| Sprint 4 | 7–8 | Template bundling (importlib.resources), 34 integration tests, 161 total tests | ✅ COMPLETE |

**Impact at end of Phase 1:** Can auto-generate stubs from any spec file. Demo to SV team.

---

### To Start Phase 1 Right Now — Say This:

```
Start Phase 1, Sprint 1. Build the Python monorepo scaffold and input auto-detector.
Use the master context from CLAUDE.md.
All Python packages come from Artifactory (I will provide the URL).
```

---

## SECTION 8 — The User Journey (Simple Version)

```
1. ADMIN sets up: creates user accounts, assigns roles (SV-Team, Project Owner, Viewer)

2. PROJECT OWNER logs in → creates project:
   Name: payments-stub | Team: PaymentsTeam | Environment: TEST | Expected TPS: 10,000

3. PROJECT OWNER uploads spec:
   Drags in: payments-api.yaml (or .txt file with raw HTTP request+response)
   Platform detects format automatically → shows preview of endpoints

4. PROJECT OWNER clicks "Generate Stubs":
   Background job generates WireMock JSON mappings
   User sees stub in editor — can edit response, add delays, add 400/404 conditions

5. PROJECT OWNER clicks "Deploy to TEST":
   GitLab CI builds Docker image (Spring Boot + WireMock + mappings)
   Terraform creates EC2 (c6i.2xlarge)
   EC2 pulls image from GitLab registry → WireMock starts
   4 minutes later: "Your stub is live at https://10.x.x.x:8080 — API Key: mk_xxx"

6. TEST TEAM calls the stub:
   POST https://10.x.x.x:8080/payments/domestic
   ← WireMock returns fake response at 10,000+ TPS

7. RELEASE SHIPS: Project Owner clicks "Suspend"
   → EC2 terminated (saves £200/month)
   → Stubs PRESERVED in database and S3

8. NEXT RELEASE (months later): Click "Redeploy"
   → Same stubs, new EC2, live in 4 minutes
   → NO re-upload, NO re-generation needed
```

---

## SECTION 9 — Key Architecture Decisions (Quick Reference)

| Decision | Choice | Reason |
|----------|--------|--------|
| Stub engine | Spring Boot + WireMock (Netty) NOT standalone WireMock JAR | Artifactory, 12K–18K TPS, Spring-WS for SOAP, extensible |
| Java version | OpenJDK 21 | Virtual threads → massive TPS improvement. |
| Docker builds | Kaniko (NOT Docker-in-Docker) | k8s runners, no privileged containers — enterprise security |
| Container registry | GitLab Container Registry | Already uses GitLab |
| Database | PostgreSQL (NOT MS SQL) | Zero licence cost — aligns with Mockingbird's £0 cost mission |
| Secrets | HashiCorp Vault | Team already uses it aggressively |
| Job queue | AWS SQS | Fully managed, no ops overhead, native AWS |
| EC2 provisioning | Terraform inside deployer-worker ECS task | No manual steps, no GitLab round-trip for infra |
| Cross-account deploy | AWS STS AssumeRole | Standard AWS pattern, no VPN needed |
| Stub persistence | Always in DB + S3 (separate from EC2) | Can terminate EC2, redeploy anytime, no re-upload |
| Logs | Splunk via CloudWatch subscription | Existing Splunk — no new tool |
| APM | AppDynamics agent | Existing AppDynamics — no new tool |

---

## SECTION 10 — Things NOT to Rebuild or Change

These decisions are final. Do not re-discuss unless new information changes them:

1. **Spring Boot + WireMock as library** — not standalone WireMock JAR (Artifactory reason is non-negotiable)
2. **Kaniko for Docker builds** — not DinD. k8s runners don't allow privileged containers in banks.
3. **PostgreSQL over MS SQL** — unless your organisation explicitly mandates MS SQL for all apps (pending C3)
4. **HashiCorp Vault** — not just AWS Secrets Manager. Team already uses Vault.
5. **GitLab Container Registry** — not ECR (pending URL confirmation but decision is made)
6. **Stub statefulness in DB** — stubs are ALWAYS in DB/S3, never only on EC2
7. **Java 21** — non-negotiable for virtual threads and TPS targets
8. **eu-west-2 as primary region** — London (UK data residency for banking)

---

*Document generated: 2026-06-14*  
*Next update: after Phase 1 code is started*
