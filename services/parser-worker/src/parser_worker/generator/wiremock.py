"""Generates WireMock JSON mapping files from parsed stub definitions."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote_plus

from ..models import (
    DelayType, MatchType, ParsedFile, ParsedScenario, ParsedStub,
    TEMPLATE_PLACEHOLDER,  # noqa: F401 — re-exported for tests
)
from .lookup_table import should_use_lookup_table

_PATH_PARAM_RE = re.compile(r'\{(\w+)\}')
_SAFE_CHAR_RE = re.compile(r'[^\w\s-]')


def build_wiremock_mappings(parsed: ParsedFile) -> list[tuple[ParsedStub, ParsedScenario, dict]]:
    """Build the WireMock mapping dict for every scenario, without writing files.

    Returns (stub, scenario, mapping_dict) triples — the same mapping_dict that
    generate_wiremock_mappings writes to disk, plus the source ParsedStub/
    ParsedScenario for callers (e.g. the setup-guide generator) that want to
    render something richer than the raw WireMock JSON. This is the single
    place mapping construction happens; generate_wiremock_mappings and any
    other consumer both go through it so nothing can drift from what actually
    gets deployed.
    """
    results: list[tuple[ParsedStub, ParsedScenario, dict]] = []
    for stub in parsed.stubs:
        if should_use_lookup_table(stub):
            # Handled by generator/lookup_table.py instead — one generic
            # request-filter route + a data file, not N static mappings.
            continue
        total = len(stub.scenarios)
        for i, scenario in enumerate(stub.scenarios):
            priority = total - i  # first listed scenario gets highest priority
            mapping = _build_mapping(stub, scenario, priority)
            results.append((stub, scenario, mapping))
    return results


def generate_wiremock_mappings(parsed: ParsedFile, output_dir: Path) -> list[Path]:
    """Write one WireMock JSON file per scenario. Returns list of created file paths."""
    mappings_dir = output_dir / "mappings"
    mappings_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for stub, scenario, mapping in build_wiremock_mappings(parsed):
        filename = _safe_filename(stub.name, scenario.name)
        path = mappings_dir / f"{filename}.json"
        path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
        created.append(path)
    return created


def _build_mapping(stub: ParsedStub, scenario: ParsedScenario, priority: int) -> dict:
    url = stub.request.url
    has_path_params = bool(_PATH_PARAM_RE.search(url))

    request_block: dict = {"method": stub.request.method.value}
    _apply_url_matcher(request_block, url, scenario.match, has_path_params)
    _apply_header_matchers(request_block, stub.request.required_headers)
    _apply_body_matcher(request_block, scenario.match, scenario.xpath_namespaces or None)

    response_block: dict = {"status": scenario.status}
    if scenario.response_headers:
        response_block["headers"] = scenario.response_headers
    if scenario.body:
        response_block["body"] = scenario.body
    # Checked independently of body: a placeholder can live only in a response
    # header (e.g. echoing back a request header) with no body at all.
    if scenario.has_dynamic_placeholders():
        response_block["transformers"] = ["response-template"]
    if scenario.fault:
        response_block["fault"] = scenario.fault.value
    _apply_delay(response_block, scenario)

    mapping: dict = {
        "name": f"{stub.name} — {scenario.name}",
        "priority": priority,
        "request": request_block,
        "response": response_block,
    }

    # Stateful scenario fields — emitted at top level alongside request/response.
    # scenarioName groups all steps; WireMock tracks state per scenarioName.
    if scenario.scenario_name:
        mapping["scenarioName"] = scenario.scenario_name
    if scenario.required_state is not None:
        mapping["requiredScenarioState"] = scenario.required_state
    if scenario.new_state is not None:
        mapping["newScenarioState"] = scenario.new_state

    return mapping


def _apply_url_matcher(
    block: dict,
    url: str,
    match: object,
    has_path_params: bool,
) -> None:
    from ..models import MatchCondition, MatchType  # local import avoids circular

    if not isinstance(match, MatchCondition):
        _set_url_and_query(block, url, has_path_params)
        return

    if match.type == MatchType.URL_CONTAINS:
        block["urlPathContaining"] = match.value or ""
    elif match.type == MatchType.URL_REGEX:
        block["urlPattern"] = match.value or ".*"
    elif has_path_params:
        # Replace {paramName} with a regex segment, anchor to full path
        pattern = _PATH_PARAM_RE.sub(r'[^/]+', url)
        block["urlPattern"] = pattern
    else:
        _set_url_and_query(block, url, has_path_params)


def _set_url_and_query(block: dict, url: str, has_path_params: bool) -> None:
    """Split URL into urlPath + queryParameters so WireMock matches correctly.

    WireMock urlPath ignores the query string, so query params must go in
    queryParameters. Without this split, ?foo=bar stays in urlPath and never matches.
    """
    if "?" in url and not has_path_params:
        path, qs = url.split("?", 1)
        block["urlPath"] = path
        qparams: dict[str, dict[str, str]] = {}
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                # WireMock decodes incoming query strings (application/x-www-form-urlencoded
                # rules: '+' -> space, %XX -> byte) before matching queryParameters, so the
                # stored matcher must be decoded the same way — storing the raw captured text
                # (e.g. a literal "SUP+FLAGS") would never match the decoded "SUP FLAGS"
                # WireMock actually sees on a real request. Found by loading a generated
                # mapping into a real WireMock instance and testing it.
                qparams[unquote_plus(k)] = {"equalTo": unquote_plus(v)}
        if qparams:
            block["queryParameters"] = qparams
    else:
        block["urlPath"] = url


def _apply_header_matchers(block: dict, required_headers: dict[str, str]) -> None:
    real_headers = {k: v for k, v in required_headers.items() if v != "*"}
    if real_headers:
        block["headers"] = {k: _header_matcher(k, v) for k, v in real_headers.items()}


def _header_matcher(name: str, value: str) -> dict:
    """Build a WireMock header matcher, case-insensitive for Content-Type.

    Media type and parameter names in Content-Type are case-insensitive per
    RFC 7231 3.1.1.1, and in practice the underlying HTTP server (Jetty, in
    WireMock's case) normalises the charset parameter's casing before this
    matcher ever runs — verified by loading a captured mapping into a real
    WireMock instance: a verbatim-captured "charset=utf-8" never matched a
    live request, regardless of the case the client actually sent. An exact
    case match on this header carries no real distinguishing meaning, so it's
    matched case-insensitively rather than case-exact like other headers.
    """
    matcher: dict = {"equalTo": value}
    if name.lower() == "content-type":
        matcher["caseInsensitive"] = True
    return matcher


def _apply_body_matcher(
    block: dict,
    match: object,
    xpath_namespaces: dict[str, str] | None = None,
) -> None:
    from ..models import MatchCondition, MatchType

    if not isinstance(match, MatchCondition):
        return

    if match.type == MatchType.BODY_CONTAINS and match.value:
        block["bodyPatterns"] = [{"contains": match.value}]
    elif match.type == MatchType.BODY_JSON_PATH and match.value:
        block["bodyPatterns"] = [{"matchesJsonPath": match.value}]
    elif match.type == MatchType.BODY_XPATH and match.value:
        pattern: dict = {"matchesXPath": match.value}
        if xpath_namespaces:
            pattern["xPathNamespaces"] = dict(xpath_namespaces)
        block["bodyPatterns"] = [pattern]
    elif match.type == MatchType.HEADER_EQUALS and match.value and " == " in match.value:
        header_name, _, header_val = match.value.partition(" == ")
        block.setdefault("headers", {})[header_name.strip()] = {
            "equalTo": header_val.strip()
        }


def _apply_delay(block: dict, scenario: ParsedScenario) -> None:
    if not scenario.delay:
        return
    d = scenario.delay
    if d.type == DelayType.FIXED and d.ms is not None:
        block["fixedDelayMilliseconds"] = d.ms
    elif d.type == DelayType.RANDOM and d.min_ms is not None and d.max_ms is not None:
        block["delayDistribution"] = {
            "type": "uniform",
            "lower": d.min_ms,
            "upper": d.max_ms,
        }
    elif d.type == DelayType.LOGNORMAL and d.ms is not None and d.sigma is not None:
        block["delayDistribution"] = {
            "type": "lognormal",
            "median": d.ms,
            "sigma": d.sigma,
        }
    elif d.type == DelayType.CHUNKED and d.chunks is not None and d.chunk_ms is not None:
        block["chunkedDribbleDelay"] = {
            "numberOfChunks": d.chunks,
            "totalDuration": d.chunk_ms,
        }
    # PROGRESSIVE delay requires WireMock stateful scenarios — deferred to Phase 4


def _safe_filename(stub_name: str, scenario_name: str) -> str:
    combined = f"{stub_name}_{scenario_name}"
    safe = _SAFE_CHAR_RE.sub("", combined).strip().replace(" ", "_").lower()
    return safe[:100]
