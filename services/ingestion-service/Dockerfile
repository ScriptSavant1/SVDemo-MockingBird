# PIP_INDEX_URL is set in config/local.env → passed at build time:
#   docker build --build-arg PIP_INDEX_URL=<your-artifactory-pypi-url> .
# Default falls back to the public PyPI for local development.
ARG PIP_INDEX_URL=https://pypi.org/simple

# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ARG PIP_INDEX_URL

WORKDIR /build

RUN pip install --upgrade pip --index-url ${PIP_INDEX_URL}

# Install parser-worker (peer service, not on PyPI)
COPY ../parser-worker /build/parser-worker
RUN pip install --prefix=/install --index-url ${PIP_INDEX_URL} /build/parser-worker

# Install ingestion-service
COPY pyproject.toml .
COPY src/ src/
RUN pip install --prefix=/install --no-deps --index-url ${PIP_INDEX_URL} .
RUN pip install --prefix=/install --index-url ${PIP_INDEX_URL} \
    fastapi uvicorn[standard] sqlalchemy psycopg2-binary python-jose[cryptography] \
    boto3 pydantic pydantic-settings python-multipart

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local

# Non-root user for security
RUN useradd --uid 1001 --no-create-home --shell /bin/false mockingbird
USER mockingbird

COPY src/ src/

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"

CMD ["uvicorn", "ingestion_service.main:app", "--host", "0.0.0.0", "--port", "8003"]
