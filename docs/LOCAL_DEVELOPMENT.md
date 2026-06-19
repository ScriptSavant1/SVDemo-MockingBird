# Local Development Guide

---

## Web UI Quick Start

This is the main path. You upload a spec file through the browser and get a stub generated.

### What you need installed

```
Python 3.11+     python --version
Node.js 20+      node --version
Docker Desktop   docker --version
Git              git --version
```

If anything is missing:
- Python: https://www.python.org/downloads/
- Node.js: https://nodejs.org/ (choose LTS)
- Docker: https://www.docker.com/get-started/

---

### Step 1 — Copy the env file

From the repo root:

```bash
cp config/example.env config/local.env
```

Open `config/local.env` and set these three values (everything else can stay as-is for local dev):

```
DB_PASSWORD=anything-you-like
DATABASE_URL=postgresql://mockingbird:anything-you-like@postgres:5432/mockingbird
JWT_SECRET=<paste output of: python -c "import secrets; print(secrets.token_hex(32))">
```

---

### Step 2 — Start the backing services

```bash
cd services
docker compose --env-file ../config/local.env up -d localstack localstack-init postgres redis
```

This starts:
- **LocalStack** on port 4566 — local mock of AWS S3 and SQS
- **localstack-init** — creates the S3 bucket and SQS queues (runs once, exits)
- **PostgreSQL 15** on port 5432
- **Redis 7** on port 6379

Wait about 20 seconds for LocalStack to become healthy, then continue.

---

### Step 3 — Start the API services

```bash
docker compose --env-file ../config/local.env up -d auth-service project-service ingestion-service
```

This starts:
- **auth-service** on `http://localhost:3001` — login and JWT
- **project-service** on `http://localhost:8001` — project and stub records
- **ingestion-service** on `http://localhost:8003` — file upload and validation

Run migrations the first time only:

```bash
docker compose --env-file ../config/local.env run --rm project-service alembic upgrade head
```

Verify they're up:

```bash
curl http://localhost:3001/health   # {"status":"ok","service":"auth-service"}
curl http://localhost:8001/health   # {"status":"ok","service":"project-service"}
curl http://localhost:8003/health   # {"status":"ok","service":"ingestion-service"}
```

---

### Step 4 — Start the portal

```bash
cd portal
npm install    # first time only
npm run dev
```

Open your browser at **http://localhost:3000**

---

### Step 5 — First-time setup in the UI

**Create the admin account** (only needed once — this endpoint closes itself after the first user):

```bash
curl -X POST http://localhost:3001/api/v1/auth/setup \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "email": "admin@example.com", "password": "your-password"}'
```

Now log in through the browser at http://localhost:3000 using those credentials.

---

### Step 6 — Upload a spec and generate a stub

1. Click **New Project** and fill in the name and team
2. Open the project → click **Upload Spec**
3. Drag or browse to your spec file (see formats below)
4. Give the stub a name → click **Upload**
5. The UI shows format detected, stub count, and any validation errors
6. Click **Generate** — the stub project is created and stored

---

### Spec file formats you can upload

| Format | File extension | Detected by |
|--------|---------------|-------------|
| Simple HTTP pairs (Level 1) | `.txt` | `--- MOCKINGBIRD v1.0 LEVEL 1 ---` header |
| Multi-scenario (Level 2) | `.txt` | `--- MOCKINGBIRD v1.0 LEVEL 2 ---` header |
| Stateful flow | `.txt` | `--- MOCKINGBIRD v1.0 STATEFUL ---` header |
| SOAP | `.txt` | `--- MOCKINGBIRD v1.0 SOAP ---` header |
| JSON Level 3 | `.json` | `_mockingbird: "1.0"` key |
| Postman v2.1 | `.json` | `info._postman_id` key |
| OpenAPI / Swagger | `.yaml` or `.json` | `openapi:` or `swagger:` key |
| Kafka | `.json` | `_mockingbird_kafka: "1.0"` key |
| AsyncAPI (Microcks) | `.yaml` or `.json` | `asyncapi:` key |
| IBM MQ | `.json` | `_mockingbird_mq: "1.0"` key |

**Quickest test — paste this into a file called `payment.txt`:**

```
--- MOCKINGBIRD v1.0 LEVEL 1 ---
Stub-Name: Payment API
Team: PaymentsTeam
Method: POST
URL: /payments/domestic

--- REQUEST ---
Content-Type: application/json

--- RESPONSE ---
Status: 200
Content-Type: application/json

{
  "transactionId": "TXN-001",
  "status": "ACCEPTED",
  "amount": 500.00,
  "currency": "GBP"
}
```

---

### Service ports at a glance

| URL | What |
|-----|------|
| http://localhost:3000 | Portal (Web UI) |
| http://localhost:3001 | auth-service |
| http://localhost:8001 | project-service (Swagger: /docs) |
| http://localhost:8003 | ingestion-service (Swagger: /docs) |
| http://localhost:4566 | LocalStack (AWS S3 + SQS mock) |
| http://localhost:5432 | PostgreSQL |
| http://localhost:6379 | Redis |

