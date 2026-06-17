# Mockingbird — Service Virtualisation Platform

> **Replacing CA LISA + IBM Rational Test Workbench with open-source tooling.**  
> NatWest / RBS Group | £0 licence cost | 10,000+ TPS per stub

---

## What is Mockingbird?

When a software team at NatWest needs to test their application, they often depend on other APIs that may not be ready, unstable, or too expensive to call in bulk. A **service stub** (also called a "mock") is a fake version of that API — it returns realistic responses, behaves like the real thing, but is fully controlled and can handle millions of test requests per second.

Today the SV (Service Virtualisation) team at NatWest creates these stubs **manually**, using paid tools (CA LISA, IBM Rational Test Workbench) that cost over £100,000 a year in licences.

**Mockingbird automates the entire process:**

```
A developer uploads their API spec (a text file or Postman export)
                          ↓
        Mockingbird reads it and generates a stub
                          ↓
  One click → stub is deployed to AWS and running in 4 minutes
                          ↓
   The team gets a URL. Their fake API handles 10,000+ requests/second.
                          ↓
   When the project is done, suspend it (costs stop).
   When the next release comes, redeploy in 4 minutes — no re-upload needed.
```

**Business impact:**
- Eliminates £100,000+/year in licence fees
- Reduces stub creation from 2–3 hours to 2 minutes
- SV team of 5 can support 100+ projects without adding headcount
- Works for REST, SOAP, Kafka, IBM MQ

---

## Current Status

| What | Status |
|------|--------|
| `sv-gen` CLI — parse any API spec, generate a stub | ✅ **Ready to use** |
| Advanced stubs — dynamic data, delays, stateful flows, fault injection | ✅ **Ready** |
| SOAP + WS-Security + WSDL support | ✅ **Ready** |
| Platform backend — project-service, auth-service | ✅ Written, Phase 3 in progress |
| Auto-deploy to AWS EC2 with Terraform | ❌ Phase 4 — not yet built |
| React self-service portal | ❌ Phase 6 — not yet built |
| Kafka / IBM MQ stubs | ❌ Phase 7 — not yet built |

**446 tests passing.** The CLI tool (`sv-gen`) is fully functional today.

---

## Prerequisites

You need these installed before you start. Minimum versions are important.

