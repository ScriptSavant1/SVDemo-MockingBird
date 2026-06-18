"""Deploy trigger and deployment management endpoints.

POST /api/v1/projects/{project_id}/stubs/{stub_id}/deploy
  → Creates a DEPLOY job, sends it to the SQS deploy-queue.
  → Returns 202 Accepted with deployment_id and job_id.

GET /api/v1/projects/{project_id}/deployments
  → Lists all deployments for a project (most recent first).

POST /api/v1/projects/{project_id}/deployments/{deployment_id}/suspend
  → Queues a SUSPEND job (deployer-worker runs terraform destroy).

POST /api/v1/projects/{project_id}/deployments/{deployment_id}/redeploy
  → Re-queues a DEPLOY job for an existing SUSPENDED deployment.

GET /api/v1/deployments/{deployment_id}
  → Returns a single deployment.
"""
from __future__ import annotations

import secrets
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import CurrentUser, get_current_user, require_sv_team_or_admin
from ..models import Deployment, Job, Project, Stub
from ..schemas import DeploymentOut, DeployTriggerOut, ReportTriggerOut, SuspendTriggerOut
from ..sqs_client import enqueue_deploy_job, enqueue_report_job, get_sqs_client

router = APIRouter(prefix="/api/v1", tags=["deployments"])

_NOT_FOUND = {"type": "https://mockingbird.internal/errors/not-found", "title": "Not Found", "status": 404}
_CONFLICT = {"type": "https://mockingbird.internal/errors/conflict", "title": "Conflict", "status": 409}


def _select_instance_type(expected_tps: int) -> str:
    """Choose EC2 instance size based on expected TPS target."""
    return "c6i.xlarge" if expected_tps < 5000 else "c6i.2xlarge"


def _generated_s3_key(project_id: uuid.UUID, stub_id: uuid.UUID) -> str:
    return f"stubs/{project_id}/{stub_id}/generated/stub-engine.zip"


