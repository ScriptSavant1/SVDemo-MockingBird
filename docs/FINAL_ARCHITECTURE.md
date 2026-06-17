# Mockingbird — Final Confirmed Architecture

**Version:** 2.0  
**Last Updated:** 2026-06-14  
**Status:** Architecture finalised — ready for Phase 1 implementation

---

## 1. Complete System Picture (Simple View)

```
                           NATWEST USERS (all browsers)
                                       │
                                       │ HTTPS
                                       ▼
                    ┌──────────────────────────────────────┐
                    │    MOCKINGBIRD PORTAL                 │
                    │    (React website)                    │
                    │    https://mockingbird.natwest.com   │
                    │    served via AWS CloudFront + S3     │
                    └──────────────────┬───────────────────┘
                                       │ API calls
                                       ▼
                    ┌──────────────────────────────────────┐
                    │    MOCKINGBIRD BACKEND (AWS)          │
                    │                                      │
                    │  auth-service    project-service     │
                    │  ingestion-svc   parser-worker       │
                    │  generator-wrkr  deployer-worker     │
                    │  metrics-svc     reporter-service    │
                    │                                      │
                    │  All: Docker containers on ECS       │
                    │  Fargate (no EC2 to manage)          │
                    └──────────────────┬───────────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 │                     │                     │
                 ▼                     ▼                     ▼
         ┌─────────────┐      ┌────────────────┐    ┌────────────────┐
         │ PostgreSQL  │      │  HashiCorp     │    │  GitLab        │
         │ (RDS)       │      │  Vault         │    │  Container     │
         │ projects    │      │  (secrets)     │    │  Registry      │
         │ stubs       │      │                │    │  (Docker imgs) │
         │ users       │      │                │    │                │
         │ audit log   │      │                │    │                │
         └─────────────┘      └────────────────┘    └────────────────┘

                                       │ when user clicks Deploy
                                       ▼
              ┌────────────────────────────────────────────────────┐
              │          STUB SERVERS (per project, on demand)      │
              │                                                    │
              │   EC2: project-A  EC2: project-B  EC2: project-C  │
              │   Spring Boot     Spring Boot      Spring Boot     │
              │   + WireMock      + WireMock       + WireMock      │
              │   10,000+ TPS    10,000+ TPS       10,000+ TPS     │
              │                                                    │
              │   Spun up on deploy. Suspended when not needed.    │
              │   Stubs always kept in DB — redeploy anytime.      │
              └────────────────────────────────────────────────────┘
```

---

## 2. AWS Account Structure

```
┌────────────────── MOCKINGBIRD AWS ACCOUNT ─────────────────────────┐
│                                                                     │
│  Everything Mockingbird platform (ECS, RDS, S3, SQS, etc.)         │
│                                                                     │
│  ┌────── eu-west-2 (London) PRIMARY ──────────────────────────┐    │
│  │                                                            │    │
│  │  ECS Fargate cluster (all platform microservices)          │    │
│  │  RDS PostgreSQL (Multi-AZ, eu-west-2a + eu-west-2b)       │    │
│  │  ElastiCache Redis                                         │    │
│  │  S3 buckets (files, reports)                              │    │
│  │  SQS queues (parse, generate, deploy, report)             │    │
│  │  CloudWatch logs and alarms                               │    │
│  │                                                            │    │
│  │  Stub EC2 instances (for projects using SV AWS account)   │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌────── eu-west-1 (Ireland) DR / OVERFLOW ──────────────────┐    │
│  │  Route 53 failover routing                                 │    │
│  │  S3 replication (reports, backups)                        │    │
│  │  Stub EC2 instances (if project team prefers Ireland)      │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌────────────────── CLIENT PROJECT ACCOUNT A ────────────────────────┐
│  Stub EC2 instances (if team wants stubs in their own account)     │
│  Mockingbird deployer assumes IAM role here via STS                │
└─────────────────────────────────────────────────────────────────────┘

┌────────────────── ON-PREMISE (via Direct Connect) ─────────────────┐
│  Stub Docker container on any Linux server with Docker             │
│  Deployed via SSH + Docker commands (Phase 4)                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. EC2 Provisioning Flow (Confirmed Approach)

```
USER ACTION: Clicks "Deploy" in Mockingbird portal
                          │
                          ▼
               SQS deploy-queue
                          │
                          ▼
         deployer-worker (ECS Fargate task)
                          │
    ┌─────────────────────┼──────────────────────┐
    │                     │                      │
    ▼                     ▼                      ▼
