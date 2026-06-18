"""Prometheus scraper for Spring Boot stub engine metrics.

The stub engine exposes /actuator/prometheus (Micrometer + WireMock metrics).
We parse the text format, derive TPS from counter deltas, and compute latency.

Key metrics consumed:
  http_server_requests_seconds_count  — cumulative request count (all outcomes)
  http_server_requests_seconds_sum    — cumulative latency seconds
  http_server_requests_seconds_max    — max latency in the last reporting period
  (outcome="SERVER_ERROR" subset counts 5xx errors)
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

from .models import MetricSnapshot

logger = logging.getLogger(__name__)

_LABEL_RE = re.compile(r'(\w+)="([^"]*)"')


def _parse_labels(label_str: str) -> dict[str, str]:
    return {k: v for k, v in _LABEL_RE.findall(label_str)}


def _split_metric_line(line: str) -> tuple[str, str, float] | None:
    """Split 'name{labels} value' handling } inside quoted label values.

    Returns (name, label_str, value) or None if the line cannot be parsed.
    The Prometheus text format allows arbitrary characters inside quoted label
    values, including '}', so we cannot use a simple [^}]* regex.
    """
    brace = line.find("{")
    if brace == -1:
        # No labels — 'name value [timestamp]'
        parts = line.split()
        if len(parts) < 2:
            return None
        try:
            return parts[0], "", float(parts[1])
        except ValueError:
            return None

    name = line[:brace]
    # Walk forward from the opening brace to find the matching closing brace,
    # skipping characters that are inside double-quoted strings.
    i = brace + 1
    in_quote = False
    while i < len(line):
        c = line[i]
        if c == '"':
            in_quote = not in_quote
        elif c == "}" and not in_quote:
            break
        i += 1
    if i >= len(line):
        return None  # malformed line

    label_str = line[brace + 1 : i]
    rest = line[i + 1 :].strip()
    parts = rest.split()
    if not parts:
        return None
    try:
        return name, label_str, float(parts[0])
    except ValueError:
        return None


@dataclass
class _ParsedRaw:
    total_count: float = 0.0
    total_sum_s: float = 0.0
    max_latency_s: float = 0.0
    error_count: float = 0.0


def parse_prometheus_text(text: str) -> _ParsedRaw:
    """Parse Prometheus exposition format. Returns aggregate metrics."""
    result = _ParsedRaw()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = _split_metric_line(line)
        if parsed is None:
            continue
        name, label_str, value = parsed
        if value != value:  # NaN guard
            continue
        labels = _parse_labels(label_str)

        if name == "http_server_requests_seconds_count":
            result.total_count += value
            if labels.get("outcome") == "SERVER_ERROR":
                result.error_count += value
        elif name == "http_server_requests_seconds_sum":
            result.total_sum_s += value
        elif name == "http_server_requests_seconds_max":
            if value > result.max_latency_s:
                result.max_latency_s = value

    return result


def fetch_prometheus(ip: str, port: int = 8080, timeout: int = 5) -> str:
    """HTTP GET the Prometheus endpoint. Raises on connection error or non-200."""
    resp = requests.get(f"http://{ip}:{port}/actuator/prometheus", timeout=timeout)
    resp.raise_for_status()
    return resp.text


class Scraper:
    """Stateful scraper that tracks previous counter values to compute TPS."""

    def __init__(self) -> None:
        # {deployment_id: (prev_count, prev_timestamp)}
        self._prev: dict[str, tuple[float, float]] = {}

    def compute_snapshot(
        self,
        deployment_id: str,
        project_id: str,
        stub_id: str,
        ec2_ip: str,
        parsed: _ParsedRaw,
        now: float | None = None,
    ) -> MetricSnapshot:
        if now is None:
            now = time.time()

        prev = self._prev.get(deployment_id)
        if prev is not None:
            prev_count, prev_time = prev
            elapsed = now - prev_time
            tps = max(0.0, (parsed.total_count - prev_count) / elapsed) if elapsed > 0 else 0.0
        else:
            tps = 0.0

        self._prev[deployment_id] = (parsed.total_count, now)

        count = int(parsed.total_count)
        errors = int(parsed.error_count)
        error_rate = (parsed.error_count / parsed.total_count) if parsed.total_count > 0 else 0.0
        latency_avg_ms = (
            (parsed.total_sum_s / parsed.total_count * 1000) if parsed.total_count > 0 else 0.0
        )
        latency_max_ms = parsed.max_latency_s * 1000

        return MetricSnapshot(
            deployment_id=deployment_id,
            project_id=project_id,
            stub_id=stub_id,
            ec2_ip=ec2_ip,
            tps=round(tps, 2),
            request_count=count,
            error_count=errors,
            error_rate=round(error_rate, 4),
            latency_avg_ms=round(latency_avg_ms, 3),
            latency_max_ms=round(latency_max_ms, 3),
            scraped_at=datetime.fromtimestamp(now, tz=timezone.utc),
        )

    def scrape(
        self,
        deployment_id: str,
        project_id: str,
        stub_id: str,
        ec2_ip: str,
        port: int = 8080,
        timeout: int = 5,
    ) -> MetricSnapshot:
        """Fetch + parse + compute. Raises on HTTP or parse error."""
        raw = fetch_prometheus(ec2_ip, port, timeout)
        parsed = parse_prometheus_text(raw)
        return self.compute_snapshot(deployment_id, project_id, stub_id, ec2_ip, parsed)
