# Mockingbird — Claude's Project Reference
## Read START_HERE.md first if resuming a session. This file is the AI-optimised version.

---

## Project Identity

| Field | Value |
|-------|-------|
| Project Name | Mockingbird |
| Organisation | your organisation |
| Owner | Performance Test Engineer — transitioning from SV consumer to SV platform builder |
| Purpose | Replace CA LISA + IBM Rational Test Workbench with open-source, automated SV platform |
| TPS Target | 10,000+ TPS per stub (Spring Boot Netty + Java 21 on c6i.2xlarge achieves 12K–18K) |
| Licence Cost Target | £0 (all open-source) |
| Timeline | 56 weeks across 7 phases |
| Year 1 Scale | 20–30 projects, mostly 1–2 stubs per project |
| SV Team | 5 people today → ramping down as automation completes |
| Primary Input Formats | Raw .txt HTTP pairs (PRIMARY), .json, Postman v2.1 collections (with saved responses) |

---

## What Mockingbird Does (One Paragraph)

Project teams upload their API spec in any format. Mockingbird auto-detects the format, parses it, generates WireMock stubs inside a Spring Boot application, builds a Docker image via GitLab CI (Kaniko), and deploys to an AWS EC2 instance. The team gets back a URL + API key. Stubs handle 10,000+ TPS. When the project is done, the EC2 is terminated (saves cost) but all stubs remain in PostgreSQL + S3. To redeploy, one click — no re-upload, no re-generation, 4 minutes to live.

---

## Confirmed Tech Stack

### Platform Backend Services

| Service | Language | Purpose |
|---------|----------|---------|
| auth-service | Node.js 20 + Fastify | LDAP auth → JWT; SAML added in Phase 3 |
| project-service | Python 3.11 + FastAPI | Project/stub CRUD, audit log |
| ingestion-service | Python 3.11 + FastAPI | File upload, format auto-detection |
| parser-worker | Python 3.11 (SQS consumer) | Parses .txt / .json / Postman / OpenAPI |
| generator-worker | Python 3.11 (SQS consumer) | Generates WireMock mappings + Spring Boot project |
| deployer-worker | Python 3.11 (SQS consumer) | Triggers GitLab CI build; runs Terraform for EC2 |
| metrics-service | Python 3.11 + FastAPI | Scrapes Prometheus → Timestream; WebSocket TPS feed |
| reporter-service | Python 3.11 (SQS consumer) | PDF (WeasyPrint) + Excel (openpyxl) + PPT (python-pptx) |
| notification-service | Node.js 20 + Fastify | Email, Slack, MS Teams webhooks |
| ai-service | Python 3.11 + FastAPI | Claude API — plain English → OpenAPI stub generation |

All Python packages from your organisation PyPI mirror (Artifactory). All Node packages from your organisation npm mirror.

### Stub Engines (Per-Project EC2)

**IMPORTANT: WireMock runs as an EMBEDDED LIBRARY inside Spring Boot — NOT as standalone JAR.**

| Engine | Used When | TPS on c6i.2xlarge | Artifactory |
|--------|----------|-------------------|-------------|
| Spring Boot + WireMock (Netty) **PRIMARY** | All REST + SOAP | 12,000–18,000 | All JARs via Maven from Artifactory |
| Hoverfly (Go) | Only if > 18K TPS needed | 18,000–25,000 | Docker image via Artifactory mirror |
| Spring Boot + Spring Kafka | Simple Kafka (Phase 4+) | messages/sec | Maven from Artifactory |
| Microcks | AsyncAPI + Avro (Phase 4+) | async | Docker image via Artifactory mirror |
| Spring Boot + Spring JMS | IBM MQ (Phase 4+) | N/A | IBM MQ JARs via Artifactory |

**Spring Boot stub engine key config:**
- Java 21, `spring.threads.virtual.enabled: true`, `server.http2.enabled: true`, `server.compression.enabled: true`
- JVM: `-Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10`
- EC2: c6i.2xlarge (8 vCPU, 16GB) for 10K TPS; c6i.xlarge for < 5K TPS

### Frontend

- React 18 + TypeScript (strict) + Vite
- shadcn/ui + Tailwind CSS
- Apache ECharts (live TPS charts — Canvas-based, not SVG)
- Grafana (embedded in portal for operational dashboards)
- TanStack Query v5 (server state), Zustand (client state)
- WebSocket for real-time TPS (via Redis pub/sub)

### Data Stores

