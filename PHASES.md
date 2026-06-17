# Mockingbird — Project Roadmap
## All 7 Phases: What Gets Built and Why

**Last Updated:** 2026-06-17  
**Total Timeline:** 56 weeks (14 months)  
**Team:** 1 engineer (you) + Claude as AI pair programmer

---

## At a Glance

| Phase | Weeks | Goal | Who Benefits | Status |
|-------|-------|------|-------------|--------|
| 1 | 1–8 | `sv-gen` CLI tool — parse any API spec, generate stub | SV Team (offline) | ✅ **COMPLETE** |
| 2 | 9–16 | Advanced stub features: SOAP, dynamic data, stateful | All stub users | ✅ **COMPLETE** |
| 3 | 17–24 | Platform backend: APIs, database, file upload | SV Team (via API) | ❌ Not started |
| 4 | 25–32 | Auto-deploy: one click → EC2 running in 4 minutes | SV Team (deploy) | ❌ Not started |
| 5 | 33–38 | Metrics + 4 report formats | Management, CTO | ❌ Not started |
| 6 | 39–48 | Self-service React portal | All project teams | ❌ Not started |
| 7 | 49–56 | Kafka stubs + AI-assisted stub creation | All teams | ❌ Not started |

---

## Phase 1 — `sv-gen` CLI Tool (Weeks 1–8)
### "Give it a file, get a runnable stub"

**Problem it solves:** SV team currently writes WireMock JSON files by hand. This is slow, error-prone, and requires WireMock knowledge. Phase 1 automates this completely for the SV team.

**How it works:**
```
sv-gen --input payment.txt --output ./payment-stub
cd payment-stub
docker compose up
# Stub is live at http://localhost:8080
```

**What gets built:**

| Sprint | Weeks | Deliverable | Status |
|--------|-------|-------------|--------|
| Sprint 1 | 1–2 | Level 1/2/3 TXT+JSON parsers, WireMock generator, Spring Boot project generator, `sv-gen` CLI | ✅ **COMPLETE** |
| Sprint 2 | 3–4 | Postman v2.1 parser, OpenAPI 3.x / Swagger 2.x parser | ✅ **COMPLETE** |
| Sprint 3 | 5–6 | SOAP input format, BODY_XPATH match type, 27 SOAP tests, 127 total tests | ✅ **COMPLETE** |
| Sprint 4 | 7–8 | CLI packaging (`pip install sv-gen`), template bundling, integration tests (34 tests, 161 total) | ✅ **COMPLETE** |

**End-of-phase demo:**
- Team uploads any format (raw TXT, Postman export, OpenAPI YAML)
- `sv-gen` parses it, generates a complete Spring Boot project
- `docker compose up` — stub live, handles 10,000+ TPS
- SV team has gone from "2-3 hours manual work" to "2 minutes"

**Business value:** Eliminates 60% of manual SV work. No CA LISA needed for new projects.

---

## Phase 2 — Advanced Stub Features (Weeks 9–16)
### "Stubs that behave like the real API"

**Problem it solves:** Real APIs don't always return the same response. They return different data based on what you send, remember state across calls, and sometimes fail. Phase 2 makes stubs do the same.

**What gets built:**

| Sprint | Weeks | Deliverable | Status |
|--------|-------|-------------|--------|
| Sprint 5 | 9–10 | **Dynamic responses:** `{{request.pathParam.X}}`, `{{now}}`, `{{randomValue}}`, `{{jsonPath}}`, all delay types | ✅ **COMPLETE** |
| Sprint 6 | 11–12 | **Stateful scenarios:** `--- MOCKINGBIRD v1.0 STATEFUL ---`, multi-step state machine (login→account→transfer→logout), 82 tests | ✅ **COMPLETE** |
| Sprint 7 | 13–14 | **SOAP/WSDL support:** Namespace-aware XPath (`Match-XPath-NS`), WS-Security `@ConditionalOnProperty`, `WsdlConfig.java`, 47 tests, 323 total | ✅ **COMPLETE** |
| Sprint 8 | 15–16 | **Fault injection:** `Fault: connection-reset/empty-response/malformed-response` across all 4 TXT formats, fixed WireMock enum values, 61 tests, 384 total | ✅ **COMPLETE** |

**End-of-phase demo:**
- Stub echoes the customer ID from the URL into the response body
- Call `POST /login` → get session token → call `GET /account` with token → get account data → call `DELETE /logout` → token invalidated
- Send request to SOAP endpoint → correct XML response returned
- Force a 30-second delay and connection reset to test timeout handling in calling system

**Business value:** Replaces 85% of CA LISA scenarios. Complex multi-step banking flows work correctly.

---

## Phase 3 — Platform Backend (Weeks 17–24)
### "A real service with a database, not just a local tool"

