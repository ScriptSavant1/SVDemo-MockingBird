"""Core data models shared by all parsers and generators."""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

TEMPLATE_PLACEHOLDER = re.compile(r'\{\{[^}]+\}\}')


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class MatchType(str, Enum):
    URL_CONTAINS = "url-contains"
    URL_REGEX = "url-regex"
    BODY_CONTAINS = "body-contains"
    BODY_JSON_PATH = "body-json-path"
    BODY_XPATH = "body-xpath"
    HEADER_EQUALS = "header-equals"
    ALWAYS = "always"


class DelayType(str, Enum):
    FIXED = "fixed"
    RANDOM = "random"
    LOGNORMAL = "lognormal"
    PROGRESSIVE = "progressive"
    CHUNKED = "chunked"


class FaultType(str, Enum):
    CONNECTION_RESET_BY_PEER = "CONNECTION_RESET_BY_PEER"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    MALFORMED_RESPONSE_CHUNK = "MALFORMED_RESPONSE_CHUNK"


class Delay(BaseModel):
    type: DelayType = DelayType.FIXED
    ms: Optional[int] = None           # fixed delay ms; also lognormal median ms
    min_ms: Optional[int] = None       # random uniform lower bound
    max_ms: Optional[int] = None       # random uniform upper bound
    start_ms: Optional[int] = None     # progressive: initial delay
    increment_ms: Optional[int] = None # progressive: added per call
    max_limit_ms: Optional[int] = None # progressive: ceiling
    chunks: Optional[int] = None       # chunked: number of chunks
    chunk_ms: Optional[int] = None     # chunked: total duration ms
    chunk_size_bytes: Optional[int] = None
    sigma: Optional[float] = None      # lognormal: standard deviation


class MatchCondition(BaseModel):
    type: MatchType
    value: Optional[str] = None


class ParsedRequestSpec(BaseModel):
    method: HttpMethod
    url: str
    required_headers: dict[str, str] = Field(default_factory=dict)


class ParsedScenario(BaseModel):
    name: str
    match: MatchCondition
    status: int
    response_headers: dict[str, str] = Field(default_factory=dict)
    body: Optional[str] = None
    delay: Optional[Delay] = None
    fault: Optional[FaultType] = None
    # WireMock stateful scenario fields (Phase 2 Sprint 6)
    # When set, the mapping gets scenarioName + requiredScenarioState + newScenarioState.
    scenario_name: Optional[str] = None
    required_state: Optional[str] = None
    new_state: Optional[str] = None
    # Namespace context for XPath body matching (Phase 2 Sprint 7)
    # Emitted as xPathNamespaces when match.type == BODY_XPATH.
    xpath_namespaces: dict[str, str] = Field(default_factory=dict)

    def has_dynamic_placeholders(self) -> bool:
        return bool(self.body and TEMPLATE_PLACEHOLDER.search(self.body))


class ParsedStub(BaseModel):
    name: str
    description: str = ""
    team: str = ""
    contact: str = ""
    request: ParsedRequestSpec
    scenarios: list[ParsedScenario]


class ParsedFile(BaseModel):
    format: str
    source_file: str
    stubs: list[ParsedStub]


class ValidationError(BaseModel):
    line: Optional[int] = None
    field: Optional[str] = None
    message: str

    def __str__(self) -> str:
        parts = []
        if self.line:
            parts.append(f"Line {self.line}")
        if self.field:
            parts.append(self.field)
        parts.append(self.message)
        return ": ".join(parts)


class ValidationResult(BaseModel):
    valid: bool
    format_detected: str = ""
    errors: list[ValidationError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""
