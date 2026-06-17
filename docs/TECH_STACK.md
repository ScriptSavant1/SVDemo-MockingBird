# Mockingbird — Technology Stack & Decisions

**Version:** 1.0  
**Last Updated:** 2026-06-12

---

## Summary Table

| Layer | Technology | Why Chosen |
|-------|-----------|-----------|
| Frontend | React 18 + TypeScript + Vite | Industry standard, enterprise-familiar, best ecosystem |
| UI Components | shadcn/ui + Tailwind CSS | Modern, accessible, no vendor lock-in, highly customisable |
| Charts | Apache ECharts | Best performance for real-time TPS charts; handles 10K+ data points |
| State (server) | TanStack Query v5 | Best-in-class, handles caching, revalidation, optimistic updates |
| State (client) | Zustand | Lightweight, no boilerplate (not Redux) |
| Python services | FastAPI + Pydantic v2 | Async, fastest Python framework, auto-generates OpenAPI docs |
| Node.js services | Fastify | Fastest Node.js framework, low overhead for auth/notifications |
| Job Queue | AWS SQS | Fully managed, no ops, scales infinitely, native AWS |
| Domain Events | AWS EventBridge | Serverless fan-out, no consumer coupling |
| Stub engine: REST | WireMock 3.x | Battle-tested, native SOAP support, Handlebars templates |
| Stub engine: HighTPS | Hoverfly (Go) | 20K+ TPS, in-memory, goroutine-based |
| Stub engine: Async | Microcks | Only OSS tool for Kafka + gRPC + GraphQL stubs |
| Container platform | AWS ECS Fargate | Serverless containers — no EC2 management for platform |
| IaC | Terraform + Terragrunt | Standard in banking; GitLab-managed state |
| CI/CD | GitLab CI/CD | Already in use; native container registry |
| Time-series DB | AWS Timestream | Fully managed, serverless, native AWS (vs self-managed InfluxDB) |
| Relational DB | AWS RDS PostgreSQL 15 | Multi-AZ, managed backups, familiar, trusted |
| Cache | AWS ElastiCache Redis 7 | Managed Redis for sessions, caching, pub/sub (live TPS WebSocket) |
| Object Storage | AWS S3 | Standard AWS storage; replaces MinIO (already on AWS) |
| LLM: complex tasks | Claude claude-sonnet-4-6 | Best structured JSON output; 200K context; strong code understanding |
| LLM: lightweight tasks | Claude claude-haiku-4-5 | 4x cheaper; fast; sufficient for field detection |
| Monitoring | Prometheus + Grafana | Industry standard; WireMock has native Prometheus exporter |
| Logging | AWS CloudWatch Logs | Native AWS; structured JSON logs; Insights for query |
| Testing: Python | pytest + testcontainers | Standard Python testing; real containers for integration tests |
| Testing: Frontend | Vitest + Playwright | Fast unit tests; Playwright for E2E |
| Testing: TPS | Locust | Python-based load testing; validates 15K TPS claim |

---

## Layer-by-Layer Decisions

### Frontend

#### React 18 + TypeScript + Vite

**Chosen because:**
- Dominant in enterprise ecosystem; large hiring pool
- TypeScript strict mode catches bugs before runtime
- Vite: 10–50x faster builds than webpack; native ESM; excellent HMR
- React 18 concurrent features (Suspense, transitions) for smooth UX

**Alternatives considered:**
- Next.js → rejected: SSR adds complexity for internal portal; not needed
- Vue 3 → rejected: smaller talent pool in enterprise contexts; React is entrenched
- Angular → rejected: heavy; slower development velocity; overkill

#### shadcn/ui + Tailwind CSS

**Chosen because:**
- shadcn/ui: copy-paste components (not npm package) — full control, no version conflicts
- Radix UI primitives underneath: WCAG 2.1 AA accessible out of the box
- Tailwind: utility-first = no naming CSS battles; dark mode built-in
- Looks genuinely modern (not Bootstrap-era design)

**Alternatives considered:**
- Material UI → rejected: opinionated look; customisation is painful
- Ant Design → rejected: heavy bundle; less customisable
- Chakra UI → rejected: shadcn/ui has better accessibility and more active community

#### Apache ECharts (for charts/dashboards)

