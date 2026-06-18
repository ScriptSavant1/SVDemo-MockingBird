"""Prompt templates for Claude API calls."""
from __future__ import annotations

GENERATION_SYSTEM_PROMPT = """\
You are a service virtualisation expert. When given a plain-English description of an API, \
produce a Postman Collection v2.1 JSON with realistic example request/response pairs.

Requirements:
- Include success (2xx), validation-error (400/422), and not-found (404) responses per endpoint
- Use realistic field names and sample values for the business domain
- All response bodies must be valid JSON strings
- Use {{baseUrl}} as the URL host variable

Return ONLY a JSON object with these exact top-level fields — no markdown fences, no explanation:
{
  "detected_intent": "<one-sentence summary of what this API does>",
  "suggested_name": "<short descriptive stub name, 2-5 words>",
  "estimated_stubs": <integer: total request/response pair count>,
  "collection": <complete valid Postman Collection v2.1 JSON object>
}
"""

CLASSIFICATION_SYSTEM_PROMPT = """\
You are an API classification assistant. Given a plain-English API description, \
identify the primary HTTP methods and resource names.
Return a JSON object: {"methods": ["GET","POST",...], "resources": ["payment","account",...]}
Return ONLY valid JSON, no explanation.
"""


def build_generation_messages(description: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": description}]


def build_classification_messages(description: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": description}]
