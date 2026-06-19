# Local Development Guide — Windows, No Docker

You need **4 PowerShell terminals** open at the same time. Start them in the order below.

---

## Prerequisites (one-time)

Make sure these are installed:

```powershell
python --version   # must be 3.11 or higher
node --version     # must be v20 or higher
git --version      # any version
```

---

## Terminal 1 — auth-service (login + JWT)

```powershell
cd C:\Workspace\Mockingbird\services\auth-service
npm install
npm run dev
```

Expected output (last line):
```
auth-service listening on 0.0.0.0:3001
```

> **What it does:** Creates `auth-local.db` (SQLite) in the current folder automatically.
> No PostgreSQL, no Docker needed.

---

## Terminal 2 — project-service (projects and stubs database)

```powershell
cd C:\Workspace\Mockingbird\services\project-service
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Set SQLite as the database (no PostgreSQL needed)
$env:DATABASE_URL = "sqlite:///./mockingbird.db"

# Create the database tables (run once only)
alembic upgrade head

# Start the service
uvicorn project_service.main:app --host 0.0.0.0 --port 8001 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8001
```

> Swagger UI available at http://localhost:8001/docs

---

## Terminal 3 — ingestion-service (file upload + validation)

```powershell
cd C:\Workspace\Mockingbird\services\ingestion-service
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# SQLite for the database, local folder for uploaded files (no S3 needed)
$env:DATABASE_URL = "sqlite:///./ingestion.db"
$env:LOCAL_STORAGE_PATH = ".\uploads"
$env:JWT_SECRET = "local-dev-secret"

uvicorn ingestion_service.main:app --host 0.0.0.0 --port 8003 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8003
```

> Uploaded files are saved to `services\ingestion-service\uploads\`

---

## Terminal 4 — portal (Web UI)

```powershell
cd C:\Workspace\Mockingbird\portal
npm install   # first time only
npm run dev
```

Expected output:
```
  VITE v5.x  ready in ...ms
  Local:   http://localhost:3000/
```

Open **http://localhost:3000** in your browser.

---

## First-time: Create the admin account

Run this **once only** (open a 5th PowerShell tab, or use any of the above after the service starts):

```powershell
curl.exe -X POST http://localhost:3001/api/v1/auth/setup `
  -H "Content-Type: application/json" `
  -d '{"username": "admin", "email": "svtest@demo.com", "password": "Test1234!"}'
```

> **Note on password:** The setup endpoint requires minimum 8 characters.
> Your earlier attempt used `"password": "test"` which is only 4 characters — that's why it failed.

Expected response:
```json
{"id":"...","username":"admin","email":"svtest@demo.com","role":"ADMIN"}
```

After this, go to http://localhost:3000 and log in with `admin` / `Test1234!`.

---

## Testing the upload flow

### What to upload

Create a file called `payment.txt` on your desktop:

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

### Steps in the portal

1. **Log in** at http://localhost:3000
2. Click **New Project** — fill in name (`Payment Tests`) and team (`QA`)
3. Open the project → click **Upload Spec**
4. Drag `payment.txt` into the upload zone (or click to browse)
5. Optionally give it a stub name → click **Upload**
6. The UI shows:
   - Format detected: `level-1-txt`
   - Stub count: `1`
   - Validation: ✅ Valid
7. Click **Generate** — the stub project is built in the background

### What "Generate" produces

A complete Spring Boot + WireMock project stored in:
```
services\ingestion-service\uploads\stubs\<project-id>\<stub-id>\
```

This is your runnable stub. To run it locally (if you have Docker):
```powershell
cd services\ingestion-service\uploads\stubs\<project-id>\<stub-id>\source
docker compose up --build
# Stub runs at http://localhost:8080
```

---

## Input file formats you can test

| Format | How to detect it |
|--------|-----------------|
| Level 1 TXT (simple) | Header line: `--- MOCKINGBIRD v1.0 LEVEL 1 ---` |
| Level 2 TXT (multi-scenario) | Header line: `--- MOCKINGBIRD v1.0 LEVEL 2 ---` |
| Stateful TXT | Header line: `--- MOCKINGBIRD v1.0 STATEFUL ---` |
| SOAP TXT | Header line: `--- MOCKINGBIRD v1.0 SOAP ---` |
| Postman v2.1 | JSON with `"info": { "_postman_id": "..." }` |
| OpenAPI / Swagger | YAML/JSON with `openapi:` or `swagger:` at the top |
| Kafka | JSON with `"_mockingbird_kafka": "1.0"` |
| IBM MQ | JSON with `"_mockingbird_mq": "1.0"` |
| AsyncAPI (Microcks) | YAML/JSON with `asyncapi:` at the top |

---

## Testing validation (invalid file on purpose)

Upload a blank `.txt` file or a file with a typo in the header — the UI will show the validation errors returned by the parser.

You can also test the validation API directly:

```powershell
# First get a token
$resp = curl.exe -s -X POST http://localhost:3001/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"Test1234!"}'
$token = ($resp | ConvertFrom-Json).access_token

# Upload a file (replace <project-id> with your actual project UUID from the portal)
curl.exe -X POST http://localhost:8003/api/v1/projects/<project-id>/stubs/upload `
  -H "Authorization: Bearer $token" `
  -F "stub_name=My Payment Stub" `
  -F "file=@C:\Users\karrir\Desktop\payment.txt"
```

Response shows format detected, stub count, any errors.

---

## Running the parser tests (no services needed)

The parser can be tested entirely from the command line — no auth, no database, no upload:

```powershell
cd C:\Workspace\Mockingbird\services\parser-worker
.\venv\Scripts\Activate.ps1   # if not already activated
pip install -e ".[dev]"

# Run all ~480 tests
pytest

# Run tests for a specific format
pytest tests/test_txt_level1.py -v
pytest tests/test_kafka_parser.py -v
pytest tests/test_mq_parser.py -v

# Generate a stub directly from the command line (skip the UI entirely)
sv-gen --input C:\Users\karrir\Desktop\payment.txt --output C:\Temp\my-stub
```

---

## Stopping everything

Press `Ctrl+C` in each terminal.

Data is saved in:
- `services\auth-service\auth-local.db` — users (SQLite)
- `services\project-service\mockingbird.db` — projects and stubs (SQLite)
- `services\ingestion-service\ingestion.db` — ingestion records (SQLite)
- `services\ingestion-service\uploads\` — uploaded spec files

Delete these files to start fresh.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `npm run dev` fails with `cannot find module` | Run `npm install` first |
| `Activate.ps1` is blocked by PowerShell | Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| Port 3001 / 8001 / 8003 already in use | Find the process: `netstat -ano \| findstr :3001` → kill it in Task Manager |
| `alembic upgrade head` fails | Make sure `$env:DATABASE_URL` is set in the same terminal before running it |
| Login fails with 401 | Password must be at least 8 characters. Try `Test1234!` |
| Portal shows proxy error | One of the backend services (3001, 8001, 8003) is not running |
| `pip install` fails | Make sure Python virtual environment is activated (you should see `(venv)` in the prompt) |
