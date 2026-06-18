"""Data models passed between the worker and renderers."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MetricPoint(BaseModel):
    """Single time-series data point from Timestream."""
    time: datetime
    tps: float
    latency_avg_ms: float
    error_rate: float


class ReportData(BaseModel):
    """All data needed to render any report format."""
    project_id: str
    project_name: str
    stub_id: str
    stub_name: str
    deployment_id: str
    stub_url: str
    environment: str
    report_period_hours: int
    generated_at: datetime
    peak_tps: float
    avg_tps: float
    avg_latency_ms: float
    p95_latency_ms: float
    total_requests: int
    error_rate_pct: float
    points: list[MetricPoint]


class ReportPaths(BaseModel):
    """S3 keys for the three rendered report files."""
    pdf_key: Optional[str] = None
    excel_key: Optional[str] = None
    ppt_key: Optional[str] = None