STEP 1               STEP 2                 STEP 3
Check if Docker      Trigger GitLab         Run Terraform
image already        pipeline via           (if image ready)
built in registry    API to build image
    │                     │                      │
    │ image exists         │ image built          │
    └─────────────────────┘                      │
                          │                      │
                          ▼                      ▼
                   EC2 PROVISIONING (Terraform in deployer-worker container)
                          │
                          ├── SAME Mockingbird account:
                          │     Uses ECS task IAM role directly
                          │     terraform apply → EC2 created in SV account
                          │
                          ├── CLIENT's own AWS account:
                          │     AWS STS: AssumeRole → client's MockingbirdDeployerRole
                          │     Gets temporary credentials (1 hour)
                          │     terraform apply → EC2 created in CLIENT account
                          │
                          └── ON-PREMISE (Phase 4):
                                SSH via Direct Connect
                                docker pull + docker run on target server
                          │
                          ▼
                   EC2 user_data.sh runs:
                     docker login registry.gitlab.natwest.internal --username deploy-token
                     docker pull registry.gitlab.natwest.internal/mockingbird/{project-id}:v{n}
                     docker run -d -p 8080:8080 \
                       --restart always \
                       --memory 12g \
                       --cpus 7 \
                       {image}
                          │
                          ▼
                   Health check loop (every 5s, up to 5 minutes):
                     curl http://{ec2-ip}:8080/actuator/health → {"status":"UP"}
                          │
                          ▼
                   Update PostgreSQL:
                     stub_url = "https://{ec2-ip}:8080"
                     status = LIVE
                     ec2_instance_id = i-xxxxxxxxxx
                     deployed_at = now()
                          │
                          ▼
                   Emit EventBridge event: stub.deployed
                   Notification service → email/Slack to project owner
```

---

## 4. Stub Engine — Confirmed Architecture

### One Engine for 90% of Projects: Spring Boot + WireMock + Netty

```
What gets deployed to each EC2 (Docker container):
─────────────────────────────────────────────────

  ┌─────────────────────────────────────────────────────────┐
  │  Spring Boot Application (Java 21)                      │
  │                                                         │
  │  ┌─────────────────────────────────────────────────┐    │
  │  │  Netty HTTP Server (non-blocking, event-loop)    │    │
  │  │  Port 8080                                       │    │
  │  │  HTTP/2 enabled                                  │    │
  │  │  gzip compression enabled                        │    │
  │  └──────────────────────┬──────────────────────────┘    │
  │                         │                               │
  │  ┌──────────────────────▼──────────────────────────┐    │
  │  │  WireMock (embedded as library)                  │    │
  │  │                                                  │    │
  │  │  Mappings loaded from: /app/mappings/            │    │
  │  │    e.g., POST_payments_domestic.json             │    │
  │  │    e.g., GET_payments_{id}.json (with 200/404)   │    │
  │  │                                                  │    │
  │  │  Supports:                                       │    │
  │  │    Static responses (60% of projects)            │    │
  │  │    Handlebars dynamic data (20%)                 │    │
  │  │    Priority mappings for conditions (15%)        │    │
  │  │    Scenarios for stateful flows                  │    │
  │  │    Response delays (fixed/random/progressive)    │    │
  │  │    Fault injection (500/timeout/partial)         │    │
  │  └──────────────────────────────────────────────────┘    │
  │                                                         │
  │  ┌──────────────────────────────────────────────────┐    │
  │  │  Spring Boot Actuator                            │    │
  │  │    /actuator/health  → deep health check         │    │
  │  │    /actuator/prometheus → metrics for scraping   │    │
  │  │    /actuator/info    → project metadata          │    │
  │  └──────────────────────────────────────────────────┘    │
  │                                                         │
  │  ┌──────────────────────────────────────────────────┐    │
  │  │  Nginx (in same container or sidecar)            │    │
  │  │    Port 443 → TLS termination → 8080 (WireMock) │    │
  │  │    SSL cert: NatWest internal CA                 │    │
  │  │    Optional: mTLS client cert verification       │    │
  │  └──────────────────────────────────────────────────┘    │
  │                                                         │
  │  JVM: OpenJDK 21                                        │
  │  Flags: -Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10  │
  │  Virtual threads: spring.threads.virtual.enabled=true   │
  └─────────────────────────────────────────────────────────┘