**Chosen because:**
- Handles real-time streaming data without performance degradation
- Canvas-based rendering: 100K+ data points at 60fps
- WebGL support for extreme data volumes
- Richer chart types than Recharts (heatmaps, sankey, etc.)

**Alternatives considered:**
- Recharts → rejected: SVG-based; slow at high data volumes (TPS chart would lag)
- Victory Charts → rejected: limited chart types; poor real-time support
- Grafana embedded → kept as secondary: used for operational dashboards; ECharts for portal

---

### Backend Services

#### Python 3.11 + FastAPI (compute-heavy services)

**Used for:** project-service, ingestion-service, parser-worker, generator-worker, deployer-worker, metrics-service, reporter-service, ai-service

**Chosen because:**
- FastAPI: native async/await; Pydantic v2 validation; auto-generates OpenAPI docs
- Python: best ecosystem for parsing (lxml, pyyaml, openpyxl), data generation (Faker), PDF (WeasyPrint), AWS (boto3)
- Pydantic v2: 5–50x faster than v1; excellent for validating parsed API specs
- `uv` (new Python package manager): 10–100x faster than pip

**Alternatives considered:**
- Django → rejected: synchronous by default; heavy ORM; not suited to microservices
- Flask → rejected: too minimal; no async; no built-in validation
- Java Spring Boot → rejected for new services: heavier; slower iteration (WireMock already runs Java — no need to add more)

#### Node.js 20 + Fastify (lightweight services)

**Used for:** auth-service, notification-service

**Chosen because:**
- Auth service: many JWT/SAML libraries are Node-native; Node is widely used for auth tooling
- Notification service: I/O-bound (sending emails/webhooks) — Node excels here
- Fastify: 2–3x faster than Express; schema-based validation built-in

**Alternatives considered:**
- Python for auth → viable but Node has more mature SAML/OIDC libraries
- Go → viable for performance; rejected because lower familiarity in the team

---

### Stub Engines

> **Architecture Decision (Post-Expert Review):** Moved from standalone WireMock JAR to
> Spring Boot + WireMock as a library. Reasons: Artifactory dependency management,
> 12,000–18,000 TPS via Netty (vs 7,000–9,000 for standalone), Spring Boot Actuator
> replaces Prometheus sidecar, Spring-WS for enterprise SOAP. See `docs/SV_EXPERT_REVIEW.md`.

#### Engine 1: Spring Boot + WireMock (PRIMARY — 90% of projects)

**Used for:** REST (static, dynamic, stateful, fault injection), SOAP

**Chosen because:**
- All JARs pulled from Artifactory (pom.xml) — no public internet dependency
- WireMock runs as an embedded library (not standalone JAR) — fully customisable
- Spring WebFlux + Netty: non-blocking I/O, achieves **12,000–18,000 TPS**
- Java 21 virtual threads (`spring.threads.virtual.enabled=true`): further TPS boost
- Spring Boot Actuator: `/actuator/health` + `/actuator/prometheus` built-in
- Spring-WS: enterprise-grade SOAP (WS-Security, complex XSD, SOAP 1.1/1.2)
- Custom transformers as Spring beans (bank-specific logic, correlation IDs)
- Single Dockerfile — no sidecar containers needed

**Key Artifactory dependencies:**
```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>     <!-- Netty, non-blocking -->
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>    <!-- health + prometheus -->
</dependency>
<dependency>
  <groupId>com.github.tomakehurst</groupId>
  <artifactId>wiremock-standalone</artifactId>             <!-- WireMock as library -->
</dependency>
<dependency>
  <groupId>org.springframework.ws</groupId>
  <artifactId>spring-ws-core</artifactId>                  <!-- enterprise SOAP -->
</dependency>
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-registry-prometheus</artifactId>  <!-- metrics -->
</dependency>
<dependency>
  <groupId>com.github.javafaker</groupId>
  <artifactId>javafaker</artifactId>                       <!-- dynamic data -->
</dependency>
```

**JVM tuning:**
```
JAVA_OPTS="-Xms4g -Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10
           -XX:+ParallelRefProcEnabled -XX:+AlwaysPreTouch
           -Djava.net.preferIPv4Stack=true"

application.yaml:
  spring.threads.virtual.enabled: true   # Java 21 virtual threads
  server.http2.enabled: true             # HTTP/2 multiplexing
  server.compression.enabled: true       # gzip (reduces bandwidth 70–80%)
```

