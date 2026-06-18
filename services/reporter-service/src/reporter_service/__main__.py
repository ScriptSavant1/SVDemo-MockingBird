"""Entry point: sv-report-worker."""
from __future__ import annotations

import logging

import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings
from .worker import run_loop

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "service": "reporter-worker", "message": "%(message)s"}',
)


def main() -> None:
    if not settings.sqs_report_queue_url:
        raise SystemExit("SQS_REPORT_QUEUE_URL is required")

    engine = create_engine(settings.database_url)
    SessionFactory = sessionmaker(bind=engine)

    sqs = boto3.client("sqs", region_name=settings.aws_region)
    ts_query = boto3.client("timestream-query", region_name=settings.aws_region)
    s3 = boto3.client("s3", region_name=settings.aws_region)

    run_loop(
        sqs_client=sqs,
        db_factory=SessionFactory,
        ts_query_client=ts_query,
        s3_client=s3,
        queue_url=settings.sqs_report_queue_url,
        poll_wait=settings.sqs_poll_wait_seconds,
    )
