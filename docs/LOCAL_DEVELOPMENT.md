# Local Development Guide

Everything you need to install, run, and test Mockingbird on a local machine.
No AWS account, no internal network, no Vault, no LDAP required.

---

## Service Map

| Service | Tech | Port | What it does |
|---------|------|------|-------------|
| `postgres` | PostgreSQL 15 | 5432 | Platform database |
| `redis` | Redis 7 | 6379 | Sessions + WebSocket pub/sub |
| `auth-service` | Node.js 20 + Fastify | **3001** | Login → JWT |
| `project-service` | Python 3.11 + FastAPI | **8001** | Project + stub CRUD |
| `ingestion-service` | Python 3.11 + FastAPI | **8003** | File upload + format detection |
| `ai-service` | Python 3.11 + FastAPI | **8004** | Plain-English → stub (Claude API) |
| `metrics-service` | Python 3.11 + FastAPI | **8005** | Prometheus scraper + WebSocket TPS |
| `notification-service` | Node.js 20 + Fastify | **3002** | Email / Slack / Teams webhooks |
| `portal` | React 18 + Nginx | **3000** | Self-service UI |
| `parser-worker` | Python 3.11, SQS consumer | — | Parses uploaded spec files |
| `generator-worker` | Python 3.11, SQS consumer | — | Generates stub projects |
| `deployer-worker` | Python 3.11, SQS consumer | — | Terraform + GitLab CI trigger |
| `reporter-worker` | Python 3.11, SQS consumer | — | PDF / Excel / PowerPoint reports |

**For most development work you only need:** `sv-gen` CLI (parser-worker), or the core platform (postgres + redis + auth-service + project-service).

---

## Prerequisites

Install these before starting. Check you have the minimum versions.

```bash
python --version     # 3.11 or higher
node --version       # v20.x.x or higher
docker --version     # any recent version
docker compose version   # any recent version (note: space, not hyphen)
java --version       # 21 or higher (only needed to compile/run Java stubs locally)
git --version        # any version
```

### Install guides (if missing)

| Tool | Install |
|------|---------|
| Python 3.11+ | https://www.python.org/downloads/ or `winget install Python.Python.3.11` |
| Node.js 20+ | https://nodejs.org/ or `winget install OpenJS.NodeJS.LTS` |
| Docker Desktop | https://www.docker.com/get-started/ |
| Java 21 | https://adoptium.net/ — choose "Temurin 21 (LTS)" |

---

## Option A: sv-gen CLI only (fastest — no Docker)

The `sv-gen` CLI is the core tool. It converts any API spec into a runnable stub project. It works standalone — no Docker, no database.

### Install

```bash
# From the repo root
cd services/parser-worker

# Create a virtual environment (one-time)
python -m venv venv

# Activate — Windows PowerShell:
venv\Scripts\Activate.ps1
# Activate — Windows CMD:
venv\Scripts\activate.bat
# Activate — Mac/Linux:
source venv/bin/activate

# Install sv-gen and all dependencies
pip install -e ".[dev]"

# Verify
sv-gen --version
# sv-gen, version 0.1.0
```

### Run sv-gen

```bash
# Parse + generate from any format (auto-detected)
sv-gen --input payment.txt --output ./my-stub

# Validate only (no output written)
sv-gen --input payment.txt --output ./out --dry-run

# Generate WireMock JSON files only (no Spring Boot project)
sv-gen --input payment.txt --output ./out --mappings-only

# With explicit project name and ID
sv-gen --input payment.txt --output ./out --project-name "Payment Gateway" --project-id payment-gw

sv-gen --help   # all options
```

### Run the generated stub

```bash
cd my-stub
docker compose up --build
# First build: 2-3 minutes (downloads Maven deps)
# Subsequent starts: under 10 seconds

# Test the stub
curl -X POST http://localhost:8080/payments/domestic \
  -H "Content-Type: application/json" \
  -d '{"amount": 500, "currency": "GBP"}'
```

**Stub ports:**

| URL | Purpose |
|-----|---------|
| `http://localhost:8080/` | Stub HTTP endpoints |
| `http://localhost:8081/actuator/health` | Health check |
| `http://localhost:8081/actuator/prometheus` | Prometheus metrics |

---

## Option B: Platform services via Docker Compose

Runs all platform services together. Requires Docker Desktop.

### One-time setup

```bash
# From the repo root — copy and edit the env file
cp config/example.env config/local.env
```

Open `config/local.env` and set at minimum:

```
DB_PASSWORD=any-local-password-you-choose
DATABASE_URL=postgresql://mockingbird:any-local-password-you-choose@postgres:5432/mockingbird
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
```

Leave all `CHANGE_THIS` values for AWS/GitLab/Vault — they are not needed for local development.

### Start infrastructure only (postgres + redis)