#### Engine 2: Hoverfly (HIGH TPS — > 18,000 TPS only)

**When to use:** auto-selected when TPS requirement exceeds Spring Boot capacity (> 18,000 TPS)

**Chosen because:**
- Written in Go: goroutines, no JVM GC pauses
- Achieves **18,000–25,000+ TPS** on c6i.4xlarge
- In-memory compiled matcher cache

**Limitation:** No SOAP, no custom transformers, limited features. Use only when raw throughput is the sole requirement and Spring Boot Netty is not sufficient.

#### Engine 3: Spring Boot + Spring Kafka (KAFKA SIMPLE)

**When to use:** Simple Kafka producer/consumer stubs, no Avro schema registry

**Chosen because:**
- Spring Kafka is in Artifactory (org.springframework.kafka)
- Simpler than Microcks for basic use cases
- Same Spring Boot stack as Engine 1 — familiar to team
- Can produce messages to Kafka topics on HTTP trigger
- Can consume from topics and produce to reply topics (request-reply pattern)

#### Engine 4: Microcks (KAFKA + AsyncAPI + Avro)

**When to use:** Complex AsyncAPI specs with Avro schema registry, gRPC stubs, GraphQL mocks

**Chosen because:**
- Only OSS tool that handles AsyncAPI + Avro schema registry natively
- Apache 2.0 licence
- Active CNCF community

**Note:** Require separate Microcks instance per project (heavier than Spring Kafka).

#### Engine 5: Spring Boot + Spring JMS (IBM MQ — Phase 4)

**When to use:** IBM MQ / JMS stubs (common in banking legacy systems)

**Chosen because:**
- IBM MQ client JARs available from IBM Fix Central → mirror to Artifactory
- `com.ibm.mq:com.ibm.mq.allclient` is the standard enterprise MQ library
- Spring JMS provides `@JmsListener` (consumer simulation) and `JmsTemplate` (producer)
- Natural fit with Spring Boot stack

#### Engine Selection Decision Tree

```
At project creation, user declares protocol + TPS requirement:

  Protocol?
  ├── REST / SOAP
  │     TPS < 18,000? → Engine 1: Spring Boot + WireMock (Netty)
  │     TPS ≥ 18,000? → Engine 2: Hoverfly
  │
  ├── Kafka
  │     Simple producer/consumer? → Engine 3: Spring Boot + Spring Kafka
  │     AsyncAPI + Avro?          → Engine 4: Microcks
  │
  ├── IBM MQ / JMS                → Engine 5: Spring Boot + Spring JMS
  │
  └── gRPC / GraphQL              → Engine 4: Microcks

EC2 sizing auto-selected by TPS tier (see DEPLOYMENT_ARCHITECTURE.md)
```

---

### Messaging & Events

#### AWS SQS (job queue)

**Chosen because:**
- Fully managed: no Redis/RabbitMQ/Kafka cluster to operate
- Visibility timeout prevents duplicate processing
- Dead-letter queue (DLQ) for failed job inspection
- FIFO queues available if ordering matters
- Auto-scales to millions of messages/second
- Pay per request (~$0.40 per million messages)

**Alternatives considered:**
- Celery + Redis → rejected: adds Redis dependency; Celery config complexity; SQS is simpler in AWS
- Apache Kafka → rejected for jobs: Kafka is for streaming, not job dispatch; MSK cluster cost ~£200+/month fixed

#### AWS EventBridge (domain events)

**Chosen because:**
- Serverless fan-out (one event → multiple consumers)
- Native AWS integration (no consumer coupling)
- Schema registry: self-documenting events
- Content-based routing: filter events without code
- 14-day event replay if consumer was down

**Pattern used:**
```json
{
  "source": "mockingbird.project-service",
  "detail-type": "Stub.Deployed",
  "detail": { "project_id": "...", "stub_url": "...", "environment": "TEST" }
}
```

---

### Data Stores

#### AWS RDS PostgreSQL 15 (primary relational DB)

**Chosen because:**
- Multi-AZ: automatic failover, no data loss
- Managed backups, point-in-time recovery
- Read replicas for reporting queries (separate from write traffic)
- Extensions: `uuid-ossp`, `pg_trgm` (trigram search for stub names)
- RDS Proxy: connection pooling for ECS services (avoids connection exhaustion)

