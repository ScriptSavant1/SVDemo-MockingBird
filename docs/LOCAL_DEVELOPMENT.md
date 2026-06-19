# Local Development Guide — Windows, No Docker

---

## Prerequisites (one-time installs)

```powershell
python --version   # 3.11 or higher
node --version     # v20 or higher
```

If missing:
- Python: https://www.python.org/downloads/
- Node.js: https://nodejs.org/ (choose LTS)

---

## One-time setup — run these BEFORE start-dev.ps1

You only do this once. Each block is a separate command sequence.

**auth-service (Node.js):**
```powershell
cd C:\Workspace\Mockingbird\services\auth-service
npm install
```

**project-service (Python):**
```powershell
cd C:\Workspace\Mockingbird\services\project-service
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DATABASE_URL = "sqlite:///./mockingbird.db"
alembic upgrade head
```
> `alembic upgrade head` creates the database tables. Run it once only.

**ingestion-service (Python):**
```powershell
cd C:\Workspace\Mockingbird\services\ingestion-service
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**portal (Node.js):**
```powershell
cd C:\Workspace\Mockingbird\portal
npm install
```

> If `Activate.ps1` is blocked, run this first (once per machine):
> ```powershell
> Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

## Starting everything (every time)

From the repo root, run **one script**:

```powershell
cd C:\Workspace\Mockingbird
.\start-dev.ps1
```

This opens 4 windows automatically — one per service. You do not need to manage them manually.

Wait about 10 seconds, then open **http://localhost:3000**

---

## First time only — create the admin account

```powershell
curl.exe -X POST http://localhost:3001/api/v1/auth/setup `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","email":"svtest@demo.com","password":"Test1234!"}'
```

Expected response:
```json
{"id":"...","username":"admin","email":"svtest@demo.com","role":"ADMIN"}
```

Log in at http://localhost:3000 with `admin` / `Test1234!`

> Password must be at least 8 characters.

---

## Testing the upload flow

1. Log in to http://localhost:3000
2. Click **New Project**, fill in a name and team
3. Open the project → click **Upload Spec**
4. Upload a spec file (see formats below)
5. The UI shows: format detected, stub count, validation result
6. Click **Generate** to build the stub project

Uploaded files are saved to `services\ingestion-service\uploads\` (no S3 or Docker needed).

---

## Spec file formats

| Format | How Mockingbird detects it |
|--------|---------------------------|
| Level 1 TXT (simple) | First line: `--- MOCKINGBIRD v1.0 LEVEL 1 ---` |
| Level 2 TXT (multi-scenario) | First line: `--- MOCKINGBIRD v1.0 LEVEL 2 ---` |
| Stateful TXT | First line: `--- MOCKINGBIRD v1.0 STATEFUL ---` |
| SOAP TXT | First line: `--- MOCKINGBIRD v1.0 SOAP ---` |
| Postman v2.1 | JSON with `"info": { "_postman_id": "..." }` |
| OpenAPI / Swagger | YAML or JSON with `openapi:` or `swagger:` key |
| Kafka | JSON with `"_mockingbird_kafka": "1.0"` |
| IBM MQ | JSON with `"_mockingbird_mq": "1.0"` |
| AsyncAPI (Microcks) | YAML or JSON with `asyncapi:` key |

**Quickest test** — save this as `payment.txt` and upload it:

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

## Service ports

| URL | Service |
|-----|---------|
| http://localhost:3000 | Portal (Web UI) |
| http://localhost:3001 | auth-service |
| http://localhost:8001 | project-service (Swagger: /docs) |
| http://localhost:8003 | ingestion-service (Swagger: /docs) |

---

## Running the parser tests (no services needed)

The entire parsing and validation logic can be tested independently:

```powershell
cd C:\Workspace\Mockingbird\services\parser-worker
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"

pytest                              # all ~480 tests
pytest tests/test_txt_level1.py -v  # one format
pytest -k "kafka"                   # keyword filter
```

Or skip the UI entirely and generate stubs from the command line:

```powershell
sv-gen --input payment.txt --output C:\Temp\my-stub
sv-gen --input payment.txt --output C:\Temp\my-stub --dry-run   # validate only
```

---

## Where data is stored (SQLite files, no database server)

| File | Contains |
|------|----------|
| `services\auth-service\auth-local.db` | Users and passwords |
| `services\project-service\mockingbird.db` | Projects and stubs |
| `services\ingestion-service\ingestion.db` | Upload records |
| `services\ingestion-service\uploads\` | Uploaded spec files |

Delete these to start completely fresh.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Activate.ps1 cannot be loaded` | Run: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| Portal shows proxy error | One of the backend windows crashed — check which one and restart `.\start-dev.ps1` |
| Login fails with 401 | Password must be 8+ characters. Use `Test1234!` |
| Port already in use | Run `netstat -ano \| findstr :3001` to find the PID, then kill it in Task Manager |
| `alembic upgrade head` fails | Make sure `$env:DATABASE_URL` is set in the same terminal before running it |
| `pip install` fails with permission error | Make sure you activated the venv first (`.\venv\Scripts\Activate.ps1`) |
