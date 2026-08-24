"""WebSocket endpoint for real-time TPS feed.

Clients connect to /ws/metrics/{deployment_id} and receive MetricSnapshot JSON
once per scrape interval (every 30 s by default).

The metrics scraper publishes to Redis channel `metrics:{deployment_id}`.
This handler subscribes to that channel and forwards each message to the client.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..config import settings
from ..dependencies import get_current_user_ws

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/metrics/{deployment_id}")
async def metrics_ws(websocket: WebSocket, deployment_id: uuid.UUID) -> None:
    # Browsers can't set an Authorization header on a WebSocket handshake,
    # so the JWT is passed as a query param instead: ?token=<jwt>.
    token = websocket.query_params.get("token")
    if get_current_user_ws(token) is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    channel = f"metrics:{deployment_id}"
    r: aioredis.Redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()
