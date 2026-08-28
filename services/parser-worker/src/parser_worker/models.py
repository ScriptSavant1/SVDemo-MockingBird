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
    # This scenario's discriminator value when the owning ParsedStub qualifies
    # for lookup-table generation (see generator/lookup_table.py) — e.g. the
    # captured "Full" name value that would otherwise be embedded in a
    # per-scenario XPath/JSONPath match predicate, OR the captured URL path
    # segment value when captures for one operation were recorded at
    # different URLs differing only in one segment (an account/customer ID
    # embedded in the path itself — see _detect_url_segment_pattern). None
    # for stubs generated the normal (static-mapping, single shared URL) way.
    lookup_key: Optional[str] = None
    # This scenario's own exact URL, when it differs from the owning
    # ParsedStub's request.url — set only in the URL-path-segment case
    # above, for the static-mapping (below lookup-table-threshold) path:
    # each scenario gets its own exact urlPath mapping instead of sharing
    # one urlPath the way same-URL body-differentiated scenarios do.
    url_override: Optional[str] = None
    # This scenario's real captured REQUEST body (not the response body
    # above), when the source parser recorded one — CA LISA captures always
    # have one; other formats (Postman, OpenAPI, ...) don't record a
    # request body at all and leave this None. Purely a convenience for
    # consumers that want a realistic example payload (e.g.
    # generator/jmeter.py) rather than having to reverse-engineer one from
    # `match`; nothing in mapping generation reads this field.
    captured_request_body: Optional[str] = None

    def has_dynamic_placeholders(self) -> bool:
        """True if a {{...}} template placeholder appears anywhere WireMock will
        render it — the body, or a response header (e.g. an echoed request
        header value). Without this covering headers too, a mapping whose only
        placeholder lives in a header gets no "transformers": ["response-template"]
        entry, and WireMock serves the literal unresolved "{{...}}" string
        instead of the real value.
        """
        if self.body and TEMPLATE_PLACEHOLDER.search(self.body):
            return True
        return any(TEMPLATE_PLACEHOLDER.search(v) for v in self.response_headers.values())


class ParsedStub(BaseModel):
    name: str
    description: str = ""
    team: str = ""
    contact: str = ""
    request: ParsedRequestSpec
    scenarios: list[ParsedScenario]
    # Set together (both or neither) when this stub has enough same-URL
    # captures that generator/lookup_table.py will emit one
    # DynamicLookupRequestFilter data file instead of one static WireMock
    # mapping per scenario. "xpath" or "json" (body-based, see
    # _differentiate_bodies) or "url-segment" (path-based, see
    # _detect_url_segment_pattern — lookup_discriminator_field is None in
    # that case; lookup_url_pattern carries the templated path instead).
    lookup_discriminator_type: Optional[str] = None
    lookup_discriminator_field: Optional[str] = None
    # Set only for the "url-segment" discriminator type: the WireMock
    # urlPathPattern regex (one capture group, at the varying path segment)
    # that a single generic route can match every captured URL against.
    lookup_url_pattern: Optional[str] = None


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