Realistic TPS on c6i.2xlarge:
  1 mapping, response < 1KB:    15,000–18,000 TPS ✓
  1 mapping, response 1–10KB:   10,000–13,000 TPS ✓ (requirement met)
  1 mapping, response > 10KB:   warning shown; suggest compression
```

---

## 5. Conditional Response Architecture (Essential Feature)

WireMock handles all scenarios via **priority-ordered mappings** in the same project:

```
EXAMPLE: GET /accounts/{accountId}

Platform generates 4 stub mappings automatically:

Priority 1 (checked first):
  Matches: accountId = "SUSPENDED"
  Returns: 403 {"error": "ACCOUNT_SUSPENDED", "code": "ACCT_003"}

Priority 2:
  Matches: accountId = "NOTFOUND" OR any 8-digit number starting with 99
  Returns: 404 {"error": "ACCOUNT_NOT_FOUND", "code": "ACCT_002"}

Priority 3:
  Matches: Authorization header is missing
  Returns: 401 {"error": "UNAUTHORIZED"}

Priority 4 (fallback — matches everything else):
  Matches: any request to /accounts/{accountId}
  Returns: 200 {"accountId": "...", "balance": 5000.00, ...}

User configures this in the portal:
  ┌──────────────────────────────────────────────────────────────┐
  │  Conditional Rules for GET /accounts/{accountId}            │
  │                                                              │
  │  [+ Add Rule]                                               │
  │                                                              │
  │  Rule 1: If accountId == "SUSPENDED" → Return 403           │
  │  Rule 2: If accountId starts with "99" → Return 404         │
  │  Rule 3: If header Authorization missing → Return 401        │
  │  Default: Return 200 (account found)                        │
  │                                                              │
  │  [Save Rules] [Preview Generated WireMock JSON]             │
  └──────────────────────────────────────────────────────────────┘
```

---

## 6. Confirmed Data Stores

### PostgreSQL (NOT MS SQL) — Reasoning

NatWest centrally manages MS SQL and Oracle. However, Mockingbird uses **PostgreSQL on AWS RDS** because:

1. Zero licence cost (MS SQL requires Windows Server licence)
2. Mockingbird's mission is £0 licence cost — using licensed SQL Server contradicts this
3. AWS RDS PostgreSQL Multi-AZ is ~60% cheaper than RDS SQL Server
4. SQLAlchemy (Python) has superior PostgreSQL support
5. This is a NEW platform — establishing its own standard is acceptable

If NatWest mandates MS SQL for all applications: switch to RDS for SQL Server (SQLAlchemy supports it via pyodbc with zero code changes).

### Full Data Store Map

```
AWS RDS PostgreSQL 15 (Multi-AZ, eu-west-2)
  Schema: projects, stubs, deployments, users, roles, jobs, audit_log
  Sizing: db.m5.large for 20–30 projects (upgrade path to db.m5.xlarge)

AWS S3 (eu-west-2, replicated to eu-west-1)
  Buckets:
    mockingbird-uploads/     → uploaded spec files
    mockingbird-projects/    → generated stub packages
    mockingbird-reports/     → PDF/Excel/PPT reports
  Lifecycle: reports expire after 90 days (presigned URL access)

AWS ElastiCache Redis 7 (cluster mode, eu-west-2)
  Used for: API response caching, session tokens, rate limiting,
            WebSocket pub/sub (live TPS dashboard)

AWS Timestream (eu-west-2)
  Used for: TPS over time, latency percentiles, error rates
  Retention: 7 days hot → 13 months magnetic

