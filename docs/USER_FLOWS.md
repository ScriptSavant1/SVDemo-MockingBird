# Mockingbird — User Flows & Journeys

**Version:** 1.0  
**Last Updated:** 2026-06-12

---

## Overview of User Roles

| Role | Who | What They Do |
|------|-----|-------------|
| **Project Owner** | Developer / Test Engineer | Upload specs, create projects, get stub URLs |
| **SV Team** | Service Virtualisation engineers | Admin of platform, handle complex stubs |
| **Viewer** | QA, BA, Manager | View stub status and metrics for their project |
| **Admin** | SV Team Lead / Platform Owner | Manage users, view all projects, generate exec reports |

---

## Flow 1 — New User: First Login & Project Setup

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTOR: Project Team Member (first time using Mockingbird)       │
└─────────────────────────────────────────────────────────────────┘

START
  │
  ▼
Opens Mockingbird portal URL in browser
  │
  ├─── Has bank AD account? 
  │         │
  │    YES ─▶ Click "Login with SSO"
  │              │
  │              ▼
  │         SAML/OIDC redirect → Bank Active Directory
  │              │ authenticate
  │              ▼
  │         Redirected back → JWT issued
  │              │
  │    NO  ─▶ Contact Admin to create account
  │
  ▼
Dashboard (first time — no projects yet)
  │
  │ Banner: "No projects yet. Create your first stub project."
  ▼
  │
  ▼
Click "Create New Project"
  │
  ▼
Project Setup Form:
  ┌─────────────────────────────────────────┐
  │  Project Name:      [payments-stub]     │
  │  Team / Cost Centre: [PaymentsTeam]     │
  │  Environment:       [TEST ▼]            │
  │  Expected TPS:      [1000 ▼]           │
  │  Description:       [optional]         │
  └─────────────────────────────────────────┘
  │
  ▼
Click "Create Project"
  │
  ▼
Project created → assigned project_id
  │
  ▼
Redirected to Project page → "Upload your API spec to get started"
  │
  └───► Continues to Flow 2
