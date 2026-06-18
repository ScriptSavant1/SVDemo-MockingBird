ARG PIP_INDEX_URL=https://pypi.org/simple
FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL
COPY pyproject.toml .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -e .

COPY src /app/src

ENV PYTHONPATH=/app/src

EXPOSE 8004

CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8004"]
