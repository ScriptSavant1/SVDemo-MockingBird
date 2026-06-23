#Requires -Version 5.1
<#
.SYNOPSIS
  Creates the complete Mockingbird project folder and file structure.
  All files are created empty — paste content from GitHub after running this.

.USAGE
  .\scripts\scaffold-project.ps1
  .\scripts\scaffold-project.ps1 -Root "C:\MyProjects\Mockingbird"
  .\scripts\scaffold-project.ps1 -Force   # overwrite existing files with empty stubs
#>
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$created = 0
$skipped = 0

function New-Stub {
    param([string]$RelPath)
    $full = Join-Path $Root $RelPath
    $dir  = Split-Path $full -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    if (-not (Test-Path $full) -or $Force) {
        New-Item -ItemType File -Path $full -Force | Out-Null
        Write-Host "  [+] $RelPath" -ForegroundColor Green
        $script:created++
    } else {
        Write-Host "  [=] $RelPath (exists, skipped)" -ForegroundColor DarkGray
        $script:skipped++
    }
}

Write-Host ""
Write-Host "Mockingbird — project scaffold" -ForegroundColor Cyan
Write-Host "Root: $Root" -ForegroundColor Cyan
Write-Host "Mode: $(if ($Force) { 'FORCE (overwrite)' } else { 'SAFE (skip existing)' })" -ForegroundColor Yellow
Write-Host ""

# ── Root files ────────────────────────────────────────────────────────────────
Write-Host "Root files" -ForegroundColor Magenta
@(
    ".gitignore"
    "BUGS.md"
    "CLAUDE.md"
    "PHASES.md"
    "README.md"
    "START_HERE.md"
    "SV_Platform_Master_Guide.md"
    "setup.ps1"
    "setup.sh"
    "start-dev.ps1"
    "start-dev.sh"
) | ForEach-Object { New-Stub $_ }

# ── Config ────────────────────────────────────────────────────────────────────
Write-Host "`nConfig" -ForegroundColor Magenta
@(
    "config/example.env"
    "config/local.env"        # gitignored — fill from example.env
) | ForEach-Object { New-Stub $_ }

# ── Logs ──────────────────────────────────────────────────────────────────────
New-Stub "logs/.gitkeep"

# ── Docs ──────────────────────────────────────────────────────────────────────
Write-Host "`nDocs" -ForegroundColor Magenta
@(
    "docs/ARCHITECTURE.md"
    "docs/DECISIONS_LOG.md"
    "docs/DEPLOYMENT_ARCHITECTURE.md"
    "docs/DOCUMENTATION_STANDARDS.md"
    "docs/FINAL_ARCHITECTURE.md"
    "docs/IMPLEMENTATION_PLAN.md"
    "docs/LOCAL_DEVELOPMENT.md"
    "docs/SV_EXPERT_REVIEW.md"
    "docs/TECH_STACK.md"
    "docs/USER_FLOWS.md"
    "docs/USER_GUIDE.md"
    "docs/input-formats/GUIDE.md"
    "docs/input-formats/examples/GET-customer-simple.txt"
    "docs/input-formats/examples/POST-payment-multi-scenario.txt"
    "docs/input-formats/examples/banking-session.txt"
    "docs/input-formats/examples/customer-api-full.json"
    "docs/input-formats/examples/customer-soap-stub.txt"
    "docs/input-formats/examples/customer-soap.txt"
    "docs/input-formats/examples/dynamic-customer.txt"
    "docs/input-formats/examples/fault-injection.txt"
    "docs/input-formats/examples/soap-namespace.txt"
    "docs/input-formats/templates/level-1-simple.txt"
    "docs/input-formats/templates/level-2-multi-scenario.txt"
    "docs/input-formats/templates/level-3-full.json"
) | ForEach-Object { New-Stub $_ }

