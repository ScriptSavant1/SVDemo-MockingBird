"""On-demand generation of NFT (performance/load testing) scripts for a stub.

Phase 1 (see docs/progress/PHASE1_JMETER_NFT_GENERATION.md): JMeter only —
`download_jmeter_nft_zip` / `nft-jmeter.zip`, kept exactly as shipped and
untouched by Phase 2.

Phase 2 (see docs/progress/PHASE2_DEVWEB_NFT_GENERATION.md) adds
`download_nft_scripts_zip` / `nft-scripts.zip`, a combined download with
`jmeter/` and `devweb/` top-level folders — one script per engine covering
every stub, built from the same parsed data. This is the endpoint the
portal's "Download NFT Scripts" button now points at; `nft-jmeter.zip`
stays in the codebase unchanged for anything already depending on it.

Both endpoints are pure, additive — they don't touch upload.py's existing
upload flow, don't add any work to that request path, and read only the
already-stored source spec file the same way wiremock.zip's local fallback
already does.

Deliberately generated fresh on every download rather than pre-generated at
upload time (unlike wiremock.zip/stub-engine.zip): an NFT script is a much
lower-stakes, occasionally-needed artifact than the actual stub, so there's
no reason to add another generation pass to the upload path (whose
performance was a real, previously-reported problem — see BUGS.md BUG-034)
just to save a few hundred milliseconds on an infrequent download.
"""
from __future__ import annotations

import io
import logging
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import CurrentUser, get_current_user
from ..models import Stub
from ..s3_client import get_s3_client, is_local_storage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/api/v1/projects/{project_id}/stubs/{stub_id}/nft-jmeter.zip",
    summary="Download an automatically generated JMeter NFT test plan for this stub",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "JMeter test plan ZIP"},
        404: {"description": "Stub or source file not found"},
        422: {"description": "Source file could not be re-parsed"},
    },
)
def download_jmeter_nft_zip(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Response:
    stub = db.get(Stub, stub_id)
    if stub is None or stub.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stub {stub_id} not found in project {project_id}",
        )
    if not stub.source_file_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No source file stored for this stub")

    source_path, tmp_dir = _materialize_source_file(stub.source_file_key)
    try:
        from parser_worker.detector import detect_and_parse  # noqa: PLC0415 — deferred import, matches upload.py's style
        from parser_worker.generator.jmeter import build_jmeter_test_plan_files  # noqa: PLC0415

        _, validation_result, parsed_file = detect_and_parse(source_path)
        if not validation_result.valid or parsed_file is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not re-parse the stored source file to generate an NFT script.",
            )

        files = build_jmeter_test_plan_files(parsed_file, project_name=stub.name)
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for relative_path, text_content in files.items():
            zf.writestr(relative_path, text_content)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="nft-jmeter-{stub_id}.zip"'},
    )


@router.get(
    "/api/v1/projects/{project_id}/stubs/{stub_id}/nft-scripts.zip",
    summary="Download automatically generated NFT scripts (JMeter + DevWeb) for this stub",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "NFT scripts ZIP (jmeter/ + devweb/ folders)"},
        404: {"description": "Stub or source file not found"},
        422: {"description": "Source file could not be re-parsed"},
    },
)
def download_nft_scripts_zip(
    project_id: uuid.UUID,
    stub_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Response:
    stub = db.get(Stub, stub_id)
    if stub is None or stub.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stub {stub_id} not found in project {project_id}",
        )
    if not stub.source_file_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No source file stored for this stub")

    source_path, tmp_dir = _materialize_source_file(stub.source_file_key)
    try:
        from parser_worker.detector import detect_and_parse  # noqa: PLC0415 — deferred import, matches upload.py's style
        from parser_worker.generator.devweb import build_devweb_project_files  # noqa: PLC0415
        from parser_worker.generator.jmeter import build_jmeter_test_plan_files  # noqa: PLC0415

        _, validation_result, parsed_file = detect_and_parse(source_path)
        if not validation_result.valid or parsed_file is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not re-parse the stored source file to generate NFT scripts.",
            )

        jmeter_files = build_jmeter_test_plan_files(parsed_file, project_name=stub.name)
        devweb_files = build_devweb_project_files(parsed_file, project_name=stub.name)
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for relative_path, text_content in jmeter_files.items():
            zf.writestr(f"jmeter/{relative_path}", text_content)
        for relative_path, text_content in devweb_files.items():
            zf.writestr(f"devweb/{relative_path}", text_content)
        zf.writestr(
            "README.md",
            "# NFT Scripts\n\n"
            "- `jmeter/` — Apache JMeter test plan. Open `jmeter/test-plan.jmx`.\n"
            "- `devweb/` — LoadRunner DevWeb (VuGen) project. Open `devweb/*.usr` in VuGen.\n\n"
            "Each folder has its own README.md with setup details and scope notes.\n",
        )

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="nft-scripts-{stub_id}.zip"'},
    )


def _materialize_source_file(source_file_key: str) -> tuple[Path, Path | None]:
    """Return a real filesystem Path to the stub's stored source spec file
    (parser_worker's detect_and_parse needs one) plus a temp directory to
    clean up afterwards, or (path, None) when no cleanup is needed (local
    storage already is a real file — no copy required)."""
    if is_local_storage():
        local_path = Path(settings.local_storage_path or "./uploads") / source_file_key
        if not local_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found on disk")
        return local_path, None

    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=settings.s3_bucket, Key=source_file_key)
        content = obj["Body"].read()
    except Exception as exc:
        logger.exception("Failed to fetch source file %s from S3 for NFT generation", source_file_key)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source file not found: {exc}") from exc

    tmp_dir = Path(tempfile.mkdtemp(prefix="mb-nft-source-"))
    tmp_path = tmp_dir / Path(source_file_key).name
    tmp_path.write_bytes(content)
    return tmp_path, tmp_dir