```

---

## Flow 2 — Core Flow: Upload Spec → Generate Stubs → Deploy

This is the primary user journey — covers 80%+ of daily usage.

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTOR: Project Owner on their project page                      │
└─────────────────────────────────────────────────────────────────┘

[STEP 1: UPLOAD]
  │
  ▼
Click "Upload Spec" button
  │
  ▼
Upload modal opens:
  ┌────────────────────────────────────────────┐
  │  Drag & drop or browse files               │
  │                                            │
  │  Supported formats:                        │
  │  • OpenAPI 3.x (YAML/JSON)                 │
  │  • Swagger 2.x (YAML/JSON)                 │
  │  • Postman Collection v2.1 (JSON)          │
  │  • WSDL 1.1/2.0 (SOAP)                     │
  │  • HAR file (browser traffic recording)    │
  │  • Bruno collection                        │
  │  • Raw HTTP request+response (TXT)         │
  │  • CSV / Excel (request-response pairs)    │
  │  • ZIP (multiple files)                    │
  └────────────────────────────────────────────┘
  │
  │ User drops: payments-api.yaml
  ▼
File uploaded to platform
  │
  ▼
AUTO-DETECTION (instant, client-side preview):
  ┌────────────────────────────────────────────┐
  │  ✓ Detected: OpenAPI 3.0                   │
  │  ✓ 12 endpoints found                      │
  │  Preview:                                  │
  │    POST /payments/domestic                 │
  │    GET  /payments/{id}                     │
  │    POST /payments/international             │
  │    ... (9 more)                            │
  └────────────────────────────────────────────┘
  │
  ├─── Looks wrong?
  │         YES → User selects type manually from dropdown
  │         NO  → Continue
  │
  ▼
Click "Parse & Preview"
  │
  ▼
Background parse job (SQS → parser-worker)
  │ Progress indicator: "Parsing... (usually < 10 seconds)"
  │
  ▼
Parse complete → Endpoint preview table:
  ┌──────────────────────────────────────────────────────────────┐
  │  Method │ Path                    │ Stub Type  │ Action       │
  │─────────┼─────────────────────────┼────────────┼──────────────│
  │  POST   │ /payments/domestic      │ Dynamic ▼  │ ✎ Edit      │
  │  GET    │ /payments/{id}          │ Static ▼   │ ✎ Edit      │
  │  POST   │ /payments/international │ Dynamic ▼  │ ✎ Edit      │
  │  DELETE │ /payments/{id}          │ Static ▼   │ ✎ Edit      │
  │  ...    │ ...                     │ ...        │ ...          │
  └──────────────────────────────────────────────────────────────┘
  │
  │ User can:
  ├── Change stub type (Static / Dynamic / Stateful / Fault)
  ├── Edit individual endpoint response in inline editor
  ├── Add custom data rules (e.g., "account number = 10 digits")
  └── Remove endpoints they don't need
  │
  ▼

[STEP 2: GENERATE]
  │
  ▼
Click "Generate Stubs"
  │
  ▼
Background generation job (SQS → generator-worker)
  │ Progress bar: "Generating WireMock mappings... (usually < 30 seconds)"
  │
  ▼
Generation complete → Stub Library:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Stub Library (12 stubs generated)                               │
  │                                                                  │
  │  ▶ POST /payments/domestic           [Active] [Edit] [Preview]  │
  │  ▶ GET  /payments/{id}               [Active] [Edit] [Preview]  │
  │  ▶ POST /payments/international      [Active] [Edit] [Preview]  │
  │  ...                                                             │
  │                                                                  │
  │  [Deploy All →]   [Export as ZIP]   [Re-generate]               │
  └──────────────────────────────────────────────────────────────────┘
  │
  │ User can preview each stub's WireMock JSON:
  │   { "request": {...}, "response": {...} }
  │ User can edit response body, status code, headers inline
  │
  ▼

[STEP 3: DEPLOY]
  │
  ▼
Click "Deploy to TEST"
  │
  ▼
Deploy confirmation modal:
  ┌──────────────────────────────────────────────┐
  │  Deploying: payments-stub                    │
  │  Environment: TEST                           │
  │  Engine: WireMock (auto-selected)            │
  │  Instance: c6i.xlarge (based on 1000 TPS)   │
  │  Estimated cost: ~£100/month                 │
  │                                              │
  │  [Confirm Deploy]  [Cancel]                  │
  └──────────────────────────────────────────────┘
  │
  ▼
Deploy job triggered (SQS → deployer-worker)
  │
  ▼
Deploy status page (live updates via WebSocket):
  ┌──────────────────────────────────────────────┐
  │  Deploy Status                               │
  │                                              │
  │  ✓  Building Docker image          00:12     │
  │  ✓  Pushing to ECR                 00:45     │
  │  ⟳  Provisioning EC2 (Terraform)   01:30...  │
  │  ○  Health check                             │
  │  ○  Registering stub URL                     │
  └──────────────────────────────────────────────┘
  │
  ▼ (typically 3–5 minutes total)
Deploy complete:
  ┌──────────────────────────────────────────────┐
  │  ✓ LIVE: payments-stub (TEST)                │
  │                                              │
  │  Stub URL:  https://10.x.x.x:8080           │
  │  API Key:   mk_live_xxxxxxxxxxxxxxxxxx       │
  │                                              │
  │  [Copy URL]  [Download Firewall Doc]         │
  │  [View Metrics]  [Share with Team]           │
  └──────────────────────────────────────────────┘
  │
  ▼
Email/Slack notification sent to project owner and team

END: Consuming team can now hit https://10.x.x.x:8080/payments/domestic
```

---

## Flow 3 — Monitoring & Metrics

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTOR: Project Owner or Viewer, checking their stub's health   │
└─────────────────────────────────────────────────────────────────┘

START: Project page → Click "Metrics" tab
  │
  ▼
Live Dashboard loads:
  ┌──────────────────────────────────────────────────────────────────┐
  │  payments-stub — LIVE METRICS                         TEST        │
  │                                                                  │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
  │  │Current   │ │Peak TPS  │ │P95 Lat.  │ │Error     │           │
  │  │TPS       │ │          │ │          │ │Rate      │           │
  │  │ 847      │ │ 1,203    │ │ 12ms     │ │ 0.02%    │           │
  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
  │                                                                  │
  │  [Live 60s ▼] [1h] [24h] [7d] [30d]   [Export PNG]            │
  │                                                                  │
  │  TPS over time chart (ECharts real-time line)                   │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━         │
  │                                                                  │
  │  Per-Endpoint Breakdown:                                        │
  │  POST /payments/domestic    → 643 TPS  P95: 8ms                │
  │  GET  /payments/{id}        → 154 TPS  P95: 5ms                │
  │  POST /payments/international→ 50 TPS  P95: 35ms               │
  └──────────────────────────────────────────────────────────────────┘
  │
  │ User can:
  ├── Switch to historical view (loads from Timestream)
  ├── Export chart as PNG
  ├── Filter by specific endpoint
  └── Set TPS alert threshold (notify if TPS > X)