**Schema ownership:** single database, service-specific schemas:
```
public schema    → shared types only
project_svc     → projects, stubs, deployments
auth_svc        → users, roles, sessions
metrics_svc     → metrics_summary (daily rollups)
audit_svc       → audit_log (INSERT-only)
```

#### AWS Timestream (time-series metrics)

**Chosen because:**
- Fully managed (no InfluxDB cluster to run)
- Automatic tiering: recent data in memory, older data in SSD
- Serverless: pay per query, not per instance
- Native integration with Grafana (Grafana Cloud → Timestream)
- Retention policy: 7 days hot, 13 months magnetic (configurable)

**Alternatives considered:**
- InfluxDB Cloud → viable; rejected because adding another vendor outside AWS
- InfluxDB self-managed → rejected: operational burden; Timestream is simpler in AWS
- AWS CloudWatch metrics → rejected: expensive at high cardinality (per-endpoint-per-project)

#### AWS S3 (object storage)

**Chosen because:**
- Already widely used; familiar
- Replaces MinIO (MinIO = S3-compatible on-premise; on AWS, use real S3)
- 99.999999999% durability
- Presigned URLs for report sharing (time-limited, no public bucket needed)
- S3 lifecycle policies: auto-archive old reports to Glacier

---

### Infrastructure

#### AWS ECS Fargate (platform services)

**Chosen because:**
- Serverless containers: no EC2 to patch, resize, or manage for platform services
- Task-level auto-scaling based on SQS queue depth
- Native CloudWatch integration
- Pay per vCPU/memory per second (cost-efficient for variable workloads)

**Why EC2 for stub engines:**
- Stub EC2s need a fixed private IP for firewall rules (consuming team opens port to specific IP)
- ECS Fargate tasks get ephemeral IPs; not suitable for firewall documentation
- EC2 allows direct port mapping without ALB (lower latency for high TPS)

#### Terraform + Terragrunt

**Terraform chosen because:**
- Already standard for AWS in enterprise environments
- GitLab native integration (`gitlab-terraform` image)
- Remote state in S3 + DynamoDB lock (no Terraform Cloud needed)
- `assume_role` provider block handles cross-account deployments natively

**Terragrunt added because:**
- DRY configs across dev/test/prod (inherit common vars)
- Dependency management between modules (ECR before ECS, RDS before services)

#### Multi-Account + On-Premise Deployment

Mockingbird supports three deployment targets via the deployer-worker. The Terraform `aws` provider `assume_role` block is used for cross-account deployments:

```hcl
# Cross-account: deployer assumes role in project's account
provider "aws" {
  assume_role {
    role_arn = var.target_role_arn  # e.g., arn:aws:iam::PROJECT_ACCOUNT:role/MockingbirdDeployerRole
  }
  region = var.target_region
}
```

For **on-premise targets**, Terraform is not used. The deployer-worker uses Paramiko (Python SSH) to:
1. Transfer Docker image tar via SCP
2. `docker load` + `docker run` on the target server
3. Poll health check endpoint

**Target types stored in PostgreSQL:**

```sql
-- deployments table stores target config as JSONB
target_type:   'sv-aws' | 'project-aws' | 'on-premise'
target_config: {
  -- sv-aws / project-aws:
  "aws_account_id": "123456789012",
  "region": "eu-west-1",
  "vpc_id": "vpc-xxx",
  "subnet_id": "subnet-xxx",
  "assume_role_arn": "arn:aws:iam::123456...:role/MockingbirdDeployerRole",
  
  -- on-premise:
  "host": "10.10.20.50",
  "ssh_port": 22,
  "ssh_key_secret_id": "mockingbird/onprem/ssh-key-payments-team"
}
```

See `docs/DEPLOYMENT_ARCHITECTURE.md` for full cross-account and lifecycle details.

---

### LLM Selection

#### Claude claude-sonnet-4-6 — Primary Model for Complex Generation

**Model ID:** `claude-sonnet-4-6`

**Used for:**
- Plain English description → OpenAPI 3.0 JSON spec generation
- Complex WSDL ambiguity resolution
- Full stub set generation from natural language
- Smart data rule suggestion for entire API specs

**Why Claude over alternatives:**

