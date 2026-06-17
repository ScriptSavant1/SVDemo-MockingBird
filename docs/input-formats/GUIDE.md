# Mockingbird — Input File Guide
## How to Define Your API Stub in 5 Minutes

**Last Updated:** 2026-06-14  
**Version:** 1.0

---

## What Is a Stub Definition File?

A stub definition file tells Mockingbird:
- What HTTP requests to intercept (method + URL + headers)
- What response to return (status code + body + delay)
- What different scenarios to handle (success / error / timeout)

You upload one file → Mockingbird validates it → generates and deploys a live API endpoint that your test systems can call.

---

## Which Format Should I Use?

```
Do you have a running API you can call right now?
        │
        ├── YES → Use Postman to send the request, save the response, export as Postman Collection v2.1
        │         → Upload the .json Postman collection file
        │
        └── NO → Do you need multiple scenarios (success + errors)?
                        │
                        ├── NO (just one response) → Use Level 1: Simple TXT
                        │
                        ├── YES, few scenarios → Use Level 2: Multi-Scenario TXT
                        │
                        └── YES, with dynamic values (echo request in response) → Use Level 3: JSON
```

---

## Level 1 — Simple HTTP (TXT)

**Best for:** Teams who just need a single response. Simplest possible format. No conditions.

**Template:** `templates/level-1-simple.txt`  
**Example:** `examples/GET-customer-simple.txt`

### Format

```
--- MOCKINGBIRD v1.0 ---
Name: <stub name>
Method: <HTTP method>
URL: <URL path>

--- REQUEST HEADERS ---
<HeaderName>: <HeaderValue>

--- RESPONSE ---
Status: <HTTP status code>
Delay: <milliseconds>ms

Content-Type: <content type>

<response body here>
```

### Step-by-Step

1. Copy the template from `templates/level-1-simple.txt`
2. Fill in `Name`, `Method`, `URL`
3. Add any request headers your API requires (e.g., `Authorization`)
4. Fill in the `Status` code (200, 201, etc.)
5. Add optional `Delay` in milliseconds (e.g., `150ms`)
6. Paste your response body (JSON, XML, plain text — anything)
7. Save as `.txt` and upload

### What Mockingbird Validates
- Method must be: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
- URL must start with `/`
- Status must be a valid HTTP status code (100–599)
- Delay must be a number followed by `ms`
- Body cannot be empty if status is 200/201/202

---

## Level 2 — Multi-Scenario (TXT)

**Best for:** Teams who need different responses for different inputs (success + 404 + 500).  
Each scenario is checked **in order — first match wins**. Put specific cases first, default last.

**Template:** `templates/level-2-multi-scenario.txt`  
**Example:** `examples/POST-payment-multi-scenario.txt`

### Format

```
--- MOCKINGBIRD v1.0 ---
Name: <stub name>
Method: <HTTP method>
URL: <URL path, use {param} for path variables>

--- REQUEST HEADERS ---
<HeaderName>: <HeaderValue>

--- SCENARIO: <scenario name> ---
Match-Type: <url-contains | body-contains | header-equals | always>
Match-Value: <the value to match against>
Status: <HTTP status code>
Delay: <milliseconds>ms

Content-Type: <content type>

<response body>

--- SCENARIO: <next scenario name> ---
...

--- SCENARIO DEFAULT ---
Status: <HTTP status code>

Content-Type: <content type>

<default response body>
```

### Match Types

| Match-Type | What It Checks | Example Match-Value |
|-----------|---------------|-------------------|
| `url-contains` | URL path contains this string | `/99999` |
| `url-regex` | URL matches this regex | `/api/v1/customers/[0-9]{5}` |
| `body-contains` | Request body contains this string | `"action": "CANCEL"` |
| `body-json-path` | JSON path in request body equals value | `$.payment.status == "FAILED"` |
| `header-equals` | Request header equals this value | `X-Test-Mode: error` |
| `always` | Always matches (use only for DEFAULT) | (leave blank) |

### Step-by-Step

1. Copy the template from `templates/level-2-multi-scenario.txt`
2. Fill in header section (Name, Method, URL)
3. Add your most **specific** scenarios first (e.g., 404 for specific IDs)
4. Add a `--- SCENARIO DEFAULT ---` at the very bottom
5. For each scenario: set `Match-Type` + `Match-Value`, then the response
6. Scenarios are checked top to bottom — first match wins
7. Save as `.txt` and upload

---

## Level 3 — Full Control (JSON)

**Best for:** Teams who need dynamic responses (echo request values in response body), complex conditions, or precise delay configuration.

