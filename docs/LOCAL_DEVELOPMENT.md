# Mockingbird — Local Development Setup Guide

This guide walks you through every step to get Mockingbird running on your Windows laptop.
Follow every step in order. Do not skip anything.

---

## What you will have at the end

A working Mockingbird platform running entirely on your laptop — no internet connection to AWS
needed, no company infrastructure required. You will be able to:

- Log in to the Mockingbird web portal
- Create a project
- Upload a spec file (any supported format)
- See it validated and parsed
- Generate a stub
- Run tests against the generated stub

---

## Section 1 — Install the required tools (one-time, per machine)

You need four tools installed before you can do anything else. If you already have them,
skip to the check step to confirm the versions are new enough.

---

### 1.1 — Check what you already have

Open **PowerShell** (press `Windows key`, type `powershell`, press Enter) and run:

```powershell
python --version
node --version
git --version
```

**What you should see:**

```
Python 3.11.x   ← must be 3.11 or higher (3.12 is fine too)
v20.x.x         ← must be v20 or higher
git version 2.x.x
```

If you see an error or a version that is too old, install the tools below.

---

### 1.2 — Install Python (if missing or below 3.11)

1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **Download Python 3.x.x** button
3. Run the downloaded `.exe`
4. On the first screen, **tick "Add Python to PATH"** — this is important
5. Click **Install Now**
6. When finished, close and reopen PowerShell, then run `python --version` to confirm

---

### 1.3 — Install Node.js (if missing or below v20)

1. Go to **https://nodejs.org/**
2. Click the **LTS** (Long Term Support) button to download
3. Run the downloaded `.msi`
4. Accept all defaults, click Next through all screens
5. When finished, close and reopen PowerShell, then run `node --version` to confirm

---

### 1.4 — Install Git (if missing)

1. Go to **https://git-scm.com/download/win**
2. Download the 64-bit installer and run it
3. Accept all defaults throughout the installer
4. When finished, close and reopen PowerShell, then run `git --version` to confirm

---

### 1.5 — Allow PowerShell to run scripts

By default Windows blocks `.ps1` script files. Run this once to allow them:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

When prompted, type `Y` and press Enter.

---

## Section 2 — Get the code (one-time, per machine)

### 2.1 — Clone the repository

```powershell
cd C:\
git clone https://github.com/ScriptSavant1/SVDemo-MockingBird.git Workspace\Mockingbird
```

This downloads all the code into `C:\Workspace\Mockingbird`.

If you already have the folder, skip this step and just make sure you have the latest code:

```powershell
cd C:\Workspace\Mockingbird
git pull
```

---

## Section 3 — One-time setup (per machine, run once only)

You must complete all four setup blocks below before starting the application for the first time.
Each block installs the packages for one service. You only ever need to do this once per machine.

Open a **new PowerShell window** for each block, or run them one after another in the same window.

---

### 3.1 — Set up auth-service (login and user management)

```powershell
cd C:\Workspace\Mockingbird\services\auth-service
npm install
```

**What this does:** Downloads the Node.js packages that auth-service needs.

**Expected output:** A long list of packages downloading, ending with something like:
```
added 312 packages in 45s
```

If you see `npm warn` messages, that is fine — ignore them.
If you see `npm error`, stop and check your Node.js installation.

---

### 3.2 — Set up project-service (projects and stubs database)

Run each line one at a time:

```powershell
cd C:\Workspace\Mockingbird\services\project-service
```

```powershell
python -m venv venv
```
> **What this does:** Creates an isolated Python environment called `venv` inside the project-service folder.
> You will see a new folder `C:\Workspace\Mockingbird\services\project-service\venv` appear.

```powershell
.\venv\Scripts\Activate.ps1
```
> **What this does:** Switches your terminal to use the isolated Python environment.
> Your prompt will change to start with `(venv)` — this tells you it worked.
> If this fails, go back to step 1.5 and run the `Set-ExecutionPolicy` command.

```powershell
pip install -e ".[dev]"
```
> **What this does:** Installs all Python packages project-service needs.
> **Expected output:** A long list ending with `Successfully installed ...`

```powershell
$env:DATABASE_URL = "sqlite:///./mockingbird.db"
alembic upgrade head
```
> **What this does:** Creates the database file (`mockingbird.db`) and sets up all the tables inside it.
> **Expected output:**
> ```
> INFO  [alembic.runtime.migration] Running upgrade  -> 001, initial schema
> ```

---

### 3.3 — Set up ingestion-service (file upload and validation)

```powershell
cd C:\Workspace\Mockingbird\services\ingestion-service
```

```powershell
python -m venv venv
```

```powershell
.\venv\Scripts\Activate.ps1
```
> Your prompt will change to `(venv)`.