AWS SQS (eu-west-2)
  Queues: parse-queue, generate-queue, deploy-queue, report-queue
  DLQ: mockingbird-dlq (failed jobs, manual retry)

HashiCorp Vault (existing NatWest instance)
  Secrets: DB password, GitLab deploy tokens, LDAP bind credentials,
           EC2 SSH keys (on-prem), Vault accessed via hvac (Python)
           and spring-vault-core (Java stub engine)
```

---

## 7. Monitoring & Observability Strategy

NatWest has: DX APM, AppDynamics, Splunk, Elasticsearch, CloudWatch

Mockingbird uses existing tools — no new monitoring infrastructure:

```
LOGS → Splunk (existing NatWest Splunk)
──────────────────────────────────────
All ECS containers: structured JSON logs to stdout
CloudWatch Logs Group: /mockingbird/{service-name}
CloudWatch Logs Subscription Filter → Splunk HTTP Event Collector (HEC)
  Format: { "timestamp": "...", "level": "INFO", "service": "parser-worker",
             "correlation_id": "...", "project_id": "...", "message": "..." }

METRICS → CloudWatch + Grafana (embedded in portal)
──────────────────────────────────────────────────
Platform services: CloudWatch metrics (ECS CPU, memory, SQS depth)
Stub engines: Spring Boot Actuator /actuator/prometheus
              → Prometheus scrapes every 30s
              → Writes to AWS Timestream
              → Grafana reads from Timestream → embedded in portal

APM (Application Performance) → AppDynamics or DX APM
────────────────────────────────────────────────────────
AppDynamics Java agent: injected into Spring Boot stub containers
  → Transaction tracing, slow request detection, error tracking
  → Feeds into existing NatWest AppDynamics dashboards

ALERTS → CloudWatch Alarms → SNS → Slack / email
──────────────────────────────────────────────────
Alert: SQS queue depth > 50 (jobs backing up)
Alert: EC2 stub health check failing > 2 minutes
Alert: RDS CPU > 80%
Alert: Any ECS task crash (task count drops below desired)
```

---

## 8. Authentication — Three-Phase Plan

```
PHASE 1 (Weeks 1–16): Local Credentials
  Admin creates username + password in Mockingbird portal
  Stored as: bcrypt hash in users table
  No external dependency — works offline
  Use during: platform development and SV team internal testing

PHASE 2 (Weeks 17–32): LDAP Integration
  Connect to NatWest LDAP server
  User logs in with NatWest network credentials (same as laptop login)
  LDAP query: filter by uid, get memberOf groups
  Role mapping:
    CN=SV-Team,OU=Groups,DC=natwest,DC=com       → role: ADMIN
    CN=SV-Users,OU=Groups,DC=natwest,DC=com      → role: SV_TEAM
    CN={project-group},OU=Groups,DC=natwest,DC=com → role: PROJECT_OWNER
    (any authenticated user with no group match)   → role: VIEWER
  
  Python: ldap3 library (from NatWest PyPI mirror)
  Config: LDAP_SERVER, LDAP_BASE_DN, LDAP_BIND_USER from HashiCorp Vault

PHASE 3 (Weeks 39+): SAML SSO (Europa users — additive)
  SAML 2.0 integration for Europa SSO
  LDAP still works for non-Europa users
  python3-saml library
  Both auth methods active simultaneously
  User lands on login page → chooses "NatWest Network Login" (LDAP) or "SSO Login" (SAML)
```

---

## 9. GitLab CI Architecture

### Pipeline 1: Build Mockingbird Platform (when developers commit code)

```yaml
# .gitlab-ci.yml (root)
stages: [test, build, deploy]

build-portal:
  image: node:20-alpine  # from Artifactory mirror
  script:
    - npm install --registry https://npm.natwest.internal
    - npm run build
    - # Build Nginx container with built assets

build-python-services:
  image: python:3.11-slim  # from Artifactory mirror
  script:
    - pip install --index-url https://pypi.natwest.internal/simple -r requirements.txt
    - pytest
    - # Build service Docker image via Kaniko

