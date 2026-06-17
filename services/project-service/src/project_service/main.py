"""FastAPI application factory for project-service."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .database import create_tables
from .routers import projects, stubs
from .schemas import HealthOut

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "service": "project-service", "message": "%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    create_tables()
    logger.info("project-service started, tables ensured")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mockingbird Project Service",
        description="Project and stub management API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    app.include_router(projects.router)
    app.include_router(stubs.router)

    @app.get("/health", response_model=HealthOut, tags=["health"])
    def health() -> HealthOut:
        return HealthOut(status="ok", service=settings.service_name)

    return app


app = create_app()
