"""Job trigger and status endpoints.

POST /api/v1/projects/{project_id}/stubs/{stub_id}/generate
  → Creates a PARSE job, sends it to the SQS parse-queue.
  → Returns 202 Accepted with job_id for polling.

GET /api/v1/jobs/{job_id}
  → Returns the current job state.
"""
from __future__ import annotations

import uuid
from pathlib import PurePosixPath

import boto3
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import CurrentUser, get_current_user, require_sv_team_or_admin
from ..models import Job, Project, Stub
from ..schemas import DownloadUrlOut, GenerateTriggerOut, JobOut
from ..sqs_client import enqueue_parse_job, get_sqs_client

router = APIRouter(prefix="/api/v1", tags=["jobs"])

_404_PROJECT = {"type": "https://mockingbird.internal/errors/not-found", "title": "Not Found", "status": 404}
_404_STUB = {"type": "https://mockingbird.internal/errors/not-found", "title": "Not Found", "status": 404}


@router.post(
    "/projects/{project_id}/stubs/{stub_id}/generate",
    response_model=GenerateTriggerOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger stub generation",
)
def trigger_generate(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_sv_team_or_admin),
) -> GenerateTriggerOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={**_404_PROJECT, "detail": f"Project {project_id} not found"})

    stub = db.get(Stub, stub_id)
    if stub is None or stub.project_id != project_id:
        raise HTTPException(status_code=404, detail={**_404_STUB, "detail": f"Stub {stub_id} not found in project {project_id}"})

    if not stub.source_file_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stub has no uploaded source file. Upload a spec file first via POST /stubs/upload.",
        )

    filename = PurePosixPath(stub.source_file_key).name

    job = Job(
        type="PARSE",
        project_id=project_id,
        stub_id=stub_id,
        status="QUEUED",
        payload={
            "source_s3_key": stub.source_file_key,
            "filename": filename,
        },
    )
    db.add(job)
    db.flush()

    if settings.sqs_parse_queue_url:
        sqs = get_sqs_client()
        msg_id = enqueue_parse_job(sqs, job.id, stub_id, project_id, stub.source_file_key, filename)
        job.sqs_message_id = msg_id

    db.commit()
    db.refresh(job)

    return GenerateTriggerOut(job_id=job.id, status=job.status, type=job.type)


@router.get(
    "/jobs/{job_id}",
    response_model=JobOut,
    summary="Get job status",
)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"type": "https://mockingbird.internal/errors/not-found", "title": "Not Found", "status": 404, "detail": f"Job {job_id} not found"},
        )
    return job


_FORMAT_KEY_MAP = {"pdf": "pdf_key", "excel": "excel_key", "ppt": "ppt_key"}


@router.get(
    "/jobs/{job_id}/download",
    response_model=DownloadUrlOut,
    summary="Get a presigned S3 download URL for a completed report job",
)
def download_report(
    job_id: uuid.UUID,
    format: str = Query(..., pattern="^(pdf|excel|ppt)$", description="pdf | excel | ppt"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> DownloadUrlOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"type": "https://mockingbird.internal/errors/not-found", "title": "Not Found", "status": 404, "detail": f"Job {job_id} not found"})
    if job.type != "REPORT":
        raise HTTPException(status_code=400, detail="Job is not a REPORT job")
    if job.status != "DONE":
        raise HTTPException(status_code=400, detail=f"Report is not ready yet (status={job.status})")

    s3_key = (job.result or {}).get(_FORMAT_KEY_MAP[format])
    if not s3_key:
        raise HTTPException(status_code=404, detail=f"{format.upper()} report not available for this job")

    expires = 900
    try:
        s3 = boto3.client("s3", region_name=settings.aws_region)
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": s3_key},
            ExpiresIn=expires,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate download URL: {exc}") from exc

    return DownloadUrlOut(url=url, format=format, expires_in_seconds=expires)
