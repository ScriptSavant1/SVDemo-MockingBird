from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Plain-English description of the API to generate stubs for",
        examples=["A REST API for processing card payments with create, get, and refund endpoints"],
    )
    project_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional project to associate this generation with",
    )


class GenerateResponse(BaseModel):
    generation_id: uuid.UUID
    detected_intent: str
    suggested_stub_name: str
    spec_format: str = "postman_v21"
    spec_content: str
    estimated_stub_count: int
    model_used: str
    input_tokens: int
    output_tokens: int
    created_at: str

    model_config = {"from_attributes": True}


class GenerationHistoryItem(BaseModel):
    generation_id: uuid.UUID
    detected_intent: str
    suggested_stub_name: str
    estimated_stub_count: int
    model_used: str
    created_at: str

    model_config = {"from_attributes": True}
