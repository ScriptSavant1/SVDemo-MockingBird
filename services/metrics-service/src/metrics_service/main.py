"""metrics-service FastAPI application.

Exposes:
  GET  /health                              — liveness probe
  GET  /api/v1/metrics/{id}/current        — latest snapshot from Redis
  GET  /api/v1/metrics/{id}/history        — time-series from Timestream
  WS   /ws/metrics/{id}                    — real-time TPS via Redis pub/sub

Background task: scrapes all LIVE stub EC2 instances every scrape_interval_seconds,
writes results to Timestream, and publishes to Redis for live WebSocket consumers.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import boto3
import redis
from fastapi import FastAPI
from sqlalchemy import create_engine, text

from .config import settings
from .redis_pub import publish_snapshot
from .routers import metrics as metrics_router
from .routers import ws as ws_router
from .scraper import Scraper
from .timestream import write_snapshot

logger = logging.getLogger(__name__)

_scraper = Scraper()


def _scrape_cycle(db_engine, ts_write_client, r_client) -> None:
    """Blocking scrape cycle — runs in a thread pool."""
    try:
        with db_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, project_id, stub_id, ec2_ip_address "
                    "FROM deployments WHERE status = 'LIVE'"
                )
            ).fetchall()
    except Exception as exc:
        logger.error("DB query failed in scrape cycle: %s", exc)
        return

    for row in rows:
        deployment_id, project_id, stub_id, ec2_ip = (str(c) for c in row)
        if not ec2_ip:
            continue
        try:
            snapshot = _scraper.scrape(
                deployment_id, project_id, stub_id, ec2_ip,
                port=settings.scrape_port,
                timeout=settings.scrape_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("Scrape failed for deployment %s (%s): %s", deployment_id, ec2_ip, exc)
            continue

        try:
            write_snapshot(
                ts_write_client,
                settings.timestream_database,
                settings.timestream_table,
                snapshot,
            )
        except Exception as exc:
            logger.warning("Timestream write failed for %s: %s", deployment_id, exc)

        try:
            publish_snapshot(r_client, snapshot.model_dump())
        except Exception as exc:
            logger.warning("Redis publish failed for %s: %s", deployment_id, exc)


async def _scrape_loop(db_engine, ts_write_client, r_client) -> None:
    while True:
        await asyncio.to_thread(_scrape_cycle, db_engine, ts_write_client, r_client)
        await asyncio.sleep(settings.scrape_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_engine = create_engine(settings.database_url)
    ts_write = boto3.client("timestream-write", region_name=settings.aws_region)
    ts_query = boto3.client("timestream-query", region_name=settings.aws_region)
    r = redis.StrictRedis.from_url(settings.redis_url, decode_responses=True)

    app.state.redis = r
    app.state.timestream_write_client = ts_write
    app.state.timestream_query_client = ts_query
    app.state.timestream_database = settings.timestream_database
    app.state.timestream_table = settings.timestream_table

    task = asyncio.create_task(_scrape_loop(db_engine, ts_write, r))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    db_engine.dispose()


app = FastAPI(
    title="Mockingbird Metrics Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(metrics_router.router)
app.include_router(ws_router.router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok", "service": "metrics-service"}
