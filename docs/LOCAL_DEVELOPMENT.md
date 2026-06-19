# Mockingbird — Local Development Guide

This guide covers two environments:

| Environment | OS | Script |
|-------------|-----|--------|
| Local laptop | Windows 10 / 11 | `setup.ps1` + `start-dev.ps1` |
| AWS EC2 / server | RHEL 9 | `setup.sh` + `start-dev.sh` |

---

## What you will have at the end

A fully running Mockingbird platform:

- Web portal at http://localhost:3000
- Login, create projects, upload spec files
- Auto-detect format, validate, generate stubs
- No Docker required
- No AWS credentials required
- Data stored locally in SQLite files

---

---

# PART A — Windows (local laptop)

---

## A1 — Install required tools (one time per machine)

You need three tools. If already installed, skip to A2.

### Python 3.11 or higher

1. Go to **https://www.python.org/downloads/**
2. Click **Download Python 3.x.x**
3. Run the installer — on the first screen **tick "Add Python to PATH"** (important)
4. Click **Install Now**

Verify in PowerShell:
```powershell
python --version
```
Expected: `Python 3.11.x` or higher

---

### Node.js 20 or higher

1. Go to **https://nodejs.org/**
2. Click the **LTS** download button
3. Run the `.msi` installer — accept all defaults

Verify:
```powershell
node --version
```
Expected: `v20.x.x` or higher

---

### Git

1. Go to **https://git-scm.com/download/win**
2. Download 64-bit installer and run it — accept all defaults

Verify:
```powershell
git --version
```

---

## A2 — Get the code (one time per machine)

```powershell
cd C:\
git clone https://github.com/ScriptSavant1/SVDemo-MockingBird.git Workspace\Mockingbird
cd C:\Workspace\Mockingbird
```

If you already have the folder, just pull latest changes:
```powershell
cd C:\Workspace\Mockingbird
git pull
```

---

## A3 — One-time setup (one time per machine)

This single script does everything automatically:

- Creates Python virtual environments (venvs) for all services
- Installs all Python packages into each venv
- Generates `requirements.txt` files for each service
- Creates the database and all tables
- Installs all Node.js packages for auth-service and portal

```powershell
cd C:\Workspace\Mockingbird
.\setup.ps1
```

**This takes about 3-5 minutes** the first time (downloading packages).

Expected final output:
```
============================================
  Setup complete. All checks passed.
============================================

Next steps:
  1. Start services:  .\start-dev.ps1
  2. Open browser:    http://localhost:3000
  3. Create admin:    see docs\LOCAL_DEVELOPMENT.md Section A5
```

If any step fails, the script tells you exactly which item is missing and exits with an error.
Fix the issue and run `.\setup.ps1` again — it skips steps already completed.

---

## A4 — Start the application (every day)

```powershell
cd C:\Workspace\Mockingbird
.\start-dev.ps1
```

Four PowerShell windows open automatically — one per service. Leave them open.

Wait about 20 seconds, then check all services are running:

```powershell
curl.exe http://localhost:3001/health
curl.exe http://localhost:8001/health
curl.exe http://localhost:8003/health
```

Each should respond with `{"status":"ok", ...}`.

Open the portal: **http://localhost:3000**

---

## A5 — First time only: create the admin account

Do this once, after the services are running for the first time.
Your account persists in the database — you do not need to do this again after a restart.

```powershell
curl.exe -X POST http://localhost:3001/api/v1/auth/setup `
  -H "Content-Type: application/json" `
  -d "{""username"":""admin"",""email"":""svtest@demo.com"",""password"":""Test1234!""}"
```

Expected response:
```json
{"id":"...","username":"admin","email":"svtest@demo.com","role":"ADMIN"}
```

> Password must be at least 8 characters. Use `Test1234!` if unsure.
>
> If you see `409 Conflict` — the admin already exists. Go ahead and log in.

---

## A6 — Stop the application

Close the four PowerShell windows that `start-dev.ps1` opened, or press **Ctrl+C** in each one.

---

## A7 — Restart after a reboot

Just run the start script again. No setup needed.

```powershell
cd C:\Workspace\Mockingbird
.\start-dev.ps1
```

All your data (users, projects, stubs) is saved in the SQLite files and will still be there.

---

---

# PART B — RHEL 9 (AWS EC2 or any Linux server)

---

## B1 — Connect to the server

```bash
ssh -i your-key.pem ec2-user@<your-ec2-ip>
```

---

## B2 — Get the code

```bash
cd ~
git clone https://github.com/ScriptSavant1/SVDemo-MockingBird.git mockingbird
cd mockingbird
```

---

