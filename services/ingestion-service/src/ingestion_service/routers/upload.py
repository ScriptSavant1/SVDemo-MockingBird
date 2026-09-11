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

import logging
import re
import shutil
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
from ..tls_cert import TlsCertValidationError, read_limited, store_tls_files, validate_ca_bundle, validate_cert_key_pair

logger = logging.getLogger(__name__)

router = APIRouter()

_PRESIGNED_EXPIRY = 3600  # 60 minutes
_VALID_PROTOCOLS = {"HTTP", "HTTPS", "BOTH"}


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
    protocol: str = Form("HTTP", description="Stub traffic protocol: HTTP, HTTPS, or BOTH"),
    mtls_enabled: bool = Form(False, description="Require a client certificate (only meaningful with protocol != HTTP)"),
    server_cert: UploadFile | None = File(None, description="PEM server certificate — omit to auto-generate a self-signed one"),
    server_key: UploadFile | None = File(None, description="PEM private key matching server_cert"),
    ca_bundle: UploadFile | None = File(None, description="PEM CA bundle for verifying client certs (required if mtls_enabled)"),
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

    # 2. Validate protocol + any TLS cert provided alongside the spec file.
    #    A stub's protocol/cert are set at upload time (per-stub, not
    #    per-project — see project-service migration 006); a cert is
    #    optional even for HTTPS/BOTH — entrypoint.sh auto-generates a
    #    self-signed one at container startup when none is uploaded here.
    if protocol not in _VALID_PROTOCOLS:
        return IngestionResult(valid=False, errors=[f"protocol must be one of {sorted(_VALID_PROTOCOLS)}"])

    tls_cert_bytes: bytes | None = None
    tls_key_bytes: bytes | None = None
    tls_bundle_bytes: bytes | None = None
    tls_warnings: list[str] = []
    if protocol != "HTTP":
        if server_cert is not None or server_key is not None:
            if server_cert is None or server_key is None:
                return IngestionResult(valid=False, errors=["server_cert and server_key must both be provided together"])
            tls_cert_bytes = read_limited(server_cert, "server_cert")
            tls_key_bytes = read_limited(server_key, "server_key")
            if ca_bundle is not None:
                tls_bundle_bytes = read_limited(ca_bundle, "ca_bundle")
            try:
                _cert, tls_warnings = validate_cert_key_pair(tls_cert_bytes, tls_key_bytes)
                if tls_bundle_bytes is not None:
                    validate_ca_bundle(tls_bundle_bytes)
            except TlsCertValidationError as exc:
                return IngestionResult(valid=False, errors=[str(exc)])
        if mtls_enabled and tls_bundle_bytes is None:
            return IngestionResult(
                valid=False,
                errors=["mTLS requires a CA bundle — upload one together with the server certificate"],
            )

    # 3. Read file content and enforce size limit
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

    # 4. Write to a temp file so the parser (which expects a Path) can read it.
    #    file.filename is client-supplied — take only the basename (Path.name
    #    strips any ../ or / segments) before it's ever used to build a storage key.
    #
    #    The file is written under its ORIGINAL name (in a fresh temp dir), not
    #    a randomly-generated temp filename. Some parsers — notably CA LISA,
    #    whose "%%StatusCode%%" template variable can only be resolved from a
    #    filename hint like "Error400Response" — infer meaning from the source
    #    filename. A random name (tmpXXXXXX.txt) silently defeats that
    #    inference and makes every such response fall back to 200, including
    #    genuine error responses. Using the real filename here is what lets
    #    that inference actually work end-to-end.
    original_name = Path(file.filename or "upload.txt").name or "upload.txt"
    tmp_dir: Path | None = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="mb-upload-"))
        tmp_path = tmp_dir / original_name
        tmp_path.write_bytes(content)

        # 5. Detect format and validate
        from parser_worker.detector import detect_and_parse  # noqa: PLC0415 — deferred import

        _, validation_result, parsed_file = detect_and_parse(tmp_path)
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

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

    # 6. Create Stub record (flush first so we have an ID before S3 upload).
    #    stub_id is generated here, before the Stub row exists, specifically
    #    so the TLS cert (if any) can be stored under a key that includes it
    #    — same reasoning as the source-file key just below.
    stub_id = uuid.uuid4()
    s3_key = f"stubs/{project_id}/{stub_id}/source/{original_name}"
    stub_count = len(parsed_file.stubs)
    scenario_count = sum(len(s.scenarios) for s in parsed_file.stubs)

    tls_cert_source: str | None = None
    tls_cert_s3_key: str | None = None
    tls_key_s3_key: str | None = None
    tls_ca_bundle_s3_key: str | None = None
    if protocol != "HTTP":
        if tls_cert_bytes is not None:
            tls_cert_source = "UPLOADED"
            tls_cert_s3_key, tls_key_s3_key, tls_ca_bundle_s3_key = store_tls_files(
                f"stubs/{project_id}/{stub_id}/tls", tls_cert_bytes, tls_key_bytes, tls_bundle_bytes,  # type: ignore[arg-type]
            )
        else:
            tls_cert_source = "AUTO_GENERATED"

    stub = Stub(
        id=stub_id,
        project_id=project_id,
        name=stub_name,
        format=validation_result.format_detected,
        source_file_key=s3_key,
        wiremock_mapping_count=scenario_count,
        protocol=protocol,
        mtls_enabled=mtls_enabled,
        tls_cert_source=tls_cert_source,
        tls_cert_s3_key=tls_cert_s3_key,
        tls_key_s3_key=tls_key_s3_key,
        tls_ca_bundle_s3_key=tls_ca_bundle_s3_key,
    )
    db.add(stub)
    db.flush()  # write to transaction — file storage must succeed before commit

    # 7. Store the uploaded source file — local disk or S3
    content_type = file.content_type or "application/octet-stream"
    if is_local_storage():
        upload_local(s3_key, content)
    else:
        s3 = get_s3_client()
        upload_bytes(s3, s3_key, content, content_type)

    # 8. Pre-generate WireMock ZIP so the download endpoint works immediately.
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
        logger.exception(
            "WireMock pre-generation failed for stub %s (project %s) — upload still succeeds, "
            "but the user will need to retry Generate manually",
            stub_id, project_id,
        )
        wiremock_key = None  # non-fatal — upload still succeeds

    # 9. Pre-generate the full Spring Boot stub project in local dev.
    #    In production the generator-worker does this from the SQS generate-queue.
    #    Stored at stubs/{project_id}/{stub_id}/generated/stub-engine.zip
    #
    #    Built directly as ZIP bytes in memory (generate_springboot_project_zip)
    #    rather than writing every generated file to a real temp directory,
    #    reading them all back with rglob to build a ZIP, then deleting the
    #    directory — that used to mean real disk I/O for every one of
    #    potentially hundreds of generated files (mappings, lookup tables,
    #    Java sources), on every single upload, purely to immediately
    #    re-read and discard them.
    if is_local_storage():
        springboot_key = f"stubs/{project_id}/{stub_id}/generated/stub-engine.zip"
        try:
            from parser_worker.generator.springboot import generate_springboot_project_zip  # noqa: PLC0415
            _slug = re.sub(r"[^\w-]", "-", stub_name.lower())[:50] or "stub"
            gen_bytes = generate_springboot_project_zip(
                parsed_file,
                project_id=_slug,
                project_name=stub_name,
                mtls_enabled=mtls_enabled,
                protocol=protocol,
            )
            upload_local(springboot_key, gen_bytes)
        except Exception:
            logger.exception(
                "Spring Boot stub-engine pre-generation failed for stub %s (project %s) — "
                "upload still succeeds, but Download Stub Project will 404 until regenerated",
                stub_id, project_id,
            )

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
