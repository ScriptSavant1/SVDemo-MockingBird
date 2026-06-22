<#
.SYNOPSIS
    Create the initial admin user and a test SV_TEAM user in the auth-service.

.DESCRIPTION
    Calls POST /api/v1/auth/setup  (admin — only works on empty DB)
    Then logs in as admin and calls POST /api/v1/users (sv.user)

    Run this ONCE after a fresh database wipe.
#>
$authBase = "http://localhost:3001"

Write-Host "Creating admin user (sv.admin)..." -ForegroundColor Cyan
$body = @{ username = "sv.admin"; email = "sv.admin@mockingbird.internal"; password = "Admin@2026!" } | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Method Post -Uri "$authBase/api/v1/auth/setup" `
        -ContentType "application/json" -Body $body
    Write-Host "  Admin created: $($r.username) [$($r.role)]" -ForegroundColor Green
} catch {
    $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode.value__ } else { 0 }
    if ($status -eq 409) {
        Write-Host "  Admin already exists (409) — skipping" -ForegroundColor Yellow
    } else {
        Write-Host "  ERROR: $_" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Logging in as sv.admin to get token..." -ForegroundColor Cyan
$loginBody = @{ username = "sv.admin"; password = "Admin@2026!" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$authBase/api/v1/auth/login" `
    -ContentType "application/json" -Body $loginBody
$token = $login.access_token
Write-Host "  Token acquired" -ForegroundColor Green

Write-Host "Creating SV_TEAM user (sv.user)..." -ForegroundColor Cyan
$userBody = @{
    username = "sv.user"
    email    = "sv.user@mockingbird.internal"
    password = "User@2026!"
    role     = "SV_TEAM"
} | ConvertTo-Json
try {
    $r2 = Invoke-RestMethod -Method Post -Uri "$authBase/api/v1/users" `
        -ContentType "application/json" -Body $userBody `
        -Headers @{ Authorization = "Bearer $token" }
    Write-Host "  User created: $($r2.username) [$($r2.role)]" -ForegroundColor Green
} catch {
    $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode.value__ } else { 0 }
    if ($status -eq 409) {
        Write-Host "  sv.user already exists (409) — skipping" -ForegroundColor Yellow
    } else {
        Write-Host "  ERROR: $_" -ForegroundColor Red
    }
}

# ── Mirror users into project-service (admin panel data) ──────────────────────
# project-service has its own users table for the admin panel.
# Users must exist there too; authentication is still done by auth-service.
$projBase = "http://localhost:8001"
$headers  = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

Write-Host "`nMirroring sv.admin into project-service..." -ForegroundColor Cyan
$projAdmin = @{
    username = "sv.admin"
    email    = "sv.admin@mockingbird.internal"
    password = "Admin@2026!"
    role     = "ADMIN"
} | ConvertTo-Json
try {
    $pr = Invoke-RestMethod -Method Post -Uri "$projBase/api/v1/admin/users" `
        -ContentType "application/json" -Body $projAdmin -Headers $headers
    Write-Host "  project-service admin created: $($pr.username) [$($pr.role)]" -ForegroundColor Green
} catch {
    $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode.value__ } else { 0 }
    if ($status -eq 409) {
        Write-Host "  sv.admin already in project-service (409) — skipping" -ForegroundColor Yellow
    } else {
        Write-Host "  WARN: could not mirror admin to project-service: $_" -ForegroundColor Yellow
    }
}

Write-Host "Mirroring sv.user into project-service..." -ForegroundColor Cyan
$projUser = @{
    username = "sv.user"
    email    = "sv.user@mockingbird.internal"
    password = "User@2026!"
    role     = "SV_TEAM"
} | ConvertTo-Json
try {
    $pu = Invoke-RestMethod -Method Post -Uri "$projBase/api/v1/admin/users" `
        -ContentType "application/json" -Body $projUser -Headers $headers
    Write-Host "  project-service user created: $($pu.username) [$($pu.role)]" -ForegroundColor Green
} catch {
    $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode.value__ } else { 0 }
    if ($status -eq 409) {
        Write-Host "  sv.user already in project-service (409) — skipping" -ForegroundColor Yellow
    } else {
        Write-Host "  WARN: could not mirror sv.user to project-service: $_" -ForegroundColor Yellow
    }
}

Write-Host "`nSeeding complete." -ForegroundColor Cyan
Write-Host "  Admin  : sv.admin  / Admin@2026!"
Write-Host "  SV Team: sv.user   / User@2026!"
