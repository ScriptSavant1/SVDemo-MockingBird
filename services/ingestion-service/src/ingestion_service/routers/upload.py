"""File upload, format detection, validation, and S3 storage.

POST /api/v1/projects/{project_id}/stubs/upload
  — accepts multipart/form-data (file + stub_name)
  — auto-detects format via parser-worker
  — on valid file: creates Stub record, uploads to S3, returns 201 + IngestionResult
  — on invalid file: returns 200 + IngestionResult(valid=False, errors=[...])

GET /api/v1/projects/{project_id}/stubs/{stub_id}/source
  — returns a presigned S3 URL (60-minute expiry)

GET /api/v1/projects/{project_id}/stubs/{stub_id}/wiremock.zip
  — download the generated WireMock mapping files as a ZIP
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import CurrentUser, get_current_user, require_sv_team_or_admin
from ..models import Project, Stub
from ..s3_client import (
    generate_presigned_url,
    get_s3_client,
    is_local_storage,
    local_file_url,
    upload_bytes,
    upload_local,
)
from ..schemas import DownloadUrlResponse, IngestionResult

router = APIRouter()

_PRESIGNED_EXPIRY = 3600  # 60 minutes


@router.post(
    "/api/v1/projects/{project_id}/stubs/upload",
    response_model=IngestionResult,
    status_code=status.HTTP_200_OK,
    summary="Upload a spec file and validate it",
)
def upload_stub_file(
    project_id: uuid.UUID,
    stub_name: str = Form(..., description="Display name for this stub"),
    file: UploadFile = File(..., description="Spec file (.txt, .json, Postman collection)"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_sv_team_or_admin),
) -> IngestionResult:
    # 1. Verify the project exists
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # 2. Read file content and enforce size limit
    content = file.file.read()
    if len(content) == 0:
        return IngestionResult(
            valid=False,
            errors=["Uploaded file is empty"],
        )
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB limit",
        )

    # 3. Write to a temp file so the parser (which expects a Path) can read it
    original_name = file.filename or "upload.txt"
    suffix = Path(original_name).suffix or ".txt"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        # 4. Detect format and validate
        from parser_worker.detector import detect_and_parse  # noqa: PLC0415 — deferred import

        _, validation_result, parsed_file = detect_and_parse(tmp_path)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    if not validation_result.valid:
        return IngestionResult(
            valid=False,
            format_detected=validation_result.format_detected or None,
            errors=[str(e) for e in validation_result.errors],
            warnings=validation_result.warnings,
        )

    # 5. Create Stub record (flush first so we have an ID before S3 upload)
    stub_id = uuid.uuid4()
    s3_key = f"stubs/{project_id}/{stub_id}/source/{original_name}"
    stub_count = len(parsed_file.stubs)
    scenario_count = sum(len(s.scenarios) for s in parsed_file.stubs)

    stub = Stub(
        id=stub_id,
        project_id=project_id,
        name=stub_name,
        format=validation_result.format_detected,
        source_file_key=s3_key,
        wiremock_mapping_count=scenario_count,
    )
    db.add(stub)
    db.flush()  # write to transaction — file storage must succeed before commit

    # 6. Store the uploaded source file — local disk or S3
    content_type = file.content_type or "application/octet-stream"
    if is_local_storage():
        upload_local(s3_key, content)
    else:
        s3 = get_s3_client()
        upload_bytes(s3, s3_key, content, content_type)

    # 7. Pre-generate WireMock ZIP so the download endpoint works immediately.
    #    Stored at stubs/{project_id}/{stub_id}/wiremock/mappings.zip
    wiremock_key = f"stubs/{project_id}/{stub_id}/wiremock/mappings.zip"
    try:
        from ..wiremock_generator import generate_wiremock_zip  # noqa: PLC0415
        wiremock_bytes = generate_wiremock_zip(parsed_file)
        if is_local_storage():
            upload_local(wiremock_key, wiremock_bytes)
        else:
            upload_bytes(get_s3_client(), wiremock_key, wiremock_bytes, "application/zip")
    except Exception:
        wiremock_key = None  # non-fatal — upload still succeeds

    db.commit()

    return IngestionResult(
        valid=True,
        format_detected=validation_result.format_detected,
        summary=validation_result.summary,
        stub_count=stub_count,
        scenario_count=scenario_count,
        warnings=validation_result.warnings,
        s3_key=s3_key,
        stub_id=str(stub_id),
    )


@router.get(
    "/api/v1/projects/{project_id}/stubs/{stub_id}/source",
    response_model=DownloadUrlResponse,
    summary="Get a presigned S3 URL to download the original spec file",
)
def get_source_url(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> DownloadUrlResponse:
    stub = db.get(Stub, stub_id)
    if stub is None or stub.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stub {stub_id} not found in project {project_id}",
        )
    if stub.source_file_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No source file stored for this stub",
        )

    if is_local_storage():
        url = local_file_url(stub.source_file_key)
    else:
        s3 = get_s3_client()
        url = generate_presigned_url(s3, stub.source_file_key, expires_in=_PRESIGNED_EXPIRY)
    filename = Path(stub.source_file_key).name

    return DownloadUrlResponse(
        stub_id=str(stub_id),
        filename=filename,
        presigned_url=url,
        expires_in_seconds=_PRESIGNED_EXPIRY,
    )


@router.get(
    "/api/v1/projects/{project_id}/stubs/{stub_id}/wiremock.zip",
    summary="Download generated WireMock mappings as a ZIP",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "WireMock mapping ZIP"},
        404: {"description": "Stub or WireMock ZIP not found"},
    },
)
def download_wiremock_zip(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Response:
    stub = db.get(Stub, stub_id)
    if stub is None or stub.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Stub {stub_id} not found in project {project_id}")

    wiremock_key = f"stubs/{project_id}/{stub_id}/wiremock/mappings.zip"

    if is_local_storage():
        local_path = Path(settings.local_storage_path or "./uploads") / wiremock_key
        if not local_path.exists():
            # Re-generate on demand if not pre-generated (e.g. uploaded before this feature)
            if not stub.source_file_key:
                raise HTTPException(status_code=404, detail="No source file stored for this stub")
            source_path = Path(settings.local_storage_path or "./uploads") / stub.source_file_key
            if not source_path.exists():
                raise HTTPException(status_code=404, detail="Source file not found on disk")
            from parser_worker.detector import detect_and_parse  # noqa: PLC0415
            from ..wiremock_generator import generate_wiremock_zip  # noqa: PLC0415
            _, vr, parsed_file = detect_and_parse(source_path)
            if not vr.valid or parsed_file is None:
                raise HTTPException(status_code=422, detail="Could not re-parse source file")
            zip_bytes = generate_wiremock_zip(parsed_file)
            upload_local(wiremock_key, zip_bytes)
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="wiremock-{stub_id}.zip"'},
            )
        return Response(
            content=local_path.read_bytes(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="wiremock-{stub_id}.zip"'},
        )

    # S3 path — generate presigned URL
    try:
        s3 = get_s3_client()
        url = generate_presigned_url(s3, wiremock_key, expires_in=_PRESIGNED_EXPIRY)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"WireMock ZIP not found: {exc}") from exc
    from fastapi.responses import RedirectResponse  # noqa: PLC0415
    return RedirectResponse(url=url)