build-with-kaniko:
  image:
    name: gcr.io/kaniko-project/executor:v1.19.0-debug  # from Artifactory Docker mirror
    entrypoint: [""]
  script:
    - /kaniko/executor
        --context "${CI_PROJECT_DIR}"
        --dockerfile "Dockerfile"
        --destination "${CI_REGISTRY_IMAGE}/portal:${CI_COMMIT_SHA}"
  # CI_REGISTRY_IMAGE = registry.gitlab.natwest.internal/mockingbird/platform
```

### Pipeline 2: Build Stub Docker Image (triggered by Mockingbird when user deploys)

```yaml
# gitlab-ci/stub-build.yml (template)
build-stub-image:
  image:
    name: gcr.io/kaniko-project/executor:v1.19.0-debug
    entrypoint: [""]
  variables:
    PROJECT_ID: ${PROJECT_ID}    # passed by deployer-worker via GitLab API
    VERSION: ${VERSION}
  script:
    - /kaniko/executor
        --context "${CI_PROJECT_DIR}/stub-package"
        --dockerfile "${CI_PROJECT_DIR}/stub-package/Dockerfile"
        --build-arg ARTIFACTORY_URL=https://artifactory.natwest.internal
        --destination "${CI_REGISTRY_IMAGE}/${PROJECT_ID}:${VERSION}"
```

**Triggering this from Python (deployer-worker):**
```python
import httpx

async def trigger_stub_build(project_id: str, version: str) -> str:
    """Trigger GitLab pipeline to build stub Docker image"""
    response = await httpx.post(
        f"https://gitlab.natwest.internal/api/v4/projects/{MOCKINGBIRD_GITLAB_PROJECT_ID}/trigger/pipeline",
        json={
            "token": vault.get_secret("gitlab/pipeline-trigger-token"),
            "ref": "main",
            "variables": {
                "PROJECT_ID": project_id,
                "VERSION": version,
                "PIPELINE_TYPE": "stub-build"
            }
        }
    )
    return response.json()["id"]  # pipeline_id to poll for status
```

---

## 10. Report Formats — All Four Supported

```
LIVE DASHBOARD (React + ECharts + WebSocket)
  Available in portal: /projects/{id}/metrics
  Real-time: updates every second via WebSocket
  Shows: Current TPS, Peak TPS, P95 latency, error rate
  Historical: switch to 1h/24h/7d/30d view
  Grafana embedded: operational dashboards

PDF REPORT (WeasyPrint Python library)
  Executive Summary: NatWest branded, charts, license savings, availability
  Project Report: per-endpoint metrics, deployment history
  Delivered: email attachment + portal download link

EXCEL REPORT (openpyxl Python library)
  Raw data: per-stub request counts, latency, errors by date
  For finance: EC2 cost per project, total savings vs CA/IBM
  Multiple worksheets: summary + per-project tabs

POWERPOINT REPORT (python-pptx Python library)
  Pre-formatted slides: ready for management presentation
  Includes: charts as embedded images, key metrics as large numbers
  NatWest slide template applied (colours, logo, footer)

All reports:
  Generated on demand OR scheduled (daily/weekly/monthly email)
  Stored in S3 for 90 days
  Shared via presigned URL (7-day expiry)
  Access controlled by role (Admin sees all; Project Owner sees own project)
```

---

## 11. What Remains Unknown (Final Open Questions)

| Question | Needed For |
|----------|-----------|
| GitLab Container Registry exact hostname | Phase 1 — all Docker push/pull commands |
| Artifactory URLs (Maven, PyPI, npm, Docker) | Phase 1 — all dependency downloads |
| mTLS or server-side TLS only for stubs? | Phase 2 — Nginx config on EC2 |
| Is PostgreSQL acceptable or is MS SQL mandatory? | Phase 1 — DB setup |
| HashiCorp Vault endpoint + auth method (AppRole? k8s?) | Phase 3 — secrets integration |
| NatWest branding assets (logo, colours, fonts) | Phase 5 — report templates |
| AppDynamics agent key for stub containers | Phase 2 — APM integration |
| Splunk HEC endpoint + token | Phase 3 — log forwarding |
| LDAP server hostname + bind credentials | Phase 2 — auth |