```

---

## Flow 4 — Management Report Generation

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTOR: SV Team Lead / Admin generating monthly exec report     │
└─────────────────────────────────────────────────────────────────┘

START: Platform Dashboard → "Reports" tab
  │
  ▼
Reports Page:
  ┌─────────────────────────────────────────────┐
  │  Generate Report                            │
  │                                             │
  │  Report Type: [Executive Summary ▼]         │
  │  Period:      [Last 30 days ▼]             │
  │  Format:      [PDF ▼] [Excel] [JSON]        │
  │  Scope:       [All Projects ▼]             │
  │                                             │
  │  [Generate Now]  [Schedule (weekly)]        │
  └─────────────────────────────────────────────┘
  │
  ▼
Report generated (background job, ~30 seconds)
  │
  ▼
Report ready notification (email + in-app):
  ┌─────────────────────────────────────────────┐
  │  Executive Summary — June 2026              │
  │                                             │
  │  ✓ 47 projects served                       │
  │  ✓ 284 stubs active                         │
  │  ✓ 1.2 billion requests processed           │
  │  ✓ Platform availability: 99.97%            │
  │  ✓ Estimated license saving: £108,000/yr    │
  │                                             │
  │  [Download PDF]  [View in Portal]           │
  │  [Share Link]  (expires in 7 days)          │
  └─────────────────────────────────────────────┘
  
Report types available:
  ├── Executive Summary    → CTO / Head of Testing (non-technical)
  ├── Project Report       → Project team (per-endpoint detail)
  ├── Platform Audit       → Compliance / Security (who did what)
  └── Cost Report          → Finance (EC2 hours × rate vs CA/IBM)
```

---

## Flow 5 — Admin: User & Platform Management

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTOR: Admin / SV Team Lead                                     │
└─────────────────────────────────────────────────────────────────┘

Admin Dashboard shows:
  ┌──────────────────────────────────────────────────────────────────┐
  │  PLATFORM OVERVIEW                                               │
  │                                                                  │
  │  Active Projects: 47    Total Stubs: 284    Live EC2s: 38        │
  │  Today's Requests: 4.2M   Platform TPS (now): 1,847              │
  │  Failed Jobs: 0   Pending Jobs: 2   Alerts: 1                    │
  │                                                                  │
  │  RECENT ACTIVITY                       SYSTEM HEALTH             │
  │  ─────────────                         ─────────────             │
  │  09:12 - team-A deployed new stub      RDS:       ✓ HEALTHY      │
  │  08:45 - team-B uploaded OpenAPI       Redis:     ✓ HEALTHY      │
  │  08:30 - admin generated exec report   SQS depth: 2 messages     │
  │  ...                                   All EC2s:  38/38 live      │
  └──────────────────────────────────────────────────────────────────┘

Admin actions available:
  ├── USER MANAGEMENT
  │     Create / deactivate users
  │     Assign roles (Admin / SV_Team / ProjectOwner / Viewer)
  │     View user activity log
  │     Manage team assignments
  │
  ├── PROJECT MANAGEMENT
  │     View all projects (any team)
  │     Force-redeploy any project
  │     Emergency stub disable (kill switch)
  │     Archive stale projects
  │
  ├── SYSTEM OPERATIONS
  │     View dead-letter queue (failed jobs)
  │     Retry failed jobs
  │     View all Terraform apply logs
  │     EC2 cost summary by project
  │
  └── REPORTING
        Generate platform-wide reports
        Configure email report schedules
        Manage report sharing links