| Store | Technology | Notes |
|-------|-----------|-------|
| Primary DB | **PostgreSQL 15 on AWS RDS** (Multi-AZ, eu-west-2) | NOT MS SQL. Licence-free. SQLAlchemy + psycopg2. |
| Object storage | AWS S3 (eu-west-2 + eu-west-1 replica) | Spec files, stub packages, reports |
| Cache / sessions | AWS ElastiCache Redis 7 | Sessions, API cache, WebSocket pub/sub |
| Time-series metrics | AWS Timestream | TPS, latency, error rates |
| Job queue | AWS SQS | parse/generate/deploy/report queues + DLQ |
| Events | AWS EventBridge | Cross-service domain events |
| Container images | **GitLab Container Registry** (NOT ECR) | URL: TBC — user confirming |
| Secrets | **HashiCorp Vault** (primary) | `hvac` Python, `spring-vault-core` Java |

### Infrastructure

| Area | Decision |
|------|---------|
| AWS Regions | eu-west-2 (London, PRIMARY) + eu-west-1 (Ireland, DR) |
| Platform containers | AWS ECS Fargate (eu-west-2) |
| Stub EC2 | c6i.2xlarge per project; can deploy to: (A) Mockingbird AWS account, (B) Client's AWS account via STS AssumeRole, (C) On-prem via SSH + Direct Connect |
| EC2 provisioning | Terraform inside deployer-worker ECS task (IAM role — no manual steps) |
| Cross-account deploy | AWS STS AssumeRole → client's `MockingbirdDeployerRole` |
| On-premise | SSH + Docker via Python Paramiko (Phase 4); Direct Connect exists |
| CI/CD | GitLab CI/CD (self-hosted, AWS-hosted Kubernetes runners) |
| Docker image builds | **Kaniko** (NOT Docker-in-Docker) — required for k8s runners |
| IaC state | Terraform remote state in S3 + DynamoDB lock |

### Authentication (Three Phases)

| Phase | Method | Status |
|-------|--------|--------|
| 1 (Weeks 1–16) | Local admin-created credentials (bcrypt) | Build this first |
| 2 (Weeks 17–32) | LDAP: `memberOf: CN=SV-Team,OU=Groups,DC=company,DC=com` | LDAP server details TBC |
| 3 (Weeks 39+) | SAML Europa SSO (additive — LDAP still works) | Europa-domain users only |

LDAP role mapping: `CN=SV-Team` → ADMIN, `CN=SV-Users` → SV_TEAM, project groups → PROJECT_OWNER

### Monitoring

| Concern | Tool | Integration |
|---------|------|------------|
| Application logs | Splunk (existing) | JSON logs → CloudWatch → Splunk HEC (endpoint TBC) |
| APM / tracing | AppDynamics (existing) | Java agent in stub containers (agent key TBC) |
| AWS alarms | CloudWatch | SQS depth, ECS crashes, RDS CPU |
| Live dashboards | Grafana (embedded) | Reads Prometheus metrics → Timestream |
| Stub metrics | Prometheus scrapes `/actuator/prometheus` every 30s | |

### Reports (All Four Required)

| Format | Library | Audience |
|--------|---------|---------|
| Live Dashboard | ECharts + WebSocket + Grafana | All users — real-time |
| PDF | WeasyPrint | Management, CTO — branded |
| Excel | openpyxl | Finance, analysts |
| PowerPoint | python-pptx | Management presentations |

---

## Project Lifecycle (Critical Design Concept)

Stubs live in PostgreSQL + S3 ALWAYS. EC2 is ephemeral.

```
DRAFT → READY → DEPLOYING → LIVE → SUSPENDED → (REDEPLOY) → LIVE
                                        ↑
                              EC2 terminated but stubs kept
                              Redeploy: 4 minutes, no re-upload
```

---

## Deployment Targets

| Target | Mechanism | When |
|--------|-----------|------|
| Mockingbird's own AWS account | Terraform via ECS task IAM role | Default |
| Client's AWS account | Terraform + STS AssumeRole | Client wants stubs in their VPC |
| On-premise | SSH + Docker via Direct Connect | Air-gapped or no-AWS teams |

---

## Stub Features (All Required)

- Static responses (60% of projects)
- Dynamic data via Handlebars templates (account numbers, dates, UUIDs)
- Conditional responses by request body/header/param: 200/400/404/500
- Fault injection: 500 errors, timeouts, partial responses
- Response delays: fixed / random / progressive / chunked dribble
- Request field echo: JSONPath extraction in response
- Stateful multi-step scenarios (login → account → transfer)
- SOAP: Spring-WS, WS-Security configurable per project
- No restriction on response body size (compression auto-enabled, bandwidth warning above threshold)

---

## Phase Reference