| Criteria | Claude claude-sonnet-4-6 | GPT-4o | Gemini 1.5 Pro |
|----------|--------------|--------|----------------|
| Structured JSON output | Excellent | Good | Good |
| Context window | 200K tokens | 128K | 1M |
| API spec understanding | Excellent | Good | Good |
| Following format instructions | Excellent | Good | Variable |
| Cost (input/output per M tokens) | ~$3 / $15 | ~$5 / $15 | ~$3.50 / $10.50 |
| Latency (p50) | ~2s | ~3s | ~2s |
| Already in use | Yes (Claude Code) | No | No |

**Key reason:** The platform already uses Claude Code (Anthropic). Reusing the same vendor simplifies procurement, billing, and security approvals.

#### Claude claude-haiku-4-5 — Lightweight Tasks

**Model ID:** `claude-haiku-4-5-20251001`

**Used for:**
- Field name → data type inference (is "accountNumber" → NUMERIC 10 digits?)
- Stub description auto-generation
- Simple input validation feedback messages
- Pattern detection (run on each field — runs 50+ times per spec)

**Why Haiku not Sonnet:**
- 12–15x cheaper per token than Sonnet
- 3–4x faster response time
- Accuracy is sufficient for field classification (not complex reasoning)
- Scales economically as platform processes thousands of stubs per day

#### Integration Pattern

```python
# services/ai-service/app/clients/claude_client.py

from anthropic import Anthropic

client = Anthropic()  # ANTHROPIC_API_KEY from HashiCorp Vault

async def generate_openapi_from_description(description: str) -> dict:
    """Complex task: uses Sonnet 4.6"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="""You are an API specification expert for UK banking systems.
                  Generate valid OpenAPI 3.0 JSON only. No markdown. No explanations.
                  Pure JSON. Use UK banking conventions (GBP, sort codes, IBANs).""",
        messages=[{"role": "user", "content": description}]
    )
    return json.loads(response.content[0].text)


async def classify_field_type(field_name: str, sample_value: str) -> DataRule:
    """Lightweight task: uses Haiku"""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system="Classify the data generation rule. Reply with JSON only: {rule, length, format}",
        messages=[{"role": "user", "content": f"Field: {field_name}, Sample: {sample_value}"}]
    )
    return DataRule.model_validate_json(response.content[0].text)
```

---

### Monitoring & Observability

#### Three Pillars

```
METRICS:  Prometheus (stub engines) + AWS CloudWatch (platform services)
          → Grafana dashboards (embedded in portal)
          → AWS Timestream (long-term TPS/latency storage)

LOGS:     All services: structured JSON to stdout
          → AWS CloudWatch Logs (collected by ECS)
          → CloudWatch Insights for ad-hoc queries

TRACES:   AWS X-Ray (distributed tracing)
          → traces requests across API Gateway → services → SQS → workers
          → find bottlenecks in the generate/deploy pipeline
```

#### Grafana Setup

- Grafana OSS running as ECS Fargate task
- Data sources: Prometheus (stub engines) + Timestream (historical)
- Embedded in portal via iframe (authentication pass-through)
- Pre-built dashboards: per-project TPS, latency heatmap, error rates

---

### Testing Strategy

| Layer | Tool | What's Tested |
|-------|------|--------------|
| Unit | pytest (Python), Vitest (TS) | Functions, parsers, generators in isolation |
| Integration | testcontainers (Python) | Services + real DB/Redis/S3 (local Docker) |
| Contract | Pact | API contracts between portal and backend services |
| E2E | Playwright | Full user flows in real browser |
| Load | Locust | Validates 15K TPS claim on stub engines |
| Security | OWASP ZAP (in CI) | API security scanning per deployment |

---

### Monorepo Strategy

**Single GitLab repository** with service-level CI jobs:

```yaml
# .gitlab-ci.yml (root)
# Each service has its own build/test/deploy stage
# Changes to services/parser-worker/** → only triggers parser-worker pipeline
# Changes to terraform/** → triggers infra validation

stages:
  - lint
  - test
  - build
  - security-scan
  - deploy-dev
  - deploy-test
  - deploy-prod   # manual gate
```

**Why monorepo:**
- Shared types/schemas (ParsedEndpoint, WireMockMapping) imported across services
- Atomic commits spanning multiple services
- Single place for dependency updates
- Easier for a small team (1–3 developers in Phase 1–3)
- GitLab handles per-path change detection natively

**When to split:** if the team grows to 5+ squads, consider extracting high-churn services into separate repos. Phase 1–6 does not need this.
