# Mockingbird — Deployment Architecture

**Version:** 1.0  
**Last Updated:** 2026-06-12

---

## The Core Principle: Project vs Infrastructure are Separate

This is the most important concept in Mockingbird's design:

```
┌────────────────────────────────────────────────────────────────────┐
│  PROJECT (permanent — stored in platform forever)                   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │  Stub definitions    → PostgreSQL (always available)       │     │
│  │  Generated packages  → S3 (always available)               │     │
│  │  Docker image        → ECR (available until policy expires)│     │
│  └───────────────────────────────────────────────────────────┘     │
│                                                                     │
│  INFRASTRUCTURE (ephemeral — can be started, stopped, moved)        │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │  EC2 instance   → can be terminated anytime               │     │
│  │  On-prem server → can be decommissioned anytime           │     │
│  │  Security group → provisioned on demand                   │     │
│  └───────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────┘
```

**Terminating a server never deletes a project.** The stubs always live in the platform.

---

## Project Lifecycle

A project moves through these states independently of any infrastructure:

```
                    ┌─────────────────────────────────────────────┐
                    │           PROJECT LIFECYCLE                  │
                    └─────────────────────────────────────────────┘

  Upload spec
      │
      ▼
  ┌────────┐    Parse + Generate    ┌─────────┐    User edits
  │ DRAFT  │ ─────────────────────▶│  READY  │◀─── stubs
  └────────┘                       └────┬────┘
                                        │
                                        │ Click Deploy
                                        ▼
                                   ┌──────────┐
                                   │DEPLOYING │ (3–5 minutes)
                                   └────┬─────┘
                                        │
                              ┌─────────┴──────────┐
                              │                    │
                              ▼                    ▼
                          ┌──────┐           ┌──────────┐
                          │ LIVE │           │  FAILED  │
                          └──┬───┘           └──────────┘
                             │                    │
                  ┌──────────┴──────────┐         │ Retry
                  │                    │          │
                  ▼                    ▼          ▼
            ┌──────────┐         ┌─────────┐
            │SUSPENDED │         │ARCHIVED │
            │(infra    │         │(project │
            │terminated│         │retired) │
            │but stubs │         └─────────┘
            │preserved)│
            └────┬─────┘
                 │
                 │ Redeploy (no re-upload needed)
                 ▼
            ┌──────────┐
            │DEPLOYING │ → LIVE again
            └──────────┘
```

### State Descriptions

| State | Meaning | Infrastructure | Stubs in DB/S3 |
|-------|---------|---------------|----------------|
| DRAFT | Spec uploaded, stubs being configured | None | Yes (parsed) |
| READY | Stubs generated, not yet deployed | None | Yes (generated) |
| DEPLOYING | Deploy job running | Provisioning | Yes |
| LIVE | Stub server running, taking traffic | EC2 / server running | Yes |
| SUSPENDED | Infrastructure terminated intentionally | None | **Yes — preserved** |
| ARCHIVED | Project retired, kept for audit/history | None | Yes (read-only) |
| FAILED | Deploy failed — infrastructure cleaned up | None | Yes |

---

## Redeployment Without Re-uploading

When you redeploy a SUSPENDED or previously LIVE project:

```
User clicks "Redeploy" (or API: POST /projects/{id}/deploy)
  │
  ▼
Deployer Worker checks:
  │
  ├─── Does ECR image still exist for this project version?
  │         │
  │    YES ─▶  Skip build entirely
  │              │
  │              ▼
  │           Provision infrastructure only:
  │             - Terraform apply (new EC2 or target server)
  │             - EC2 user_data pulls existing ECR image
  │             - Health check passes
  │             - Update DB: status=LIVE, new stub_url
  │
  │    NO  ─▶  Image expired (ECR lifecycle policy)
  │              │
  │              ▼
  │           Rebuild only (no re-upload needed):
  │             - Load stubs from DB (always stored)
  │             - Regenerate WireMock mappings
  │             - docker build → push to ECR
  │             - Deploy as above
  │
  ▼
Result: Same stubs running on new infrastructure
        User gets new stub URL (same port, new IP)
        No file re-upload, no manual re-configuration
```

**ECR image retention policy:** Keep last 5 images per project. Typically covers months of inactivity. If expired, rebuild from DB takes ~2 minutes.

---

## Deployment Targets: Where Can a Stub Run?

Mockingbird supports three deployment targets. The user selects at deploy time.

