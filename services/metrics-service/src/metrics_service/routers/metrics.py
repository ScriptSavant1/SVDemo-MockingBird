"""REST endpoints for metrics retrieval."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import MetricCurrentResponse, MetricHistoryResponse, MetricSnapshot
from ..redis_pub import get_latest_snapshot
from ..timestream import query_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.get(
    "/{deployment_id}/current",
    response_model=MetricCurrentResponse,
    summary="Latest metrics snapshot for a deployment (from Redis cache)",
)
def get_current(deployment_id: str, request: Request) -> MetricCurrentResponse:
    redis = request.app.state.redis
    data = get_latest_snapshot(redis, deployment_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"type": "not_found", "title": "No metrics available",
                    "status": 404, "detail": f"No metrics cached for deployment {deployment_id}"},
        )
    return MetricCurrentResponse(deployment_id=deployment_id, snapshot=MetricSnapshot(**data))


@router.get(
    "/{deployment_id}/history",
    response_model=MetricHistoryResponse,
    summary="Historical metrics from Timestream (default last 60 minutes)",
)
def get_history(
    deployment_id: str,
    request: Request,
    minutes: int = Query(default=60, ge=1, le=1440),
) -> MetricHistoryResponse:
    ts_write = request.app.state.timestream_write_client
    # We need the query client — stored separately
    ts_query = request.app.state.timestream_query_client
    ts_db = request.app.state.timestream_database
    ts_table = request.app.state.timestream_table

    points = query_history(ts_query, ts_db, ts_table, deployment_id, minutes)
    return MetricHistoryResponse(
        deployment_id=deployment_id,
        points=points,
        query_minutes=minutes,
    )