**Template:** `templates/level-3-full.json`  
**Example:** `examples/customer-api-full.json`

### Dynamic Parameter Reference

Use these placeholders anywhere in the response body:

| Placeholder | Returns | Example |
|------------|---------|---------|
| `{{request.path[0]}}` | First URL path segment | For `/api/v1/customers` → `api` |
| `{{request.path[2]}}` | Third URL path segment (0-indexed) | For `/api/v1/customers/12345` → `customers` |
| `{{request.pathParam.NAME}}` | Named path variable | For URL `/customers/{customerId}` with `/customers/12345` → `12345` |
| `{{request.queryParam.NAME}}` | URL query string value | For `?status=ACTIVE` → `ACTIVE` |
| `{{request.body.FIELD}}` | Field from JSON request body | For body `{"id": "X"}` → `X` |
| `{{request.header.NAME}}` | Request header value | `{{request.header.X-Correlation-ID}}` |
| `{{now}}` | Current UTC timestamp (ISO 8601) | `2026-06-14T10:30:00Z` |
| `{{now format='yyyy-MM-dd'}}` | Current date formatted | `2026-06-14` |
| `{{uuid}}` | Random UUID | `a1b2c3d4-...` |
| `{{randomInt lower=1 upper=1000}}` | Random integer in range | `547` |

### Delay Types

```json
"delay": { "type": "fixed", "ms": 100 }
"delay": { "type": "random", "min_ms": 50, "max_ms": 500 }
"delay": { "type": "progressive", "start_ms": 100, "increment_ms": 50, "max_ms": 5000 }
"delay": { "type": "chunked", "chunk_ms": 200, "chunk_size_bytes": 1024 }
```

### Fault Injection (for resilience testing)

```json
"fault": "CONNECTION_RESET"        // Drops the TCP connection mid-response
"fault": "EMPTY_RESPONSE"          // Connects but sends nothing
"fault": "MALFORMED_RESPONSE"      // Sends garbled data
```

---

## After You Upload

When you upload a file to Mockingbird, this is what happens:

```
Upload File
    ↓
Auto-Detect Format (TXT Level 1 / TXT Level 2 / JSON / Postman / OpenAPI)
    ↓
Validate
    ├── ❌ ERROR: Shows exactly what is wrong and which line
    └── ✅ VALID: Shows summary:
              "3 endpoints detected, 7 scenarios, 1 dynamic parameter"
    ↓
Choose Response Mode (you click one)
    ├── 🟢 Static       — always return exact response from file
    ├── 🟡 Conditional  — return different response based on request content
    ├── 🔵 Dynamic      — extract values from request and echo in response
    └── 🟣 AI-Suggest   — Claude analyses your file and suggests additional scenarios
    ↓
Review Generated Stubs (you can edit before generating)
    ↓
Generate Stub Code
    ↓
Deploy to EC2 (one click)
```

---

## Common Mistakes

| Mistake | Error Message | Fix |
|---------|--------------|-----|
| No `--- SCENARIO DEFAULT ---` at end | `Missing default scenario` | Add a catch-all scenario at the bottom |
| Scenario with `Match-Type` but no `Match-Value` | `Match-Value is required when Match-Type is not 'always'` | Add the value |
| Response body is not valid JSON when Content-Type is `application/json` | `Response body is not valid JSON at line 24` | Fix JSON syntax |
| URL does not start with `/` | `URL must begin with /` | Change `api/v1/...` to `/api/v1/...` |
| Using dynamic placeholders in a Static stub | Warning: `Dynamic placeholders found — switch to Dynamic mode?` | Switch to Dynamic mode or remove placeholders |
| Empty response body with status 200 | `Status 200/201/202 must have a response body` | Add response body or change status to 204 |

---

## SOAP Stubs

For SOAP APIs, use the JSON format (Level 3) with:

```json
"request": {
  "method": "POST",
  "url": "/ws/CustomerService",
  "headers": {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "\"GetCustomer\""
  },
  "body-xpath": "//GetCustomerRequest/CustomerId[text()='12345']"
},
"response": {
  "status": 200,
  "headers": {
    "Content-Type": "text/xml; charset=utf-8"
  },
  "body": "<soap:Envelope>...</soap:Envelope>"
}
```

SOAP WS-Security (username token) is configured separately in the project settings, not in the stub file.

---

## Need Help?

Contact the SV Team: raise a ticket in your team's SV project or contact the Mockingbird team directly.  
Mockingbird portal includes an AI assistant (Claude) that can help you create stub files from a description.