```
┌──────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT TARGETS                             │
│                                                                  │
│  TARGET 1: SV Platform Account (default)                         │
│  ─────────────────────────────────────                           │
│  EC2 lives in Mockingbird's own AWS account                      │
│  SV team manages all infrastructure                              │
│  Firewall: project team opens port from their servers to SV EC2  │
│                                                                  │
│  TARGET 2: Project's Own AWS Account (cross-account)             │
│  ─────────────────────────────────────────────────────           │
│  EC2 lives inside the project team's AWS account                 │
│  Deployer assumes cross-account IAM role                         │
│  Firewall: simpler (stub EC2 is inside their own VPC)            │
│  Use when: team wants full ownership, or has VPN restrictions    │
│                                                                  │
│  TARGET 3: On-Premise / Internal Server                          │
│  ──────────────────────────────────────                          │
│  Any Linux server with Docker installed                          │
│  Deployer connects via SSH and runs docker commands              │
│  Use when: project is in air-gapped network, no AWS              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Target 1: SV Platform AWS Account (Default)

```
┌──────────────── SV PLATFORM ACCOUNT ────────────────────────────┐
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  ECS Fargate Cluster (Mockingbird platform services)   │     │
│  │  RDS, S3, ECR, SQS, Redis, Timestream                  │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Stub EC2 Instances (per project)                      │     │
│  │                                                        │     │
│  │  ec2-payments-stub   (10.0.20.10)  WireMock :8080      │     │
│  │  ec2-accounts-stub   (10.0.20.11)  Hoverfly :8080      │     │
│  │  ec2-cards-stub      (10.0.20.12)  WireMock :8080      │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
         ▲ firewall opened (port 8080) from project CIDR
         │
┌────────────────── PROJECT TEAM NETWORK ──────────────────────────┐
│  Test servers → hit https://10.0.20.10:8080/api/payments         │
└──────────────────────────────────────────────────────────────────┘
```

**How it works:**
- Mockingbird deploys EC2 in its own account (existing model)
- Platform generates firewall doc: "open port 8080 from {your CIDR} to {SV EC2 IP}"
- Project team's infra team opens that firewall rule

---

## Target 2: Project's Own AWS Account (Cross-Account)

This is the modern approach — stub EC2 lives **inside the project's own AWS account**.

```
┌───────────────── SV PLATFORM ACCOUNT ──────────────────────────────┐
│                                                                     │
│  deployer-worker                                                    │
│       │                                                             │
│       │  1. AssumeRole: arn:aws:iam::PROJECT_ACCOUNT_ID:role/      │
│       │                  MockingbirdDeployerRole                    │
│       │                                                             │
│       │  2. Terraform applies in PROJECT account context           │
│       │                                                             │
│       │  3. EC2 provisioned in PROJECT account                     │
│       │                                                             │
│       │  4. EC2 IAM role → can pull from SV account's ECR          │
│       │     (via ECR cross-account resource policy)                 │
└───────────────────────────────────────────────────────────────────┘