## B3 — One-time setup

This single script does everything:

- Installs system packages (Python 3.11, Node.js 20, git) via `dnf`
- Creates Python virtual environments for all services
- Installs all packages and generates `requirements.txt` files
- Creates the database and tables
- Installs Node.js packages

```bash
chmod +x setup.sh
./setup.sh
```

> Requires `sudo` for system package installation. You will be prompted for your password.

Expected final output:
```
============================================
  Setup complete. All checks passed.
============================================
```

---

## B4 — Start the application

```bash
./start-dev.sh
```

All services start in the background. Logs go to the `logs/` folder.

```
logs/auth-service.log
logs/project-service.log
logs/ingestion-service.log
logs/portal.log
```

To follow a log in real time:
```bash
tail -f logs/project-service.log
tail -f logs/ingestion-service.log
```

Check health:
```bash
curl http://localhost:3001/health
curl http://localhost:8001/health
curl http://localhost:8003/health
```

Open the portal from your browser: **http://\<your-ec2-ip\>:3000**

> Make sure your EC2 security group allows inbound TCP on ports 3000, 3001, 8001, 8003 from your IP.

---

## B5 — First time only: create the admin account

```bash
curl -X POST http://localhost:3001/api/v1/auth/setup \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"svtest@demo.com","password":"Test1234!"}'
```

---

## B6 — Stop the application

Press **Ctrl+C** in the terminal running `start-dev.sh`. It stops all services together.

Or kill by port:
```bash
kill $(lsof -ti:3001) 2>/dev/null
kill $(lsof -ti:8001) 2>/dev/null
kill $(lsof -ti:8003) 2>/dev/null
kill $(lsof -ti:3000) 2>/dev/null
```

---

---

# PART C — Using the web portal

---

## C1 — Log in

Open **http://localhost:3000** (Windows) or **http://\<server-ip\>:3000** (RHEL 9).

- Username: `admin`
- Password: `Test1234!`

---

## C2 — Create a project

1. Click **New Project**
2. Fill in Project name, Team, Environment, Expected TPS
3. Click **Create**

---

## C3 — Upload a spec file

1. Click into your project
2. Click **Upload Spec**
3. Drag your file in or click to browse
4. Enter a stub name
5. Click **Upload**

The portal shows:
- Format detected (e.g. `level-1-txt`, `postman`, `openapi`)
- Number of stubs found
- Any validation errors in red — fix and re-upload if needed

---

## C4 — Generate the stub

After a successful upload, click **Generate**.

---

## C5 — Supported spec file formats

Mockingbird auto-detects the format. You do not need to tell it what you are uploading.

---

### Format 1 — Simple REST endpoint (Level 1 TXT)

One endpoint, one response. Save as `.txt`:

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

### Format 2 — Multi-scenario REST (Level 2 TXT)

One endpoint, multiple responses based on what is sent:

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
Content-Type: application/json
{"status": "ACCEPTED", "transactionId": "TXN-001"}

--- SCENARIO: wrong-currency ---
Match-Body: $.currency != "GBP"
--- RESPONSE ---
Status: 422
Content-Type: application/json
{"error": "Only GBP supported"}

--- SCENARIO: server-error ---
Match-Header: X-Force-Error: true
--- RESPONSE ---
Status: 500
{"error": "Internal server error"}
```

---

### Format 3 — Stateful multi-step (TXT)

Calls that must happen in a fixed sequence (login then get data then logout):

```
--- MOCKINGBIRD v1.0 STATEFUL ---
Stub-Name: Banking Session
Team: RetailBanking

--- STEP 1: login ---
Method: POST
URL: /auth/login
--- RESPONSE ---
Status: 200
Content-Type: application/json
{"sessionToken": "tok-abc123"}

--- STEP 2: get-account ---
Method: GET
URL: /accounts/me
--- RESPONSE ---
Status: 200
Content-Type: application/json
{"balance": 5000.00, "currency": "GBP"}

