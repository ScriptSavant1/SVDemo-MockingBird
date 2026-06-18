"""Phase 5 Sprint 14 — metrics-service tests.

Tests cover:
  - parse_prometheus_text: counts, error detection, comment/blank skip
  - Scraper.compute_snapshot: TPS from counter delta, zero TPS on first scrape
  - Scraper.compute_snapshot: latency avg/max, error rate
  - fetch_prometheus: mocked HTTP 200 returns text
  - fetch_prometheus: raises on HTTP 503
  - timestream.write_snapshot: calls boto3 write_records with correct shape
  - timestream.query_history: parses Timestream response into MetricHistoryPoints
  - redis_pub.publish_snapshot: calls setex + publish
  - redis_pub.get_latest_snapshot: returns parsed dict or None
  - REST /api/v1/metrics/{id}/current: 200 from Redis, 404 when missing
  - REST /api/v1/metrics/{id}/history: calls timestream and returns points
  - GET /health: 200 ok
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_lib
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

# ── Constants ──────────────────────────────────────────────────────────────────

DEPLOYMENT_ID = str(uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"))
PROJECT_ID = str(uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001"))
STUB_ID = str(uuid.UUID("cccccccc-0000-0000-0000-000000000001"))
EC2_IP = "10.0.1.100"

SAMPLE_PROMETHEUS = """\
# HELP http_server_requests_seconds Duration of HTTP server request handling
# TYPE http_server_requests_seconds summary
http_server_requests_seconds_count{exception="None",method="GET",outcome="SUCCESS",status="200",uri="/api/v1/stubs/{id}"} 10000.0
http_server_requests_seconds_sum{exception="None",method="GET",outcome="SUCCESS",status="200",uri="/api/v1/stubs/{id}"} 50.0
http_server_requests_seconds_max{exception="None",method="GET",outcome="SUCCESS",status="200",uri="/api/v1/stubs/{id}"} 0.02
http_server_requests_seconds_count{exception="None",method="GET",outcome="SERVER_ERROR",status="500",uri="/api/v1/stubs/{id}"} 100.0
http_server_requests_seconds_sum{exception="None",method="GET",outcome="SERVER_ERROR",status="500",uri="/api/v1/stubs/{id}"} 5.0
http_server_requests_seconds_max{exception="None",method="GET",outcome="SERVER_ERROR",status="500",uri="/api/v1/stubs/{id}"} 0.05
"""

# ── Prometheus parser tests ───────────────────────────────────────────────────

def test_parse_prometheus_counts_total_requests():
    from metrics_service.scraper import parse_prometheus_text
    result = parse_prometheus_text(SAMPLE_PROMETHEUS)
    assert result.total_count == 10100.0


def test_parse_prometheus_counts_server_errors():
    from metrics_service.scraper import parse_prometheus_text
    result = parse_prometheus_text(SAMPLE_PROMETHEUS)
    assert result.error_count == 100.0


def test_parse_prometheus_aggregates_latency_sum():
    from metrics_service.scraper import parse_prometheus_text
    result = parse_prometheus_text(SAMPLE_PROMETHEUS)
    assert result.total_sum_s == pytest.approx(55.0)


def test_parse_prometheus_takes_max_latency():
    from metrics_service.scraper import parse_prometheus_text
    result = parse_prometheus_text(SAMPLE_PROMETHEUS)
    assert result.max_latency_s == pytest.approx(0.05)


def test_parse_prometheus_ignores_comments_and_blanks():
    from metrics_service.scraper import parse_prometheus_text
    text = "\n# HELP foo bar\n# TYPE foo counter\n\nfoo{a=\"1\"} 1.0\n"
    result = parse_prometheus_text(text)
    # foo is not an http_server_requests metric — all fields should be 0
    assert result.total_count == 0.0


# ── Scraper.compute_snapshot tests ───────────────────────────────────────────

def _make_parsed(count=10000.0, sum_s=50.0, max_s=0.05, errors=100.0):
    from metrics_service.scraper import _ParsedRaw
    r = _ParsedRaw()
    r.total_count = count
    r.total_sum_s = sum_s
    r.max_latency_s = max_s
    r.error_count = errors
    return r


def test_scraper_tps_zero_on_first_scrape():
    from metrics_service.scraper import Scraper
    s = Scraper()
    snapshot = s.compute_snapshot(DEPLOYMENT_ID, PROJECT_ID, STUB_ID, EC2_IP,
                                  _make_parsed(), now=1000.0)
    assert snapshot.tps == 0.0


def test_scraper_tps_calculated_from_counter_delta():
    from metrics_service.scraper import Scraper
    s = Scraper()
    s.compute_snapshot(DEPLOYMENT_ID, PROJECT_ID, STUB_ID, EC2_IP,
                       _make_parsed(count=0.0), now=0.0)
    snapshot = s.compute_snapshot(DEPLOYMENT_ID, PROJECT_ID, STUB_ID, EC2_IP,
                                  _make_parsed(count=1000.0), now=1.0)
    assert snapshot.tps == pytest.approx(1000.0)


def test_scraper_latency_avg_computed_correctly():
    from metrics_service.scraper import Scraper
    s = Scraper()
    # 10000 requests, 50s total → avg 5ms
    snapshot = s.compute_snapshot(DEPLOYMENT_ID, PROJECT_ID, STUB_ID, EC2_IP,
                                  _make_parsed(count=10000.0, sum_s=50.0), now=1.0)
    assert snapshot.latency_avg_ms == pytest.approx(5.0, abs=0.01)


def test_scraper_error_rate_calculated_correctly():
    from metrics_service.scraper import Scraper
    s = Scraper()
    # 100 errors out of 10100 total ≈ 0.0099
    snapshot = s.compute_snapshot(DEPLOYMENT_ID, PROJECT_ID, STUB_ID, EC2_IP,
                                  _make_parsed(count=10100.0, errors=100.0), now=1.0)
    assert snapshot.error_rate == pytest.approx(100 / 10100, abs=0.0001)


# ── fetch_prometheus tests ────────────────────────────────────────────────────

@responses_lib.activate
def test_fetch_prometheus_returns_text_on_200():
    from metrics_service.scraper import fetch_prometheus
    responses_lib.add(
        responses_lib.GET,
        f"http://{EC2_IP}:8080/actuator/prometheus",
        body=SAMPLE_PROMETHEUS,
        status=200,
    )
    text = fetch_prometheus(EC2_IP)
    assert "http_server_requests_seconds" in text


@responses_lib.activate
def test_fetch_prometheus_raises_on_non_200():
    from metrics_service.scraper import fetch_prometheus
    responses_lib.add(
        responses_lib.GET,
        f"http://{EC2_IP}:8080/actuator/prometheus",
        status=503,
    )
    with pytest.raises(Exception):
        fetch_prometheus(EC2_IP)


# ── Timestream tests ──────────────────────────────────────────────────────────

def _make_snapshot() -> "MetricSnapshot":
    from metrics_service.models import MetricSnapshot
    return MetricSnapshot(
        deployment_id=DEPLOYMENT_ID,
        project_id=PROJECT_ID,
        stub_id=STUB_ID,
        ec2_ip=EC2_IP,
        tps=1234.5,
        request_count=100000,
        error_count=50,
        error_rate=0.0005,
        latency_avg_ms=5.2,
        latency_max_ms=50.0,
        scraped_at=datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_timestream_write_calls_write_records():
    from metrics_service.timestream import write_snapshot
    mock_client = MagicMock()
    write_snapshot(mock_client, "mockingbird", "stub_metrics", _make_snapshot())
    mock_client.write_records.assert_called_once()
    call_kwargs = mock_client.write_records.call_args[1]
    assert call_kwargs["DatabaseName"] == "mockingbird"
    assert call_kwargs["TableName"] == "stub_metrics"
    records = call_kwargs["Records"]
    assert len(records) == 1
    assert records[0]["MeasureValueType"] == "MULTI"
    measure_names = [m["Name"] for m in records[0]["MeasureValues"]]
    assert "tps" in measure_names
    assert "error_rate" in measure_names


def test_timestream_query_parses_response():
    from metrics_service.timestream import _parse_query_response
    response = {
        "ColumnInfo": [
            {"Name": "time"},
            {"Name": "tps"},
            {"Name": "latency_avg_ms"},
            {"Name": "error_rate"},
        ],
        "Rows": [
            {
                "Data": [
                    {"ScalarValue": "2026-06-18 12:00:00.000000000 UTC"},
                    {"ScalarValue": "1234.5"},
                    {"ScalarValue": "5.2"},
                    {"ScalarValue": "0.0005"},
                ]
            }
        ],
    }
    points = _parse_query_response(response)
    assert len(points) == 1
    assert points[0].tps == pytest.approx(1234.5)
    assert points[0].latency_avg_ms == pytest.approx(5.2)


# ── Redis pub/sub tests ───────────────────────────────────────────────────────

def test_redis_publish_calls_setex_and_publish():
    from metrics_service.redis_pub import publish_snapshot
    mock_redis = MagicMock()
    snapshot_dict = _make_snapshot().model_dump()
    publish_snapshot(mock_redis, snapshot_dict)
    mock_redis.setex.assert_called_once()
    mock_redis.publish.assert_called_once()
    # Verify correct channel name
    channel_arg = mock_redis.publish.call_args[0][0]
    assert DEPLOYMENT_ID in channel_arg


def test_redis_get_latest_returns_dict():
    from metrics_service.redis_pub import get_latest_snapshot
    mock_redis = MagicMock()
    snapshot_dict = _make_snapshot().model_dump()
    mock_redis.get.return_value = json.dumps(snapshot_dict, default=str)
    result = get_latest_snapshot(mock_redis, DEPLOYMENT_ID)
    assert result is not None
    assert result["deployment_id"] == DEPLOYMENT_ID


def test_redis_get_latest_returns_none_when_missing():
    from metrics_service.redis_pub import get_latest_snapshot
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    result = get_latest_snapshot(mock_redis, DEPLOYMENT_ID)
    assert result is None


# ── REST API tests ────────────────────────────────────────────────────────────

def _build_test_app(redis_mock=None, ts_query_mock=None):
    """Build a TestClient with pre-wired app state (skips real DB/AWS)."""
    from metrics_service.main import app
    from fastapi.testclient import TestClient

    app.state.redis = redis_mock or MagicMock()
    app.state.timestream_write_client = MagicMock()
    app.state.timestream_query_client = ts_query_mock or MagicMock()
    app.state.timestream_database = "mockingbird"
    app.state.timestream_table = "stub_metrics"

    # Use TestClient with lifespan=False so background scraper doesn't start
    return TestClient(app, raise_server_exceptions=True)


def test_health_endpoint_returns_ok():
    client = _build_test_app()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_metrics_current_returns_snapshot_from_redis():
    from metrics_service.redis_pub import _snapshot_key
    mock_redis = MagicMock()
    snapshot_dict = _make_snapshot().model_dump()
    mock_redis.get.return_value = json.dumps(snapshot_dict, default=str)

    client = _build_test_app(redis_mock=mock_redis)
    resp = client.get(f"/api/v1/metrics/{DEPLOYMENT_ID}/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deployment_id"] == DEPLOYMENT_ID
    assert data["snapshot"]["tps"] == pytest.approx(1234.5)


def test_metrics_current_returns_404_when_not_in_redis():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    client = _build_test_app(redis_mock=mock_redis)
    resp = client.get(f"/api/v1/metrics/{DEPLOYMENT_ID}/current")
    assert resp.status_code == 404


def test_metrics_history_returns_points():
    from metrics_service.models import MetricHistoryPoint
    mock_ts_query = MagicMock()
    mock_ts_query.query.return_value = {
        "ColumnInfo": [
            {"Name": "time"},
            {"Name": "tps"},
            {"Name": "latency_avg_ms"},
            {"Name": "error_rate"},
        ],
        "Rows": [
            {
                "Data": [
                    {"ScalarValue": "2026-06-18 12:00:00.000000000 UTC"},
                    {"ScalarValue": "999.0"},
                    {"ScalarValue": "4.5"},
                    {"ScalarValue": "0.001"},
                ]
            }
        ],
    }

    client = _build_test_app(ts_query_mock=mock_ts_query)
    resp = client.get(f"/api/v1/metrics/{DEPLOYMENT_ID}/history?minutes=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query_minutes"] == 30
    assert len(data["points"]) == 1
    assert data["points"][0]["tps"] == pytest.approx(999.0)
