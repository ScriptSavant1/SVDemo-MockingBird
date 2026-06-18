"""Redis pub/sub helpers for real-time metrics streaming.

The scraper publishes a MetricSnapshot JSON to channel `metrics:{deployment_id}`
after each successful scrape. The WebSocket handler subscribes to that channel
and forwards messages to connected browser clients.

Latest snapshots are also stored at key `metrics:snapshot:{deployment_id}` with
a TTL of 2× the scrape interval so the /current REST endpoint can serve them
without hitting Timestream.
"""
from __future__ import annotations

import json
from typing import Any

_SNAPSHOT_TTL = 120  # seconds — 2× default scrape interval
_CHANNEL_PREFIX = "metrics"
_SNAPSHOT_PREFIX = "metrics:snapshot"


def _channel(deployment_id: str) -> str:
    return f"{_CHANNEL_PREFIX}:{deployment_id}"


def _snapshot_key(deployment_id: str) -> str:
    return f"{_SNAPSHOT_PREFIX}:{deployment_id}"


def publish_snapshot(client: Any, snapshot_dict: dict) -> None:
    """Publish a snapshot dict to the deployment's Redis channel and cache it."""
    deployment_id = snapshot_dict["deployment_id"]
    payload = json.dumps(snapshot_dict, default=str)
    client.setex(_snapshot_key(deployment_id), _SNAPSHOT_TTL, payload)
    client.publish(_channel(deployment_id), payload)


def get_latest_snapshot(client: Any, deployment_id: str) -> dict | None:
    """Read the cached snapshot from Redis. Returns None if not found / expired."""
    raw = client.get(_snapshot_key(deployment_id))
    if raw is None:
        return None
    return json.loads(raw)