--- STEP 3: logout ---
Method: DELETE
URL: /auth/session
--- RESPONSE ---
Status: 204
```

---

### Format 4 — Postman collection

1. In Postman, right-click your collection and click **Export**
2. Choose **Collection v2.1** — make sure responses are saved inside each request
3. Save as `.json`
4. Upload the `.json` to Mockingbird

---

### Format 5 — OpenAPI / Swagger

Upload any `.yaml` or `.json` file that begins with `openapi:` or `swagger:`.

---

### Format 6 — Kafka

Save as `.json`:

```json
{
  "_mockingbird_kafka": "1.0",
  "stubs": [
    {
      "name": "payment-event",
      "topic": "payment.events",
      "response_body": "{\"status\": \"PROCESSED\", \"paymentId\": \"PAY-001\"}",
      "response_headers": {"content-type": "application/json"},
      "delay_ms": 0
    }
  ]
}
```

---

### Format 7 — IBM MQ

Save as `.json`:

```json
{
  "_mockingbird_mq": "1.0",
  "stubs": [
    {
      "name": "payment-reply",
      "type": "consumer-reply",
      "consume_queue": "PAYMENT.REQUEST.QUEUE",
      "produce_queue": "PAYMENT.REPLY.QUEUE",
      "response_body": "{\"status\": \"PROCESSED\"}",
      "response_properties": {"JMSType": "PaymentResponse"},
      "delay_ms": 100
    }
  ]
}
```

Stub types:
- **`consumer-reply`** — listens on `consume_queue`, sends reply to `produce_queue`
- **`producer`** — HTTP call triggers a message put to `produce_queue`

---

### Format 8 — AsyncAPI (Microcks)

Upload any `.yaml` or `.json` that begins with `asyncapi:`.

---

---

# PART D — Running parser tests

No services need to be running for this.

Windows:
```powershell
cd C:\Workspace\Mockingbird\services\parser-worker
.\venv\Scripts\python.exe -m pytest

# Run tests for a specific format
.\venv\Scripts\python.exe -m pytest tests\test_txt_level1.py -v
.\venv\Scripts\python.exe -m pytest tests\test_kafka_parser.py -v
.\venv\Scripts\python.exe -m pytest tests\test_mq_parser.py -v
```

RHEL 9:
```bash
cd ~/mockingbird/services/parser-worker
venv/bin/python -m pytest
venv/bin/python -m pytest tests/test_txt_level1.py -v
```

---

---

# PART E — Data locations

| What | Windows path | RHEL 9 path |
|------|-------------|-------------|
| User accounts | `services\auth-service\auth-local.db` | `services/auth-service/auth-local.db` |
| Projects and stubs | `services\project-service\mockingbird.db` | `services/project-service/mockingbird.db` |
| Upload records | `services\ingestion-service\ingestion.db` | `services/ingestion-service/ingestion.db` |
| Uploaded files | `services\ingestion-service\uploads\` | `services/ingestion-service/uploads/` |
| Service logs | shown in each open window | `logs/` folder |

To start completely fresh: delete the `.db` files and the `uploads\` folder, then repeat Section A5 / B5 to create the admin account again.

---

---

# PART F — API documentation (Swagger UI)

When services are running, open these URLs in your browser for interactive API docs:

| URL | Service |
|-----|---------|
| http://localhost:8001/docs | project-service — project and stub management |
| http://localhost:8003/docs | ingestion-service — file upload and validation |

---

---

# PART G — Troubleshooting

### `setup.ps1` says "python not found"

Python was not added to PATH during installation.
Reinstall Python — on the first screen tick **"Add Python to PATH"**.

---

### `setup.ps1` says "Activate.ps1 cannot be loaded"

Run this once and try again:
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Health check returns "connection refused"

The service on that port did not start. Check the corresponding window or log:

| Port | Where to look |
|------|--------------|
| 3001 | auth-service window (Windows) or `logs/auth-service.log` (RHEL 9) |
| 8001 | project-service window or `logs/project-service.log` |
| 8003 | ingestion-service window or `logs/ingestion-service.log` |
| 3000 | portal window or `logs/portal.log` |

Common error messages:

| Error in log | Fix |
|-------------|-----|
| `Cannot find module` | `npm install` was not run — run `.\setup.ps1` again |
| `No module named` | pip install failed — run `.\setup.ps1` again |
| `address already in use` | Something else is on that port — see below |
| `SQLITE_CANTOPEN` | Database not created — run `.\setup.ps1` again |

---

### Port already in use

Windows:
```powershell
netstat -ano | findstr :3001
# Note the PID in the last column
# Open Task Manager > Details tab > find PID > End task
```

RHEL 9:
```bash
kill $(lsof -ti:3001)
```

Replace `3001` with the port number that is blocked.

---

### Login returns 401 Unauthorized

Password must be at least 8 characters. Use `Test1234!`.

---

### Setup curl returns 409 Conflict

The admin account already exists. Log in normally — no action needed.

---

### `pip install` fails on RHEL 9 with gcc error

```bash
sudo dnf install -y gcc gcc-c++ python3.11-devel postgresql-devel
```
Then run `./setup.sh` again.

---

### Portal shows blank screen or proxy error

A backend service crashed. Check the health endpoints (A4 / B4) and read the log for the failing service.
