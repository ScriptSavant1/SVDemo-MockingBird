# Service Virtualisation (SV) Platform — Master Implementation Guide
### Prompt Engineering & Architecture Reference Document
**Version:** 1.0  
**Created from:** Full requirements discovery session  
**Context:** Enterprise Banking Environment  
**Author Context:** Performance Test Engineer transitioning to SV Platform Builder  

---

## Table of Contents

1. [Project Vision & Mission](#1-project-vision--mission)
2. [Business Context & Current State](#2-business-context--current-state)
3. [Problem Statement](#3-problem-statement)
4. [Solution Overview](#4-solution-overview)
5. [Technology Stack — Final Decisions](#5-technology-stack--final-decisions)
6. [Protocol Support Strategy](#6-protocol-support-strategy)
7. [Complete Feature List](#7-complete-feature-list)
8. [Architecture — Full Detail](#8-architecture--full-detail)
9. [Dynamic Response Scenarios](#9-dynamic-response-scenarios)
10. [TPS Strategy & EC2 Sizing](#10-tps-strategy--ec2-sizing)
11. [Reporting Requirements](#11-reporting-requirements)
12. [Phased Implementation Plan](#12-phased-implementation-plan)
13. [Prompt Engineering — Implementation Prompts](#13-prompt-engineering--implementation-prompts)
14. [Prompt Library — Phase by Phase](#14-prompt-library--phase-by-phase)
15. [What to Ask Claude at Each Stage](#15-what-to-ask-claude-at-each-stage)
16. [Glossary — SV Concepts for Beginners](#16-glossary--sv-concepts-for-beginners)

---

## 1. Project Vision & Mission

### Vision
> Build an **open-source, license-free, bank-grade Service Virtualisation platform** that completely replaces CA LISA and IBM Rational Test Workbench — with richer reporting, better automation, and AI-assisted stub generation — deployable on AWS EC2 or on-premise, supporting 15,000+ TPS.

### Mission
- Eliminate the manual bottleneck where the SV team hand-crafts every stub
- Allow project teams to self-serve: upload spec → get stub URL in minutes
- Replace $100,000+/year licensed tools with $0 open-source alternatives
- Generate management-grade reporting richer than paid tools
- Future-proof the platform for the next 10 years

### Success Criteria
- [ ] 60% of plain vanilla REST stubs auto-generated in < 2 minutes
- [ ] 20% dynamic stubs auto-generated with data rules in < 5 minutes
- [ ] SOAP stubs generated from WSDL without manual intervention
- [ ] Kafka stubs supported
- [ ] 15,000+ TPS verified under load test
- [ ] One-click deploy to EC2
- [ ] Management dashboard live with real-time TPS, request counts, audit trail
- [ ] Zero license cost

---

## 2. Business Context & Current State

### Organisation
- **Organisation:** your organisation
- **Environment:** AWS EC2 (per-project instances) + internal on-premise network
- **Network model:** Firewalls opened per project between source server and stub EC2

### Current SV Team Workflow (AS-IS)
```
Project Team
    │
    │ shares request headers, response bodies, parameters
    ▼
SV Team (manual)
    │
    ├── Uses IBM Rational Test Workbench
    ├── Uses CA LISA (Service Virtualization)
    │
    │ manually creates project
    │ manually creates stubs
    │ manually deploys to AWS EC2
    │
    ▼
EC2 Instance (per project)
    │
    │ firewall opened by project team
    ▼
Project Team consumes stubs
```

### Pain Points (Current State)
- SV team is a manual bottleneck for every project
- Every stub requires SV team involvement
- Deployment is manual and slow
- No self-service capability
- Expensive licensed tools (CA + IBM)
- No rich reporting or management dashboards
- No audit trail of who created what
- Firewall documentation is manual

### API Usage Breakdown (Real Data from Conversation)
| Type | Percentage | Description |
|------|------------|-------------|
| Plain Vanilla REST | 60% | Static request/response, no logic |
| Dynamic REST | 20% | Generated account numbers, dates, IDs |
| REST with logic | 15% | Conditional responses, business rules |
| SOAP / XML | 5% | WSDL-based, XPath matching |
| Kafka | Small but growing | Async messaging, event-driven |

---

## 3. Problem Statement

### Primary Problem
**The SV team manually creates every stub using IBM/CA tools, which:**
- Creates a bottleneck (one team serves entire bank)
- Takes days per project instead of minutes
- Costs $100K+/year in licenses
- Produces no management visibility
- Cannot scale as bank's API estate grows

### Secondary Problem
**No automation exists for:**
- Parsing API specs (Postman, OpenAPI, WSDL, HAR)
- Generating WireMock-compatible stub projects
- Deploying to EC2 automatically
- Monitoring TPS and request metrics
- Reporting to management

### Tertiary Problem
**Knowledge gap:**
- SV is a specialist skill — hard to hire for
- Project teams cannot self-serve
- SV team is not scalable

---

## 4. Solution Overview

### TO-BE Architecture (What We're Building)
```
Project Team
    │
    │ uploads: OpenAPI / Postman / WSDL / HAR / Raw request-response
    ▼
SELF-SERVICE PORTAL (React Web App)
    │
    ▼
PLATFORM BACKEND (FastAPI + Python)
    ├── Parser Service      (detects and parses any input)
    ├── Generator Engine    (creates WireMock / Microcks stubs)
    ├── Project Packager    (Docker image + config)
    ├── Deployer Service    (Terraform + EC2 + ECR)
    └── Reporter Service    (metrics, dashboards, exports)
    │
    ▼
AWS EC2 (one per project, auto-provisioned)
    └── WireMock / Hoverfly / Microcks container
        └── Prometheus exporter (metrics)
    │
    ▼
Project Team gets: stub URL + API key + firewall spec doc
```

### Key Differentiators vs CA/IBM
| Feature | CA LISA / IBM | Our Platform |
|---------|---------------|--------------|
| License cost | $100K+/year | $0 |
| Stub generation | Manual | Fully automated |
| Supported inputs | Limited | OpenAPI, Postman, WSDL, HAR, Bruno, Raw, CSV |
| TPS | High (expensive HW) | 15K+ (optimised OSS) |
| Deployment | Manual | One-click auto |
| Reporting | Basic | Rich, multi-audience |
| AI assistance | None | Phase 7 |
| Self-service | No | Yes |
| Audit trail | Limited | Complete |
| Source control | Limited | GitLab native |

---

## 5. Technology Stack — Final Decisions

### Stub Engines
```
WireMock (Java)     — Primary REST + SOAP engine
                      Handles: static, dynamic, stateful, fault injection
                      TPS: up to 10K on right hardware
                      License: Apache 2.0 (FREE)

Hoverfly (Go)       — High TPS REST engine
                      Handles: simulate mode, 20K+ TPS
                      Used when: project needs > 10K TPS
                      License: Apache 2.0 (FREE)

Microcks            — Kafka + GraphQL + gRPC + AsyncAPI
                      Handles: async protocols, Kafka topic stubs
                      License: Apache 2.0 (FREE)
```

### Platform Backend
```
Python 3.11+        — Primary language
FastAPI             — REST API framework (async, fast, auto-docs)
Pydantic v2         — Data validation and schema
Celery              — Async job queue (generate, deploy, report jobs)
Redis               — Job broker + caching
SQLAlchemy          — ORM for PostgreSQL
Alembic             — Database migrations
```

### Storage
```
PostgreSQL 15       — Project metadata, stub registry, audit logs, users
Redis 7             — Job queue, caching, session storage
MinIO               — File storage (uploaded specs, HAR files, XMLs)
                      S3-compatible, runs on-premise or AWS
InfluxDB 2          — Time-series metrics (TPS, request counts, latency)
```

### Infrastructure & Deployment
```
Docker              — Container per project
AWS EC2             — One instance per project (as per current model)
AWS ECR             — Container registry
Terraform           — Infrastructure as code (EC2 provisioning)
GitLab CI/CD        — Pipeline automation
Nginx               — Reverse proxy + SSL termination
AWS Secrets Manager — Secrets management
```

### Frontend
```
React 18 + TypeScript   — Portal frontend
Vite                    — Build tool
TanStack Query          — API state management
Apache ECharts          — Rich interactive charts
Grafana (embedded)      — Real-time TPS dashboards
Tailwind CSS            — Styling
React Router v6         — Navigation
```

### Monitoring & Observability
```
Prometheus          — Metrics scraping from WireMock exporters
Grafana             — Dashboards (embedded in portal)
InfluxDB            — Long-term metrics storage
Loki                — Log aggregation (lightweight ELK alternative)
```

### Testing
```
pytest              — Backend unit + integration tests
Testcontainers      — Docker-based integration testing
Locust              — TPS validation testing
Playwright          — Frontend E2E testing
```

---

## 6. Protocol Support Strategy

### Priority Tiers
```
TIER 1 — Phase 1 & 2 (covers 85% of bank's needs)
├── REST / HTTP/HTTPS     (60% plain vanilla + 20% dynamic + 15% logic)
└── SOAP / XML / WSDL     (5% of projects)

TIER 2 — Phase 3 (growing protocols)
├── Kafka                 (async messaging, event-driven projects)
├── GraphQL               (20% industry, growing in bank)
└── gRPC                  (microservices)

TIER 3 — Phase 4 (future/legacy)
├── IBM MQ / JMS          (40% banking legacy)
├── TIBCO                 (20% banking)
├── WebSocket             (10%)
├── JDBC / Database       (20%)
└── SFTP / FTP            (10% legacy)
```

### Engine Selection Logic
```python
# Platform auto-selects engine based on:

if protocol == "REST" and tps_requirement < 10000:
    engine = "WireMock"
    instance = "c6i.xlarge"  # 4 vCPU, 8GB

elif protocol == "REST" and tps_requirement >= 10000:
    engine = "Hoverfly"
    instance = "c6i.2xlarge"  # 8 vCPU, 16GB

elif protocol == "SOAP":
    engine = "WireMock"  # native SOAP support
    instance = "c6i.xlarge"

elif protocol == "Kafka":
    engine = "Microcks"
    instance = "c6i.xlarge"  # + Kafka broker

elif protocol in ["GraphQL", "gRPC"]:
    engine = "Microcks"
    instance = "c6i.xlarge"
```

---

## 7. Complete Feature List

### 7.1 Input Processing
- [ ] Auto-detect input type (zero user config needed)
- [ ] OpenAPI 3.x YAML and JSON parsing
- [ ] Swagger 2.x YAML and JSON parsing
- [ ] Postman Collection v2.1 parsing
- [ ] WSDL 1.1 / 2.0 parsing (SOAP)
- [ ] HAR file parsing (browser traffic capture)
- [ ] Bruno collection parsing
- [ ] Raw HTTP request + response pair (plain text)
- [ ] AsyncAPI spec parsing (Kafka)
- [ ] Excel / CSV with request-response pairs
- [ ] Multiple files per project (bulk upload as ZIP)
- [ ] Input validation with clear error messages
- [ ] Preview parsed endpoints before generation

### 7.2 Stub Generation
- [ ] Plain vanilla static stubs (exact match)
- [ ] Dynamic data generation (UUID, random number, date, alphanumeric)
- [ ] Request data echo in response (JSONPath extraction)
- [ ] XPath matching for SOAP requests
- [ ] Conditional responses (if/else on request fields)
- [ ] Stateful scenarios (multi-step sequences)
- [ ] Response delays (fixed, random, progressive)
- [ ] Fault injection (timeout, 500 error, network drop, partial response)
- [ ] Multiple responses per endpoint (round-robin)
- [ ] Data-driven responses from CSV or database
- [ ] Custom logic via client-provided rules
- [ ] SOAP envelope wrapping and unwrapping
- [ ] Multiple XML documents per endpoint
- [ ] Kafka message production stubs
- [ ] Kafka message consumption simulation
- [ ] Schema-based random data generation (respects data types)
- [ ] Regex-based request matching
- [ ] Header-based routing to different responses

### 7.3 Project Management
- [ ] Create, edit, delete, clone projects
- [ ] Per-project stub library with search
- [ ] Stub versioning and history
- [ ] Import / export project (ZIP)
- [ ] Environment tagging (dev / test / perf / uat / prod-like)
- [ ] Project ownership with team assignment
- [ ] Role-based access per project
- [ ] Project metadata (owner, team, created date, cost centre)
- [ ] Stub editor (inline, web-based)
- [ ] Bulk stub operations (enable, disable, delete)
- [ ] Project health status dashboard

### 7.4 Deployment
- [ ] One-click deploy button in portal
- [ ] Auto EC2 provisioning via Terraform
- [ ] Docker image build (per project)
- [ ] Push to AWS ECR
- [ ] Pull and run on EC2
- [ ] Health check post-deploy with retry
- [ ] Stub URL returned to user immediately
- [ ] API key generated per project
- [ ] Zero-downtime redeploy
- [ ] Rollback to any previous version
- [ ] On-premise deployment support (same Terraform, different target)
- [ ] Auto-generated firewall documentation (source IP, port, protocol)
- [ ] Deploy status tracking (queued, building, deploying, live, failed)
- [ ] GitLab CI/CD pipeline integration
- [ ] Environment-specific deploy (deploy to test vs perf)

### 7.5 Reporting — Management Grade
- [ ] Total stubs created (all time, per period, per project, per team)
- [ ] Stub creation timeline (who created, when, what)
- [ ] Total requests processed (per stub, per project, per team, total)
- [ ] Live TPS per project (real-time)
- [ ] Historical TPS (hourly, daily, weekly, monthly)
- [ ] Peak TPS recorded per project
- [ ] Latency percentiles (P50, P90, P95, P99) per endpoint
- [ ] Error rate per stub and per project
- [ ] Fault injection statistics (how many timeouts simulated etc.)
- [ ] Deployment history and audit trail
- [ ] User activity log (who did what, when — full audit)
- [ ] Project uptime and availability percentage
- [ ] EC2 cost per project (estimated from instance hours)
- [ ] Executive summary (one-page, fully non-technical)
- [ ] Project team view (technical detail, per endpoint)
- [ ] Business view (SLA compliance, availability, business transactions)
- [ ] Cross-project comparison
- [ ] Export to PDF, Excel, CSV
- [ ] Scheduled email reports (daily, weekly, monthly)
- [ ] Custom date range filter
- [ ] Grafana embedded dashboards (real-time)
- [ ] Report sharing (public link, time-limited)

### 7.6 Security
- [ ] JWT-based authentication
- [ ] Role-based access control (Admin / SV Team / Project Owner / Viewer)
- [ ] Per-project API keys for consuming teams
- [ ] Full audit log (immutable)
- [ ] HTTPS everywhere (Nginx + SSL)
- [ ] AWS Secrets Manager for all credentials
- [ ] IP whitelist per project stub endpoint
- [ ] Token expiry and refresh
- [ ] SSO integration (SAML/OIDC — bank AD)

### 7.7 Developer & SV Team Experience
- [ ] Full REST API for everything (headless automation)
- [ ] Auto-generated Swagger docs for platform API
- [ ] CLI tool for power users
- [ ] GitLab CI YAML templates for projects to self-integrate
- [ ] Webhook notifications (deploy complete, health fail)
- [ ] Slack / Teams notification integration
- [ ] Postman collection for platform API

---

## 8. Architecture — Full Detail

### 8.1 High-Level Architecture
```
╔══════════════════════════════════════════════════════════════════════╗
║                     SELF-SERVICE PORTAL (React)                      ║
║                                                                      ║
║  [Upload Spec] [Manage Projects] [Live Dashboard] [Reports] [Admin] ║
╚═══════════════════════════╦══════════════════════════════════════════╝
                            ║ HTTPS
                            ▼
╔══════════════════════════════════════════════════════════════════════╗
║                    NGINX (Reverse Proxy + SSL)                       ║
╚═══════════════════════════╦══════════════════════════════════════════╝
                            ║
                            ▼
╔══════════════════════════════════════════════════════════════════════╗
║                   PLATFORM API (FastAPI)                             ║
║                                                                      ║
║  ┌──────────────┐ ┌──────────────┐ ┌────────────┐ ┌─────────────┐  ║
║  │ Auth Service │ │Parser Service│ │ Generator  │ │  Deployer   │  ║
║  │ JWT + RBAC   │ │              │ │  Engine    │ │  Service    │  ║
║  │              │ │ OpenAPI      │ │            │ │             │  ║
║  │              │ │ WSDL         │ │ WireMock   │ │ Terraform   │  ║
║  │              │ │ Postman      │ │ mappings   │ │ Docker      │  ║
║  │              │ │ HAR          │ │ generator  │ │ ECR push    │  ║
║  │              │ │ Bruno        │ │            │ │ EC2 run     │  ║
║  │              │ │ Raw          │ │ Hoverfly   │ │             │  ║
║  │              │ │ AsyncAPI     │ │ config     │ │             │  ║
║  │              │ │ CSV/Excel    │ │ generator  │ │             │  ║
║  └──────────────┘ └──────────────┘ └────────────┘ └─────────────┘  ║
║                                                                      ║
║  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐  ║
║  │  Reporter    │ │   Project    │ │    Celery Job Queue        │  ║
║  │  Service     │ │   Manager   │ │    (Redis broker)          │  ║
║  │              │ │              │ │                            │  ║
║  │  Metrics     │ │  CRUD        │ │  parse_job                 │  ║
║  │  Dashboards  │ │  Versioning  │ │  generate_job              │  ║
║  │  PDF/Excel   │ │  Access ctrl │ │  deploy_job                │  ║
║  │  Email       │ │              │ │  report_job                │  ║
║  └──────────────┘ └──────────────┘ └────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════╝
          │              │              │
          ▼              ▼              ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │ PostgreSQL │ │   MinIO    │ │  InfluxDB  │
   │ (metadata) │ │  (files)   │ │ (metrics)  │
   └────────────┘ └────────────┘ └────────────┘
          │              │
          ▼              ▼
   ┌────────────┐ ┌────────────┐
   │   Redis    │ │ Prometheus │
   │ (queue+    │ │ (scraping) │
   │  cache)    │ │            │
   └────────────┘ └────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
  ╔═══════════════╗ ╔═══════════════╗ ╔═══════════════╗
  ║ EC2: Proj A   ║ ║ EC2: Proj B   ║ ║ EC2: Proj C   ║
  ║               ║ ║               ║ ║               ║
  ║  WireMock     ║ ║  WireMock     ║ ║  Microcks     ║
  ║  REST stubs   ║ ║  SOAP stubs   ║ ║  Kafka stubs  ║
  ║               ║ ║               ║ ║               ║
  ║  Prometheus   ║ ║  Prometheus   ║ ║  Prometheus   ║
  ║  exporter     ║ ║  exporter     ║ ║  exporter     ║
  ╚═══════════════╝ ╚═══════════════╝ ╚═══════════════╝
```

### 8.2 Database Schema (PostgreSQL)
```sql
-- Core tables

projects
  id, name, description, team, owner_id, environment,
  protocol, engine, tps_tier, ec2_instance_id, stub_url,
  api_key, status, created_at, updated_at

stubs
  id, project_id, name, method, path, request_matcher,
  response_body, response_headers, status_code, delay_ms,
  is_dynamic, template, scenario, version, created_by, created_at

deployments
  id, project_id, version, ec2_instance_id, docker_image,
  status, deployed_by, deployed_at, rolled_back_at

users
  id, email, name, role, team, created_at, last_login

audit_log
  id, user_id, action, resource_type, resource_id,
  details, ip_address, timestamp

metrics_summary (daily rollup from InfluxDB)
  id, project_id, stub_id, date, total_requests,
  peak_tps, avg_latency_ms, p99_latency_ms, error_count
```

### 8.3 File Storage Structure (MinIO)
```
sv-platform/
├── uploads/
│   ├── {project_id}/
│   │   ├── original/          (user uploaded files)
│   │   └── parsed/            (parsed JSON intermediate)
├── projects/
│   ├── {project_id}/
│   │   ├── mappings/          (WireMock JSON stub files)
│   │   ├── __files/           (response body files)
│   │   ├── extensions/        (custom transformer JARs)
│   │   └── docker/            (Dockerfile + docker-compose)
└── reports/
    ├── {project_id}/
    │   └── {date}/            (generated PDF/Excel reports)
```

---

## 9. Dynamic Response Scenarios

### Scenario 1 — Plain Vanilla (60% of projects)
```
Input:
  POST /api/accounts/balance
  Headers: Content-Type: application/json, Authorization: Bearer xxx
  Body: {"accountId": "12345"}

Expected Response:
  {"accountId": "12345", "balance": 5000.00, "currency": "GBP"}

Generated WireMock mapping:
{
  "request": {
    "method": "POST",
    "url": "/api/accounts/balance",
    "headers": {"Content-Type": {"equalTo": "application/json"}},
    "bodyPatterns": [{"equalToJson": {"accountId": "12345"}}]
  },
  "response": {
    "status": 200,
    "jsonBody": {"accountId": "12345", "balance": 5000.00, "currency": "GBP"},
    "headers": {"Content-Type": "application/json"}
  }
}
```

### Scenario 2 — Dynamic Data Generation (20% of projects)
```
Client rule: "Account number must be 10 random digits, 
              sortCode 6 digits, referenceId 8 alphanumeric"

Generated WireMock mapping (Handlebars):
{
  "response": {
    "status": 200,
    "body": "{
      \"accountNumber\": \"{{randomValue length=10 type='NUMERIC'}}\",
      \"sortCode\": \"{{randomValue length=6 type='NUMERIC'}}\",
      \"referenceId\": \"{{randomValue length=8 type='ALPHANUMERIC'}}\",
      \"createdAt\": \"{{now format='yyyy-MM-dd'T'HH:mm:ss'}}\",
      \"currency\": \"GBP\"
    }",
    "transformers": ["response-template"]
  }
}
```

### Scenario 3 — Echo Request Fields in Response
```
Client rule: "Return the same accountId, fromAccount, toAccount 
              that was sent in the request"

Generated WireMock mapping:
{
  "response": {
    "body": "{
      \"transactionId\": \"TXN-{{randomValue length=12 type='ALPHANUMERIC'}}\",
      \"fromAccount\": \"{{jsonPath request.body '$.fromAccount'}}\",
      \"toAccount\": \"{{jsonPath request.body '$.toAccount'}}\",
      \"amount\": {{jsonPath request.body '$.amount'}},
      \"status\": \"SUCCESS\",
      \"timestamp\": \"{{now format='yyyy-MM-dd'T'HH:mm:ss'}}\"
    }",
    "transformers": ["response-template"]
  }
}
```

### Scenario 4 — Conditional Logic (IF/ELSE)
```
Client rule: "If amount > 10000, return status PENDING_APPROVAL.
              If amount <= 10000, return status SUCCESS."

Implementation: WireMock priority mappings (two stubs, priority order)

Mapping 1 (priority 1 — checked first):
  matches: amount > 10000 (via custom matcher or scenario)
  returns: {"status": "PENDING_APPROVAL"}

Mapping 2 (priority 2 — fallback):
  matches: any transfer request
  returns: {"status": "SUCCESS"}

For complex logic → Python transformer layer sits in front of WireMock
```

### Scenario 5 — Stateful Multi-Step
```
Client scenario: Login → Get Account → Transfer → Verify Balance

Step 1: POST /login
  → Returns: {"token": "abc123", "sessionId": "xyz"}
  → Sets WireMock scenario state: LOGGED_IN

Step 2: GET /account (with token)
  → Required state: LOGGED_IN
  → Returns: {"balance": 5000.00}
  → Sets state: ACCOUNT_VIEWED

Step 3: POST /transfer
  → Required state: ACCOUNT_VIEWED
  → Returns: {"transactionId": "TXN-xxx", "status": "SUCCESS"}
  → Sets state: TRANSFER_COMPLETE

Step 4: GET /account
  → Required state: TRANSFER_COMPLETE
  → Returns: {"balance": 4500.00}  ← updated balance
```

### Scenario 6 — Data-Driven from File
```
Client provides: customers.csv with 1000 rows
  customerId, name, accountNumber, balance, sortCode

Platform:
  Loads CSV into lookup table
  When GET /customer/{id} received:
    Looks up row where customerId = {id}
    Returns that row's data as JSON response

Result: 1000 different realistic customer responses
```

### Scenario 7 — SOAP / XML
```
Client provides: WSDL file

Platform generates:
  WireMock stub with:
    - SOAPAction header matching
    - XPath request body matching
    - Full SOAP envelope response wrapping
    
  Example:
  <soap:Envelope>
    <soap:Body>
      <GetAccountResponse>
        <AccountNumber>12345678</AccountNumber>
        <Balance>5000.00</Balance>
      </GetAccountResponse>
    </soap:Body>
  </soap:Envelope>
```

---

## 10. TPS Strategy & EC2 Sizing

### Engine Selection by TPS
| TPS Requirement | Engine | EC2 Size | Monthly Cost (est.) |
|----------------|--------|----------|---------------------|
| < 1,000 | WireMock | t3.medium | ~$30 |
| 1,000 – 5,000 | WireMock | c6i.xlarge | ~$120 |
| 5,000 – 15,000 | Hoverfly | c6i.2xlarge | ~$240 |
| 15,000+ | Hoverfly + Nginx LB | c6i.4xlarge | ~$480 |
| 20,000+ | Multiple Hoverfly | c6i.4xlarge x2 | ~$960 |

### WireMock JVM Tuning (for high TPS)
```bash
java -jar wiremock-standalone.jar \
  --port 8080 \
  --async-response-enabled true \
  --async-response-threads 50 \
  -Xmx8g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -XX:+ParallelRefProcEnabled
```

### Hoverfly Configuration (for 15K+ TPS)
```yaml
# hoverfly.yaml
mode: simulate
proxy:
  port: 8080
responses:
  cache: true          # cache compiled matchers
  cacheSize: 10000     # in-memory cache size
server:
  threads: 200         # goroutine pool
```

---

## 11. Reporting Requirements

### Audience Matrix
| Report Type | Audience | Content | Frequency |
|-------------|----------|---------|-----------|
| Executive Summary | CTO / Head of Testing | Uptime, cost saving, stubs count, availability | Monthly |
| Business Dashboard | Business Analysts, PMs | SLA compliance, business transaction counts | Weekly |
| Project Report | Project Teams | Per-endpoint TPS, latency, errors | Daily |
| Operational | SV Team, DevOps | EC2 health, deploy status, error alerts | Real-time |
| Audit Report | Compliance, Security | Who did what, when, all changes | On demand |

### Key Metrics to Capture
```
Per Stub:
  - Total requests served (all time)
  - Requests per hour / day
  - Average response time (ms)
  - P50, P90, P95, P99 latency
  - Error rate (%)
  - Last request timestamp

Per Project:
  - Current TPS (live)
  - Peak TPS (with timestamp)
  - Total stubs count
  - Active stubs vs inactive
  - Uptime percentage
  - Deploy count and history
  - EC2 cost (instance hours × rate)

Platform Wide:
  - Total projects
  - Total stubs generated
  - Total requests processed
  - License cost saved (vs CA/IBM equivalent)
  - SV team hours saved (estimated)
  - Most used endpoints
  - Most active projects
```

### Report Formats
- **Live Dashboard** — React + ECharts (real-time WebSocket updates)
- **Grafana Embedded** — Professional time-series TPS graphs
- **PDF Export** — Management-ready formatted report
- **Excel Export** — Raw data for further analysis
- **Email** — Scheduled HTML email with summary + PDF attachment

---

## 12. Phased Implementation Plan

### Phase 1 — Core Generator (Weeks 1–8)
**Goal: Auto-generate plain vanilla REST stubs from any input**

Deliverables:
- Python parser for: OpenAPI, Postman, HAR, Raw request-response
- WireMock JSON mapping generator
- CLI tool: `sv-gen --input spec.yaml --output ./project`
- Docker packaging of generated project
- Local run + test

**Impact: Automates 60% of current manual SV work**

---

### Phase 2 — Dynamic + SOAP (Weeks 9–16)
**Goal: Cover all 85% of project types**

Deliverables:
- Handlebars template generator (dynamic data)
- Faker integration for data rules
- Request field extraction (JSONPath / XPath)
- WSDL parser + SOAP stub generator
- Conditional response logic
- Stateful scenario generation
- Multiple XML document support

**Impact: 85% of SV work automated**

---

### Phase 3 — Platform Backend (Weeks 17–24)
**Goal: REST API + database + job queue**

Deliverables:
- FastAPI application (full CRUD)
- PostgreSQL schema + migrations
- Redis + Celery job queue
- MinIO file storage integration
- JWT auth + RBAC
- Audit logging
- Project versioning

**Impact: SV team uses API, no manual file management**

---

### Phase 4 — Auto Deploy (Weeks 25–32)
**Goal: One-click deploy to EC2**

Deliverables:
- Terraform modules for EC2 provisioning
- ECR push pipeline
- GitLab CI YAML templates
- Health check + retry
- Rollback mechanism
- Auto-generated firewall documentation

**Impact: Zero manual deployment, zero manual firewall docs**

---

### Phase 5 — Metrics + Reporting (Weeks 33–38)
**Goal: Management-grade reporting**

Deliverables:
- Prometheus scraping from WireMock containers
- InfluxDB ingestion pipeline
- Report API (FastAPI)
- PDF and Excel export
- Email scheduler
- Grafana dashboards

**Impact: Full management visibility**

---

### Phase 6 — Self-Service Portal (Weeks 39–48)
**Goal: Project teams self-serve without SV team**

Deliverables:
- React portal (full feature)
- Upload → generate → deploy → monitor (end to end in UI)
- Role-based views (exec / team / admin)
- Live TPS dashboard
- Stub editor

**Impact: SV team no longer a bottleneck. Any team self-serves.**

---

### Phase 7 — Kafka + AI (Weeks 49–56)
**Goal: Complete protocol coverage + AI assistance**

Deliverables:
- Microcks integration
- Kafka stub generation from AsyncAPI
- AI-assisted stub generation from plain English description
- Smart data pattern detection
- Anomaly detection in traffic

**Impact: Industry-leading. No competitor has this.**

---

## 13. Prompt Engineering — Implementation Prompts

> **How to use this section:**  
> Copy each prompt exactly when starting that implementation task with Claude.  
> The prompts are engineered to give you production-ready, extensible code — not throwaway examples.

---

### MASTER CONTEXT PROMPT
> Use this at the START of every new Claude conversation about this project.

```
I am building an open-source Service Virtualisation platform.
The platform auto-generates WireMock/Hoverfly/Microcks stubs from API specs and 
auto-deploys to AWS EC2 instances. It must support 15,000+ TPS.

Tech stack:
- Backend: Python 3.11, FastAPI, Celery, Redis, PostgreSQL, MinIO, InfluxDB
- Stub engines: WireMock (REST/SOAP), Hoverfly (high TPS), Microcks (Kafka)
- Frontend: React 18, TypeScript, Apache ECharts, Tailwind CSS
- Infra: Docker, Terraform, AWS EC2, ECR, GitLab CI
- Auth: JWT + RBAC (Admin, SV Team, Project Owner, Viewer roles)

Usage breakdown:
- 60% plain vanilla REST (static request/response)
- 20% dynamic REST (generated account numbers, dates, IDs)
- 15% REST with conditional logic
- 5% SOAP/XML
- Some Kafka

Design principles:
- Every module must be extensible (new protocols can be added as plugins)
- Production-grade error handling (not happy-path only)
- Full audit logging on all operations
- Clean separation: parser → generator → packager → deployer → reporter
- All code must have docstrings and type hints
- Write tests alongside each module

Current phase: [INSERT PHASE HERE]
Current task: [INSERT TASK HERE]
```

---

## 14. Prompt Library — Phase by Phase

### PHASE 1 PROMPTS

#### P1.1 — Project Structure
```
Using the master context above (Phase 1), create the complete Python project 
structure for the SV platform generator engine.

Requirements:
- Use Python 3.11 with pyproject.toml (not requirements.txt)
- FastAPI app structure (routers, services, models, schemas)
- Celery worker structure
- Clean separation of concerns
- Docker and docker-compose for local development
- Include .env.example with all required variables
- Include Makefile with: install, run, test, lint, docker-up commands

Show the complete directory tree and create each key file with its 
initial content (not placeholder comments — actual working skeleton code).
```

#### P1.2 — Input Type Auto-Detector
```
Using the master context (Phase 1), build the input type auto-detector service.

File: app/services/parser/detector.py

Requirements:
- Accept a file (bytes) and optional filename
- Detect type: OpenAPI3, Swagger2, Postman, HAR, WSDL, Bruno, AsyncAPI, Raw, CSV
- Detection logic: try JSON parse, check keys; try YAML parse, check structure; 
  check file extension as hint only (not reliable)
- Return: InputType enum + confidence score + detected endpoints count (preview)
- Handle malformed files gracefully with descriptive errors
- Include type hints, docstrings, and pytest tests

Detection rules to implement:
- OpenAPI3: JSON/YAML with "openapi": "3.x.x" key
- Swagger2: JSON/YAML with "swagger": "2.0" key  
- Postman: JSON with "info._postman_id" key
- HAR: JSON with "log.version" and "log.entries" keys
- WSDL: XML with wsdl:definitions root element
- Bruno: text file with "meta {" blocks
- AsyncAPI: JSON/YAML with "asyncapi" key
- Raw: plain text with HTTP method at start (GET /path, POST /path etc.)
- CSV: comma-separated with header row
```

#### P1.3 — OpenAPI Parser
```
Using the master context (Phase 1), build the OpenAPI 3.x parser.

File: app/services/parser/openapi_parser.py

Input: OpenAPI 3.x YAML or JSON (as dict after loading)
Output: List[ParsedEndpoint] where ParsedEndpoint contains:
  - method: str (GET, POST, PUT, DELETE, PATCH)
  - path: str (/api/accounts/{accountId})
  - path_parameters: List[Parameter]
  - query_parameters: List[Parameter]
  - request_headers: Dict[str, str]
  - request_body_schema: Optional[dict]
  - request_body_example: Optional[dict]
  - response_status_code: int (use first 2xx response found)
  - response_body_schema: Optional[dict]
  - response_body_example: Optional[dict]
  - response_headers: Dict[str, str]
  - description: Optional[str]
  - tags: List[str]

Requirements:
- Handle both YAML and JSON input (caller loads, parser receives dict)
- Resolve $ref references (inline them — do not leave $ref in output)
- Extract examples from: example field, examples field (first one), schema default
- Generate synthetic example if no example provided (from schema types)
- Handle allOf, oneOf, anyOf schemas gracefully
- Handle missing optional fields without crashing
- Full type hints and docstrings
- pytest tests with real OpenAPI fixtures (banking API examples)
```

#### P1.4 — Postman Parser
```
Using the master context (Phase 1), build the Postman Collection v2.1 parser.

File: app/services/parser/postman_parser.py

Input: Postman Collection JSON (as dict)
Output: Same List[ParsedEndpoint] format as OpenAPI parser

Requirements:
- Handle nested folders (recursive item parsing)
- Extract: method, URL (full), headers, body (raw JSON, form-data, urlencoded)
- Handle Postman variables: {{baseUrl}}, {{token}} — replace with placeholders
- Extract pre-request scripts for dynamic variable hints
- Extract test scripts for expected response hints
- Parse raw body as JSON where possible; keep as string otherwise
- Handle disabled headers (skip them)
- Handle auth at collection level and request level
- Full type hints, docstrings, tests with real Postman collection fixture
```

#### P1.5 — WireMock Mapping Generator
```
Using the master context (Phase 1), build the WireMock mapping generator.

File: app/services/generator/wiremock_generator.py

Input: List[ParsedEndpoint] + GeneratorConfig (stub_type: static|dynamic|stateful)
Output: List[WireMockMapping] (each is a dict matching WireMock JSON format)

Requirements:
- Generate valid WireMock 3.x JSON mappings
- For static stubs:
    - urlPattern matching (handle path params as regex)
    - method matching
    - header matching (Content-Type at minimum)
    - exact response body from parsed example
    - correct status code
    - response headers
- For dynamic stubs:
    - Use Handlebars response templating
    - Add "transformers": ["response-template"]
    - Replace: UUIDs → {{randomValue type='UUID'}}
    - Replace: account numbers (8-12 digits) → {{randomValue length=10 type='NUMERIC'}}
    - Replace: dates → {{now format='yyyy-MM-dd'}}
    - Replace: timestamps → {{now format='yyyy-MM-dd'T'HH:mm:ss'}}
    - Echo path params back: {{request.pathSegments.[1]}}
    - Echo body fields: {{jsonPath request.body '$.fieldName'}}
- Add metadata: stub name, description, created timestamp as WireMock metadata
- Generate unique stub UUID for each mapping
- Full type hints, docstrings, tests
- Include test that takes a real OpenAPI spec end-to-end and validates output JSON
```

#### P1.6 — Project Packager
```
Using the master context (Phase 1), build the project packager.

File: app/services/packager/project_packager.py

Input: 
  - project_name: str
  - List[WireMockMapping]
  - PackagerConfig (engine: wiremock|hoverfly, tps_tier: low|medium|high)

Output: 
  - Project directory structure (on disk or as ZIP bytes)
  - docker-compose.yml
  - Dockerfile
  - prometheus.yml (for metrics scraping)
  - start.sh

Directory structure to generate:
  {project_name}/
  ├── mappings/           ← WireMock JSON stub files (one per endpoint)
  ├── __files/            ← Response body files (for large responses)
  ├── extensions/         ← Custom transformer JARs (empty initially)
  ├── Dockerfile
  ├── docker-compose.yml
  ├── prometheus.yml
  ├── config.json         ← Platform metadata (project_id, version, created_at)
  └── start.sh

Dockerfile must:
  - Use wiremock/wiremock:3.x as base
  - Copy mappings and __files
  - Set JVM flags for high TPS (-Xmx4g -XX:+UseG1GC)
  - Expose 8080 and 9090 (prometheus)
  - Include health check

docker-compose.yml must:
  - Start WireMock
  - Start prometheus exporter sidecar
  - Define volumes for hot-reload of mappings
  - Include resource limits

Return: bytes (ZIP) of the complete project directory
Full type hints, docstrings, and tests.
```

---

### PHASE 2 PROMPTS

#### P2.1 — Dynamic Data Rules Engine
```
Using the master context (Phase 2), build the dynamic data rules engine.

File: app/services/generator/data_rules_engine.py

This engine takes a JSON schema or example and applies data generation rules.

Requirements:
- Detect field semantics from field name patterns:
    accountNumber, accountNo, account_number → NUMERIC 10 digits
    sortCode, sort_code → NUMERIC 6 digits  
    iban → GB format IBAN
    bic, swift → 8-11 char alphanumeric
    email → valid email format
    phone, phoneNumber → UK format phone
    name, firstName, lastName → realistic name (Faker)
    address → UK address
    postcode → UK postcode format
    date, createdAt, updatedAt → ISO date
    timestamp → ISO timestamp  
    uuid, id, referenceId → UUID4
    amount, balance, value → decimal 2dp
    currency → 3-char ISO currency code
    status → from enum values if provided
    description → short sentence (Faker)

- Allow client to override rules via config:
    {"fieldName": "accountNumber", "rule": "NUMERIC", "length": 10}

- Output Handlebars template strings for WireMock
- Output Python Faker calls for our own data generator layer
- Full type hints, docstrings, tests with banking field name examples
```

#### P2.2 — WSDL / SOAP Parser
```
Using the master context (Phase 2), build the WSDL parser for SOAP stubs.

File: app/services/parser/wsdl_parser.py

Input: WSDL file content (bytes or string)
Output: List[ParsedSoapOperation] containing:
  - operation_name: str
  - soap_action: str
  - endpoint_url: str
  - input_message_schema: dict (XSD schema as dict)
  - input_example: str (XML string)
  - output_message_schema: dict
  - output_example: str (XML string)
  - soap_version: str (1.1 or 1.2)

Requirements:
- Parse WSDL 1.1 and 2.0
- Resolve XSD type definitions (handle included schemas)
- Generate XML request examples from input schema
- Generate XML response examples from output schema
- Wrap in correct SOAP envelope (1.1 vs 1.2)
- Handle namespaces correctly
- Full type hints, docstrings
- Tests with a real banking WSDL example (account service)

Then build the SOAP WireMock mapping generator:
File: app/services/generator/soap_generator.py
- Generate WireMock mappings with:
  - SOAPAction header matching
  - bodyPatterns with XPath matching on operation name
  - Full SOAP envelope in response body
  - Content-Type: text/xml
```

#### P2.3 — Stateful Scenario Generator
```
Using the master context (Phase 2), build the stateful scenario generator.

File: app/services/generator/scenario_generator.py

This handles multi-step API sequences (e.g., login → getAccount → transfer → verify)

Input: List[ScenarioStep] where each step has:
  - step_number: int
  - endpoint: ParsedEndpoint
  - required_state: Optional[str]  (state that must exist before this step)
  - next_state: str                (state to set after this step)
  - response_modifications: dict  (how response differs from base)

Output: List[WireMockMapping] with correct WireMock Scenario configuration

Requirements:
- Generate WireMock "scenarioName", "requiredScenarioState", "newScenarioState"
- First step uses "Started" as requiredScenarioState
- Each mapping linked to same scenario name
- Handle state-specific response bodies
- Support scenario reset endpoint (DELETE /admin/scenarios → resets all)
- Full type hints, docstrings, tests with login→account→transfer example
```

---

### PHASE 3 PROMPTS

#### P3.1 — FastAPI Application Setup
```
Using the master context (Phase 3), build the complete FastAPI application.

Requirements:
- Main app with: CORS, JWT middleware, request logging, error handlers
- Router structure:
    /auth          → login, refresh, logout
    /projects      → CRUD for projects
    /stubs         → CRUD for stubs within a project
    /upload        → file upload endpoint (multipart)
    /generate      → trigger generation job
    /deploy        → trigger deploy job
    /metrics       → metrics query API
    /reports       → report generation
    /admin         → admin operations
    /health        → health check

- Each router in its own file: app/routers/{name}.py
- Services in: app/services/{name}_service.py
- Models in: app/models/{name}.py (SQLAlchemy)
- Schemas in: app/schemas/{name}.py (Pydantic v2)
- Dependencies in: app/dependencies.py (auth, db session, etc.)

- Full JWT auth with refresh tokens
- RBAC decorator: @require_role(["admin", "sv_team"])
- Request/response logging with correlation ID
- Global exception handler returning RFC 7807 Problem JSON
- OpenAPI docs at /docs (Swagger UI)
- Pydantic settings from .env file

Generate all files with full working code, not placeholders.
```

#### P3.2 — Celery Job Queue
```
Using the master context (Phase 3), build the Celery job queue setup.

Requirements:
File: app/workers/celery_app.py        ← Celery app config
File: app/workers/tasks/parse_task.py  ← Parse uploaded file
File: app/workers/tasks/generate_task.py ← Generate stubs
File: app/workers/tasks/deploy_task.py   ← Deploy to EC2
File: app/workers/tasks/report_task.py   ← Generate report

Each task must:
- Accept job_id and update job status in PostgreSQL
- Log start, progress, completion with timestamps
- Handle errors: retry up to 3 times with exponential backoff
- Send webhook notification on completion (if configured)
- Return result stored in DB (not just Celery result backend)

Job status flow:
  QUEUED → RUNNING → SUCCESS / FAILED / RETRYING

DB table: jobs
  id, type, status, project_id, input_params, result,
  error_message, created_at, started_at, completed_at, retry_count

Include docker-compose service for: celery worker + celery beat (scheduler)
Full type hints, docstrings, tests.
```

---

### PHASE 4 PROMPTS

#### P4.1 — Terraform EC2 Module
```
Using the master context (Phase 4), build the Terraform module for EC2 provisioning.

Directory: terraform/modules/sv-ec2-instance/

Files needed:
  main.tf          ← EC2 instance, security group, IAM role
  variables.tf     ← project_name, instance_type, ami_id, vpc_id, subnet_id, 
                      ecr_image_uri, stub_port, region, tags
  outputs.tf       ← instance_id, public_ip, private_ip, stub_url
  user_data.sh     ← install Docker, pull ECR image, run container, 
                      install Prometheus node exporter

Security group must:
  - Allow inbound on stub_port (8080) from specified CIDR (configurable)
  - Allow inbound on 9090 (Prometheus) from platform monitoring CIDR only
  - Allow outbound to ECR (HTTPS)
  - Allow SSH from bastion only (not 0.0.0.0/0)

IAM role must:
  - ECR pull permissions
  - CloudWatch logs permissions
  - Secrets Manager read (for platform API key)

user_data.sh must:
  - Wait for network
  - Install Docker CE
  - Authenticate to ECR (aws ecr get-login-password)
  - Pull specified image
  - Run container with:
      - Port mapping 8080:8080
      - Prometheus port 9090:9090
      - Restart policy: always
      - Resource limits: memory, CPU
  - Install and configure Prometheus node exporter

Also create: terraform/environments/dev/main.tf and prod/main.tf

Full production-ready Terraform with:
  - Remote state (S3 backend)
  - State locking (DynamoDB)
  - Proper tagging strategy
```

#### P4.2 — Python Deploy Service
```
Using the master context (Phase 4), build the Python deployer service.

File: app/services/deployer/ec2_deployer.py

This service orchestrates:
  1. Build Docker image from packaged project
  2. Tag with ECR registry URI
  3. Push to ECR
  4. Run Terraform to provision/update EC2
  5. Wait for health check to pass
  6. Register stub URL in database
  7. Generate firewall documentation

Requirements:
- Use boto3 for AWS operations (ECR, EC2)
- Use subprocess to run Terraform (with timeout)
- Health check: poll http://{ec2_ip}:8080/__admin/health every 5s for up to 5 min
- Firewall doc: generate text file showing:
    Source: (consuming team's server — from project config)
    Destination: {ec2_ip}:8080
    Protocol: TCP/HTTPS
    Direction: Inbound to stub server
- Store all deployment metadata in PostgreSQL deployments table
- Full type hints, docstrings
- Tests with mocked AWS and Terraform calls
```

---

### PHASE 5 PROMPTS

#### P5.1 — Prometheus + InfluxDB Metrics Pipeline
```
Using the master context (Phase 5), build the metrics collection pipeline.

WireMock exposes Prometheus metrics at: http://{ec2_ip}:9090/metrics

Key WireMock metrics to collect:
  wiremock_requests_total (counter, labels: project_id, method, path, status)
  wiremock_request_duration_seconds (histogram, labels: project_id, method, path)
  wiremock_stubs_total (gauge, labels: project_id)
  wiremock_scenarios_total (gauge, labels: project_id)

Build:
File: app/services/metrics/prometheus_scraper.py
  - Scrape all registered EC2 instances on schedule (every 30s via Celery beat)
  - Parse Prometheus text format
  - Write to InfluxDB with tags: project_id, stub_path, method

File: app/services/metrics/influx_writer.py
  - Write time-series metrics to InfluxDB
  - Data retention: 90 days raw, 2 years aggregated
  - Aggregation: compute hourly P50/P90/P99 from raw histogram data

File: app/services/metrics/metrics_query_service.py
  - Query InfluxDB for report data
  - Methods:
      get_project_tps(project_id, start, end, resolution)
      get_stub_request_count(project_id, stub_path, start, end)
      get_latency_percentiles(project_id, stub_path, start, end)
      get_error_rate(project_id, start, end)
      get_platform_summary(start, end)

Full type hints, docstrings, tests with mocked InfluxDB.
```

#### P5.2 — Report Generator
```
Using the master context (Phase 5), build the report generator.

File: app/services/reporter/report_generator.py

Report types to support:
  1. EXECUTIVE_SUMMARY — one page, non-technical, for CTO/management
  2. PROJECT_REPORT — per project, technical detail, for project teams
  3. PLATFORM_AUDIT — all actions, for compliance/security
  4. COST_REPORT — EC2 usage + cost saving vs CA/IBM, for finance

For each report type, generate:
  - PDF (using ReportLab or WeasyPrint)
  - Excel (using openpyxl)
  - JSON (for API consumers)

Executive Summary PDF must include:
  - Bank logo placeholder
  - Period covered
  - Total stubs: {n} across {m} projects
  - Total requests served: {n} million
  - Platform availability: 99.x%
  - Estimated license saving: £xxx,xxx
  - Top 5 most used projects (bar chart)
  - Monthly request trend (line chart)

Project Report PDF must include:
  - Project name, team, environment
  - Stub inventory table
  - TPS chart (hourly, last 30 days)
  - Latency percentile table (per endpoint)
  - Error rate chart
  - Deployment history

Full type hints, docstrings.
Include sample output generation in tests.
```

---

### PHASE 6 PROMPTS

#### P6.1 — React Portal Structure
```
Using the master context (Phase 6), build the React portal project structure.

Tech: React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Apache ECharts,
      React Router v6, Zustand (state), React Hook Form, Zod (validation)

Pages to create:
  /login                    → Login page
  /dashboard                → Platform overview (stats, recent activity)
  /projects                 → Project list
  /projects/new             → Create project + upload spec
  /projects/{id}            → Project detail (stubs, metrics, deployments)
  /projects/{id}/stubs      → Stub list + editor
  /projects/{id}/deploy     → Deploy page (status, history, rollback)
  /projects/{id}/metrics    → Live TPS + latency charts
  /reports                  → Report dashboard
  /reports/executive        → Executive summary view
  /reports/projects         → Per-project reports
  /admin                    → Admin panel (users, roles, system health)

Requirements:
- Full TypeScript strict mode
- API client: typed fetch wrapper using TanStack Query
- Auth: JWT stored in httpOnly cookie (not localStorage)
- Role-based rendering (show/hide menu items by role)
- Real-time TPS: WebSocket connection to platform API
- Responsive (desktop + tablet)
- Dark mode support (Tailwind dark:)
- Error boundaries on all pages
- Loading skeletons (not spinners)

Generate: complete project scaffold with all pages as working components
(not placeholder text — actual working UI with real API calls)
```

#### P6.2 — Live TPS Dashboard Component
```
Using the master context (Phase 6), build the live TPS dashboard React component.

File: src/components/dashboard/LiveTpsDashboard.tsx

Requirements:
- WebSocket connection to: ws://{platform}/ws/metrics/{project_id}
- Real-time line chart using Apache ECharts
- Shows: current TPS, peak TPS, P95 latency, error rate
- Chart updates every second (sliding 60-second window)
- Colour coding: green (< 80% capacity), amber (80–95%), red (> 95%)
- Metric cards: Current TPS | Peak TPS | P95 Latency | Error Rate | Uptime
- Historical toggle: switch between live (60s) and historical (1h/24h/7d/30d)
- Historical loads from REST API (InfluxDB query)
- Export chart as PNG
- Responsive layout
- TypeScript strict, no any types
- Include Storybook story
```

---

### PHASE 7 PROMPTS

#### P7.1 — AI-Assisted Stub Generation
```
Using the master context (Phase 7), build the AI-assisted stub generation feature.

File: app/services/generator/ai_stub_generator.py

This feature allows users to describe an API in plain English and get stubs generated.

Example user input:
  "I need a stub for a UK banking payment API. 
   POST /payments/domestic with a payment amount and account details.
   Return a transaction ID and status. If amount > 50000, return PENDING."

Process:
  1. Send user description to LLM (Anthropic Claude API)
  2. LLM generates: OpenAPI spec fragment (JSON)
  3. Pass to standard OpenAPI parser
  4. Generate WireMock mappings as normal
  5. Return stubs to user for review before save

LLM prompt engineering:
  - System: You are an API specification expert. Generate OpenAPI 3.0 JSON only.
             No explanations. No markdown. Pure JSON.
  - Include: banking context, UK-specific data formats
  - Validate: output is valid OpenAPI before passing downstream

Also build: smart data pattern detector
File: app/services/generator/pattern_detector.py
  - Analyse existing stub responses in a project
  - Detect: field name patterns, value formats, data ranges
  - Suggest: data generation rules to apply automatically
  - Useful when user uploads raw request/response pairs

Full type hints, docstrings, tests with mocked LLM calls.
```

---

## 15. What to Ask Claude at Each Stage

### Before Starting Each Phase
```
"I am starting Phase {N} of the SV platform. 
Here is the master context: [paste master context prompt]
Here is what Phase {N} needs to deliver: [paste phase description]
Before writing any code, review the design and tell me:
1. Any technical risks I should know about
2. Any dependencies I need to set up first  
3. Any design decisions I need to make
4. Suggested order of implementation within this phase"
```

### When You Hit a Bug
```
"In the SV platform (master context above), I have this error:
[paste error + stack trace]

The code that caused it:
[paste relevant code]

Context: This is in the {module name} which does {what it does}.
What is the root cause and what is the correct fix?"
```

### When You Need to Test Something
```
"In the SV platform (master context), write pytest tests for:
File: {file path}
Function/class: {name}

Test scenarios to cover:
1. Happy path with real banking API example
2. Edge case: {describe edge case}
3. Error case: {describe error}
4. Performance: should complete in < {n}ms for {size} input

Use fixtures, not hardcoded values.
Mock all external services (AWS, WireMock, PostgreSQL).
Use testcontainers for integration tests that need real DB."
```

### When Adding a New Input Type
```
"In the SV platform (master context), I need to add support for 
a new input type: {input type name}.

Format description: {describe the format}
Example file: {paste example or describe it}

Following the same pattern as app/services/parser/openapi_parser.py,
create app/services/parser/{name}_parser.py that:
1. Parses this format
2. Returns List[ParsedEndpoint] (same output as all other parsers)
3. Handles all edge cases
4. Has full tests"
```

### When Adding a New Protocol
```
"In the SV platform (master context), I need to add support for
a new stub engine/protocol: {protocol name}

Requirements:
- Input: {what the user provides}
- Engine: {WireMock / Hoverfly / Microcks / other}
- Deployment: {any special EC2/Docker considerations}

Following the plugin pattern established in app/services/generator/,
create the generator, packager, and deployer extensions for this protocol.
The main platform code should NOT change — only new plugin files added."
```

---

## 16. Glossary — SV Concepts for Beginners

| Term | Simple Explanation |
|------|-------------------|
| **Stub** | A fake API endpoint that pretends to be the real one |
| **Virtualisation** | Running a fake version of a service so you don't need the real one |
| **Mapping** | The rule that says "when request X comes in, send back response Y" |
| **Static stub** | Always returns the exact same response |
| **Dynamic stub** | Returns a different response each time (random data, echoed values) |
| **Stateful stub** | Remembers previous requests and changes behaviour (login → session) |
| **Handlebars** | A templating language WireMock uses for dynamic responses `{{variable}}` |
| **Scenario** | A named sequence of states a stub can be in |
| **Transformer** | A plugin that modifies the response before sending (e.g. Handlebars template engine) |
| **WireMock** | The open-source stub server we use for REST and SOAP |
| **Hoverfly** | A high-performance stub server (Go-based) for 15K+ TPS |
| **Microcks** | An open-source stub server for Kafka, GraphQL, gRPC |
| **HAR file** | Browser traffic recording (HTTP Archive) — contains real requests/responses |
| **WSDL** | Web Service Description Language — the "spec" for SOAP APIs |
| **XPath** | A query language for XML (like JSONPath but for XML) |
| **JSONPath** | A query language for JSON (e.g. `$.accountId` extracts accountId field) |
| **TPS** | Transactions Per Second — how many requests per second the stub can handle |
| **P95 latency** | 95% of requests respond faster than this time (e.g. P95 = 50ms) |
| **ECR** | AWS Elastic Container Registry — stores Docker images |
| **Terraform** | Tool to create AWS infrastructure by writing code |
| **Celery** | Python task queue — runs jobs in the background (generate, deploy) |
| **InfluxDB** | Database designed for time-series data (TPS over time, latency over time) |
| **Prometheus** | Collects metrics from running services (scrapes WireMock every 30s) |
| **Grafana** | Visualises metrics from Prometheus/InfluxDB as dashboards |

---

## Quick Reference — Key Commands

### Run Platform Locally
```bash
make docker-up          # Start PostgreSQL, Redis, MinIO, InfluxDB
make run                # Start FastAPI + Celery worker
make frontend           # Start React dev server
```

### Generate Stubs (CLI)
```bash
sv-gen --input api-spec.yaml --output ./my-project --type openapi
sv-gen --input collection.json --output ./my-project --type postman
sv-gen --input service.wsdl --output ./my-project --type wsdl
sv-gen --input requests.csv --output ./my-project --type csv
```

### Deploy to EC2
```bash
sv-deploy --project my-project --env test --tps 5000
sv-deploy --project my-project --env perf --tps 15000
```

### Run Tests
```bash
make test               # All tests
make test-unit          # Unit tests only
make test-integration   # Integration tests (needs Docker)
make test-tps           # TPS validation (needs running EC2)
```

---

*Document generated from full requirements discovery session.*  
*Keep this document updated as the project evolves.*  
*Version this document in GitLab alongside the codebase.*