```powershell
pip install -e ".[dev]"
```
> **Expected output:** Ends with `Successfully installed ...`

---

### 3.4 — Set up the portal (web UI)

```powershell
cd C:\Workspace\Mockingbird\portal
npm install
```

**Expected output:** Ends with `added N packages in Xs`

---

### 3.5 — Verify setup completed

After completing all four blocks above, confirm the key files exist:

```powershell
Test-Path C:\Workspace\Mockingbird\services\auth-service\node_modules
Test-Path C:\Workspace\Mockingbird\services\project-service\venv
Test-Path C:\Workspace\Mockingbird\services\ingestion-service\venv
Test-Path C:\Workspace\Mockingbird\portal\node_modules
Test-Path C:\Workspace\Mockingbird\services\project-service\mockingbird.db
```

Every line should print `True`. If any print `False`, repeat the setup for that service.

---

## Section 4 — Start the application

### 4.1 — Run the startup script

Open PowerShell, navigate to the repo root, and run:

```powershell
cd C:\Workspace\Mockingbird
.\start-dev.ps1
```

**What happens:** Four new PowerShell windows open automatically, one for each service.
You do not need to do anything in those windows — just leave them open.

```
Window 1 → auth-service     (port 3001)
Window 2 → project-service  (port 8001)
Window 3 → ingestion-service (port 8003)
Window 4 → portal           (port 3000)
```

**Wait about 30 seconds** for all services to finish starting.

---

### 4.2 — Confirm all services are running

Open a new PowerShell window and run these checks one at a time:

```powershell
curl.exe http://localhost:3001/health
```
Expected: `{"status":"ok","service":"auth-service"}`

```powershell
curl.exe http://localhost:8001/health
```
Expected: `{"status":"ok","service":"project-service"}`

```powershell
curl.exe http://localhost:8003/health
```
Expected: `{"status":"ok","service":"ingestion-service"}`

If any check fails, look at the corresponding window for error messages.
Common causes are listed in the Troubleshooting section at the end of this document.

---

## Section 5 — First-time only: create the admin account

This step only needs to be done **once ever** — the account is saved in the database and
persists across restarts.

Open a PowerShell window and run:

```powershell
curl.exe -X POST http://localhost:3001/api/v1/auth/setup `
  -H "Content-Type: application/json" `
  -d "{""username"":""admin"",""email"":""svtest@demo.com"",""password"":""Test1234!""}"
```

**Expected response:**
```json
{"id":"...","username":"admin","email":"svtest@demo.com","role":"ADMIN","created_at":"..."}
```

> **Important:** The password must be at least 8 characters. `Test1234!` works.
>
> This endpoint only works **once** — when there are no users in the database yet.
> If you run it again you will get a 409 (conflict) error — that is expected and means
> the admin already exists.

---

## Section 6 — Use the web portal

### 6.1 — Open the portal

Open your browser and go to: **http://localhost:3000**

You will see the Mockingbird login screen.

---

### 6.2 — Log in

- **Username:** `admin`
- **Password:** `Test1234!`

Click **Sign In**.

---

### 6.3 — Create a project

1. Click **New Project** (top right or main dashboard button)
2. Fill in:
   - **Project name** — e.g. `Payment Tests`
   - **Team** — e.g. `QA`
   - **Environment** — e.g. `TEST`
   - **Expected TPS** — e.g. `1000`
3. Click **Create**

---

### 6.4 — Upload a spec file

1. Click into the project you just created
2. Click **Upload Spec**
3. Drag your spec file into the upload area, or click to browse
4. Optionally type a **Stub name**
5. Click **Upload**

The portal will show:
- The **format** that was detected (e.g. `level-1-txt`)
- The **number of stubs** found
- Any **validation errors** (in red) — fix your file and re-upload if there are errors

---

### 6.5 — Generate the stub

After a successful upload, click **Generate**.

The stub project is built and saved to:
```
C:\Workspace\Mockingbird\services\ingestion-service\uploads\stubs\
```

---

## Section 7 — Spec file formats

Mockingbird auto-detects the format from the file content. You do not need to tell it what format you are using.

### Format 1 — Simple REST (Level 1 TXT)

For a single endpoint with one response. Create a `.txt` file:

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

For endpoints that return different responses depending on what is sent:

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

### Format 3 — Stateful multi-step TXT

For flows where calls must happen in a specific order (e.g. login → get data → logout):

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

Export a collection from Postman (with saved responses):

1. In Postman, right-click your collection → **Export**
2. Choose **Collection v2.1**
3. Save as `.json`
4. Upload that `.json` file to Mockingbird

---

### Format 5 — OpenAPI / Swagger

Upload any `.yaml` or `.json` file that starts with `openapi:` or `swagger:`.

---

### Format 6 — Kafka

Create a `.json` file with this structure:

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

