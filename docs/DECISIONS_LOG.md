# Mockingbird — Decisions Log
## Single source of truth for all confirmed decisions and pending inputs

**Last Updated:** 2026-06-14 (Session 2 — sample files reviewed, C1/C2/I1 confirmed)

---

## PART 1 — ALL CONFIRMED DECISIONS

### Infrastructure & Deployment

| Decision | Confirmed Value | Date Confirmed |
|----------|----------------|---------------|
| AWS regions | eu-west-2 (London, PRIMARY) + eu-west-1 (Ireland, DR) | 2026-06-14 |
| Platform container platform | AWS ECS Fargate | 2026-06-12 |
| Stub server type | AWS EC2 per project (fixed IP for firewall rules) | 2026-06-12 |
| EC2 size for 10K TPS | c6i.2xlarge (8 vCPU, 16GB RAM) | 2026-06-12 |
| EC2 provisioning method | Terraform inside deployer-worker ECS task (IAM role) — no manual steps | 2026-06-14 |
| Cross-account deployment | AWS STS AssumeRole → client's `MockingbirdDeployerRole` | 2026-06-13 |
| On-premise deployment | SSH + Docker via Paramiko (Phase 4). Direct Connect exists. | 2026-06-14 |
| Container registry | **GitLab Container Registry** (NOT AWS ECR) | 2026-06-14 |
| Docker image build tool | **Kaniko** (NOT Docker-in-Docker) — k8s runners, no privileged containers | 2026-06-14 |
| GitLab type | Self-hosted, AWS-hosted Kubernetes runners | 2026-06-14 |
| IaC tool | Terraform + Terragrunt. State in S3 + DynamoDB lock | 2026-06-12 |
| CDN | AWS CloudFront → S3 (React portal) | 2026-06-12 |
| DNS | AWS Route 53 | 2026-06-12 |
| On-premise connectivity | AWS Direct Connect exists (not VPN) | 2026-06-14 |

