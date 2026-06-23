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

import io
import re
import shutil
import tempfile
import uuid
import zipfile
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

    # Override parser-derived stub names with the user-supplied stub_name.
    # Parsers like CA LISA derive names from the source filename, which is a
    # random temp path (e.g. tmppn51v54h.txt) when files arrive via the portal.
    if parsed_file is not None and parsed_file.stubs and stub_name:
        if len(parsed_file.stubs) == 1:
            parsed_file.stubs[0].name = stub_name
        else:
            for _i, _s in enumerate(parsed_file.stubs, 1):
                _s.name = f"{stub_name} {_i}"

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
        from datetime import datetime, timezone  # noqa: PLC0415
        from ..wiremock_generator import generate_wiremock_zip  # noqa: PLC0415
        wiremock_bytes = generate_wiremock_zip(parsed_file)
        if is_local_storage():
            upload_local(wiremock_key, wiremock_bytes)
        else:
            upload_bytes(get_s3_client(), wiremock_key, wiremock_bytes, "application/zip")
        stub.generated_at = datetime.now(timezone.utc)
    except Exception:
        wiremock_key = None  # non-fatal — upload still succeeds

    # 8. Pre-generate the full Spring Boot stub project in local dev.
    #    In production the generator-worker does this from the SQS generate-queue.
    #    Stored at stubs/{project_id}/{stub_id}/generated/stub-engine.zip
    if is_local_storage():
        springboot_key = f"stubs/{project_id}/{stub_id}/generated/stub-engine.zip"
        try:
            from parser_worker.generator.springboot import generate_springboot_project  # noqa: PLC0415
            _slug = re.sub(r"[^\w-]", "-", stub_name.lower())[:50] or "stub"
            gen_dir = Path(tempfile.mkdtemp(prefix="mb-gen-"))
            try:
                generate_springboot_project(parsed_file, gen_dir, project_id=_slug, project_name=stub_name)
                gen_buf = io.BytesIO()
                with zipfile.ZipFile(gen_buf, "w", compression=zipfile.ZIP_DEFLATED) as gen_zf:
                    for gen_fp in gen_dir.rglob("*"):
                        if gen_fp.is_file():
                            gen_zf.write(gen_fp, gen_fp.relative_to(gen_dir))
                upload_local(springboot_key, gen_buf.getvalue())
            finally:
                shutil.rmtree(gen_dir, ignore_errors=True)
        except Exception:
            pass  # non-fatal — upload still succeeds

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


@router.get(
    "/api/v1/projects/{project_id}/stubs/{stub_id}/stub-engine.zip",
    summary="Download the full Spring Boot stub project as a ZIP (runnable on EC2)",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "Spring Boot stub project ZIP"},
        404: {"description": "Project ZIP not found — re-upload the spec file"},
    },
)
def download_stub_engine_zip(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Response:
    stub = db.get(Stub, stub_id)
    if stub is None or stub.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Stub {stub_id} not found in project {project_id}")

    engine_key = f"stubs/{project_id}/{stub_id}/generated/stub-engine.zip"

    if is_local_storage():
        local_path = Path(settings.local_storage_path or "./uploads") / engine_key
        if not local_path.exists():
            raise HTTPException(
                status_code=404,
                detail="Spring Boot project not found. Re-upload the spec file to regenerate it.",
            )
        return Response(
            content=local_path.read_bytes(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="stub-engine-{stub_id}.zip"'},
        )

    # S3 path — generate presigned URL
    try:
        s3 = get_s3_client()
        url = generate_presigned_url(s3, engine_key, expires_in=_PRESIGNED_EXPIRY)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Spring Boot project ZIP not found: {exc}") from exc
    from fastapi.responses import RedirectResponse  # noqa: PLC0415
    return RedirectResponse(url=url)
