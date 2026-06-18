from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import create_tables
from .routers.generate import router as generate_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="Mockingbird AI Service",
    version="1.0.0",
    description="Plain-English → Postman stub spec generation via Claude API",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "service": settings.service_name, "environment": settings.environment}
