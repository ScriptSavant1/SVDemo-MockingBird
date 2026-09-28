"""Unit tests for the shared error-response shape (ingestion_service.errors)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from project_service.errors import MockingbirdError, install_error_handlers


class Body(BaseModel):
    name: str
    tps: int


def _client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app, "test-service")

    @app.get("/coded")
    def coded() -> None:
        raise MockingbirdError(413, "MB-UPL-002", "Upload is 60.0 MB — the limit is 50 MB")

    @app.get("/plain")
    def plain() -> None:
        raise HTTPException(status_code=404, detail="Stub 1 not found")

    @app.get("/legacy-dict")
    def legacy_dict() -> None:
        # The shape project-service's older raise sites use.
        raise HTTPException(status_code=404, detail={"type": "x", "title": "Stub Not Found", "status": 404, "detail": "Stub 1 does not exist"})

    @app.post("/validate")
    def validate(body: Body) -> None:
        return None

    @app.get("/crash")
    def crash() -> None:
        raise ValueError("db password=hunter2 at /srv/internal")

    return TestClient(app, raise_server_exceptions=False)


def test_coded_error_keeps_its_code_and_detail():
    r = _client().get("/coded")
    assert r.status_code == 413
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "MB-UPL-002"
    assert body["detail"] == "Upload is 60.0 MB — the limit is 50 MB"
    assert body["status"] == 413
    assert "ref" not in body


def test_plain_http_exception_gets_generic_request_code():
    body = _client().get("/plain").json()
    assert body["code"] == "MB-REQ-404"
    assert body["detail"] == "Stub 1 not found"


def test_legacy_problem_dict_is_flattened_to_a_string_detail():
    body = _client().get("/legacy-dict").json()
    assert body["detail"] == "Stub 1 does not exist"
    assert body["title"] == "Stub Not Found"
    assert isinstance(body["detail"], str)


def test_request_validation_is_one_readable_line():
    body = _client().post("/validate", json={"name": "x", "tps": "lots"}).json()
    assert body["code"] == "MB-REQ-422"
    assert body["detail"].startswith("Invalid value for 'tps':")
    assert "\n" not in body["detail"]


def test_request_validation_counts_further_errors():
    body = _client().post("/validate", json={}).json()
    assert body["detail"].endswith("(+1 more)")


def test_unexpected_error_hides_internals_but_gives_a_ref():
    r = _client().get("/crash")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "MB-SYS-001"
    assert len(body["ref"]) == 8
    assert f"(ref {body['ref']})" in body["detail"]
    assert "test-service" in body["detail"]
    assert "hunter2" not in r.text and "/srv/internal" not in r.text
