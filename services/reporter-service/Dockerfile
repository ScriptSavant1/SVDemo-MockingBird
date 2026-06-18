# reporter-service — Python 3.11, WeasyPrint (requires GTK/Pango/Cairo)
ARG PIP_INDEX_URL=https://pypi.org/simple
FROM python:3.11-slim

WORKDIR /app

# WeasyPrint runtime deps (Pango, Cairo, GLib font rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 \
        libffi-dev libxml2 libxslt1.1 fonts-liberation \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL
COPY pyproject.toml .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -e ".[pdf]"

COPY src /app/src

ENV PYTHONPATH=/app/src

CMD ["sv-report-worker"]