┌───────────────── PROJECT AWS ACCOUNT ──────────────────────────────┐
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Stub EC2 (provisioned by Mockingbird into this account)   │    │
│  │                                                            │    │
│  │  IAM Role: MockingbirdEC2Role                              │    │
│  │    - ecr:GetAuthorizationToken (from SV account ECR)       │    │
│  │    - ecr:BatchGetImage         (from SV account ECR)       │    │
│  │    - logs:PutLogEvents         (to project CloudWatch)     │    │
│  │                                                            │    │
│  │  WireMock :8080  (inside project's own VPC)               │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Project's test servers                                    │    │
│  │  → hit stub EC2 directly (same VPC or VPC peering)        │    │
│  │  → no cross-account firewall needed                       │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### What the Project Team Must Set Up Once (one-time)

The project team creates this IAM role in their account (Mockingbird provides the Terraform for this):

```hcl
# terraform/cross-account-setup/main.tf
# Project team runs this ONCE in their account

resource "aws_iam_role" "mockingbird_deployer" {
  name = "MockingbirdDeployerRole"

  assume_role_policy = jsonencode({
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::SV_ACCOUNT_ID:role/MockingbirdDeployer" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "mockingbird_deployer_policy" {
  role = aws_iam_role.mockingbird_deployer.id
  policy = jsonencode({
    Statement = [
      { Effect = "Allow", Action = ["ec2:*"], Resource = "*" },
      { Effect = "Allow", Action = ["iam:CreateRole", "iam:AttachRolePolicy", "iam:PassRole"], Resource = "*" }
    ]
  })
}
```

After this one-time setup, Mockingbird can deploy any number of stub EC2s into their account on demand.

---

## Target 3: On-Premise / Internal Server

For teams in air-gapped networks or without AWS access.

```
┌──────────────── SV PLATFORM ACCOUNT ──────────────────────────────┐
│                                                                    │
│  deployer-worker                                                   │
│       │                                                            │
│       │  1. Download Docker image from ECR → local tar file       │
│       │  2. SSH into on-prem server (Paramiko / Fabric)           │
│       │  3. scp Docker image tar to server                        │
│       │  4. docker load < image.tar                               │
│       │  5. docker run -d -p 8080:8080 ...                        │
│       │  6. curl http://{server}:8080/__admin/health               │
│       │  7. Update DB: stub_url = http://{server}:8080            │
│       │                                                            │
└────────────────────────────────────────────────────────────────────┘

┌──────────────── ON-PREMISE NETWORK ────────────────────────────────┐
│                                                                    │
│  Server: rhel-test-server-01 (10.10.20.50)                        │
│    └── Docker daemon running                                      │
│    └── Mockingbird stub container                                 │
│           WireMock :8080                                          │
│                                                                    │
│  Project team test servers → http://10.10.20.50:8080              │
└────────────────────────────────────────────────────────────────────┘
```

**Requirements for on-premise target:**
- Server must have Docker installed
- Mockingbird platform must have SSH access (either VPN or bastion)
- SSH key stored in AWS Secrets Manager (platform pulls it at deploy time)

---

## Multi-Account Architecture Overview

```
                    ┌──────────────────────────────────────┐
                    │     SV PLATFORM ACCOUNT               │
                    │                                      │
                    │  Mockingbird (all platform services) │
                    │  ECR (all Docker images)             │
                    │  RDS, S3, SQS, Redis                 │
                    └───────────────────┬──────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
          ┌─────────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐
          │  PROJECT A        │ │  PROJECT B     │ │  ON-PREMISE   │
          │  AWS Account      │ │  AWS Account   │ │  Servers      │
          │                  │ │                │ │               │
          │  Stub EC2        │ │  Stub EC2      │ │  Docker host  │
          │  (cross-account) │ │  (cross-account│ │  (SSH deploy) │
          │                  │ │   deploy)      │ │               │
          └──────────────────┘ └────────────────┘ └───────────────┘
```

---

## Deployment Target Configuration in Portal

When a user clicks Deploy, they see:

```
┌──────────────────────────────────────────────────────────────────┐
│  Deploy: payments-stub                                           │
│                                                                  │
│  WHERE TO DEPLOY?                                                │
│                                                                  │
│  ● SV Platform Account (default)                                 │
│    SV team manages infra. Firewall doc auto-generated.           │
│                                                                  │
│  ○ My Project's AWS Account (cross-account)                      │
│    AWS Account ID: [123456789012        ]                        │
│    Region:         [eu-west-1 ▼         ]                        │
│    VPC ID:         [vpc-xxxxxxxx        ]                        │
│    Subnet ID:      [subnet-xxxxxxxx     ]                        │
│    Deployer Role:  [auto-filled if registered]                   │
│                                                                  │
│  ○ On-Premise Server                                             │
│    Host IP:        [10.10.20.50         ]                        │
│    SSH Port:       [22                  ]                        │
│    SSH Key:        [Select from secrets ▼]                       │
│    Docker Socket:  [/var/run/docker.sock]                        │
│                                                                  │
│  ENVIRONMENT: [TEST ▼]   TPS TIER: [1,000–5,000 ▼]             │
│                                                                  │
│  [Deploy →]                                                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## What's Stored Where (The Full Picture)

```
SV PLATFORM ACCOUNT (permanent project storage)
──────────────────────────────────────────────

PostgreSQL (RDS):
  projects table:
    id, name, team, environment, tps_tier, engine
    status: DRAFT | READY | LIVE | SUSPENDED | ARCHIVED
    current_version: 3
    current_deployment_id: uuid
    
  stubs table:
    id, project_id, name, method, path, 
    request_matcher (JSON), response_body (JSON)
    → ALWAYS stored, never deleted on undeploy
    
  deployments table:
    id, project_id, version, target_type, target_config
    ec2_instance_id OR server_host, stub_url
    status, deployed_at, terminated_at
    → Full deployment history preserved

S3:
  projects/{project_id}/
    versions/
      v1/  → WireMock mappings + Dockerfile (always kept)
      v2/  → WireMock mappings + Dockerfile (always kept)
      v3/  → WireMock mappings + Dockerfile (current)
    
ECR:
  mockingbird/{project_id}:v1  → kept per lifecycle policy (last 5)
  mockingbird/{project_id}:v2  → kept
  mockingbird/{project_id}:v3  → current

REMOTE INFRASTRUCTURE (ephemeral — can come and go)
───────────────────────────────────────────────────

SV Account / Project Account / On-premise:
  EC2 instance or Docker host
  → Terminated when project is SUSPENDED
  → Reprovisioned when project is redeployed
  → Stub URL changes with new IP (same port)
  → Stubs themselves unchanged
```

---

## Release Management (Your Key Use Case)

```
RELEASE 1 (e.g., January 2026)
─────────────────────────────

  Week 1:   Upload payments-api-v1.yaml → generate → deploy (SV account, c6i.xlarge)
  Week 2-8: Test team hits stubs. 2.4 million requests served.
  Week 9:   Release 1 ships to production.

  Week 10:  Project Owner clicks "Suspend" in Mockingbird portal.
            → EC2 terminated (saves ~£100/month)
            → Project status = SUSPENDED
            → All stubs preserved in DB and S3
            → ECR image preserved

BETWEEN RELEASES (February–March 2026)
───────────────────────────────────────
  Project exists in SUSPENDED state.
  Nothing running. Zero cost.

RELEASE 2 (e.g., April 2026)
─────────────────────────────

  Scenario A: Same stubs, new environment
  ─────────────────────────────────────────
    Project Owner: "Redeploy payments-stub for Release 2 testing"
    → Click "Redeploy" in portal
    → Select target: TEST / SV account (or their own account)
    → Deployer checks ECR: image still exists (v1 or v3)
    → Provisions new EC2 (3–5 minutes)
    → Status = LIVE
    → New stub URL generated (new IP)
    → Email sent to project owner
    
    ✓ No re-upload. No re-generation. No configuration.

  Scenario B: Stubs changed (new endpoints added for R2)
  ──────────────────────────────────────────────────────
    Project Owner: Upload payments-api-v2.yaml (new endpoints)
    → Platform detects this is version 2 of existing project
    → Parses new endpoints → MERGES with existing stubs
    → User reviews: "3 new endpoints detected. 8 existing unchanged."
    → Generate → creates v3 Docker image (v1 stubs + 3 new)
    → Deploy → same as Scenario A
    
    ✓ Minimal re-work. Existing stubs untouched.

  Scenario C: Deploy to project's own AWS account (not SV account)
  ─────────────────────────────────────────────────────────────────
    Same redeploy flow, but select "My Project's AWS Account"
    → Enter AWS Account ID + VPC + Subnet
    → Same Docker image pulled from SV account ECR into project's EC2
    → Stub runs inside project's own account/network
    
    ✓ Works identically. Stub content unchanged.
```

---

## Version History in Portal

Every project shows full version and deployment history:

```
┌──────────────────────────────────────────────────────────────────────┐
│  payments-stub — History                                             │
│                                                                      │
│  VERSIONS                                                            │
│  ─────────                                                           │
│  v3 (current)  Jun 12 2026  12 stubs  [Deploy] [Download]          │
│  v2            Mar 05 2026  10 stubs  [Deploy] [Download]          │
│  v1            Jan 10 2026   8 stubs  [Deploy] [Download]          │
│                                                                      │
│  DEPLOYMENTS                                                         │
│  ───────────                                                         │
│  LIVE    v3  SV Account/TEST    10.0.20.10:8080  Jun 12 - present   │
│  TERM.   v2  SV Account/TEST    10.0.20.11:8080  Mar 5 - Apr 1     │
│  TERM.   v1  Own Account/TEST   172.31.0.50:8080 Jan 10 - Feb 28   │
│                                                                      │
│  [Redeploy v1 →]  [Redeploy v2 →]  [Redeploy v3 →]                 │
└──────────────────────────────────────────────────────────────────────┘
```

Any version can be redeployed to any target at any time.

---

## Summary: What You Can and Cannot Change Without Re-uploading

| Action | Need Re-upload? | Need Re-generate? | Need Redeploy? |
|--------|----------------|-------------------|----------------|
| Suspend and resume same stubs | No | No | Yes (new EC2) |
| Deploy to different environment (test→perf) | No | No | Yes (new EC2) |
| Deploy to different target (SV→project account) | No | No | Yes (new EC2) |
| Deploy to on-premise instead of AWS | No | No | Yes (new server) |
| Change response body of an existing stub | No | **Yes** (edit in portal) | Yes |
| Add new endpoints for Release 2 | **Yes** (upload new spec) | Yes | Yes |
| Rollback to previous version's stubs | No | No (image in ECR) | Yes |
| Change TPS tier (scale up EC2) | No | No | Yes (bigger EC2) |
| Change delay/fault settings on a stub | No | **Yes** (edit in portal) | Yes |
