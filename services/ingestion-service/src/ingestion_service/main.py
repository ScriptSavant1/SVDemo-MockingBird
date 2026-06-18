from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .database import create_tables
from .routers.upload import router as upload_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="Mockingbird ingestion-service",
    description="File upload, format detection, validation, and S3 storage for stub spec files.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(upload_router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok", "service": settings.service_name}