```bash
cd services
docker compose --env-file ../config/local.env up -d postgres redis
```

### Start core platform services

```bash
docker compose --env-file ../config/local.env up -d auth-service project-service
```

### Run database migrations (first time only)

```bash
docker compose --env-file ../config/local.env run --rm project-service alembic upgrade head
```

### Verify everything is running

```bash
curl http://localhost:3001/health
# {"status":"ok","service":"auth-service"}

curl http://localhost:8001/health
# {"status":"ok","service":"project-service"}
```

### Create the first admin user (first time only)

```bash
curl -X POST http://localhost:3001/api/v1/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "choose-a-strong-password"
  }'
# Returns: {"id": "...", "username": "admin", "role": "ADMIN"}
```

> This endpoint only works when the users table is empty. Calling it again returns 409.

### Log in and get a token

```bash
curl -X POST http://localhost:3001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "choose-a-strong-password"}'
# Returns: {"access_token": "eyJ...", "token_type": "Bearer"}

# Save for subsequent calls
export TOKEN="eyJ..."
```

### Use the API

```bash
# Create a project
curl -X POST http://localhost:8001/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Payment Gateway", "team": "PaymentsTeam", "environment": "TEST", "expected_tps": 10000}'

# List projects
curl http://localhost:8001/api/v1/projects \
  -H "Authorization: Bearer $TOKEN"

# Swagger UI (interactive docs)
open http://localhost:8001/docs
```

### Start optional services

```bash
# AI stub generation (requires ANTHROPIC_API_KEY in local.env)
docker compose --env-file ../config/local.env up -d ai-service

# File upload + ingestion
docker compose --env-file ../config/local.env up -d ingestion-service

# Metrics WebSocket feed
docker compose --env-file ../config/local.env up -d metrics-service

# Notifications (email/Slack/Teams — requires SMTP/webhook config)
docker compose --env-file ../config/local.env up -d notification-service
```

### Start everything at once

```bash
cd services
docker compose --env-file ../config/local.env up -d
# Note: parser-worker, generator-worker, deployer-worker, reporter-worker
#       are SQS consumers — they start but sit idle without SQS queues configured.
```

### Stop all services

```bash
docker compose --env-file ../config/local.env down        # keeps postgres data
docker compose --env-file ../config/local.env down -v     # deletes postgres data too
```

---

## Option C: Running individual services without Docker (for development)

Useful when you are actively editing a service and want fast restart.

### auth-service (Node.js)

```bash
cd services/auth-service
npm install

# Requires postgres running (use docker compose up -d postgres)
# Set env vars in your shell:
export DATABASE_URL="postgresql://mockingbird:local-dev-change-this@localhost:5432/mockingbird"
export JWT_SECRET="local-dev-change-this"
export PORT=3001

npm run dev      # ts-node, hot reload
# OR
npm run build && npm start
```

### project-service (Python/FastAPI)

```bash
cd services/project-service
python -m venv venv
venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate    # Mac/Linux
pip install -e ".[dev]"

export DATABASE_URL="postgresql://mockingbird:local-dev-change-this@localhost:5432/mockingbird"
export JWT_SECRET="local-dev-change-this"

# Run migrations first (one-time)
alembic upgrade head

# Start the server
uvicorn project_service.main:app --host 0.0.0.0 --port 8001 --reload
# Swagger UI: http://localhost:8001/docs
```

### ai-service (Python/FastAPI)

```bash
cd services/ai-service
python -m venv venv
venv\Scripts\Activate.ps1
pip install -e ".[dev]"

export ANTHROPIC_API_KEY="your-key-here"
export JWT_SECRET="local-dev-change-this"
export DATABASE_URL="sqlite:///./mockingbird_ai.db"   # SQLite is fine for local dev

uvicorn ai_service.main:app --host 0.0.0.0 --port 8004 --reload
# Swagger UI: http://localhost:8004/docs
```

### ingestion-service (Python/FastAPI)

```bash
cd services/ingestion-service
python -m venv venv
venv\Scripts\Activate.ps1
pip install -e ".[dev]"

export DATABASE_URL="postgresql://mockingbird:local-dev-change-this@localhost:5432/mockingbird"
export JWT_SECRET="local-dev-change-this"
export S3_BUCKET="mockingbird-stubs"
export AWS_REGION="eu-west-2"
# For local dev, AWS calls will fail unless you have localstack or real AWS credentials

uvicorn ingestion_service.main:app --host 0.0.0.0 --port 8003 --reload
```

---

## Running the Tests

### parser-worker (~480 tests — covers all input formats + all stub generators)