```

---

## Flow 6 — Dynamic Stub with Data Rules (Advanced)

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTOR: Project Owner who needs dynamic/conditional stubs       │
└─────────────────────────────────────────────────────────────────┘

After parsing endpoints (Flow 2, Step 1), for a dynamic endpoint:
  │
  ▼
User clicks "Edit" on: POST /accounts/create
  │
  ▼
Stub Editor opens (full-page modal):
  ┌──────────────────────────────────────────────────────────────────┐
  │  Stub Editor — POST /accounts/create                            │
  │                                                                  │
  │  REQUEST MATCHING                                               │
  │  ─────────────────                                              │
  │  Method: POST    URL: /accounts/create   [exact ▼]             │
  │  Headers: Content-Type = application/json                       │
  │  Body match: [contains JSON ▼]  { "accountType": ... }         │
  │                                                                  │
  │  RESPONSE CONFIGURATION                                         │
  │  ──────────────────────                                         │
  │  Status: 201    Delay: 50ms (fixed ▼)                           │
  │                                                                  │
  │  Response Body:                          DATA RULES             │
  │  {                                       ────────────           │
  │    "accountNumber": "...",               accountNumber          │
  │    "sortCode": "...",                    → NUMERIC 8 digits ✎   │
  │    "iban": "...",                        sortCode               │
  │    "createdAt": "..."                    → NUMERIC 6 digits ✎   │
  │  }                                       iban                   │
  │                                          → UK IBAN format ✎     │
  │  [AI Suggest Rules] ← uses Claude        createdAt             │
  │                                          → ISO timestamp ✎      │
  │                                                                  │
  │  STUB TYPE: ● Dynamic  ○ Static  ○ Stateful  ○ Fault           │
  │                                                                  │
  │  [Save]  [Preview Generated WireMock JSON]  [Cancel]            │
  └──────────────────────────────────────────────────────────────────┘

"AI Suggest Rules" button:
  │
  ▼
Claude API call: analyse field names in response body
  │
  ▼
Auto-detects and pre-fills data rules:
  accountNumber → detected as "bank account number" → NUMERIC 8 digits
  sortCode      → detected as "UK sort code" → NUMERIC 6 digits, formatted XX-XX-XX
  iban          → detected as "IBAN" → UK IBAN format GB29NWBK60161331926819
  createdAt     → detected as "timestamp" → ISO 8601 format
```

---

## Flow 7 — AI-Assisted Stub Creation (Phase 7)

```
┌─────────────────────────────────────────────────────────────────┐
│  ACTOR: Developer who has no spec file — describes API in words │
└─────────────────────────────────────────────────────────────────┘

Project page → "Create Stub" → Choose "Describe in Plain English"
  │
  ▼
AI Stub Assistant opens:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Describe what API you want to stub:                            │
  │                                                                  │
  │  "I need a UK domestic payment API stub. POST /payments with    │
  │   fromAccount, toAccount, amount in GBP and reference.          │
  │   Return a transactionId (TXN- prefix), status SUCCESS,         │
  │   timestamp. If amount > 50000, return status PENDING_REVIEW."  │
  │                                                                  │
  │  [Generate Stub →]                                              │
  └──────────────────────────────────────────────────────────────────┘
  │
  ▼
Claude claude-sonnet-4-6 generates OpenAPI 3.0 JSON from description
  │
  ▼
Standard parse → generate flow runs automatically
  │
  ▼
User sees generated stubs (including conditional logic for > £50,000)
  │
  ▼
User reviews, adjusts, deploys → same as Flow 2
```

---

## Input Format Reference

### What files Mockingbird accepts

| Format | File Type | Example Use Case |
|--------|-----------|-----------------|
| OpenAPI 3.x | `.yaml`, `.json` | Team has a proper API spec |
| Swagger 2.x | `.yaml`, `.json` | Older API spec |
| Postman Collection v2.1 | `.json` | Team uses Postman for development |
| WSDL 1.1 / 2.0 | `.wsdl`, `.xml` | SOAP API stubs |
| HAR file | `.har` | Captured real browser/app traffic |
| Bruno collection | `.bru` | Team uses Bruno API client |
| Raw HTTP pairs | `.txt` | Plain text request + response examples |
| CSV / Excel | `.csv`, `.xlsx` | Request-response pairs in spreadsheet |
| AsyncAPI | `.yaml`, `.json` | Kafka / async event stubs |
| ZIP | `.zip` | Multiple files at once |

### Raw HTTP Pair format (simplest input)

```
POST /api/payments/domestic
Content-Type: application/json
Authorization: Bearer {{token}}

{"fromAccount":"12345678","toAccount":"87654321","amount":500.00,"currency":"GBP"}

---RESPONSE---
HTTP/1.1 201 Created
Content-Type: application/json

{"transactionId":"TXN-ABC123","status":"SUCCESS","timestamp":"2026-06-12T09:00:00Z"}
```

### CSV format

```csv
method,path,request_body,response_status,response_body
POST,/payments/domestic,{"fromAccount":"12345678"},201,{"transactionId":"TXN-001"}
GET,/payments/TXN-001,,200,{"status":"SUCCESS","amount":500.00}
GET,/payments/TXN-999,,404,{"error":"NOT_FOUND"}
```