| Phase | Weeks | Goal | Status |
|-------|-------|------|--------|
| 1 | 1–8 | Parser + Generator CLI (`sv-gen` command) | ❌ NOT STARTED |
| 2 | 9–16 | Dynamic stubs + SOAP + stateful scenarios | Not started |
| 3 | 17–24 | Platform backend (FastAPI + DB + SQS + LDAP) | Not started |
| 4 | 25–32 | Auto-deploy (Terraform + EC2 + GitLab CI) | Not started |
| 5 | 33–38 | Metrics + Reporting (all 4 formats) | Not started |
| 6 | 39–48 | Self-service React portal | Not started |
| 7 | 49–56 | Kafka + AI-assisted generation | Not started |

---

## Pending Inputs (Blocking)

| Priority | Item | Needed For |
|----------|------|-----------|
| 🔴 C1 | GitLab Container Registry URL | Phase 1 Docker commands |
| 🔴 C2 | Artifactory URLs (Maven, PyPI, npm, Docker) | Phase 1 — all builds |
| 🔴 C3 | PostgreSQL acceptable, or MS SQL mandated? | Phase 1 — DB setup |
| 🟡 I1 | HashiCorp Vault endpoint + auth method | Phase 3 |
| 🟡 I2 | mTLS or server-side TLS only? | Phase 2 Nginx |
| 🟡 I3 | Splunk HEC endpoint + token | Phase 3 |
| 🟡 I4 | AppDynamics agent key + controller hostname | Phase 2 |
| 🟡 I5 | LDAP server hostname + base DN | Phase 2 |
| 🟢 U1 | Branding assets (logo, colours, PPT template) | Phase 5 |
| 🟢 U2 | Internal CA certificate | Phase 2 HTTPS |

---

## Repository Structure

```
mockingbird/
├── START_HERE.md                    ← Human resume document (read first)
├── CLAUDE.md                        ← This file (AI context)
├── SV_Platform_Master_Guide.md      ← Full requirements + prompt library
├── docs/
│   ├── ARCHITECTURE.md              ← System + AWS diagrams
│   ├── USER_FLOWS.md                ← User journey flows
│   ├── TECH_STACK.md                ← Technology decisions + rationale
│   ├── IMPLEMENTATION_PLAN.md       ← 7-phase roadmap + sprint breakdown
│   ├── DEPLOYMENT_ARCHITECTURE.md   ← Multi-account + project lifecycle
│   ├── SV_EXPERT_REVIEW.md          ← TPS benchmarks, SV expert findings
│   ├── DECISIONS_LOG.md             ← All confirmed decisions + pending items
│   └── FINAL_ARCHITECTURE.md        ← Consolidated final architecture
├── services/                        ← (Phase 1+) — does not exist yet
├── stub-engines/                    ← (Phase 1+) — does not exist yet
└── terraform/                       ← (Phase 4+) — does not exist yet
```

---

## LLM Integration (Phase 7)

```python
from anthropic import Anthropic
client = Anthropic()  # ANTHROPIC_API_KEY from HashiCorp Vault

# Complex: plain English → OpenAPI spec
model = "claude-sonnet-4-6"   # 200K context, best structured JSON

# Lightweight: field type detection, data rules
model = "claude-haiku-4-5-20251001"  # 12x cheaper, sufficient for classification
```

---

## Coding Conventions (Apply From Phase 1)

- **Python**: type hints on every function, Pydantic v2 models, no `Any`, PEP 8
- **TypeScript**: strict mode, no `any`, functional components, named exports
- **API errors**: RFC 7807 Problem JSON (`type`, `title`, `status`, `detail`)
- **DB columns**: snake_case, UUID primary keys, `created_at` + `updated_at` on all tables
- **SQS messages**: JSON with `job_id`, `type`, `payload`, `created_at`, `project_id`
- **EventBridge**: `source: "mockingbird.{service}"`, `detail-type: "{Entity}.{Action}"`
- **Secrets**: NEVER in code or env vars — always HashiCorp Vault
- **Tests**: one test file per source file, fixtures not hardcoded values, no mocking DB in integration tests
- **Comments**: only when WHY is non-obvious — never explain WHAT the code does

---

## Non-Breaking Change Rules (Apply From Day 1)

1. All API routes versioned: `/api/v1/`, `/api/v2/`
2. New parsers/engines are plugins implementing `BaseParser`/`BaseEngine` interface — zero core changes
3. DB migrations: add columns with defaults only; never drop/rename (expand-contract pattern)
4. New stub features behind feature flags — existing projects unaffected
5. Contract tests (Pact) between portal and backend services — CI blocks on contract failures
6. Stub engine version locked per project in ECR image tag — upgrades are opt-in