```bash
cd services/parser-worker
# Activate venv (see Option A install above)
venv\Scripts\Activate.ps1

# Run all tests
pytest

# Run with coverage
pytest --cov=src/parser_worker --cov-report=term-missing

# Run a specific test file
pytest tests/test_txt_level1.py
pytest tests/test_kafka_parser.py
pytest tests/test_mq_parser.py
pytest tests/test_asyncapi_parser.py

# Run tests matching a keyword
pytest -k "test_parse_delay"
pytest -k "kafka"

# Run only Sprint 24 (IBM MQ) tests
pytest tests/test_mq_parser.py tests/test_mq_generator.py -v
```

Test file → what it covers:

| Test file | Sprint | Covers |
|-----------|--------|--------|
| `test_txt_level1.py` | Sprint 1 | Simple TXT format |
| `test_txt_level2.py` | Sprint 1 | Multi-scenario TXT |
| `test_stateful.py` | Sprint 2 | Stateful flows |
| `test_soap.py` | Sprint 2 | SOAP/XML |
| `test_postman.py` | Sprint 3 | Postman v2.1 |
| `test_openapi.py` | Sprint 3 | OpenAPI 3.x/Swagger 2.x |
| `test_json_level3.py` | Sprint 3 | JSON Level 3 |
| `test_wiremock_generator.py` | Sprint 1-3 | WireMock JSON output |
| `test_springboot_generator.py` | Sprint 1-3 | Spring Boot project output |
| `test_kafka_parser.py` | Sprint 22 | Kafka JSON format |
| `test_kafka_generator.py` | Sprint 22 | Kafka Spring Boot project |
| `test_asyncapi_parser.py` | Sprint 23 | AsyncAPI 2.x/3.x (YAML + JSON) |
| `test_microcks_generator.py` | Sprint 23 | Microcks docker-compose output |
| `test_mq_parser.py` | Sprint 24 | IBM MQ JSON format |
| `test_mq_generator.py` | Sprint 24 | IBM MQ Spring Boot project |

### project-service (~44 tests)

```bash
cd services/project-service
# Activate venv
venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Uses SQLite in-memory — no postgres required
pytest
pytest --cov=src/project_service
```

### auth-service (~18 tests)

```bash
cd services/auth-service
npm install
npm test
npm run test:coverage
```

### ai-service

```bash
cd services/ai-service
python -m venv venv
venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

### Other Python services (ingestion, metrics, reporter, generator, deployer)

```bash
cd services/<service-name>
python -m venv venv
venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

---

## Testing the Async Stub Engines Locally

### Kafka stubs (Sprint 22)

```bash
# Generate a Kafka stub project
cat > payment-events.kafka.json << 'EOF'
{
  "_mockingbird_kafka": "1.0",
  "stubs": [
    {
      "name": "payment-processed",
      "topic": "payment.events",
      "partition": 0,
      "response_body": "{\"status\": \"PROCESSED\", \"paymentId\": \"PAY-001\"}",
      "response_headers": {"content-type": "application/json"},
      "delay_ms": 0
    }
  ]
}
EOF

sv-gen --input payment-events.kafka.json --output ./kafka-stub

# The output is a Spring Boot + Kafka project.
# To run locally you need a Kafka broker.
# Simplest option — start Kafka via Docker:
docker run -d --name kafka -p 9092:9092 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=true \
  apache/kafka:3.7.0

# Build and run the stub
cd kafka-stub
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 docker compose up --build
```

### AsyncAPI / Microcks stubs (Sprint 23)

```bash
# Create an AsyncAPI spec
cat > orders.asyncapi.yaml << 'EOF'
asyncapi: "2.6.0"
info:
  title: Orders API
  version: 1.0.0
channels:
  order/created:
    subscribe:
      message:
        contentType: application/json
        payload:
          type: object
EOF

sv-gen --input orders.asyncapi.yaml --output ./microcks-stub
# Output: docker-compose.microcks.yml + asyncapi.yaml

cd microcks-stub
docker compose -f docker-compose.microcks.yml up -d
# Microcks UI: http://localhost:8080
# Microcks API: http://localhost:9090
```

### IBM MQ stubs (Sprint 24)

```bash
# Create an IBM MQ stub spec
cat > payment-mq.mq.json << 'EOF'
{
  "_mockingbird_mq": "1.0",
  "stubs": [
    {
      "name": "payment-reply",
      "type": "consumer-reply",
      "consume_queue": "PAYMENT.REQUEST.QUEUE",
      "produce_queue": "PAYMENT.REPLY.QUEUE",
      "response_body": "{\"status\": \"PROCESSED\", \"paymentId\": \"PAY-001\"}",
      "response_properties": {"JMSType": "PaymentResponse"},
      "delay_ms": 100
    }
  ]
}
EOF

sv-gen --input payment-mq.mq.json --output ./mq-stub
# Output: Spring Boot + Spring JMS project

# To run locally you need IBM MQ. Use the free IBM MQ Developer image:
docker run -d --name ibmmq \
  -p 1414:1414 -p 9443:9443 \
  -e LICENSE=accept \
  -e MQ_QMGR_NAME=QM1 \
  icr.io/ibm-messaging/mq:latest

cd mq-stub
MQ_HOST=localhost MQ_PORT=1414 MQ_QUEUE_MANAGER=QM1 \
MQ_CHANNEL=DEV.APP.SVRCONN MQ_USER=app MQ_PASSWORD=passw0rd \
docker compose up --build

# Stub endpoints
curl http://localhost:8080/api/stubs           # list stubs
curl http://localhost:8081/actuator/health     # health check
```

