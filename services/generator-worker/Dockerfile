ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PYTHON_BASE=python:3.11-slim

FROM ${PYTHON_BASE} AS builder
ARG PIP_INDEX_URL
WORKDIR /build

COPY ../parser-worker /build/parser-worker
COPY . /build/generator-worker

RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} \
    /build/parser-worker \
    "/build/generator-worker[worker]" \
    --target /install

FROM ${PYTHON_BASE}
WORKDIR /app

COPY --from=builder /install /usr/local/lib/python3.11/site-packages

RUN groupadd -r mockingbird && useradd -r -g mockingbird mockingbird
USER mockingbird

ENV PYTHONUNBUFFERED=1

CMD ["sv-generate-worker"]