Create a `.json` file with this structure:

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

Two stub types:
- **`consumer-reply`** — listens on `consume_queue`, replies to `produce_queue`
- **`producer`** — HTTP trigger puts a message on `produce_queue`

---

### Format 8 — AsyncAPI (Microcks, for Avro/event schemas)

Upload any `.yaml` or `.json` file that starts with `asyncapi:`.

---

## Section 8 — Stopping the application

To stop Mockingbird, close the four PowerShell windows that `start-dev.ps1` opened.

Or press `Ctrl + C` inside each of the four windows.

---

## Section 9 — Restarting after a reboot

After your laptop restarts, just run the startup script again:

```powershell
cd C:\Workspace\Mockingbird
.\start-dev.ps1
```

You do **not** need to repeat Section 3 (one-time setup). Your data (users, projects, stubs)
is saved in the SQLite database files and will still be there.

---

## Section 10 — Where files are saved

| What | Where |
|------|-------|
| User accounts | `services\auth-service\auth-local.db` |
| Projects and stub records | `services\project-service\mockingbird.db` |
| Upload records | `services\ingestion-service\ingestion.db` |
| Uploaded spec files | `services\ingestion-service\uploads\` |

To start completely fresh (wipe all data), delete these files and the `uploads` folder,
then repeat Section 5 (create admin account).

---

## Section 11 — Running tests (for the parser engine)

The parsing and validation engine can be tested entirely from the command line.
No services need to be running for this.

```powershell
cd C:\Workspace\Mockingbird\services\parser-worker
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Run all tests (about 480 tests)
pytest

# Run tests for one specific format
pytest tests\test_txt_level1.py -v
pytest tests\test_kafka_parser.py -v
pytest tests\test_mq_parser.py -v

# Validate a file without the web UI
sv-gen --input C:\path\to\payment.txt --output C:\Temp\my-stub --dry-run
```

---

## Section 12 — API documentation (Swagger UI)

When the services are running, these URLs show interactive API documentation:

| URL | Service |
|-----|---------|
| http://localhost:8001/docs | project-service — project and stub management |
| http://localhost:8003/docs | ingestion-service — file upload |

You can use these pages to call the API directly from your browser without writing any code.

---

## Section 13 — Troubleshooting

### PowerShell says "cannot be loaded because running scripts is disabled"

Run this once and try again:
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### One of the health checks returns "connection refused"

The service for that port failed to start. Look at the corresponding window:
- Port 3001 → auth-service window
- Port 8001 → project-service window
- Port 8003 → ingestion-service window
- Port 3000 → portal window

Read the error message in that window. Common causes:

| Error in the window | Fix |
|--------------------|-----|
| `Cannot find module` | `npm install` was not run for that service. Go to Section 3 and redo that step. |
| `No module named` | `pip install -e ".[dev]"` was not run. Go to Section 3 and redo that step. |
| `address already in use` | Something else is using that port. See "Port already in use" below. |
| `Error: SQLITE_CANTOPEN` | The database folder does not exist. Run `alembic upgrade head` for project-service (Section 3.2). |

---

### Login returns 401 Unauthorized

Your password may not meet the minimum length. The setup endpoint requires **at least 8 characters**.

Use `Test1234!` as the password.

---

### The setup curl command returns 409

This means the admin account already exists. You can log in normally — no need to run setup again.

---

### Port already in use (address already in use)

Find what is using the port and stop it. For example for port 3001:

```powershell
netstat -ano | findstr :3001
```

This shows a PID (process ID) in the last column. Open **Task Manager** (`Ctrl+Shift+Esc`),
go to the **Details** tab, find that PID, right-click it → **End task**.

Then run `.\start-dev.ps1` again.

---

### `pip install` fails with permission error

Make sure the venv is activated. Your prompt should start with `(venv)`.
If it does not, run `.\venv\Scripts\Activate.ps1` first.

---

### `alembic upgrade head` says "No such table" after running

This is expected — alembic creates the tables, it does not expect them to exist first.
If alembic itself errors, check that `$env:DATABASE_URL` was set in the same terminal
before running `alembic upgrade head`:

```powershell
echo $env:DATABASE_URL
```

If it prints nothing, run:
```powershell
$env:DATABASE_URL = "sqlite:///./mockingbird.db"
alembic upgrade head
```

---

### The portal shows a blank screen or "Vite proxy error"

One of the backend services crashed or did not start. Check all four health checks from Section 4.2.
Restart the failed service by running `.\start-dev.ps1` again (it opens new windows — close the old ones first).

---

### `python` command not found

Python was not added to the system PATH during installation. Fix:
1. Open the Python installer again
2. Choose **Modify**
3. On the next screen, tick **Add Python to environment variables**
4. Click **Install**
5. Close and reopen PowerShell