@router.post(
    "/projects/{project_id}/stubs/{stub_id}/deploy",
    response_model=DeployTriggerOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger stub deployment to EC2",
)
def trigger_deploy(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_sv_team_or_admin),
) -> DeployTriggerOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Project {project_id} not found"})

    stub = db.get(Stub, stub_id)
    if stub is None or stub.project_id != project_id:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Stub {stub_id} not found in project {project_id}"})

    # Require a generated stub package in S3 — set by generator-worker
    generated_key = _generated_s3_key(project_id, stub_id)
    if not stub.generated_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stub has not been generated yet. Run POST .../generate first.",
        )

    # Prevent double-deploy while one is already in flight
    existing = (
        db.query(Deployment)
        .filter(
            Deployment.stub_id == stub_id,
            Deployment.status.in_(["PENDING", "BUILDING", "PROVISIONING"]),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={**_CONFLICT, "detail": f"A deployment is already in flight (id={existing.id}, status={existing.status})"},
        )

    instance_type = _select_instance_type(project.expected_tps)
    api_key = secrets.token_urlsafe(32)
    terraform_state_key = f"stubs/{project_id}/{stub_id}/terraform.tfstate"

    # Create deployment record
    deployment = Deployment(
        project_id=project_id,
        stub_id=stub_id,
        target_type="AWS",
        status="PENDING",
        ec2_instance_type=instance_type,
        api_key=api_key,
        terraform_state_key=terraform_state_key,
    )
    db.add(deployment)
    db.flush()

    # Create DEPLOY job
    job = Job(
        type="DEPLOY",
        project_id=project_id,
        stub_id=stub_id,
        status="QUEUED",
        payload={
            "generated_s3_key": generated_key,
            "deployment_id": str(deployment.id),
            "target_type": "AWS",
        },
    )
    db.add(job)
    db.flush()

    deployment.job_id = job.id

    if settings.sqs_deploy_queue_url:
        sqs = get_sqs_client()
        msg_id = enqueue_deploy_job(sqs, job.id, stub_id, project_id, deployment.id, generated_key)
        job.sqs_message_id = msg_id

    db.commit()
    db.refresh(deployment)

    return DeployTriggerOut(deployment_id=deployment.id, job_id=job.id)


@router.get(
    "/projects/{project_id}/deployments",
    response_model=list[DeploymentOut],
    summary="List deployments for a project",
)
def list_deployments(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[Deployment]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Project {project_id} not found"})
    return (
        db.query(Deployment)
        .filter(Deployment.project_id == project_id)
        .order_by(Deployment.created_at.desc())
        .all()
    )


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentOut,
    summary="Get a single deployment",
)
def get_deployment(
    deployment_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Deployment:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Deployment {deployment_id} not found"})
    return deployment


@router.post(
    "/projects/{project_id}/deployments/{deployment_id}/suspend",
    response_model=SuspendTriggerOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Suspend a live deployment (terminate EC2, preserve stubs)",
)
def suspend_deployment(
    project_id: uuid.UUID,
    deployment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_sv_team_or_admin),
) -> SuspendTriggerOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Project {project_id} not found"})

    deployment = db.get(Deployment, deployment_id)
    if deployment is None or deployment.project_id != project_id:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Deployment {deployment_id} not found"})

    if deployment.status != "LIVE":
        raise HTTPException(
            status_code=409,
            detail={**_CONFLICT, "detail": f"Deployment is {deployment.status}, not LIVE — cannot suspend"},
        )

    job = Job(
        type="DEPLOY",
        project_id=project_id,
        stub_id=deployment.stub_id,
        status="QUEUED",
        payload={
            "action": "SUSPEND",
            "deployment_id": str(deployment_id),
            "terraform_state_key": deployment.terraform_state_key,
        },
    )
    db.add(job)
    deployment.status = "SUSPENDED"
    db.commit()

    return SuspendTriggerOut(deployment_id=deployment_id)


@router.post(
    "/projects/{project_id}/deployments/{deployment_id}/redeploy",
    response_model=DeployTriggerOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Redeploy a suspended deployment without re-upload",
)
def redeploy(
    project_id: uuid.UUID,
    deployment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_sv_team_or_admin),
) -> DeployTriggerOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Project {project_id} not found"})

    deployment = db.get(Deployment, deployment_id)
    if deployment is None or deployment.project_id != project_id:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Deployment {deployment_id} not found"})

    if deployment.status != "SUSPENDED":
        raise HTTPException(
            status_code=409,
            detail={**_CONFLICT, "detail": f"Deployment is {deployment.status}, not SUSPENDED — cannot redeploy"},
        )

    if deployment.stub_id is None:
        raise HTTPException(status_code=400, detail="Deployment has no associated stub")

    generated_key = _generated_s3_key(project_id, deployment.stub_id)

    job = Job(
        type="DEPLOY",
        project_id=project_id,
        stub_id=deployment.stub_id,
        status="QUEUED",
        payload={
            "generated_s3_key": generated_key,
            "deployment_id": str(deployment_id),
            "target_type": deployment.target_type,
        },
    )
    db.add(job)
    db.flush()

    deployment.status = "PENDING"
    deployment.job_id = job.id

    if settings.sqs_deploy_queue_url:
        sqs = get_sqs_client()
        msg_id = enqueue_deploy_job(sqs, job.id, deployment.stub_id, project_id, deployment_id, generated_key)
        job.sqs_message_id = msg_id

    db.commit()

    return DeployTriggerOut(deployment_id=deployment_id, job_id=job.id)


@router.post(
    "/projects/{project_id}/deployments/{deployment_id}/report",
    response_model=ReportTriggerOut,
    status_code=202,
    summary="Queue a REPORT job for a deployment (PDF + Excel + PowerPoint)",
)
def trigger_report(
    project_id: uuid.UUID,
    deployment_id: uuid.UUID,
    report_period_hours: int = 24,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> ReportTriggerOut:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None or deployment.project_id != project_id:
        raise HTTPException(status_code=404, detail={**_NOT_FOUND, "detail": f"Deployment {deployment_id} not found"})
    if deployment.status not in ("LIVE", "SUSPENDED"):
        raise HTTPException(
            status_code=409,
            detail={**_CONFLICT, "detail": f"Reports can only be generated for LIVE or SUSPENDED deployments"},
        )

    job = Job(
        type="REPORT",
        project_id=project_id,
        stub_id=deployment.stub_id,
        status="QUEUED",
        payload={"deployment_id": str(deployment_id), "report_period_hours": report_period_hours},
    )
    db.add(job)
    db.flush()

    if settings.sqs_report_queue_url:
        sqs = get_sqs_client()
        msg_id = enqueue_report_job(sqs, job.id, deployment_id, project_id, report_period_hours)
        job.sqs_message_id = msg_id

    db.commit()

    return ReportTriggerOut(deployment_id=deployment_id, job_id=job.id)
