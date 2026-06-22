<#
.SYNOPSIS
    Full automated test cycle: start services → seed → run real E2E tests → stop.

.DESCRIPTION
    1. Starts auth, project, and ingestion services
    2. Seeds admin + test user (idempotent)
    3. Runs Playwright real E2E test suite (portal/e2e/real/)
    4. On any failure, appends a bug entry to BUGS.md
    5. Stops all services
    6. Returns exit code 0 = all pass, 1 = failures

.PARAMETER KeepServicesRunning
    Don't stop services after the test run (useful when developing tests).
#>
param([switch]$KeepServicesRunning)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

# ── 1. Start services ─────────────────────────────────────────────────────────
Write-Host "=== Starting services ===" -ForegroundColor Cyan
& "$PSScriptRoot\start-services.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Services failed to start. Aborting tests." -ForegroundColor Red
    exit 1
}

# ── 2. Seed users ──────────────────────────────────────────────────────────────
Write-Host "`n=== Seeding users ===" -ForegroundColor Cyan
& "$PSScriptRoot\seed-users.ps1"

# ── 3. Run real Playwright tests ───────────────────────────────────────────────
Write-Host "`n=== Running real E2E tests ===" -ForegroundColor Cyan
$portalDir = Join-Path $root "portal"
Push-Location $portalDir
$testOutput = npx playwright test --config=playwright.real.config.ts --reporter=list 2>&1
$testExitCode = $LASTEXITCODE
Pop-Location

# Print output
$testOutput | ForEach-Object { Write-Host $_ }

# ── 4. On failure: append to BUGS.md ──────────────────────────────────────────
if ($testExitCode -ne 0) {
    Write-Host "`nTest failures detected — updating BUGS.md" -ForegroundColor Yellow

    # Parse failures from the output
    $failures = $testOutput | Where-Object { $_ -match "^\s+x\s+\d+\)" -or $_ -match "FAILED" }

    $bugsFile = Join-Path $root "BUGS.md"
    $content  = Get-Content $bugsFile -Raw

    # Find next bug number
    $existingNums = [regex]::Matches($content, "BUG-(\d+)") | ForEach-Object { [int]$_.Groups[1].Value }
    $nextNum = if ($existingNums) { ($existingNums | Measure-Object -Maximum).Maximum + 1 } else { 1 }
    $bugId = "BUG-{0:D3}" -f $nextNum

    $timestamp = Get-Date -Format "yyyy-MM-dd"
    $failureList = ($testOutput | Where-Object { $_ -match "^\s+\d+\)" -or $_ -match "x\s+\[" } |
        Select-Object -First 10 | ForEach-Object { "  - $_" }) -join "`n"

    $newEntry = @"

## $bugId — Real E2E test failures ($timestamp)

| Field | Value |
|-------|-------|
| **ID** | $bugId |
| **Found** | $timestamp |
| **Status** | OPEN |
| **Severity** | High |
| **File** | portal/e2e/real/ |
| **Commit** | (unfixed) |

**Description:**
Real browser E2E tests failed during automated run.

**Failing tests:**
$failureList

**Fix:**
Investigate each failing test. Run: ``cd portal && npx playwright test --config=playwright.real.config.ts --reporter=list``

---
"@

    # Insert after the first line (newest-at-top)
    $lines = Get-Content $bugsFile
    $insertAfter = 2  # after the header line and blank line
    $newLines = $lines[0..($insertAfter-1)] + $newEntry.Split("`n") + $lines[$insertAfter..($lines.Length-1)]
    $newLines | Set-Content $bugsFile
    Write-Host "Bug entry $bugId added to BUGS.md" -ForegroundColor Yellow
}

# ── 5. Stop services ───────────────────────────────────────────────────────────
if (-not $KeepServicesRunning) {
    Write-Host "`n=== Stopping services ===" -ForegroundColor Cyan
    & "$PSScriptRoot\stop-services.ps1"
}

Write-Host "`n=== Test run complete ===" -ForegroundColor Cyan
if ($testExitCode -eq 0) {
    Write-Host "All real E2E tests PASSED" -ForegroundColor Green
} else {
    Write-Host "Some tests FAILED (exit $testExitCode) — see BUGS.md" -ForegroundColor Red
}

exit $testExitCode