**Problem it solves:** Right now sv-gen runs on one person's laptop. There is no central place to manage projects, no history, no multi-user access. Phase 3 turns Mockingbird into a proper shared platform.

**Architecture decision (confirmed):** Single EC2 + Docker Compose. All platform services (10 microservices + PostgreSQL + Redis) run on one EC2 instance. Simple, cheap, right-sized for Year 1.

**What gets built:**

| Sprint | Weeks | Deliverable |
|--------|-------|-------------|
| Sprint 9 | 17–18 | PostgreSQL database schema (projects, stubs, users, deployments, audit_log). FastAPI project-service (CRUD). auth-service (local username/password login, bcrypt). |
| Sprint 10 | 19–20 | ingestion-service: file upload API. Format auto-detection. Validation. Stores uploaded file in S3. Returns validation result. |
| Sprint 11 | 21–22 | SQS job queues: parse-queue → parser-worker (runs sv-gen logic as a service). generate-queue → generator-worker. Async job status tracking. |
| Sprint 12 | 23–24 | LDAP authentication (NatWest network login). Redis session cache. |

**End-of-phase demo:**
- SV team member logs in at `http://mockingbird.internal` (no Postman needed)
- Uploads `payment.txt` → API validates, confirms "2 endpoints, 5 scenarios"
- Clicks Generate → job queued → WireMock mappings created → project status: READY
- All other SV team members can see the project and its stubs

**Business value:** SV team has a shared system. No more "files on someone's laptop." Full audit trail of every change.

---

## Phase 4 — Auto-Deploy (Weeks 25–32)
### "One click → stub live in 4 minutes on AWS EC2"

**Problem it solves:** Even after generating the stub files, someone still has to manually spin up an EC2, install Docker, pull the image, and start the container. Phase 4 makes this a single button click.

**Architecture:**
```
Click "Deploy"
    → deployer-worker provisions EC2 (Terraform)
    → GitLab CI builds Docker image (Kaniko + Artifactory)
    → image pushed to GitLab Container Registry
    → EC2 pulls image → stub running
    → team gets URL + API key
    ← 4 minutes total
```

**What gets built:**