---

### Stopping everything

```bash
cd services
docker compose --env-file ../config/local.env down        # stops containers, keeps data
docker compose --env-file ../config/local.env down -v     # stops and deletes all data
```

---

## Optional services

Start these if you need them. They are not required for basic upload and generation.

### AI stub generation (plain English → spec)

Requires an Anthropic API key. Add to `config/local.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Then:

```bash
cd services
docker compose --env-file ../config/local.env up -d ai-service
# UI: http://localhost:8004/docs
```

### Metrics and live TPS feed

```bash
docker compose --env-file ../config/local.env up -d metrics-service
# WebSocket TPS feed on ws://localhost:8005/ws/metrics/{project_id}
```

### Notifications (email / Slack / Teams)

Set `SMTP_HOST` or `SLACK_DEFAULT_WEBHOOK_URL` in `config/local.env`, then:

```bash
docker compose --env-file ../config/local.env up -d notification-service
```

### SQS workers (parse / generate / deploy / report)

These are needed for the fully automated pipeline where uploaded files are processed in the background via SQS queues. For local dev the ingestion-service calls the parser inline so you usually don't need these.

```bash
docker compose --env-file ../config/local.env up -d parser-worker generator-worker
```

---

## CLI (sv-gen) — no browser, no Docker

Use this when you want to generate a stub project directly from the command line without starting any services.

```bash
cd services/parser-worker

# One-time install
python -m venv venv
venv\Scripts\Activate.ps1        # Windows
# source venv/bin/activate        # Mac / Linux
pip install -e ".[dev]"

# Verify
sv-gen --version

# Generate a stub
sv-gen --input payment.txt --output ./my-stub

# Validate only (no files written)
sv-gen --input payment.txt --output ./out --dry-run

# Run the generated stub locally
cd my-stub
docker compose up --build
# Stub: http://localhost:8080
# Health: http://localhost:8081/actuator/health
```

---

## Running the Tests

### parser-worker (~480 tests)

Covers all input format parsers and all stub generators (WireMock, Kafka, Microcks, IBM MQ).

```bash
cd services/parser-worker
venv\Scripts\Activate.ps1        # activate venv from install above
pip install -e ".[dev]"

pytest                                             # all tests
pytest -v                                          # verbose
pytest tests/test_mq_parser.py -v                  # one file
pytest -k "kafka"                                  # keyword filter
pytest --cov=src/parser_worker --cov-report=term-missing
```

| Test file | What it covers |
|-----------|---------------|
| `test_txt_level1.py` | Simple TXT format |
| `test_txt_level2.py` | Multi-scenario TXT |
| `test_stateful.py` | Stateful flows |
| `test_soap.py` | SOAP / XML |
| `test_postman.py` | Postman v2.1 |
| `test_openapi.py` | OpenAPI 3.x / Swagger 2.x |
| `test_kafka_parser.py` + `test_kafka_generator.py` | Kafka (Sprint 22) |
| `test_asyncapi_parser.py` + `test_microcks_generator.py` | AsyncAPI / Microcks (Sprint 23) |
| `test_mq_parser.py` + `test_mq_generator.py` | IBM MQ (Sprint 24) |

### project-service (~44 tests)

Uses SQLite in-memory — no postgres needed.

```bash
cd services/project-service
python -m venv venv && venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

### auth-service (~18 tests)

```bash
cd services/auth-service
npm install
npm test
```

### Other Python services

Same pattern for any service:

```bash
cd services/<name>
python -m venv venv && venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

---

## What is Pending

### Organisation config (not needed for local dev)

| Priority | Item | Used for |
|----------|------|---------|
| 🔴 | GitLab Container Registry URL | Pushing built Docker images in CI |
| 🔴 | Artifactory URLs (Maven, PyPI, npm, Docker) | GitLab CI builds (local dev uses public registries) |
| 🟡 | HashiCorp Vault endpoint | Secrets in production (local dev uses env vars) |
| 🟡 | LDAP server hostname + base DN | Phase 2 auth (local dev uses password login) |
| 🟡 | Splunk HEC endpoint + token | Log forwarding |
| 🟡 | AppDynamics agent key | APM in stub containers |

### AWS infrastructure (not yet provisioned)

Real AWS S3, SQS, RDS, ElastiCache, ECS, Timestream, IAM roles, Terraform state bucket and lock table. LocalStack fills in for S3 and SQS in local dev.

### Code still to wire up

| Item | Detail |
|------|--------|
| generator-worker MQ routing | Needs a branch to call `generate_mq_project()` when `engine_type == "MQ"` |
| deployer-worker MQ SQS payload | MQ stubs use the same GitLab CI/Kaniko build as Kafka — needs `engine_type` field in the deploy SQS message |
| Portal engine selector | UI needs connection fields (broker host, queue names) for Kafka / MQ project creation |
| Vault integration | All services currently read secrets from env vars; Vault is wired as the production path but not yet connected |
| LDAP / SAML | auth-service code is ready; needs LDAP server details |
| End-to-end integration test | No test covers the full ingestion → parse → generate → deploy flow |
