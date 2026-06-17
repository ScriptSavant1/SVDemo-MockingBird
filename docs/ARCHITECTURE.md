# Mockingbird — System Architecture

**Version:** 1.0  
**Last Updated:** 2026-06-12

---

## Table of Contents

1. [Architecture Principles](#1-architecture-principles)
2. [System Context](#2-system-context)
3. [Microservices Container Diagram](#3-microservices-container-diagram)
4. [AWS Infrastructure Layout](#4-aws-infrastructure-layout)
5. [Key Data Flows](#5-key-data-flows)
6. [Stub Engine Per-Project Model](#6-stub-engine-per-project-model)
7. [Security Architecture](#7-security-architecture)
8. [Scalability Model](#8-scalability-model)
9. [Network Topology](#9-network-topology)

---

## 1. Architecture Principles

| Principle | Implementation |
|-----------|---------------|
| **Loosely coupled** | Services communicate via API contracts and events — never shared DBs |
| **Event-driven async** | All long-running jobs (parse, generate, deploy, report) are SQS messages |
| **Cloud-native** | ECS Fargate for platform; EC2 only for stub engines (need fixed IP) |
| **Plugin-extensible** | New input formats and stub engines are plugins — no core code changes |
| **Observable** | Every service exposes Prometheus metrics + structured JSON logs |
| **Secure by default** | JWT everywhere, RBAC, all secrets in AWS Secrets Manager |
| **GitOps** | All infra changes via GitLab CI + Terraform — no manual AWS console changes |

---

## 2. System Context

Who interacts with Mockingbird and why:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         NATWEST NETWORK                              │
│                                                                      │
│  ┌─────────────┐      ┌─────────────────────────────────────────┐   │
│  │  Project    │      │          MOCKINGBIRD PLATFORM           │   │
│  │  Teams      │─────▶│  (self-service portal + backend APIs)   │   │
│  │  (consumers)│      └─────────────────────────────────────────┘   │
│  └─────────────┘                       │                            │
│                                        │ auto-provisions             │
│  ┌─────────────┐                       ▼                            │
│  │  SV Team    │      ┌─────────────────────────────────────────┐   │
│  │  (admin)    │─────▶│  Stub EC2 Instances (per project)       │   │
│  └─────────────┘      │  WireMock / Hoverfly / Microcks          │   │
│                       └─────────────────────────────────────────┘   │
│  ┌─────────────┐                       │                            │
│  │  Management │      ┌────────────────▼────────────────────────┐   │
│  │  / CTO      │◀─────│  Dashboards + Reports                   │   │
│  └─────────────┘      └─────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────┐      ┌─────────────────────────────────────────┐   │
│  │  GitLab CI  │─────▶│  Terraform + ECR + ECS Deploy Pipeline  │   │
│  └─────────────┘      └─────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                                  │ External
                    ┌─────────────▼──────────────┐
                    │   Anthropic Claude API       │
                    │   (AI stub generation)       │
                    └────────────────────────────┘
```

---

## 3. Microservices Container Diagram

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        AWS CloudFront + S3                                   ║
║                    React SPA (portal) — Static Assets                        ║
╚══════════════════════════════════════════╦═══════════════════════════════════╝
                                           ║ HTTPS
╔══════════════════════════════════════════▼═══════════════════════════════════╗
║                          AWS API Gateway (HTTP + WebSocket)                  ║
║           Rate limiting │ JWT verification │ Route-to-service                ║
╚══╦═════════╦════════════╦════════╦═════════╦═════════╦════════╦═════════════╝
   ║         ║            ║        ║         ║         ║        ║
   ▼         ▼            ▼        ▼         ▼         ▼        ▼
┌──────┐ ┌───────┐ ┌─────────┐ ┌──────┐ ┌───────┐ ┌──────┐ ┌───────┐
│auth  │ │project│ │ingest-  │ │metr- │ │report-│ │notif-│ │  ai-  │
│serv. │ │serv.  │ │service  │ │ics   │ │service│ │ication│ │service│
│      │ │       │ │         │ │serv. │ │       │ │serv. │ │       │
│Node  │ │Python │ │Python   │ │Python│ │Python │ │Node  │ │Python │
│Fastify│ │FastAPI│ │FastAPI  │ │FastAPI│ │FastAPI│ │Fastify│ │FastAPI│
└──────┘ └───┬───┘ └────┬────┘ └──────┘ └───────┘ └──────┘ └───────┘
             │           │
             │           │ uploads file
             ▼           ▼
          ┌──────────────────────────────────────────────────────┐
          │                   AWS SQS Queues                      │
          │                                                        │
          │  ┌────────────┐ ┌────────────┐ ┌────────────────┐    │
          │  │parse-queue │ │gen-queue   │ │deploy-queue    │    │
          │  └──────┬─────┘ └──────┬─────┘ └───────┬────────┘    │
          │         │              │               │              │
          │  ┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐      │
          │  │report-queue│ │notify-queue│ │dlq (failed) │      │
          │  └────────────┘ └────────────┘ └─────────────┘       │
          └──────────────────────────────────────────────────────┘
                   │              │               │
                   ▼              ▼               ▼
          ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
          │parser-worker │ │generator-    │ │deployer-     │
          │              │ │worker        │ │worker        │
          │Python 3.11   │ │Python 3.11   │ │Python 3.11   │
          │SQS consumer  │ │SQS consumer  │ │SQS consumer  │
          └──────────────┘ └──────────────┘ └──────────────┘
                                                    │
                                           Terraform + boto3
                                                    │
                                         ┌──────────▼──────────┐
                                         │  AWS ECR             │
                                         │  (Docker images)     │
                                         └──────────┬──────────┘
                                                    │
                                         ┌──────────▼──────────┐
                                         │  AWS EC2 (per proj) │
                                         │  WireMock/Hoverfly  │
                                         └─────────────────────┘
```

### AWS EventBridge (Domain Events)

All services emit and consume domain events for cross-cutting concerns:

```
project-service ──emit──▶ project.created ──▶ deployer-worker (auto-trigger)
                                            ──▶ notification-service (notify owner)

deployer-worker ──emit──▶ stub.deployed   ──▶ metrics-service (start scraping)
                                           ──▶ notification-service (send URL)
                                           ──▶ project-service (update status)

metrics-service ──emit──▶ tps.threshold.exceeded ──▶ notification-service (alert)
```

---

## 4. AWS Infrastructure Layout

```
┌─────────────────────────── AWS ACCOUNT: NatWest Mockingbird ────────────────────────────┐
│                                                                                           │
│  ┌─────────────── VPC: 10.0.0.0/16 ───────────────────────────────────────────────┐     │
│  │                                                                                  │     │
│  │  ┌──── Public Subnets (10.0.1.x, 10.0.2.x) ────────────────────────────────┐   │     │
│  │  │                                                                           │   │     │
│  │  │   ┌─────────────────┐     ┌───────────────────────────────────────────┐  │   │     │
│  │  │   │  AWS API Gateway │     │  Application Load Balancer                │  │   │     │
│  │  │   │  (HTTP + WS)     │     │  (routes to ECS services)                 │  │   │     │
│  │  │   └────────┬─────────┘     └──────────────────────────────┬────────────┘  │   │     │
│  │  │            │                                               │               │   │     │
│  │  └────────────┼───────────────────────────────────────────── ┼ ──────────────┘   │     │
│  │               │                                               │                  │     │
│  │  ┌──── Private Subnets (10.0.10.x, 10.0.11.x) ──────────────┼──────────────┐   │     │
│  │  │                                                            │              │   │     │
│  │  │  ┌──── ECS Fargate Cluster (Platform Services) ───────────▼──────────┐   │   │     │
│  │  │  │                                                                    │   │   │     │
│  │  │  │  auth-service    project-service    ingestion-service              │   │   │     │
│  │  │  │  metrics-service reporter-service   notification-service           │   │   │     │
│  │  │  │  ai-service      parser-worker      generator-worker               │   │   │     │
│  │  │  │  deployer-worker                                                   │   │   │     │
│  │  │  │                                                                    │   │   │     │
│  │  │  │  Each service: min 1, max 10 Fargate tasks (auto-scale on SQS)    │   │   │     │
│  │  │  └────────────────────────────────────────────────────────────────────┘   │   │     │
│  │  │                                                                            │   │     │
│  │  │  ┌──── Stub EC2 Instances (one per project) ───────────────────────────┐   │   │     │
│  │  │  │                                                                      │   │   │     │
│  │  │  │  ec2-projA (c6i.xlarge)   ec2-projB (c6i.2xlarge)  ec2-projC (...)  │   │   │     │
│  │  │  │  WireMock :8080           Hoverfly :8080            Microcks :8080   │   │   │     │
│  │  │  │  Prometheus :9090         Prometheus :9090          Prometheus :9090  │   │   │     │
│  │  │  │                                                                      │   │   │     │
│  │  │  └──────────────────────────────────────────────────────────────────────┘   │   │     │
│  │  │                                                                            │   │     │
│  │  │  ┌──── Managed Data Services ─────────────────────────────────────────┐   │   │     │
│  │  │  │                                                                      │   │   │     │
│  │  │  │  RDS PostgreSQL 15    ElastiCache Redis 7    AWS Timestream          │   │   │     │
│  │  │  │  (Multi-AZ, encrypted) (cluster mode)       (pay-per-query)         │   │   │     │
│  │  │  │                                                                      │   │   │     │
│  │  │  └──────────────────────────────────────────────────────────────────────┘   │   │     │
│  │  │                                                                            │   │     │
│  │  └────────────────────────────────────────────────────────────────────────────┘   │     │
│  │                                                                                  │     │
│  └──────────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                           │
│  ┌── Global / Regional Services ─────────────────────────────────────────────────────┐   │
│  │  CloudFront + S3 (portal)   ECR (Docker images)   SQS (queues)   EventBridge      │   │
│  │  Route 53 (DNS)             Secrets Manager        CloudWatch Logs + Alarms        │   │
│  └────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Key Data Flows

### 5.1 — Upload Spec → Generate Stubs (Primary Flow)

```
User (Browser)
    │
    │ 1. POST /upload (multipart file)
    ▼
Ingestion Service
    │ 2. Save file to S3 (uploads/{projectId}/original/{filename})
    │ 3. Auto-detect file type (OpenAPI / Postman / WSDL / HAR / CSV / Raw)
    │ 4. Return: { upload_id, detected_type, endpoint_count_preview }
    │ 5. Send message → SQS parse-queue
    ▼
Parser Worker (SQS consumer)
    │ 6. Pull message from parse-queue
    │ 7. Download file from S3
    │ 8. Parse → List[ParsedEndpoint] (normalised internal format)
    │ 9. Save parsed result to S3 (uploads/{projectId}/parsed/{upload_id}.json)
    │ 10. Update job status in PostgreSQL: PARSED
    │ 11. Send message → SQS generate-queue
    ▼
Generator Worker (SQS consumer)
    │ 12. Pull message from generate-queue
    │ 13. Load ParsedEndpoints from S3
    │ 14. Apply data rules engine (dynamic field detection)
    │ 15. Generate WireMock/Hoverfly/Microcks mappings
    │ 16. Package: Dockerfile + mappings + docker-compose + prometheus.yml
    │ 17. Save project package to S3 (projects/{projectId}/v{n}/)
    │ 18. Update job status: GENERATED
    │ 19. Emit EventBridge: stubs.generated → (optional: auto-trigger deploy)
    ▼
User reviews stubs in portal (can edit via web editor)
    │
    │ 20. POST /deploy (user clicks Deploy button)
    ▼
Deployer Worker (SQS consumer)
    │ 21. Download project package from S3
    │ 22. docker build → tag with ECR URI
    │ 23. docker push → AWS ECR
    │ 24. terraform apply → provision EC2 (or update existing)
    │ 25. Poll EC2 health check (http://{ip}:8080/__admin/health) every 5s, up to 5min
    │ 26. Update PostgreSQL: stub_url, api_key, ec2_instance_id, status=LIVE
    │ 27. Generate firewall documentation PDF → S3
    │ 28. Emit EventBridge: stub.deployed
    ▼
Notification Service
    │ 29. Send email/Slack/Teams to project owner:
    │     Stub URL: https://{ec2-ip}:8080
    │     API Key: {key}
    │     Firewall doc: {s3-presigned-url}
    ▼
User: copy stub URL, configure consuming app
```

### 5.2 — Live TPS Monitoring Flow

```
Stub EC2 (WireMock)
    │ Prometheus metrics endpoint: http://{ip}:9090/metrics (every request)
    │
Metrics Service (Celery Beat — every 30s)
    │ 1. Scrape all registered EC2 Prometheus endpoints
    │ 2. Parse: wiremock_requests_total, wiremock_request_duration_seconds
    │ 3. Write to AWS Timestream with tags: project_id, path, method, status
    │
    │ Also:
    │ 4. Calculate current TPS (delta requests / 30s)
    │ 5. Publish to Redis pub/sub channel: metrics:{project_id}
    │
API Gateway (WebSocket)
    │ 6. Forward Redis pub/sub messages to connected browser WebSocket clients
    │
Portal Dashboard
    │ 7. Real-time ECharts line chart updates every second
    │ 8. Shows: current TPS, peak TPS, P95 latency, error rate
```

### 5.3 — Report Generation Flow

```
User or Scheduler
    │
    │ POST /reports/generate { type, project_id, date_range, format }
    ▼
Reporter Service
    │ 1. Send to SQS report-queue
    ▼
Reporter Worker
    │ 2. Query AWS Timestream: TPS trends, latency percentiles
    │ 3. Query PostgreSQL: stubs created, deployments, audit events
    │ 4. Render PDF (WeasyPrint) or Excel (openpyxl) or JSON
    │ 5. Save to S3: reports/{project_id}/{date}/{type}.pdf
    │ 6. Generate S3 presigned URL (7-day expiry)
    │ 7. Emit EventBridge: report.ready
    ▼
Notification Service
    │ 8. Email report link to requester (or attach PDF if < 5MB)
```

---

## 6. Stub Engine Per-Project Model

Each project gets its own isolated EC2 instance:

```
┌────────────────────────────────────────────────────────────┐
│              EC2: c6i.xlarge (project: payments-api)         │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Nginx (reverse proxy + SSL termination)  :443      │    │
│  │  → forwards to WireMock :8080                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────┐  ┌────────────────────────┐     │
│  │  WireMock 3.x          │  │  Prometheus Exporter   │     │
│  │  Port: 8080            │  │  Port: 9090            │     │
│  │                        │  │                        │     │
│  │  mappings/             │  │  scrapes WireMock      │     │
│  │    POST_payments.json  │  │  /metrics endpoint     │     │
│  │    GET_accounts.json   │  │                        │     │
│  │    ...                 │  │  exposes to platform   │     │
│  │                        │  │  metrics-service       │     │
│  │  __files/              │  │                        │     │
│  │    large_responses/    │  │                        │     │
│  └────────────────────────┘  └────────────────────────┘     │
│                                                              │
│  Security Group:                                             │
│    Inbound :8080 ← consuming team's server CIDR              │
│    Inbound :9090 ← platform monitoring CIDR only             │
│    Inbound :22   ← bastion host only                         │
│    Outbound: ECR, Secrets Manager, CloudWatch                │
│                                                              │
│  IAM Role:                                                   │
│    ECR:GetAuthorizationToken, ECR:BatchGetImage              │
│    secretsmanager:GetSecretValue                             │
│    logs:CreateLogGroup, logs:PutLogEvents                    │
└────────────────────────────────────────────────────────────┘
```

**Engine selection logic (auto):**

| Project TPS Requirement | Engine | EC2 Size | Est. Monthly |
|------------------------|--------|----------|-------------|
| < 1,000 | WireMock | t3.medium (2vCPU, 4GB) | ~£25 |
| 1,000 – 5,000 | WireMock | c6i.xlarge (4vCPU, 8GB) | ~£100 |
| 5,000 – 15,000 | Hoverfly | c6i.2xlarge (8vCPU, 16GB) | ~£200 |
| 15,000+ | Hoverfly + NLB | c6i.4xlarge (16vCPU, 32GB) | ~£400 |
| Kafka/async | Microcks | c6i.xlarge + MSK | ~£150 |

---

## 7. Security Architecture

```
AUTHENTICATION LAYER
────────────────────
Browser → API Gateway → auth-service → JWT token (15-min expiry)
                                     → Refresh token (7-day, Redis stored)
                                     
Bank SSO (SAML/OIDC via AD) ──▶ auth-service ──▶ JWT (same flow)

AUTHORISATION LAYER (RBAC)
──────────────────────────
Role         │ Can do
─────────────┼───────────────────────────────────────────
ADMIN        │ Everything + manage users + view all projects
SV_TEAM      │ Create/edit/deploy any project + view all reports  
PROJECT_OWNER│ Create/edit/deploy own projects only
VIEWER       │ View stubs + metrics for assigned projects only

SECRETS MANAGEMENT
──────────────────
All credentials → AWS Secrets Manager
Services pull at startup via boto3 (never in env vars or code)
Rotation: DB passwords every 30 days (automatic)

DATA IN TRANSIT
───────────────
Portal ↔ API Gateway: HTTPS (TLS 1.3)
API Gateway ↔ Services: HTTPS (internal ALB, ACM cert)
Services ↔ RDS/Redis: TLS (AWS-managed)
EC2 stub → consuming team: HTTPS (Nginx + ACM/self-signed)

DATA AT REST
────────────
RDS: encrypted (AWS KMS)
S3: SSE-S3 encryption
ElastiCache: in-transit + at-rest encryption
Timestream: encrypted by default

AUDIT LOG (IMMUTABLE)
──────────────────────
Every project-service mutation appends to audit_log table:
  user_id, action, resource_type, resource_id, old_value, 
  new_value, ip_address, timestamp
Table: INSERT only, no UPDATE/DELETE permissions for app user
```

---

## 8. Scalability Model

### Platform Services (ECS Fargate Auto-Scaling)

```
Metric that triggers scale-out:
  SQS queue depth > 10 messages → scale generator-worker up to 10 tasks
  SQS queue depth < 2 messages  → scale down after 5 minutes

CPU > 70% for 2 minutes → scale any service up
CPU < 20% for 10 minutes → scale down (min 1 task always)
```

### Stub Engines (Vertical Scaling per Project)

```
At project creation, user declares expected TPS tier.
Platform provisions right-sized EC2.
To rescale: re-deploy with new Terraform var (instance_type).
Zero-downtime: new EC2 spun up, traffic switched, old terminated.
```

### Database Scaling

```
RDS PostgreSQL: Multi-AZ (automatic failover), read replica for reporting queries
ElastiCache Redis: Cluster mode (sharding across 3 nodes)
Timestream: Serverless (scales automatically, pay per query)
SQS: Serverless (unlimited throughput)
```

---

## 9. Network Topology

```
INTERNET
    │
    ▼ HTTPS :443
AWS CloudFront (CDN)
    ├── Origin 1: S3 bucket (React SPA static files)
    └── Origin 2: API Gateway (API calls from portal)
    
    │
    ▼
AWS API Gateway
    ├── /api/v1/*  → ALB → ECS Fargate services
    ├── /ws/*      → WebSocket API → Redis pub/sub
    └── Auth: Lambda authorizer (JWT validation)
    
    │
    ▼ (internal, private subnets)
ECS Fargate Services
    └── Outbound via NAT Gateway (to ECR, Secrets Manager, EventBridge, etc.)
    
    │
    ▼ Terraform provisions
EC2 Stub Instances (private subnets)
    └── Firewall: SG allows inbound only from consuming team's CIDR on :8080
    └── Firewall: SG allows inbound from monitoring CIDR on :9090

FIREWALL DOCUMENTATION (auto-generated per project):
  Source IP:    {consuming team server IP or CIDR}
  Destination:  {EC2 private IP}:8080
  Protocol:     TCP/HTTPS
  Direction:    Inbound to stub server
  → PDF sent to project owner + infrastructure team via email
```