| Sprint | Weeks | Deliverable |
|--------|-------|-------------|
| Sprint 13 | 25–26 | GitLab CI pipeline per stub project: Kaniko builds Docker image using Artifactory. Image in GitLab registry. |
| Sprint 14 | 27–28 | Terraform EC2 provisioning inside deployer-worker. EC2 startup script pulls image from GitLab registry. Stub running. |
| Sprint 15 | 29–30 | Project lifecycle: SUSPEND (terminate EC2, stubs kept in DB/S3). RESUME (re-provision EC2, same image, 4 minutes). |
| Sprint 16 | 31–32 | Cross-account deploy (STS AssumeRole → client's AWS). On-premise deploy (SSH + Docker via Direct Connect). |

**End-of-phase demo:**
- SV team clicks "Deploy" on the Mockingbird portal
- 4 minutes later: "Your stub is live at http://10.x.x.x:8080"
- Project team runs their load test: 10,000+ TPS handled
- SV team clicks "Suspend": EC2 terminated, AWS cost stops
- Next week: "Resume" clicked → same stub back in 4 minutes, no re-upload needed

**Business value:** Zero manual AWS work. Any stub deployed or suspended in minutes. Direct cost comparison to CA LISA licences visible.

---

## Phase 5 — Metrics + Reporting (Weeks 33–38)
### "Management sees business value in numbers and slides"

**Problem it solves:** There is currently no way to show management how many tests are running, how well the stubs are performing, or what the ROI of Mockingbird is versus CA LISA. Phase 5 makes this automatic.

**What gets built:**

| Sprint | Weeks | Deliverable |
|--------|-------|-------------|
| Sprint 17 | 33–34 | Prometheus scrapes each stub EC2 every 30 seconds → AWS Timestream (time-series storage). Grafana dashboard embedded in portal (live TPS, latency, uptime). |
| Sprint 18 | 35–36 | PDF report (WeasyPrint, NatWest branded): project summary, TPS graph, uptime %, response time percentiles (p50/p95/p99). Emailed to management weekly. Excel report (openpyxl): raw data for analysts. |
| Sprint 19 | 37–38 | PowerPoint report (python-pptx, NatWest template): executive slides. WebSocket live feed: real-time TPS counter on portal. |

**Report formats:** PDF (management/CTO) + Excel (finance/analysts) + PowerPoint (presentations) + Live Dashboard (everyone).

**End-of-phase demo:**
- Management receives a PDF report on Monday morning showing: 23 active stubs, 2.4 million requests handled last week, 99.97% uptime, average response time 48ms
- CTO opens PowerPoint: one slide showing cost savings vs CA LISA licences
- SV team sees live dashboard: Payment API stub at 8,423 TPS right now

**Business value:** Proves ROI to leadership. Shows exactly what the platform is doing. Justifies continued investment.

---

## Phase 6 — React Self-Service Portal (Weeks 39–48)
### "Any project team does it themselves — no SV team involvement"

**Problem it solves:** In Phases 1–5, the SV team still has to do everything. Phase 6 gives every project team a browser-based portal so they can upload their own API specs, generate stubs, and deploy them without waiting for the SV team.

**What gets built:**

| Sprint | Weeks | Deliverable |
|--------|-------|-------------|
| Sprint 20–21 | 39–42 | React 18 + TypeScript portal. Login page, project dashboard, file upload with real-time validation, Generate button, Deploy button. |
| Sprint 22 | 43–44 | Live TPS dashboard (Apache ECharts, Canvas-based, handles 60fps updates). Download reports. Admin panel: manage users, view all projects. |
| Sprint 23 | 45–46 | Dynamic stub editor: UI to add/edit conditions (200/400/404/500) without editing JSON files. |
| Sprint 24 | 47–48 | SAML Europa SSO (NatWest SSO for Europa-domain users). Contextual help tooltips. First-time user wizard. |

**End-of-phase demo:**
- A developer from the Payment Gateway team logs in using their NatWest network credentials
- Uploads their Postman collection → "3 endpoints detected, 8 scenarios"
- Clicks Generate → sees the stub code preview → clicks Deploy
- 4 minutes later: their stub URL is shown. They configure their test environment to point to it.
- The SV team was not involved at any point

**Business value:** SV team is no longer a bottleneck. Teams self-serve 24/7. SV team of 5 can now support 100+ projects without adding headcount.

---

## Phase 7 — Kafka Stubs + AI-Assisted Generation (Weeks 49–56)
### "Messaging protocols + plain English stub creation"

**Problem it solves:** Some teams use Kafka or IBM MQ, not HTTP. And some teams don't have API specs — they just know what the API should do. Phase 7 handles both.

**What gets built:**

| Sprint | Weeks | Deliverable |
|--------|-------|-------------|
| Sprint 25–26 | 49–52 | Kafka stubs: Spring Boot + Spring Kafka (simple topics). Microcks for AsyncAPI + Avro schemas. IBM MQ: Spring Boot + Spring JMS. |
| Sprint 27–28 | 53–56 | AI service: team types "simulate a payment API that returns success for amounts under £1000 and declines above" → Claude (claude-sonnet-4-6) generates OpenAPI spec → stub created automatically |

**End-of-phase demo:**
- Team publishes a message to a Kafka topic → stub consumes it and publishes a response to the reply topic
- Team types: "I need a stub for a credit card validation API. It should approve cards starting with 4 (Visa) and decline cards starting with 5 (Mastercard) with a 150ms delay." → stub generated and deployed in 5 minutes

**Business value:** Covers 100% of NatWest integration patterns (REST, SOAP, Kafka, IBM MQ). AI generation means teams with no technical SV knowledge can create stubs from plain English.

---

## Deployment Architecture (Confirmed)

```
┌─────────────────────────────────────────────────────┐
│  Mockingbird Platform EC2 (t3.2xlarge)               │
│  Single machine, Docker Compose, eu-west-2           │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │PostgreSQL│  │  Redis   │  │ All 10 services  │   │
│  │(Docker)  │  │(Docker)  │  │ (FastAPI+Fastify)│   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────┘
         │
         │ provisions (Terraform)
         ▼
┌──────────────────┐  ┌──────────────────┐  ┌─────┐
│  Stub EC2 #1     │  │  Stub EC2 #2     │  │ ... │
│  Payment API     │  │  Customer API    │  │     │
│  10K+ TPS        │  │  10K+ TPS        │  │     │
│  c6i.2xlarge     │  │  c6i.2xlarge     │  │     │
└──────────────────┘  └──────────────────┘  └─────┘
```

Each stub EC2 is **completely independent**. Even if the platform machine goes down for maintenance, all deployed stubs keep running at full TPS.

---

## How to Resume This Project

### Opening prompt (copy-paste exactly):
```
Read START_HERE.md and CLAUDE.md. 
Resume Mockingbird. Phase 1 Sprint 1 is complete. Continue Phase 1 Sprint 2.
```

### If you want to jump to a specific phase:
```
Read START_HERE.md and CLAUDE.md.
Resume Mockingbird. Start Phase [N] Sprint [N].
```

### Files to read if starting fresh:
1. `START_HERE.md` — full project status and confirmed decisions
2. `CLAUDE.md` — complete tech stack and coding conventions
3. `docs/DECISIONS_LOG.md` — every confirmed decision and pending input
4. `PHASES.md` — this file (full roadmap)
