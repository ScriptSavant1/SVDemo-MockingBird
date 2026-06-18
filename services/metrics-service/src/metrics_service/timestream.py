"""AWS Timestream write + query for stub metrics time-series data.

Write: one multi-measure record per scrape per deployment.
Query: last N minutes of metrics for a deployment, used by the history endpoint.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from .models import MetricHistoryPoint, MetricSnapshot

logger = logging.getLogger(__name__)


def write_snapshot(client: Any, database: str, table: str, snapshot: MetricSnapshot) -> None:
    """Write a MetricSnapshot as a multi-measure Timestream record."""
    ts_ms = str(int(snapshot.scraped_at.timestamp() * 1000))
    client.write_records(
        DatabaseName=database,
        TableName=table,
        Records=[
            {
                "Dimensions": [
                    {"Name": "deployment_id", "Value": snapshot.deployment_id},
                    {"Name": "project_id", "Value": snapshot.project_id},
                    {"Name": "stub_id", "Value": snapshot.stub_id},
                ],
                "MeasureName": "stub_metrics",
                "MeasureValueType": "MULTI",
                "MeasureValues": [
                    {"Name": "tps", "Value": str(snapshot.tps), "Type": "DOUBLE"},
                    {"Name": "request_count", "Value": str(snapshot.request_count), "Type": "BIGINT"},
                    {"Name": "error_count", "Value": str(snapshot.error_count), "Type": "BIGINT"},
                    {"Name": "error_rate", "Value": str(snapshot.error_rate), "Type": "DOUBLE"},
                    {"Name": "latency_avg_ms", "Value": str(snapshot.latency_avg_ms), "Type": "DOUBLE"},
                    {"Name": "latency_max_ms", "Value": str(snapshot.latency_max_ms), "Type": "DOUBLE"},
                ],
                "Time": ts_ms,
                "TimeUnit": "MILLISECONDS",
            }
        ],
    )


def query_history(
    query_client: Any,
    database: str,
    table: str,
    deployment_id: str,
    minutes: int = 60,
) -> list[MetricHistoryPoint]:
    """Query Timestream for the last N minutes of metrics for a deployment."""
    sql = (
        f"SELECT time, tps, latency_avg_ms, error_rate "
        f"FROM \"{database}\".\"{table}\" "
        f"WHERE deployment_id = '{deployment_id}' "
        f"AND time between ago({minutes}m) and now() "
        f"ORDER BY time DESC"
    )
    try:
        response = query_client.query(QueryString=sql)
    except Exception as exc:
        logger.warning("Timestream query failed for %s: %s", deployment_id, exc)
        return []

    return _parse_query_response(response)


def _parse_query_response(response: dict) -> list[MetricHistoryPoint]:
    columns = [c["Name"] for c in response.get("ColumnInfo", [])]
    points: list[MetricHistoryPoint] = []

    for row in response.get("Rows", []):
        data = row.get("Data", [])
        if len(data) != len(columns):
            continue
        values = {col: d.get("ScalarValue") for col, d in zip(columns, data)}
        try:
            points.append(MetricHistoryPoint(
                time=datetime.fromisoformat(values["time"].rstrip(" UTC").replace(" ", "T") + "+00:00"),
                tps=float(values.get("tps") or 0),
                latency_avg_ms=float(values.get("latency_avg_ms") or 0),
                error_rate=float(values.get("error_rate") or 0),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    return points
