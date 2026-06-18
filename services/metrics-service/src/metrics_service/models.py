from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MetricSnapshot(BaseModel):
    deployment_id: str
    project_id: str
    stub_id: str
    ec2_ip: str
    tps: float
    request_count: int
    error_count: int
    error_rate: float
    latency_avg_ms: float
    latency_max_ms: float
    scraped_at: datetime


class MetricHistoryPoint(BaseModel):
    time: datetime
    tps: float
    latency_avg_ms: float
    error_rate: float


class MetricCurrentResponse(BaseModel):
    deployment_id: str
    snapshot: MetricSnapshot


class MetricHistoryResponse(BaseModel):
    deployment_id: str
    points: list[MetricHistoryPoint]
    query_minutes: int