---

## AI Service — Local Testing

```bash
# Requires a real ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY="sk-ant-..."

cd services/ai-service
venv\Scripts\Activate.ps1
uvicorn ai_service.main:app --port 8004 --reload

# Generate a stub from plain English
curl -X POST http://localhost:8004/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "description": "A payment API that accepts POST /payments with amount and currency, returns transactionId and status ACCEPTED",
    "format": "txt"
  }'
# Returns a .txt stub spec ready for sv-gen
```

---

## What is Pending

### Organisation-specific config (blocks production deployment — not local dev)

| Priority | Item | Needed For |
|----------|------|-----------|
| 🔴 Critical | GitLab Container Registry URL | Push built Docker images in CI |
| 🔴 Critical | Artifactory URLs (Maven, PyPI, npm, Docker) | All GitLab CI builds — local dev uses public registries |
| 🟡 Important | HashiCorp Vault endpoint + auth method | Secrets in production (local dev uses env vars) |
| 🟡 Important | LDAP server hostname + base DN | Phase 2 auth (local dev uses password auth) |
| 🟡 Important | Splunk HEC endpoint + token | Log forwarding to Splunk |
| 🟡 Important | AppDynamics agent key + controller hostname | APM in stub containers |
| 🟢 Optional | Branding assets (logo, colours, PPT template) | Phase 5 report branding |
| 🟢 Optional | Internal CA certificate | HTTPS on stub EC2 instances |

### AWS infrastructure (not yet provisioned)

- SQS queues: `mockingbird-parse-queue`, `mockingbird-generate-queue`, `mockingbird-deploy-queue`, `mockingbird-report-queue`, `mockingbird-dlq`
- S3 bucket: `mockingbird-stubs`
- RDS PostgreSQL 15 (Multi-AZ, eu-west-2)
- ElastiCache Redis 7
- Timestream database + table
- ECS cluster + task definitions for all platform services
- IAM roles: `MockingbirdDeployerRole`, `MockingbirdStubInstanceProfile`
- Terraform remote state: S3 bucket + DynamoDB lock table
- EC2 key pair: `mockingbird-key`

### Code still to wire up

| Item | Detail |
|------|--------|
| `generator-worker` MQ routing | Needs to call `generate_mq_project()` when message `engine_type == "MQ"` |
| `deployer-worker` MQ routing | MQ stubs use the existing SPRINGBOOT CI/CD path — needs engine type marker in SQS payload |
| End-to-end pipeline test | No integration test covers the full ingestion → parse → generate → deploy flow |
| Portal engine selector | UI needs fields for Kafka/MQ/AsyncAPI connection details at project creation |
| Vault integration | All services currently read secrets from env vars; Vault integration is stubbed via env vars |
| LDAP/SAML login | auth-service has the LDAP code wired; LDAP server details pending (I2 above) |

### Nice-to-have (not blocking)

- Load test baseline: confirm 10K+ TPS on actual c6i.2xlarge with WireMock engine
- Hoverfly engine integration (only needed if a project exceeds 18K TPS)
- Cross-account deploy (Terraform + STS AssumeRole) — code written, not tested against real client AWS account
- Grafana embed in portal
- Contract tests (Pact) between portal and backend

---

## Useful Commands Reference

```bash
# Check all parser-worker tests pass
cd services/parser-worker && pytest

# Check a single service's tests
cd services/auth-service && npm test
cd services/project-service && pytest
cd services/ai-service && pytest

# Generate a stub (from repo root)
cd services/parser-worker
source venv/bin/activate  # or venv\Scripts\Activate.ps1 on Windows
sv-gen --input <file> --output <dir>

# Start postgres + redis only
cd services && docker compose --env-file ../config/local.env up -d postgres redis

# Start core platform
cd services && docker compose --env-file ../config/local.env up -d postgres redis auth-service project-service

# View logs for a service
cd services && docker compose --env-file ../config/local.env logs -f auth-service

# Restart a single service
cd services && docker compose --env-file ../config/local.env restart project-service

# Destroy all containers and volumes (full reset)
cd services && docker compose --env-file ../config/local.env down -v
```
