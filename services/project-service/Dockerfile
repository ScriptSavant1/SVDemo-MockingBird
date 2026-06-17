# Build stage — resolves deps; separate from runtime to keep image lean
FROM python:3.11-slim AS builder

WORKDIR /build

# PIP_INDEX_URL can be overridden in GitLab CI to point to Artifactory PyPI mirror
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --upgrade pip

COPY pyproject.toml ./
RUN pip install --prefix=/install --no-cache-dir --index-url "$PIP_INDEX_URL" .

# Production stage
FROM python:3.11-slim AS production

WORKDIR /app

RUN addgroup --system mockingbird && adduser --system --ingroup mockingbird mockingbird

# Copy installed packages from builder
COPY --from=builder /install /usr/local

COPY src/ ./src/

USER mockingbird

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "project_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
