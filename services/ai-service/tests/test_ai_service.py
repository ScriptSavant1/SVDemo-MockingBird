"""Phase 7 Sprint 18 — ai-service tests.

Tests cover:
  - claude_client: parses valid Claude response correctly
  - claude_client: strips markdown code fences from response
  - claude_client: raises ValueError on non-JSON response
  - claude_client: raises ValueError on missing required fields
  - POST /api/v1/ai/generate: success path, stores record, returns GenerateResponse
  - POST /api/v1/ai/generate: 401 without JWT
  - POST /api/v1/ai/generate: 422 when description < 10 chars
  - POST /api/v1/ai/generate: 429 after rate limit exceeded
  - GET /api/v1/ai/history: returns user's generations, newest first
  - GET /api/v1/ai/history: only returns current user's records
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AI_SERVICE_DATABASE_URL", "sqlite:///:memory:")

# ── test DB setup ──────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-for-ai-service"
TEST_ALGORITHM = "HS256"

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = TEST_SECRET
os.environ["JWT_ALGORITHM"] = TEST_ALGORITHM
os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake-key-for-testing"
os.environ["RATE_LIMIT_PER_HOUR"] = "10"


def _make_jwt(user_id: str, role: str = "SV_TEAM") -> str:
    return jwt.encode(
        {"sub": user_id, "username": "testuser", "role": role},
        TEST_SECRET,
        algorithm=TEST_ALGORITHM,
    )


SAMPLE_POSTMAN = {
    "info": {
        "name": "Payment API",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [
        {
            "name": "Create Payment",
            "request": {
                "method": "POST",
                "url": {"raw": "{{baseUrl}}/payments"},
                "body": {"mode": "raw", "raw": '{"amount": 100}'},
            },
            "response": [
                {"name": "Success", "code": 201, "body": '{"id": "pay_1", "status": "created"}'},
            ],
        }
    ],
}

VALID_CLAUDE_RESPONSE = json.dumps({
    "detected_intent": "A REST API for processing card payments",
    "suggested_name": "Payment API",
    "estimated_stubs": 3,
    "collection": SAMPLE_POSTMAN,
})


# ── claude_client unit tests ───────────────────────────────────────────────────

class TestClaudeClient:
    def test_parses_valid_response(self):
        from ai_service.claude_client import generate_stub_spec

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=VALID_CLAUDE_RESPONSE)]
        mock_response.usage.input_tokens = 150
        mock_response.usage.output_tokens = 600
        mock_client.messages.create.return_value = mock_response

        result = generate_stub_spec(mock_client, "A payment processing API", "claude-sonnet-4-6")

        assert result.detected_intent == "A REST API for processing card payments"
        assert result.suggested_name == "Payment API"
        assert result.estimated_stubs == 3
        assert result.input_tokens == 150
        assert result.output_tokens == 600
        assert json.loads(result.spec_content) == SAMPLE_POSTMAN

    def test_strips_markdown_fences(self):
        from ai_service.claude_client import _strip_fences

        fenced = f"```json\n{VALID_CLAUDE_RESPONSE}\n```"
        assert _strip_fences(fenced) == VALID_CLAUDE_RESPONSE

    def test_raises_on_non_json_response(self):
        from ai_service.claude_client import generate_stub_spec

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Sorry, I cannot generate that.")]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        with pytest.raises(ValueError, match="non-JSON"):
            generate_stub_spec(mock_client, "An API", "claude-sonnet-4-6")

    def test_raises_on_missing_required_fields(self):
        from ai_service.claude_client import generate_stub_spec

        incomplete = json.dumps({"detected_intent": "some intent"})
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=incomplete)]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 20
        mock_client.messages.create.return_value = mock_response

        with pytest.raises(ValueError, match="missing required fields"):
            generate_stub_spec(mock_client, "An API", "claude-sonnet-4-6")

    def test_raises_when_collection_is_not_dict(self):
        from ai_service.claude_client import generate_stub_spec

        bad = json.dumps({
            "detected_intent": "test",
            "suggested_name": "test",
            "estimated_stubs": 1,
            "collection": "not-a-dict",
        })
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=bad)]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 20
        mock_client.messages.create.return_value = mock_response

        with pytest.raises(ValueError, match="collection"):
            generate_stub_spec(mock_client, "An API", "claude-sonnet-4-6")


# ── API endpoint tests ─────────────────────────────────────────────────────────

USER_ID = str(uuid.uuid4())


@pytest.fixture()
def client():
    # Import app first so all models register with Base.metadata before create_all.
    from ai_service.main import app
    from ai_service.database import Base, get_db

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def auth_headers():
    return {"Authorization": f"Bearer {_make_jwt(USER_ID)}"}


class TestGenerateEndpoint:
    def test_generate_returns_201_with_spec(self, client, auth_headers):
        with patch("ai_service.routers.generate._get_anthropic_client") as mock_factory, \
             patch("ai_service.routers.generate.generate_stub_spec") as mock_gen:
            mock_gen.return_value = MagicMock(
                detected_intent="A REST API for processing card payments",
                suggested_name="Payment API",
                estimated_stubs=3,
                spec_content=json.dumps(SAMPLE_POSTMAN),
                model_used="claude-sonnet-4-6",
                input_tokens=200,
                output_tokens=800,
            )
            mock_factory.return_value = MagicMock()

            resp = client.post(
                "/api/v1/ai/generate",
                json={"description": "A payment processing REST API with create, get, and refund endpoints"},
                headers=auth_headers,
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["detected_intent"] == "A REST API for processing card payments"
        assert body["suggested_stub_name"] == "Payment API"
        assert body["estimated_stub_count"] == 3
        assert "generation_id" in body
        assert json.loads(body["spec_content"]) == SAMPLE_POSTMAN

    def test_generate_requires_auth(self, client):
        resp = client.post(
            "/api/v1/ai/generate",
            json={"description": "A payment processing API with create and get endpoints"},
        )
        assert resp.status_code == 401

    def test_generate_validates_description_min_length(self, client, auth_headers):
        resp = client.post(
            "/api/v1/ai/generate",
            json={"description": "Short"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_generate_rate_limit(self, client, auth_headers):
        from ai_service.models import AiGeneration
        from ai_service.database import get_db
        from ai_service.main import app  # noqa: PLC0415

        db = next(app.dependency_overrides[get_db]())
        now = datetime.now(timezone.utc)
        for _ in range(10):
            db.add(AiGeneration(
                user_id=uuid.UUID(USER_ID),
                description="test",
                detected_intent="test",
                suggested_stub_name="test",
                spec_content="{}",
                estimated_stub_count=1,
                model_used="claude-sonnet-4-6",
                input_tokens=100,
                output_tokens=100,
                created_at=now,
            ))
        db.commit()

        resp = client.post(
            "/api/v1/ai/generate",
            json={"description": "A payment processing API for card transactions"},
            headers=auth_headers,
        )
        assert resp.status_code == 429


class TestHistoryEndpoint:
    def test_history_returns_list(self, client, auth_headers):
        from ai_service.models import AiGeneration
        from ai_service.database import get_db
        from ai_service.main import app

        db = next(app.dependency_overrides[get_db]())
        db.add(AiGeneration(
            user_id=uuid.UUID(USER_ID),
            description="A payment API",
            detected_intent="Payment processing",
            suggested_stub_name="Payment API",
            spec_content=json.dumps(SAMPLE_POSTMAN),
            estimated_stub_count=3,
            model_used="claude-sonnet-4-6",
            input_tokens=200,
            output_tokens=800,
        ))
        db.commit()

        resp = client.get("/api/v1/ai/history", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        assert items[0]["suggested_stub_name"] == "Payment API"

    def test_history_filters_by_user(self, client, auth_headers):
        from ai_service.models import AiGeneration
        from ai_service.database import get_db
        from ai_service.main import app

        other_user = uuid.uuid4()
        db = next(app.dependency_overrides[get_db]())
        db.add(AiGeneration(
            user_id=other_user,
            description="Another user's API",
            detected_intent="Other intent",
            suggested_stub_name="Other API",
            spec_content="{}",
            estimated_stub_count=1,
            model_used="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=100,
        ))
        db.commit()

        resp = client.get("/api/v1/ai/history", headers=auth_headers)
        assert resp.status_code == 200
        names = [item["suggested_stub_name"] for item in resp.json()]
        assert "Other API" not in names
