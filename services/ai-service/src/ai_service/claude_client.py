"""Wrapper around the Anthropic Python SDK.

The Anthropic client is created once at startup and injected via FastAPI
dependency injection. API key is NEVER hard-coded — it comes from config
(injected from HashiCorp Vault in production, env var in dev).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .prompt import GENERATION_SYSTEM_PROMPT, build_generation_messages

if TYPE_CHECKING:
    from anthropic import Anthropic


@dataclass
class GenerationResult:
    detected_intent: str
    suggested_name: str
    estimated_stubs: int
    spec_content: str  # JSON string of the Postman collection
    model_used: str
    input_tokens: int
    output_tokens: int


def generate_stub_spec(
    client: "Anthropic",
    description: str,
    model: str,
    max_tokens: int = 8192,
) -> GenerationResult:
    """Call Claude to produce a Postman v2.1 collection from a plain-English description.

    Raises:
        ValueError: if the response cannot be parsed as valid JSON with required fields.
    """
    messages = build_generation_messages(description)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=GENERATION_SYSTEM_PROMPT,
        messages=messages,
    )
    raw_text: str = response.content[0].text
    parsed = _parse_response(raw_text)

    return GenerationResult(
        detected_intent=parsed["detected_intent"],
        suggested_name=parsed["suggested_name"],
        estimated_stubs=int(parsed.get("estimated_stubs", 0)),
        spec_content=json.dumps(parsed["collection"]),
        model_used=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if Claude accidentally wraps the response."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", text)
    return match.group(1).strip() if match else text


def _parse_response(raw: str) -> dict:
    clean = _strip_fences(raw)
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned non-JSON response: {exc}") from exc

    required = {"detected_intent", "suggested_name", "estimated_stubs", "collection"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Claude response missing required fields: {missing}")

    if not isinstance(data["collection"], dict):
        raise ValueError("'collection' field must be a JSON object (Postman collection)")

    return data
