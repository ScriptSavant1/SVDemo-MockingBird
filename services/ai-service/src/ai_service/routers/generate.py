"""AI spec generation endpoints.

POST /api/v1/ai/generate
  — Accepts a plain-English API description.
  — Calls Claude to produce a Postman v2.1 collection.
  — Stores the result in ai_generations table.
  — Returns GenerateResponse.

GET /api/v1/ai/history
  — Returns the current user's last 20 generations, newest first.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from ..claude_client import GenerationResult, generate_stub_spec
from ..config import settings
from ..database import get_db
from ..dependencies import CurrentUser, get_current_user, require_sv_team_or_admin
from ..errors import MockingbirdError
from ..models import AiGeneration
from ..schemas import GenerateRequest, GenerateResponse, GenerationHistoryItem

logger = logging.getLogger(__name__)

# Codes catalogued in docs/ERROR_CODES.md — stable once shipped.
AI_RATE_LIMITED = "MB-AI-001"
AI_GENERATION_FAILED = "MB-AI-002"
AI_NOT_CONFIGURED = "MB-AI-003"

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


def _check_rate_limit(db: Session, user_id: uuid.UUID) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    count = (
        db.query(AiGeneration)
        .filter(AiGeneration.user_id == user_id, AiGeneration.created_at >= cutoff)
        .count()
    )
    if count >= settings.rate_limit_per_hour:
        raise MockingbirdError(
            status.HTTP_429_TOO_MANY_REQUESTS, AI_RATE_LIMITED,
            f"Limit reached: {settings.rate_limit_per_hour} AI generations per hour — try again later",
        )


def _get_anthropic_client():
    """Create Anthropic client — raises 503 if API key not configured."""
    try:
        from anthropic import Anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise MockingbirdError(
            status.HTTP_503_SERVICE_UNAVAILABLE, AI_NOT_CONFIGURED,
            "AI generation isn't available on this server (the 'anthropic' package is not installed)",
        ) from exc

    if not settings.anthropic_api_key:
        raise MockingbirdError(
            status.HTTP_503_SERVICE_UNAVAILABLE, AI_NOT_CONFIGURED,
            "AI generation isn't configured on this server (no Anthropic API key) — ask an admin",
        )
    return Anthropic(api_key=settings.anthropic_api_key)


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate stub spec from plain-English description",
)
def generate(
    body: GenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_sv_team_or_admin),
) -> GenerateResponse:
    _check_rate_limit(db, user.id)

    client = _get_anthropic_client()

    try:
        result: GenerationResult = generate_stub_spec(
            client=client,
            description=body.description,
            model=settings.generation_model,
            max_tokens=settings.max_tokens,
        )
    except ValueError as exc:
        ref = uuid.uuid4().hex[:8]
        logger.warning("[ref %s] AI reply could not be used: %s", ref, exc)
        raise MockingbirdError(
            status.HTTP_502_BAD_GATEWAY, AI_GENERATION_FAILED,
            f"The AI reply couldn't be turned into a stub spec — try rephrasing the description (ref {ref})",
        ) from exc

    record = AiGeneration(
        user_id=user.id,
        project_id=body.project_id,
        description=body.description,
        detected_intent=result.detected_intent,
        suggested_stub_name=result.suggested_name,
        spec_content=result.spec_content,
        estimated_stub_count=result.estimated_stubs,
        model_used=result.model_used,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return GenerateResponse(
        generation_id=record.id,
        detected_intent=record.detected_intent,
        suggested_stub_name=record.suggested_stub_name,
        spec_format="postman_v21",
        spec_content=record.spec_content,
        estimated_stub_count=record.estimated_stub_count,
        model_used=record.model_used,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        created_at=record.created_at.isoformat(),
    )


@router.get(
    "/history",
    response_model=list[GenerationHistoryItem],
    summary="List recent AI generations for current user",
)
def history(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[GenerationHistoryItem]:
    records = (
        db.query(AiGeneration)
        .filter(AiGeneration.user_id == user.id)
        .order_by(AiGeneration.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        GenerationHistoryItem(
            generation_id=r.id,
            detected_intent=r.detected_intent,
            suggested_stub_name=r.suggested_stub_name,
            estimated_stub_count=r.estimated_stub_count,
            model_used=r.model_used,
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]