### Application & Languages

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| Primary backend language | Python 3.11 | 2026-06-12 |
| API framework | FastAPI + Pydantic v2 | 2026-06-12 |
| Auth / notification services | Node.js 20 + Fastify | 2026-06-12 |
| Java version | **OpenJDK 21** (virtual threads, confirmed) | 2026-06-14 |
| Stub engine (primary) | Spring Boot + WireMock as embedded library (NOT standalone JAR) + Netty | 2026-06-13 |
| Stub engine (high TPS) | Hoverfly — only if > 18K TPS needed | 2026-06-13 |
| SOAP implementation | Spring-WS (NOT WireMock's SOAP mode) | 2026-06-13 |
| Kafka stubs (Phase 4+) | Spring Boot + Spring Kafka (simple) OR Microcks (AsyncAPI + Avro) | 2026-06-13 |
| IBM MQ stubs (Phase 4+) | Spring Boot + Spring JMS | 2026-06-13 |
| Frontend framework | React 18 + TypeScript strict + Vite | 2026-06-12 |
| UI components | shadcn/ui + Tailwind CSS | 2026-06-12 |
| Charts | Apache ECharts (Canvas-based, handles high data volumes) | 2026-06-12 |
| Operational dashboards | Grafana embedded in portal | 2026-06-12 |

### Data Stores

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| Primary database | **PostgreSQL 15 on AWS RDS** (Multi-AZ, eu-west-2) | 2026-06-12 |
| Why NOT MS SQL | MS SQL requires paid licence — contradicts £0 cost mission. Your organisation may use MS SQL centrally but Mockingbird is a new platform. PostgreSQL is free. | 2026-06-14 |
| Object storage | AWS S3 (eu-west-2 primary, eu-west-1 replica) | 2026-06-12 |
| Cache / sessions | AWS ElastiCache Redis 7 (cluster mode) | 2026-06-12 |
| Time-series metrics | AWS Timestream | 2026-06-12 |
| Job queue | AWS SQS (parse, generate, deploy, report queues + DLQ) | 2026-06-12 |
| Secrets management | **HashiCorp Vault (primary)** — team uses it aggressively | 2026-06-14 |
| Python Vault client | `hvac` library | 2026-06-14 |
| Java Vault client | `spring-vault-core` | 2026-06-14 |

### Dependencies & Packages

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| Artifactory base URL | `https://artifactory.internal/artifactory/dws-all-repos` | 2026-06-14 |
| Artifactory repo ID | `dws-all-fallback-zambezi-mirror` (mirrors Maven Central + all other repos) | 2026-06-14 |
| Artifactory credentials | `ARTIFACTORY_USR` + `ARTIFACTORY_PSWD` environment variables → fetched from Vault in CI | 2026-06-14 |
| Maven settings file | `settings_linux.xml` pattern (confirmed working) — must be bundled in all Java GitLab CI jobs | 2026-06-14 |
| ⚠️ CRITICAL CONSTRAINT | Artifactory is on internal network — **NOT accessible from AWS EC2** | 2026-06-14 |
| Build consequence | ALL Maven/pip/npm builds happen in GitLab CI only. EC2 only runs pre-built Docker images. | 2026-06-14 |
| Docker base images | From GitLab Container Registry (internal mirrors) — accessible from both GitLab CI AND EC2 | 2026-06-14 |

### GitLab Registry & CI

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| GitLab Container Registry URL | `registry.gitlab.internal` | 2026-06-14 |
| Java 21 base image (full path) | `registry.gitlab.internal/your-group/engineeringartifacts/executors/build/java/java-21:latest` | 2026-06-14 |
| Kaniko builder image | `registry.gitlab.internal/your-group/engineeringartifacts/executors/build/kaniko/multi-arch/v1.24:v1.24.0-debug` | 2026-06-14 |
| GitLab runner tag | `nwg-rosa-sharedrunner-scan` | 2026-06-14 |
| CI secret retrieval | Vault JWT auth (`VAULT_AUTH_PATH: jwt/gitlab`) — VAULT_ID_TOKEN auto-generated by GitLab | 2026-06-14 |
| CI includes | `Container-Scanning.gitlab-ci.yml` + `Secret-Detection.gitlab-ci.yml` (from your GitLab group's shared CI templates) | 2026-06-14 |

### HashiCorp Vault (Partially Confirmed)

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| Vault URL (dev) | `https://vault-dev-pnf.web.deviaas.intenv01.net` | 2026-06-14 |
| Vault namespace | `secrets` | 2026-06-14 |
| Vault KV mount path | `kv` | 2026-06-14 |
| Vault auth method (GitLab CI) | JWT/GitLab OIDC — `VAULT_AUTH_PATH: jwt/gitlab` | 2026-06-14 |
| Current Vault role | `performanceengineering` (existing) → Mockingbird will need its own role | 2026-06-14 |
| Docker auth secret path (example) | `performanceengineering/ci/docker` → Mockingbird: `mockingbird/ci/docker` | 2026-06-14 |
| ⚠️ Still needed | Production Vault URL (likely `vault-prd-...` format) | TBC |

### Authentication

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| Phase 1 auth | Local admin-created credentials (bcrypt) | 2026-06-14 |
| Phase 2 auth | LDAP — network login | 2026-06-14 |
| LDAP group format | `memberOf: CN=SV-Team,OU=Groups,DC=company,DC=com` | 2026-06-14 |
| LDAP role mapping | SV-Team → ADMIN, SV-Users → SV_TEAM, project groups → PROJECT_OWNER | 2026-06-14 |
| Phase 3 auth | SAML Europa SSO (additive — LDAP still works) | 2026-06-14 |
| Python LDAP library | `ldap3` (from Artifactory PyPI mirror) | 2026-06-14 |

### Monitoring & Observability

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| Application logs | **Splunk** (existing) via CloudWatch Logs → Splunk HEC | 2026-06-14 |
| Log format | Structured JSON to stdout; collected by CloudWatch | 2026-06-14 |
| APM / tracing | **AppDynamics** (existing) — Java agent in stub containers | 2026-06-14 |
| AWS alarms | CloudWatch Alarms → SNS → Slack / email | 2026-06-14 |
| Live dashboards | Grafana (embedded in portal) reading Prometheus + Timestream | 2026-06-12 |
| Stub metrics | Spring Boot Actuator `/actuator/prometheus` scraped every 30s | 2026-06-13 |
| Other available tools | DX APM, Elasticsearch also available but not primary for Mockingbird | 2026-06-14 |

### Usage & Functional Requirements

| Decision | Confirmed Value | Date |
|----------|----------------|------|
| Stubs per project | Mostly 1 (occasionally 2) | 2026-06-14 |
| TPS requirement | 10,000+ TPS per stub (c6i.2xlarge + Spring Boot Netty achieves 12K–18K) | 2026-06-14 |
| Response size | No restriction. Compression auto-enabled. Warning if size × TPS approaches bandwidth limit. | 2026-06-14 |
| Primary input formats | Raw .txt HTTP request+response (PRIMARY), .json, Postman v2.1 (with saved response examples) | 2026-06-14 |
| Slow response simulation | YES — essential feature. Fixed / random / progressive / chunked dribble delays | 2026-06-14 |
| Conditional responses | YES — essential. 200/400/404/500/fault injection via WireMock priority mappings | 2026-06-14 |
| WS-Security for SOAP | Configurable per project (some need it, some don't) | 2026-06-14 |
| Kafka / IBM MQ | Deferred to Phase 4+ | 2026-06-14 |
| On-premise deployment | Architecture supports it; implement in Phase 4 | 2026-06-14 |
| Year 1 projects | 20–30 | 2026-06-14 |
| SV team | 5 people today → plan to ramp down as platform matures | 2026-06-14 |
| Report formats | **ALL FOUR**: PDF + Excel + PowerPoint + Live Dashboard | 2026-06-14 |
| Branding | YES — all PDF and PPT reports must use your organisation's logo/colours/template | 2026-06-14 |
| Postman response examples | YES — Postman v2.1 collections DO contain saved response examples (user was unaware) | 2026-06-14 |

---

## PART 2 — PENDING INPUTS (Blocking / Important / Useful)

### 🟢 CRITICAL INPUTS — NOW CONFIRMED

| ID | What Was Needed | What Was Confirmed | Date |
|----|----------------|-------------------|------|
| C1 | GitLab Container Registry URL | `registry.gitlab.internal` ✅ | 2026-06-14 |
| C2 | Artifactory URL (Maven) | `https://artifactory.internal/artifactory/dws-all-repos` ✅ | 2026-06-14 |

### 🔴 STILL BLOCKING

| ID | What We Need | Impact if Missing | Who Provides |
|----|-------------|------------------|-------------|
| C3 | **Is PostgreSQL acceptable** for a new application, or is MS SQL mandated for all apps? | If MS SQL mandatory, switch DB before any table is created. Phase 1 (CLI) does NOT need this. | User — check with architecture/DBA team |

### 🟡 IMPORTANT — Needed before Phase 2–3 (Weeks 9–24)

| ID | What We Need | Impact | Who Provides |
|----|-------------|--------|-------------|
| I1-partial | Vault dev URL confirmed. **Still need:** production Vault URL + confirm Mockingbird can get its own Vault role (`mockingbird`) + confirm EC2 (in AWS) can reach Vault (via Direct Connect)? | Secrets in all services | Vault/security team |
| I2 | **TLS type for stubs**: Server-side TLS only (standard HTTPS), OR mutual TLS where clients also present a certificate (mTLS)? | Nginx config on every stub EC2. mTLS = client cert verification added | User — check with security team |
| I3 | **Splunk HEC endpoint** + **token** e.g. `https://splunk.mockingbird.internal:8088` + token | Log forwarding from CloudWatch to existing Splunk | User — check with Splunk/logging team |
| I4 | **AppDynamics controller hostname** + **agent key** | APM Java agent injected into stub containers | User — check with monitoring team |
| I5 | **LDAP server hostname + port** + **base DN** e.g. `ldap.mockingbird.internal:389`, `DC=company,DC=com` | LDAP authentication (Phase 2 auth service) | User — will provide when ready |
| I6 | **LDAP bind service account** username + password | Stored in Vault, used by auth-service to query LDAP | User — DevOps/AD team |

### 🟢 USEFUL — Needed before Phase 5–6 (Weeks 33–48)

| ID | What We Need | Impact |
|----|-------------|--------|
| U1 | **Branding assets**: official logo (PNG/SVG), brand hex colours, fonts, PowerPoint template | PDF and PPT report generation |
| U2 | **Internal CA certificate** (PEM format) | HTTPS on stub servers using internal CA (avoids self-signed cert warnings) |
| U3 | **Confirm on-premise deployment scope**: which teams, what OS (RHEL/Ubuntu?), Docker already installed? | Phase 4 on-prem deployment target |
| U4 | **Existing WireMock mappings**: any teams already have WireMock JSON files created manually? | Platform should import them (avoids re-work) |

---

## PART 3 — DECISIONS THAT ARE FINAL (Do Not Re-discuss)

These are closed. Do not reopen unless new hard facts change them.

| Decision | Final Answer | Reason Closed |
|----------|-------------|---------------|
| WireMock as library vs standalone JAR | Library inside Spring Boot | Artifactory — cannot add custom logic to standalone JAR |
| Docker build tool | Kaniko (not DinD) | k8s runners don't allow privileged containers |
| Container registry | GitLab Container Registry | Already uses GitLab; avoids ECR cost |
| Database choice | PostgreSQL (not MS SQL) | £0 licence cost is core requirement; pending C3 confirmation |
| Secrets | HashiCorp Vault | Team already uses it aggressively |
| Java version | OpenJDK 21 | Virtual threads mandatory for TPS targets |
| Primary AWS region | eu-west-2 (London) | UK data residency for banking |
| Stub persistence | Always in DB + S3, never only on EC2 | Enables suspend/redeploy without re-upload |
| Stub image registry | **GitLab Container Registry** (not ECR) | ECR requires IAM role creation + VPC endpoints (complex). GitLab registry already works. |
| Build location | **GitLab CI ONLY** — never on EC2 | Artifactory not reachable from EC2. EC2 only runs pre-built images. |
| EC2 Docker image pull | EC2 pulls from GitLab registry using deploy token (stored in Vault, fetched via Direct Connect) | |
| SOAP engine | Spring-WS (not WireMock SOAP) | WireMock SOAP fragile for complex enterprise WSDLs |
| EC2 provisioning | Terraform inside deployer-worker (not separate GitLab pipeline) | Simpler, faster, full audit via Terraform state |

---

## PART 4 — QUESTIONS ANSWERED (Do Not Ask Again)

| Question | Answer |
|----------|--------|
| Does your organisation use Artifactory? | YES — Maven, PyPI, npm, Docker all mirrored internally |
| Java version? | OpenJDK 21+ |
| GitLab hosted or cloud? | Self-hosted, centrally managed |
| GitLab runner type? | AWS-hosted Kubernetes pods |
| SSO type? | SSO for Europa users only. LDAP for all others. LDAP first. |
| Direct Connect? | YES — exists between AWS and on-premise |
| Response size restriction? | NO restriction — any size supported |
| Slow response simulation needed? | YES — essential. Fixed/random/progressive/chunked |
| Conditional responses (400/404/500) needed? | YES — core requirement |
| WS-Security for SOAP? | Configurable per project |
| Stubs per project? | Mostly 1 |
| TPS requirement? | 10,000+ per stub |
| Year 1 projects? | 20–30 |
| SV team size? | 5, ramping down |
| Report formats? | ALL FOUR: PDF + Excel + PowerPoint + Live Dashboard |
| Branding on reports? | YES |
| Database standard? | MS SQL/Oracle centrally — but Mockingbird uses PostgreSQL (see C3) |
| Secret management? | HashiCorp Vault (primary), AWS Secrets Manager available |
| Monitoring tools? | DX APM, AppDynamics, Splunk, Elasticsearch, CloudWatch |
| LDAP format? | `memberOf: CN=SV-Team,OU=Groups,DC=company,DC=com` |
| Kafka/IBM MQ now? | No — deferred to Phase 4+ |
| On-prem needed? | Maybe — architecture supports it, implement Phase 4 |
| Can Postman collections have response examples? | YES — Postman v2.1 stores saved responses |
| AWS regions? | eu-west-2 (primary) + eu-west-1 (DR) |
| GitLab registry URL? | `registry.gitlab.internal` |
| Artifactory URL? | `https://artifactory.internal/artifactory/dws-all-repos` |
| Artifactory credentials format? | Env vars ARTIFACTORY_USR + ARTIFACTORY_PSWD (fetched from Vault in CI) |
| Can Artifactory be reached from EC2? | NO — artifactory.internal is on the internal network only |
| Vault URL (dev environment)? | https://vault-dev-pnf.web.deviaas.intenv01.net |
| Vault auth method in GitLab CI? | JWT/OIDC — jwt/gitlab path, auto-generated VAULT_ID_TOKEN |
| Should we use ECR for stub images? | NO for now — complexity outweighs benefit. GitLab registry used throughout. |
| Java 21 Docker base image? | registry.gitlab.internal/your-group/engineeringartifacts/executors/build/java/java-21:latest |
| Kaniko image? | registry.gitlab.internal/your-group/engineeringartifacts/executors/build/kaniko/multi-arch/v1.24:v1.24.0-debug |
| GitLab runner tag? | nwg-rosa-sharedrunner-scan |