| Tool | Version | Why | Install |
|------|---------|-----|---------|
| Python | 3.11 or higher | Runs the parser and platform services | [python.org](https://www.python.org/downloads/) |
| Node.js | 20 or higher | Runs the auth-service | [nodejs.org](https://nodejs.org/) |
| Docker + Docker Compose | Latest | Runs the generated stubs and platform | [docker.com](https://www.docker.com/get-started/) |
| Java | 21 | Required only if building the Spring Boot stub without Docker | [adoptium.net](https://adoptium.net/) |
| Git | Any | Version control | [git-scm.com](https://git-scm.com/) |

> **Not sure if you have these?** Open a terminal and run the checks below.

```bash
python --version        # should say Python 3.11.x or higher
node --version          # should say v20.x.x or higher
docker --version        # any recent version
docker compose version  # any recent version
java --version          # should say 21.x.x or higher
```

---

## Part 1 — Using the `sv-gen` CLI (Ready Today)

This is the core tool. It takes any API spec file and generates a fully working stub project.

### Step 1: Install sv-gen

```bash
# Clone the repository
git clone git@github.com:ScriptSavant1/SVDemo-MockingBird.git
cd SVDemo-MockingBird

# Install sv-gen (creates a virtual environment first — recommended)
cd services/parser-worker
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install sv-gen and its dependencies
pip install -e ".[dev]"

# Verify the install worked
sv-gen --version
# Should print: sv-gen, version 0.1.0
```

### Step 2: Create your first stub

Create a file called `payment.txt` with this content — this is the simplest input format:

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

Now generate the stub:

```bash
sv-gen --input payment.txt --output ./my-payment-stub
```

You will see:

```
  Reading: payment.txt
  VALID   [level-1-txt]  1 stub(s), 1 scenario(s)

  Generated Spring Boot project → ./my-payment-stub/
  1 stub(s)   1 scenario(s)

  To build and run locally:
    cd ./my-payment-stub
    docker compose up --build
```

### Step 3: Run the stub

```bash
cd my-payment-stub
docker compose up --build
```

Docker will build and start the stub. The first build takes 2–3 minutes (downloads dependencies). After that, subsequent starts are under 10 seconds.

Once running:

```bash
# Call your stub
curl -X POST http://localhost:8080/payments/domestic \
  -H "Content-Type: application/json" \
  -d '{"amount": 500, "currency": "GBP"}'
```

Response:
```json
{
  "transactionId": "TXN-001",
  "status": "ACCEPTED",
  "amount": 500.00,
  "currency": "GBP"
}
```

**The stub handles 10,000+ requests per second.** Run your load tests against it freely.

Useful endpoints on the running stub:

| URL | Purpose |
|-----|---------|
| `http://localhost:8080/{your-path}` | The stub itself |
| `http://localhost:8081/actuator/health` | Health check |
| `http://localhost:8081/actuator/prometheus` | Metrics (Prometheus format) |

### All sv-gen options

```bash
# Validate a file without generating anything
sv-gen --input payment.txt --output ./out --dry-run

# Generate only the WireMock JSON files (skip the Spring Boot project)
sv-gen --input payment.txt --output ./out --mappings-only

# Set a custom project name and ID
sv-gen --input payment.txt --output ./out --project-name "Payment Gateway" --project-id payment-gw

# See all options
sv-gen --help
```

---

## Input File Formats

Mockingbird accepts five different input formats — it auto-detects the format from the file content.

### Format 1: Level 1 — Simple (single scenario)

Best for: simple GET/POST endpoints with one response.

```
--- MOCKINGBIRD v1.0 LEVEL 1 ---
Stub-Name: Customer API
Team: CustomerTeam
Method: GET
URL: /customers/{customerId}

--- REQUEST ---
Accept: application/json

--- RESPONSE ---
Status: 200
Content-Type: application/json

{
  "id": "{{request.pathParam.customerId}}",
  "name": "John Smith",
  "accountNumber": "12345678"
}
```

The `{{request.pathParam.customerId}}` placeholder automatically echoes the ID from the URL into the response.

### Format 2: Level 2 — Multi-scenario (different responses per condition)

Best for: endpoints that return 200, 404, or 500 depending on what you send.

```
--- MOCKINGBIRD v1.0 LEVEL 2 ---
Stub-Name: Payment API
Team: PaymentsTeam
Method: POST
URL: /payments/domestic

--- SCENARIO: success ---
Match-Body: $.currency == "GBP"
--- RESPONSE ---
Status: 200
{ "status": "ACCEPTED" }

--- SCENARIO: wrong-currency ---
Match-Body: $.currency != "GBP"
--- RESPONSE ---
Status: 422
{ "error": "Only GBP supported" }

--- SCENARIO: server-error ---
Match-Header: X-Force-Error: true
--- RESPONSE ---
Status: 500
Delay: 2000ms
Fault: connection-reset
```

### Format 3: Stateful (multi-step flows)

Best for: login → get data → logout flows where each call must happen in order.

```
--- MOCKINGBIRD v1.0 STATEFUL ---
Stub-Name: Banking Session
Team: RetailBanking

--- STEP 1: login ---
Method: POST
URL: /auth/login
--- RESPONSE ---
Status: 200
{ "sessionToken": "tok-abc123" }

--- STEP 2: get-account ---
Method: GET
URL: /accounts/me
--- RESPONSE ---
Status: 200
{ "balance": 5000.00 }

--- STEP 3: logout ---
Method: DELETE
URL: /auth/session
--- RESPONSE ---
Status: 204
```

### Format 4: SOAP

Best for: XML/SOAP web services.

See [docs/input-formats/examples/customer-soap.txt](docs/input-formats/examples/customer-soap.txt) for a full example.

### Format 5: Postman Collection (v2.1)

Export a collection from Postman (with saved responses) and point sv-gen at it:

```bash
sv-gen --input MyCollection.postman_collection.json --output ./my-stub
```

### Format 6: OpenAPI / Swagger

Point sv-gen at any OpenAPI 3.x or Swagger 2.x file:

```bash
sv-gen --input payment-api.yaml --output ./payment-stub
sv-gen --input customer-api.json --output ./customer-stub
```

---

## Available Response Features

These features work in all TXT input formats.

### Dynamic data (Handlebars templates)

| Template | What it outputs |
|----------|----------------|
| `{{request.pathParam.id}}` | The value from the URL path, e.g. `/customers/123` → `"123"` |
| `{{request.body.[fieldName]}}` | A field from the JSON request body |
| `{{request.header.X-Correlation-Id}}` | A request header value |
| `{{now}}` | Current timestamp |
| `{{now offset='5 days'}}` | 5 days from now |
| `{{randomValue type='UUID'}}` | A random UUID |
| `{{randomValue type='ALPHANUMERIC' length=10}}` | Random 10-character string |

### Response delays

Add a `Delay:` line before the response body:

```
Delay: 500ms            # Always wait 500ms
Delay: 200ms-2000ms     # Random between 200ms and 2 seconds
Delay: chunked 500ms    # Dribble the response in 500ms chunks (simulates slow network)
```

### Fault injection

Add a `Fault:` line to simulate network failures:

```
Fault: connection-reset       # TCP connection reset mid-response
Fault: empty-response         # Server closes connection with no response
Fault: malformed-response     # Sends invalid HTTP (tests client error handling)
```

You can combine delay + fault:

```
Delay: 5000ms
Fault: connection-reset
```

This simulates: "connection times out after 5 seconds."

---

## Part 2 — Running the Platform Services (Phase 3, In Progress)

The platform services (auth-service, project-service) provide a shared backend for teams to manage stubs centrally. They are fully written and tested but require Phase 4 (auto-deploy) to be complete before they are useful for end users.

### Prerequisites for platform services

Make sure Docker is running. Then:

```bash
cd SVDemo-MockingBird/services
```

### Start all platform services

```bash
docker compose up -d postgres redis
docker compose up -d auth-service project-service
```

This starts:
- **PostgreSQL 15** on `localhost:5432`
- **Redis 7** on `localhost:6379`
- **auth-service** on `http://localhost:3001`
- **project-service** on `http://localhost:8001`

### Run database migrations (first time only)

After the first `docker compose up`, run the Alembic migration to create all database tables:

```bash
docker compose run --rm project-service alembic upgrade head
```

### Verify everything is running

```bash
curl http://localhost:3001/health
# {"status":"ok","service":"auth-service","version":"0.1.0"}

curl http://localhost:8001/health
# {"status":"ok","service":"project-service","version":"0.1.0"}
```

### Create the first admin user (first time only)

```bash
curl -X POST http://localhost:3001/api/v1/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@yourcompany.com",
    "password": "your-secure-password"
  }'
```

> **Security note:** The `setup` endpoint only works when the users table is empty. After the first admin is created, it returns 409 (conflict) — no second admin can be created this way.

### Log in and get a token

```bash
curl -X POST http://localhost:3001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-secure-password"}'
```

Response includes an `access_token`. Use it as a Bearer token for all other API calls:

```bash
export TOKEN="paste-token-here"

# Create a project
curl -X POST http://localhost:8001/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Payment Gateway",
    "team": "PaymentsTeam",
    "environment": "TEST",
    "expected_tps": 10000
  }'

# List all projects
curl http://localhost:8001/api/v1/projects \
  -H "Authorization: Bearer $TOKEN"
```

---

## Project Structure

```
SVDemo-MockingBird/
│
├── README.md                          ← You are here
├── START_HERE.md                      ← Session resume doc (for AI pair programming)
├── CLAUDE.md                          ← AI context file (tech stack, conventions)
├── PHASES.md                          ← Full 7-phase roadmap
│
├── docs/
│   ├── ARCHITECTURE.md                ← System + AWS architecture diagrams
│   ├── DECISIONS_LOG.md               ← Every confirmed decision
│   ├── DEPLOYMENT_ARCHITECTURE.md     ← EC2 provisioning + project lifecycle
│   ├── FINAL_ARCHITECTURE.md          ← Consolidated architecture reference
│   ├── IMPLEMENTATION_PLAN.md         ← Sprint-level breakdown
│   ├── TECH_STACK.md                  ← Why each technology was chosen
│   └── input-formats/
│       ├── GUIDE.md                   ← Input format reference guide
│       ├── templates/                 ← Blank templates to copy and fill in
│       └── examples/                  ← Filled examples for each format
│
├── services/
│   ├── docker-compose.yml             ← Runs all platform services locally
│   │
│   ├── parser-worker/                 ← sv-gen CLI + parsers (Phase 1+2 COMPLETE)
│   │   ├── pyproject.toml             ← pip install -e ".[dev]"
│   │   ├── src/parser_worker/
│   │   │   ├── cli.py                 ← sv-gen entry point
│   │   │   ├── detector.py            ← Auto-detects input format
│   │   │   ├── models.py              ← ParsedFile, ParsedStub, Scenario data models
│   │   │   ├── parsers/               ← One file per format
│   │   │   │   ├── txt_level1.py      ← Level 1 simple TXT
│   │   │   │   ├── txt_level2.py      ← Level 2 multi-scenario TXT
│   │   │   │   ├── soap_txt.py        ← SOAP TXT format
│   │   │   │   ├── stateful_txt.py    ← Stateful multi-step TXT
│   │   │   │   ├── json_level3.py     ← JSON Level 3 format
│   │   │   │   ├── postman.py         ← Postman v2.1 collections
│   │   │   │   └── openapi.py         ← OpenAPI 3.x + Swagger 2.x
│   │   │   ├── generator/
│   │   │   │   ├── wiremock.py        ← Generates WireMock JSON mappings
│   │   │   │   └── springboot.py      ← Generates Spring Boot project
│   │   │   └── templates/             ← Spring Boot project template files
│   │   └── tests/                     ← 384 tests (pytest)
│   │
│   ├── auth-service/                  ← Login + JWT (Phase 3, written)
│   │   ├── package.json               ← Node.js 20 + Fastify v4
│   │   ├── tsconfig.json
│   │   ├── Dockerfile
│   │   ├── src/
│   │   │   ├── app.ts                 ← Fastify app factory
│   │   │   ├── server.ts              ← HTTP listener entry point
│   │   │   ├── routes/
│   │   │   │   ├── auth.ts            ← POST /login, GET /me
│   │   │   │   └── users.ts           ← POST /users, GET /users (admin only)
│   │   │   ├── plugins/
│   │   │   │   ├── jwt.ts             ← JWT sign/verify
│   │   │   │   └── database.ts        ← PostgreSQL connection
│   │   │   └── types/index.ts         ← TypeScript type definitions
│   │   └── tests/auth.test.ts         ← 18 Jest tests
│   │
│   └── project-service/               ← Project + stub CRUD (Phase 3, written)
│       ├── pyproject.toml             ← Python 3.11 + FastAPI
│       ├── Dockerfile
│       ├── alembic.ini                ← Database migration config
│       ├── alembic/
│       │   ├── env.py                 ← Reads DATABASE_URL from settings
│       │   └── versions/
│       │       └── 001_initial_schema.py  ← Creates all 6 tables
│       ├── src/project_service/
│       │   ├── config.py              ← Settings from environment variables
│       │   ├── database.py            ← SQLAlchemy engine + session
│       │   ├── models.py              ← ORM models (users, projects, stubs, etc.)
│       │   ├── schemas.py             ← Pydantic request/response schemas
│       │   ├── dependencies.py        ← JWT auth, RBAC decorators
│       │   ├── main.py                ← FastAPI app factory
│       │   └── routers/
│       │       ├── projects.py        ← CRUD for projects
│       │       └── stubs.py           ← CRUD for stubs
│       └── tests/                     ← 44 tests (pytest)
│
└── stub-engine/                       ← Reference Spring Boot stub engine
    ├── pom.xml                        ← Maven — all deps from Artifactory
    ├── Dockerfile
    ├── docker-compose.yml
    └── src/main/java/...              ← WireMockConfig, StubApplication
```

---

## Running the Tests

### parser-worker (384 tests — Phase 1 + Phase 2)

```bash
cd services/parser-worker

# Activate virtual environment if not already active
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

# Run all tests
pytest

# Run a specific test file
pytest tests/test_txt_level1.py

# Run with coverage report
pytest --cov=src/parser_worker --cov-report=term-missing

# Run a specific test by name
pytest -k "test_parse_delay"
```

### project-service (44 tests — Phase 3)

```bash
cd services/project-service

# Create and activate virtual environment
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (uses SQLite in-memory — no PostgreSQL needed)
pytest
```

### auth-service (18 tests — Phase 3)

```bash
cd services/auth-service

# Install Node dependencies (first time only)
npm install

# Run tests (no PostgreSQL needed — uses in-memory mock)
npm test

# Run with coverage
npm run test:coverage
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  MOCKINGBIRD PLATFORM (single EC2 — t3.2xlarge — eu-west-2)     │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ auth-service│  │project-service│  │ Other platform        │   │
│  │ Node.js 20  │  │ Python/FastAPI│  │ services (Phase 3-5)  │   │
│  │ Port: 3001  │  │ Port: 8001   │  │ ingestion, parser,    │   │
│  └─────────────┘  └──────────────┘  │ generator, deployer   │   │
│         │                │           └───────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  PostgreSQL 15 (RDS Multi-AZ)  │  Redis 7 (ElastiCache) │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                               │
                    Terraform provisions
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Stub EC2 #1    │  │  Stub EC2 #2    │  │  Stub EC2 #3    │
│  Payment API    │  │  Customer API   │  │  Fraud Check    │
│  Spring Boot    │  │  Spring Boot    │  │  Spring Boot    │
│  WireMock       │  │  WireMock       │  │  WireMock       │
│  10,000+ TPS    │  │  10,000+ TPS    │  │  10,000+ TPS    │
│  c6i.2xlarge    │  │  c6i.2xlarge    │  │  c6i.2xlarge    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Key design principle:** Each stub EC2 is completely independent. If the Mockingbird platform machine goes down for maintenance, all deployed stubs keep running at full TPS. The platform is for management and deployment only — not in the test path.

**Stub lifecycle:**
```
DRAFT → READY → DEPLOYING → LIVE → SUSPENDED → (REDEPLOY) → LIVE
                                       ↑
                            EC2 terminated (cost stops)
                            but stub config stays in DB + S3 forever.
                            Redeploy = 4 minutes, no re-upload.
```

---

## Configuration Reference

### Environment Variables

These are set in `services/docker-compose.yml` for local development. In production (AWS ECS), they are injected from HashiCorp Vault — never stored in code.

| Variable | Service | What it is | Default (local dev) |
|----------|---------|------------|---------------------|
| `DATABASE_URL` | auth-service, project-service | PostgreSQL connection string | `postgresql://mockingbird:dev-postgres-password@postgres:5432/mockingbird` |
| `JWT_SECRET` | auth-service, project-service | Secret key for JWT signing | `dev-jwt-secret-change-in-production` |
| `JWT_ALGORITHM` | project-service | JWT algorithm | `HS256` |
| `PORT` | auth-service | HTTP port | `3001` |
| `ENVIRONMENT` | project-service | Environment name | `local` |

> **Important:** The `JWT_SECRET` must be the **same value** in both auth-service and project-service. auth-service signs tokens with it; project-service verifies them.

### Changing from local defaults for production

1. Generate a strong JWT secret: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Store it in HashiCorp Vault
3. Configure ECS task definitions to read from Vault at startup
4. Never put the real secret in docker-compose.yml or any code file

---

## User Roles

| Role | What they can do |
|------|----------------|
| `ADMIN` | Create users, manage all projects, full system access |
| `SV_TEAM` | Create and manage projects and stubs |
| `PROJECT_OWNER` | Manage their own project's stubs (Phase 6+) |
| `VIEWER` | Read-only access to see projects and metrics |

Phase 1 (current): admin creates all users manually via the API.  
Phase 2: NatWest LDAP login — your network username works automatically.  
Phase 3 (Weeks 39+): Europa SSO for single sign-on.

---

## API Reference

### auth-service (port 3001)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Health check |
| `POST` | `/api/v1/auth/setup` | None | Create first admin (only when users table is empty) |
| `POST` | `/api/v1/auth/login` | None | Login — returns JWT access token |
| `GET` | `/api/v1/auth/me` | Bearer token | Current user info |
| `POST` | `/api/v1/users` | ADMIN only | Create a new user |
| `GET` | `/api/v1/users` | ADMIN only | List all users |

### project-service (port 8001)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Health check |
| `POST` | `/api/v1/projects` | SV_TEAM or ADMIN | Create project |
| `GET` | `/api/v1/projects` | Any auth | List projects (paginated) |
| `GET` | `/api/v1/projects/{id}` | Any auth | Get project details |
| `PUT` | `/api/v1/projects/{id}` | SV_TEAM or ADMIN | Update project |
| `DELETE` | `/api/v1/projects/{id}` | ADMIN only | Delete project |
| `POST` | `/api/v1/projects/{id}/stubs` | SV_TEAM or ADMIN | Add stub to project |
| `GET` | `/api/v1/projects/{id}/stubs` | Any auth | List stubs |
| `GET` | `/api/v1/projects/{id}/stubs/{stub_id}` | Any auth | Get stub |
| `DELETE` | `/api/v1/projects/{id}/stubs/{stub_id}` | SV_TEAM or ADMIN | Delete stub |

Full Swagger UI is available at `http://localhost:8001/docs` when project-service is running.

---

## Roadmap

| Phase | Timeline | What Gets Built |
|-------|----------|----------------|
| ✅ Phase 1 | Weeks 1–8 | `sv-gen` CLI, all input format parsers |
| ✅ Phase 2 | Weeks 9–16 | Dynamic data, stateful flows, SOAP, fault injection |
| 🔄 Phase 3 | Weeks 17–24 | Platform backend: auth, projects DB, file upload, SQS queues, LDAP |
| ❌ Phase 4 | Weeks 25–32 | Auto-deploy: one click → EC2 running in 4 minutes via Terraform |
| ❌ Phase 5 | Weeks 33–38 | Metrics + PDF/Excel/PowerPoint reports |
| ❌ Phase 6 | Weeks 39–48 | React self-service portal (any team can create stubs themselves) |
| ❌ Phase 7 | Weeks 49–56 | Kafka stubs, IBM MQ stubs, AI stub generation (plain English → stub) |

See [PHASES.md](PHASES.md) for detailed sprint-by-sprint breakdown.

---

## Pending Configuration (NatWest-specific)

These items are needed before connecting to the NatWest internal network. They do not affect local development.

| Priority | Item | Needed For |
|----------|------|-----------|
| 🔴 Critical | GitLab Container Registry URL | Docker push/pull in CI |
| 🔴 Critical | Artifactory URLs (Maven, PyPI, npm, Docker) | All builds in GitLab CI |
| 🔴 Critical | PostgreSQL confirmed (vs MS SQL mandate) | DB setup |
| 🟡 Important | HashiCorp Vault endpoint + auth method | Secrets in all services |
| 🟡 Important | LDAP server hostname + base DN | Phase 3 Sprint 12 |
| 🟡 Important | Splunk HEC endpoint + token | Log forwarding |
| 🟡 Important | AppDynamics agent key + controller hostname | APM in stub containers |
| 🟢 Useful | NatWest branding assets (logo, colours, PPT template) | Phase 5 reports |
| 🟢 Useful | Internal NatWest CA certificate | HTTPS on stub EC2s |

---

## Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Stub engine | Spring Boot 3 + WireMock (Netty) | 12,000–18,000 TPS; supports SOAP; runs as embedded library (Artifactory-friendly) |
| Java version | OpenJDK 21 | Virtual threads — the key to 10K+ TPS on a single server |
| CLI tool | Python 3.11 + Click | Fast development, excellent file parsing libraries |
| Platform API | Python 3.11 + FastAPI | Auto-generates Swagger docs; Pydantic validation |
| Auth service | Node.js 20 + Fastify | Fastest Node.js HTTP framework; TypeScript strict mode |
| Database | PostgreSQL 15 (AWS RDS) | Zero licence cost; SQLAlchemy ORM works with both Postgres and SQLite (tests) |
| Job queue | AWS SQS | Fully managed; no ops overhead |
| Cache | Redis 7 (AWS ElastiCache) | Sessions, WebSocket pub/sub, API cache |
| Container builds | Kaniko | Required for Kubernetes CI runners in banks (no privileged Docker-in-Docker) |
| IaC | Terraform | EC2 provisioning runs inside a deployer ECS task — no manual AWS steps |
| Frontend | React 18 + TypeScript + Vite (Phase 6) | shadcn/ui components; Apache ECharts for live TPS |

---

## Contributing

This project is built by a single engineer at NatWest with Claude as an AI pair programmer.

**Adding a new input format:**

1. Create `services/parser-worker/src/parser_worker/parsers/your_format.py`
2. Implement the `BaseParser` interface from `parsers/base.py`
3. Register it in `detector.py`
4. Add test file `tests/test_your_format.py`

The plugin design means no existing code changes — zero risk to existing parsers.

**Coding conventions:**
- Python: type hints on every function, Pydantic v2 models, no `Any`, PEP 8
- TypeScript: strict mode, no `any`, named exports
- API errors: RFC 7807 Problem JSON format
- Tests: one test file per source file, fixtures not hardcoded values
- Secrets: never in code — always HashiCorp Vault

---

## Licence

Internal NatWest / RBS Group project. Not for external distribution.

All dependencies are open-source (MIT/Apache 2.0) — zero licence cost is a core requirement of this project.