# ── Sample SV Files ───────────────────────────────────────────────────────────
Write-Host "`nSample SV Files" -ForegroundColor Magenta
@(
    "Sample_SV_Files/ESP/1781082059482RTCAERv01_Request_20260610_100059.txt"
    "Sample_SV_Files/ESP/1781082059500RTCAERv01_Success1Response_20260610_100059.txt"
    "Sample_SV_Files/ESP/1781082551676RTCAERv01_Error400Response_20260610_100911.txt"
    "Sample_SV_Files/ESP/1781082552845RTCAERv01_Request_20260610_100912.txt"
    "Sample_SV_Files/ESP/combined_request_response.txt"
    "Sample_SV_Files/Wealth/CreateAdviserPOST_Request.txt"
    "Sample_SV_Files/Wealth/CreateAdviserPost_Response.txt"
    "Sample_SV_Files/Wealth/GetAdvisersByID_Response.txt"
    "Sample_SV_Files/Wealth/GetAdvisers_Request.txt"
) | ForEach-Object { New-Stub $_ }

# ── Scripts ───────────────────────────────────────────────────────────────────
Write-Host "`nScripts" -ForegroundColor Magenta
@(
    "scripts/run-real-tests.ps1"
    "scripts/scaffold-project.ps1"
    "scripts/seed-users.ps1"
    "scripts/start-services.ps1"
    "scripts/stop-services.ps1"
) | ForEach-Object { New-Stub $_ }

