"""Fetch project/stub/deployment metadata + Timestream metrics to build ReportData.

Queries the platform PostgreSQL DB (read-only) and the Timestream write/query
client to assemble everything the renderers need.
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import MetricPoint, ReportData

logger = logging.getLogger(__name__)


def _query_timestream(
    query_client: Any,
    ts_database: str,
    ts_table: str,
    deployment_id: str,
    hours: int,
) -> list[MetricPoint]:
    sql = (
        f"SELECT time, tps, latency_avg_ms, error_rate "
        f'FROM "{ts_database}"."{ts_table}" '
        f"WHERE deployment_id = '{deployment_id}' "
        f"AND time between ago({hours}h) and now() "
        f"ORDER BY time ASC"
    )
    try:
        resp = query_client.query(QueryString=sql)
    except Exception as exc:
        logger.warning("Timestream query failed for %s: %s", deployment_id, exc)
        return []

    columns = [c["Name"] for c in resp.get("ColumnInfo", [])]
    points: list[MetricPoint] = []
    for row in resp.get("Rows", []):
        data = {col: d.get("ScalarValue") for col, d in zip(columns, row.get("Data", []))}
        try:
            points.append(MetricPoint(
                time=datetime.fromisoformat(
                    data["time"].rstrip(" UTC").replace(" ", "T") + "+00:00"
                ),
                tps=float(data.get("tps") or 0),
                latency_avg_ms=float(data.get("latency_avg_ms") or 0),
                error_rate=float(data.get("error_rate") or 0),
            ))
        except (KeyError, ValueError):
            continue
    return points


def build_report_data(
    db: Session,
    query_client: Any,
    ts_database: str,
    ts_table: str,
    deployment_id: str,
    hours: int = 24,
) -> ReportData:
    """Assemble ReportData from DB + Timestream for a given deployment."""
    row = db.execute(
        text(
            "SELECT d.id, d.project_id, d.stub_id, d.stub_url, d.ec2_ip_address, "
            "p.name AS project_name, s.name AS stub_name, p.environment "
            "FROM deployments d "
            "JOIN projects p ON p.id = d.project_id "
            "JOIN stubs s ON s.id = d.stub_id "
            "WHERE d.id = :id"
        ),
        {"id": deployment_id},
    ).fetchone()

    if row is None:
        raise ValueError(f"Deployment {deployment_id} not found")

    row_dict = dict(row._mapping)
    project_id = str(row_dict["project_id"])
    stub_id = str(row_dict["stub_id"])
    project_name = row_dict.get("project_name") or project_id
    stub_name = row_dict.get("stub_name") or stub_id
    stub_url = row_dict.get("stub_url") or ""
    environment = row_dict.get("environment") or "TEST"

    points = _query_timestream(query_client, ts_database, ts_table, deployment_id, hours)

    tps_values = [p.tps for p in points] or [0.0]
    latency_values = [p.latency_avg_ms for p in points] or [0.0]
    error_values = [p.error_rate for p in points] or [0.0]

    sorted_latency = sorted(latency_values)
    p95_idx = int(len(sorted_latency) * 0.95)
    p95_latency = sorted_latency[min(p95_idx, len(sorted_latency) - 1)]

    avg_error_rate = statistics.mean(error_values)
    total_requests = max(1, int(statistics.mean(tps_values) * hours * 3600))

    return ReportData(
        project_id=project_id,
        project_name=project_name,
        stub_id=stub_id,
        stub_name=stub_name,
        deployment_id=deployment_id,
        stub_url=stub_url,
        environment=environment,
        report_period_hours=hours,
        generated_at=datetime.now(timezone.utc),
        peak_tps=max(tps_values),
        avg_tps=statistics.mean(tps_values),
        avg_latency_ms=statistics.mean(latency_values),
        p95_latency_ms=p95_latency,
        total_requests=total_requests,
        error_rate_pct=round(avg_error_rate * 100, 4),
        points=points,
    )