# ── Portal ────────────────────────────────────────────────────────────────────
Write-Host "`nPortal — config / tooling" -ForegroundColor Magenta
@(
    "portal/.gitignore"
    "portal/Dockerfile"
    "portal/index.html"
    "portal/nginx.conf"
    "portal/package.json"
    "portal/package-lock.json"
    "portal/playwright.config.ts"
    "portal/playwright.real.config.ts"
    "portal/playwright.screenshots.config.ts"
    "portal/postcss.config.js"
    "portal/tailwind.config.ts"
    "portal/tsconfig.app.json"
    "portal/tsconfig.json"
    "portal/tsconfig.node.json"
    "portal/vite.config.ts"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nPortal — source" -ForegroundColor Magenta
@(
    "portal/src/App.tsx"
    "portal/src/index.css"
    "portal/src/main.tsx"
    "portal/src/router.tsx"
    "portal/src/vite-env.d.ts"
    "portal/src/api/admin.ts"
    "portal/src/api/ai.ts"
    "portal/src/api/auth.ts"
    "portal/src/api/client.ts"
    "portal/src/api/ingestion.ts"
    "portal/src/api/jobs.ts"
    "portal/src/api/metrics.ts"
    "portal/src/api/projects.ts"
    "portal/src/api/types.ts"
    "portal/src/components/AdminRoute.tsx"
    "portal/src/components/JobProgress.tsx"
    "portal/src/components/Layout.tsx"
    "portal/src/components/MetricsHistoryChart.tsx"
    "portal/src/components/ProtectedRoute.tsx"
    "portal/src/components/StatusBadge.tsx"
    "portal/src/components/TpsChart.tsx"
    "portal/src/components/UploadZone.tsx"
    "portal/src/components/ui/Button.tsx"
    "portal/src/components/ui/Card.tsx"
    "portal/src/components/ui/Modal.tsx"
    "portal/src/components/ui/Tabs.tsx"
    "portal/src/hooks/useJobPoller.ts"
    "portal/src/hooks/useMetricsWS.ts"
    "portal/src/pages/AdminPage.tsx"
    "portal/src/pages/AiGeneratePage.tsx"
    "portal/src/pages/CreateProjectPage.tsx"
    "portal/src/pages/DashboardPage.tsx"
    "portal/src/pages/DeploymentPage.tsx"
    "portal/src/pages/JobStatusPage.tsx"
    "portal/src/pages/LoginPage.tsx"
    "portal/src/pages/ProjectPage.tsx"
    "portal/src/pages/UploadPage.tsx"
    "portal/src/store/auth.ts"
    "portal/src/test/setup.ts"
    "portal/src/utils/formatters.ts"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nPortal — tests" -ForegroundColor Magenta
@(
    "portal/tests/api/client.test.ts"
    "portal/tests/components/JobProgress.test.tsx"
    "portal/tests/components/StatusBadge.test.tsx"
    "portal/tests/components/Tabs.test.tsx"
    "portal/tests/components/UploadZone.test.tsx"
    "portal/tests/hooks/useJobPoller.test.ts"
    "portal/tests/hooks/useMetricsWS.test.ts"
    "portal/tests/pages/AdminPage.test.tsx"
    "portal/tests/pages/AiGeneratePage.test.tsx"
    "portal/tests/pages/CreateProjectPage.test.tsx"
    "portal/tests/pages/DeploymentPage.test.tsx"
    "portal/tests/pages/LoginPage.test.tsx"
    "portal/tests/pages/UploadPage.test.tsx"
    "portal/tests/store/auth.test.ts"
    "portal/tests/utils/formatters.test.ts"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nPortal — e2e" -ForegroundColor Magenta
@(
    "portal/e2e/capture-screenshots.spec.ts"
    "portal/e2e/create-project.spec.ts"
    "portal/e2e/dashboard.spec.ts"
    "portal/e2e/fixtures.ts"
    "portal/e2e/login.spec.ts"
    "portal/e2e/manual-ui-audit.ts"
    "portal/e2e/ui-audit.spec.ts"
    "portal/e2e/upload.spec.ts"
    "portal/e2e/real/01-auth.spec.ts"
    "portal/e2e/real/02-projects.spec.ts"
    "portal/e2e/real/03-upload-and-generate.spec.ts"
    "portal/e2e/real/04-admin.spec.ts"
    "portal/e2e/real/05-download-stub.spec.ts"
    "portal/e2e/real/helpers.ts"
) | ForEach-Object { New-Stub $_ }

# ── Services — shared ─────────────────────────────────────────────────────────
Write-Host "`nServices — docker-compose" -ForegroundColor Magenta
New-Stub "services/docker-compose.yml"

# ── auth-service ──────────────────────────────────────────────────────────────
Write-Host "`nauth-service" -ForegroundColor Magenta
@(
    "services/auth-service/Dockerfile"
    "services/auth-service/package.json"
    "services/auth-service/package-lock.json"
    "services/auth-service/tsconfig.json"
    "services/auth-service/.env.local"         # gitignored — fill with local values
    "services/auth-service/src/app.ts"
    "services/auth-service/src/server.ts"
    "services/auth-service/src/plugins/database-local.ts"
    "services/auth-service/src/plugins/database.ts"
    "services/auth-service/src/plugins/jwt.ts"
    "services/auth-service/src/plugins/ldap.ts"
    "services/auth-service/src/plugins/redis.ts"
    "services/auth-service/src/routes/auth.ts"
    "services/auth-service/src/routes/ldap.ts"
    "services/auth-service/src/routes/users.ts"
    "services/auth-service/src/types/index.ts"
    "services/auth-service/tests/auth.test.ts"
    "services/auth-service/tests/ldap.test.ts"
) | ForEach-Object { New-Stub $_ }

# ── ai-service ────────────────────────────────────────────────────────────────
Write-Host "`nai-service" -ForegroundColor Magenta
@(
    "services/ai-service/Dockerfile"
    "services/ai-service/pyproject.toml"
    "services/ai-service/src/ai_service/__init__.py"
    "services/ai-service/src/ai_service/claude_client.py"
    "services/ai-service/src/ai_service/config.py"
    "services/ai-service/src/ai_service/database.py"
    "services/ai-service/src/ai_service/dependencies.py"
    "services/ai-service/src/ai_service/main.py"
    "services/ai-service/src/ai_service/models.py"
    "services/ai-service/src/ai_service/prompt.py"
    "services/ai-service/src/ai_service/routers/__init__.py"
    "services/ai-service/src/ai_service/routers/generate.py"
    "services/ai-service/src/ai_service/schemas.py"
    "services/ai-service/tests/__init__.py"
    "services/ai-service/tests/test_ai_service.py"
) | ForEach-Object { New-Stub $_ }

# ── deployer-worker ───────────────────────────────────────────────────────────
Write-Host "`ndeployer-worker" -ForegroundColor Magenta
@(
    "services/deployer-worker/Dockerfile"
    "services/deployer-worker/pyproject.toml"
    "services/deployer-worker/src/deployer_worker/__init__.py"
    "services/deployer-worker/src/deployer_worker/__main__.py"
    "services/deployer-worker/src/deployer_worker/config.py"
    "services/deployer-worker/src/deployer_worker/gitlab_client.py"
    "services/deployer-worker/src/deployer_worker/health.py"
    "services/deployer-worker/src/deployer_worker/microcks.py"
    "services/deployer-worker/src/deployer_worker/terraform.py"
    "services/deployer-worker/src/deployer_worker/worker.py"
    "services/deployer-worker/tests/__init__.py"
    "services/deployer-worker/tests/test_microcks_deployer.py"
    "services/deployer-worker/tests/test_worker.py"
) | ForEach-Object { New-Stub $_ }

# ── generator-worker ──────────────────────────────────────────────────────────
Write-Host "`ngenerator-worker" -ForegroundColor Magenta
@(
    "services/generator-worker/Dockerfile"
    "services/generator-worker/pyproject.toml"
    "services/generator-worker/src/generator_worker/__init__.py"
    "services/generator-worker/src/generator_worker/worker.py"
    "services/generator-worker/tests/__init__.py"
    "services/generator-worker/tests/test_worker.py"
) | ForEach-Object { New-Stub $_ }

# ── ingestion-service ─────────────────────────────────────────────────────────
Write-Host "`ningestion-service" -ForegroundColor Magenta
@(
    "services/ingestion-service/Dockerfile"
    "services/ingestion-service/pyproject.toml"
    "services/ingestion-service/requirements.txt"
    "services/ingestion-service/.env"          # gitignored — fill with local values
    "services/ingestion-service/src/ingestion_service/__init__.py"
    "services/ingestion-service/src/ingestion_service/config.py"
    "services/ingestion-service/src/ingestion_service/database.py"
    "services/ingestion-service/src/ingestion_service/dependencies.py"
    "services/ingestion-service/src/ingestion_service/main.py"
    "services/ingestion-service/src/ingestion_service/models.py"
    "services/ingestion-service/src/ingestion_service/routers/__init__.py"
    "services/ingestion-service/src/ingestion_service/routers/upload.py"
    "services/ingestion-service/src/ingestion_service/s3_client.py"
    "services/ingestion-service/src/ingestion_service/schemas.py"
    "services/ingestion-service/src/ingestion_service/wiremock_generator.py"
    "services/ingestion-service/tests/__init__.py"
    "services/ingestion-service/tests/conftest.py"
    "services/ingestion-service/tests/test_upload.py"
) | ForEach-Object { New-Stub $_ }

# ── metrics-service ───────────────────────────────────────────────────────────
Write-Host "`nmetrics-service" -ForegroundColor Magenta
@(
    "services/metrics-service/Dockerfile"
    "services/metrics-service/pyproject.toml"
    "services/metrics-service/src/metrics_service/__init__.py"
    "services/metrics-service/src/metrics_service/__main__.py"
    "services/metrics-service/src/metrics_service/config.py"
    "services/metrics-service/src/metrics_service/main.py"
    "services/metrics-service/src/metrics_service/models.py"
    "services/metrics-service/src/metrics_service/redis_pub.py"
    "services/metrics-service/src/metrics_service/routers/__init__.py"
    "services/metrics-service/src/metrics_service/routers/metrics.py"
    "services/metrics-service/src/metrics_service/routers/ws.py"
    "services/metrics-service/src/metrics_service/scraper.py"
    "services/metrics-service/src/metrics_service/timestream.py"
    "services/metrics-service/tests/__init__.py"
    "services/metrics-service/tests/test_metrics.py"
) | ForEach-Object { New-Stub $_ }

# ── notification-service ──────────────────────────────────────────────────────
Write-Host "`nnotification-service" -ForegroundColor Magenta
@(
    "services/notification-service/Dockerfile"
    "services/notification-service/package.json"
    "services/notification-service/package-lock.json"
    "services/notification-service/tsconfig.json"
    "services/notification-service/src/app.ts"
    "services/notification-service/src/server.ts"
    "services/notification-service/src/channels/email.ts"
    "services/notification-service/src/channels/slack.ts"
    "services/notification-service/src/channels/teams.ts"
    "services/notification-service/src/handlers/events.ts"
    "services/notification-service/src/plugins/sqs.ts"
    "services/notification-service/src/routes/notify.ts"
    "services/notification-service/src/types/index.ts"
    "services/notification-service/tests/notification.test.ts"
) | ForEach-Object { New-Stub $_ }

# ── parser-worker ─────────────────────────────────────────────────────────────
Write-Host "`nparser-worker — core" -ForegroundColor Magenta
@(
    "services/parser-worker/pyproject.toml"
    "services/parser-worker/requirements.txt"
    "services/parser-worker/src/parser_worker/__init__.py"
    "services/parser-worker/src/parser_worker/cli.py"
    "services/parser-worker/src/parser_worker/detector.py"
    "services/parser-worker/src/parser_worker/models.py"
    "services/parser-worker/src/parser_worker/models_asyncapi.py"
    "services/parser-worker/src/parser_worker/models_kafka.py"
    "services/parser-worker/src/parser_worker/models_mq.py"
    "services/parser-worker/src/parser_worker/worker.py"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nparser-worker — parsers" -ForegroundColor Magenta
@(
    "services/parser-worker/src/parser_worker/parsers/__init__.py"
    "services/parser-worker/src/parser_worker/parsers/asyncapi.py"
    "services/parser-worker/src/parser_worker/parsers/base.py"
    "services/parser-worker/src/parser_worker/parsers/ca_lisa_parser.py"
    "services/parser-worker/src/parser_worker/parsers/json_level3.py"
    "services/parser-worker/src/parser_worker/parsers/kafka_json.py"
    "services/parser-worker/src/parser_worker/parsers/mq_json.py"
    "services/parser-worker/src/parser_worker/parsers/openapi.py"
    "services/parser-worker/src/parser_worker/parsers/postman.py"
    "services/parser-worker/src/parser_worker/parsers/soap_txt.py"
    "services/parser-worker/src/parser_worker/parsers/stateful_txt.py"
    "services/parser-worker/src/parser_worker/parsers/txt_level1.py"
    "services/parser-worker/src/parser_worker/parsers/txt_level2.py"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nparser-worker — generators" -ForegroundColor Magenta
@(
    "services/parser-worker/src/parser_worker/generator/__init__.py"
    "services/parser-worker/src/parser_worker/generator/kafka_springboot.py"
    "services/parser-worker/src/parser_worker/generator/microcks.py"
    "services/parser-worker/src/parser_worker/generator/mq_springboot.py"
    "services/parser-worker/src/parser_worker/generator/springboot.py"
    "services/parser-worker/src/parser_worker/generator/wiremock.py"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nparser-worker — templates (stub-engine REST)" -ForegroundColor Magenta
@(
    "services/parser-worker/src/parser_worker/templates/stub-engine/Dockerfile"
    "services/parser-worker/src/parser_worker/templates/stub-engine/docker-compose.yml"
    "services/parser-worker/src/parser_worker/templates/stub-engine/pom.xml"
    "services/parser-worker/src/parser_worker/templates/stub-engine/settings.xml"
    "services/parser-worker/src/parser_worker/templates/stub-engine/src/main/java/com/mockingbird/stubs/StubApplication.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine/src/main/java/com/mockingbird/stubs/WireMockConfig.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine/src/main/java/com/mockingbird/stubs/WsSecurityConfig.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine/src/main/java/com/mockingbird/stubs/WsdlConfig.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine/src/main/resources/application.yml"
    "services/parser-worker/src/parser_worker/templates/stub-engine/src/main/resources/wsdl/service.wsdl"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nparser-worker — templates (stub-engine-kafka)" -ForegroundColor Magenta
@(
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/Dockerfile"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/pom.xml"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/settings.xml"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/src/main/java/com/mockingbird/stubs/kafka/KafkaStubApplication.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/src/main/java/com/mockingbird/stubs/kafka/KafkaStubConsumer.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/src/main/java/com/mockingbird/stubs/kafka/StubController.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/src/main/java/com/mockingbird/stubs/kafka/StubDefinition.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/src/main/java/com/mockingbird/stubs/kafka/StubRegistry.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/src/main/resources/application.yml"
    "services/parser-worker/src/parser_worker/templates/stub-engine-kafka/src/main/resources/stubs.json"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nparser-worker — templates (stub-engine-mq)" -ForegroundColor Magenta
@(
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/Dockerfile"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/pom.xml"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/settings.xml"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/src/main/java/com/mockingbird/stubs/mq/MQStubApplication.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/src/main/java/com/mockingbird/stubs/mq/MQStubConsumer.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/src/main/java/com/mockingbird/stubs/mq/StubController.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/src/main/java/com/mockingbird/stubs/mq/StubDefinition.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/src/main/java/com/mockingbird/stubs/mq/StubRegistry.java"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/src/main/resources/application.yml"
    "services/parser-worker/src/parser_worker/templates/stub-engine-mq/src/main/resources/stubs.json"
) | ForEach-Object { New-Stub $_ }

Write-Host "`nparser-worker — tests" -ForegroundColor Magenta
@(
    "services/parser-worker/tests/__init__.py"
    "services/parser-worker/tests/test_asyncapi_parser.py"
    "services/parser-worker/tests/test_ca_lisa_parser.py"
    "services/parser-worker/tests/test_dynamic_responses.py"
    "services/parser-worker/tests/test_fault_injection.py"
    "services/parser-worker/tests/test_integration.py"
    "services/parser-worker/tests/test_kafka_generator.py"
    "services/parser-worker/tests/test_kafka_parser.py"
    "services/parser-worker/tests/test_microcks_generator.py"
    "services/parser-worker/tests/test_mq_generator.py"
    "services/parser-worker/tests/test_mq_parser.py"
    "services/parser-worker/tests/test_openapi_parser.py"
    "services/parser-worker/tests/test_postman_parser.py"
    "services/parser-worker/tests/test_soap_advanced.py"
    "services/parser-worker/tests/test_soap_parser.py"
    "services/parser-worker/tests/test_stateful_scenarios.py"
    "services/parser-worker/tests/test_txt_level1.py"
    "services/parser-worker/tests/test_txt_level2.py"
    "services/parser-worker/tests/test_wiremock_generator.py"
    "services/parser-worker/tests/test_worker.py"
) | ForEach-Object { New-Stub $_ }

# ── project-service ───────────────────────────────────────────────────────────
Write-Host "`nproject-service" -ForegroundColor Magenta
@(
    "services/project-service/Dockerfile"
    "services/project-service/pyproject.toml"
    "services/project-service/requirements.txt"
    "services/project-service/alembic.ini"
    "services/project-service/.env"           # gitignored — fill with local values
    "services/project-service/alembic/env.py"
    "services/project-service/alembic/script.py.mako"
    "services/project-service/alembic/versions/001_initial_schema.py"
    "services/project-service/alembic/versions/002_expand_deployments.py"
    "services/project-service/alembic/versions/003_add_stub_status.py"
    "services/project-service/src/project_service/__init__.py"
    "services/project-service/src/project_service/config.py"
    "services/project-service/src/project_service/database.py"
    "services/project-service/src/project_service/dependencies.py"
    "services/project-service/src/project_service/main.py"
    "services/project-service/src/project_service/models.py"
    "services/project-service/src/project_service/schemas.py"
    "services/project-service/src/project_service/sqs_client.py"
    "services/project-service/src/project_service/routers/__init__.py"
    "services/project-service/src/project_service/routers/admin.py"
    "services/project-service/src/project_service/routers/deploy.py"
    "services/project-service/src/project_service/routers/jobs.py"
    "services/project-service/src/project_service/routers/projects.py"
    "services/project-service/src/project_service/routers/stubs.py"
    "services/project-service/tests/__init__.py"
    "services/project-service/tests/conftest.py"
    "services/project-service/tests/test_deploy.py"
    "services/project-service/tests/test_jobs.py"
    "services/project-service/tests/test_projects.py"
    "services/project-service/tests/test_sprint19.py"
    "services/project-service/tests/test_sprint20.py"
    "services/project-service/tests/test_stubs.py"
) | ForEach-Object { New-Stub $_ }

# ── reporter-service ──────────────────────────────────────────────────────────
Write-Host "`nreporter-service" -ForegroundColor Magenta
@(
    "services/reporter-service/Dockerfile"
    "services/reporter-service/pyproject.toml"
    "services/reporter-service/src/reporter_service/__init__.py"
    "services/reporter-service/src/reporter_service/__main__.py"
    "services/reporter-service/src/reporter_service/config.py"
    "services/reporter-service/src/reporter_service/data_loader.py"
    "services/reporter-service/src/reporter_service/models.py"
    "services/reporter-service/src/reporter_service/renderers/__init__.py"
    "services/reporter-service/src/reporter_service/renderers/excel.py"
    "services/reporter-service/src/reporter_service/renderers/pdf.py"
    "services/reporter-service/src/reporter_service/renderers/ppt.py"
    "services/reporter-service/src/reporter_service/s3_store.py"
    "services/reporter-service/src/reporter_service/worker.py"
    "services/reporter-service/tests/__init__.py"
    "services/reporter-service/tests/test_reporter.py"
) | ForEach-Object { New-Stub $_ }

# ── stub-engine (template source of truth) ────────────────────────────────────
Write-Host "`nstub-engine (template source)" -ForegroundColor Magenta
@(
    "stub-engine/.gitlab-ci.yml"
    "stub-engine/Dockerfile"
    "stub-engine/docker-compose.yml"
    "stub-engine/pom.xml"
    "stub-engine/settings.xml"
    "stub-engine/src/main/java/com/mockingbird/stubs/StubApplication.java"
    "stub-engine/src/main/java/com/mockingbird/stubs/WireMockConfig.java"
    "stub-engine/src/main/resources/application.yml"
) | ForEach-Object { New-Stub $_ }

# ── Terraform ─────────────────────────────────────────────────────────────────
Write-Host "`nTerraform" -ForegroundColor Magenta
@(
    "terraform/stub-ec2/main.tf"
    "terraform/stub-ec2/outputs.tf"
    "terraform/stub-ec2/variables.tf"
) | ForEach-Object { New-Stub $_ }

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
Write-Host "  Created : $created files" -ForegroundColor Green
Write-Host "  Skipped : $skipped files (already exist)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Copy file contents from GitHub: https://github.com/ScriptSavant1/SVDemo-MockingBird"
Write-Host "  2. Fill in gitignored env files:"
Write-Host "       config/local.env                  (copy from config/example.env)"
Write-Host "       services/auth-service/.env.local  (JWT_SECRET, PORT=3001)"
Write-Host "       services/ingestion-service/.env   (DATABASE_URL, LOCAL_STORAGE_PATH, etc.)"
Write-Host "       services/project-service/.env     (DATABASE_URL, JWT_SECRET, etc.)"
Write-Host "  3. Install dependencies:"
Write-Host "       cd portal && npm install"
Write-Host "       cd services/auth-service && npm install"
Write-Host "       cd services/notification-service && npm install"
Write-Host "  4. Run:  .\scripts\start-services.ps1"
Write-Host "           cd portal && npm run dev"
