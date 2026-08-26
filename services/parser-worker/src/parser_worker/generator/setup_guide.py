"""Generates the per-download HTML setup guide bundled into every stub.zip
(STUB_ENGINE_SETUP_GUIDE.html).

The "Service reference" section is fully dynamic — built from the same
build_wiremock_mappings() output that actually gets written into the
project's src/main/resources/mappings/*.json, so the guide can never drift
from what the stub actually does (no hand-written "example" content, no
second copy of matcher logic to keep in sync). Every other section (software
prerequisites, build/run instructions, troubleshooting, the WS-Security and
mapping-collision explanations) is fixed boilerplate that applies to any
generated stub.
"""
from __future__ import annotations

import html as _html
import json
from datetime import datetime, timezone

from ..models import ParsedFile
from .wiremock import build_wiremock_mappings

_BODY_PREVIEW_LIMIT = 700


def generate_setup_guide_html(parsed: ParsedFile, project_name: str) -> str:
    """Render the full self-contained HTML guide for this specific stub."""
    triples = build_wiremock_mappings(parsed)
    cards_html = "\n".join(_render_card(i, stub, scenario, mapping) for i, (stub, scenario, mapping) in enumerate(triples))
    stats = _compute_stats(triples)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return _PAGE_TEMPLATE.format(
        project_name=_esc(project_name),
        generated_at=generated_at,
        endpoint_count=stats["total"],
        rest_count=stats["rest"],
        soap_count=stats["soap"],
        method_pills=stats["method_pills_html"],
        service_cards=cards_html or _EMPTY_STATE,
        endpoint_summary_sentence=stats["summary_sentence"],
    )


# ── stats / summary ───────────────────────────────────────────────────────────

def _compute_stats(triples: list[tuple]) -> dict:
    total = len(triples)
    soap = sum(1 for _, _, m in triples if _looks_like_soap(m))
    rest = total - soap
    methods: dict[str, int] = {}
    for _, _, m in triples:
        methods[m["request"]["method"]] = methods.get(m["request"]["method"], 0) + 1

    pills = []
    for method, count in sorted(methods.items()):
        pills.append(
            f'<span class="stat-pill"><span class="method-pill {method.lower()} sm">{method}</span> × {count}</span>'
        )

    parts = []
    if rest:
        parts.append(f"{rest} REST")
    if soap:
        parts.append(f"{soap} SOAP")
    kind_summary = " + ".join(parts) if parts else "0"
    summary_sentence = (
        f"This stub serves {total} endpoint{'s' if total != 1 else ''} ({kind_summary})."
        if total
        else "This stub has no mappings yet."
    )

    return {
        "total": total,
        "rest": rest,
        "soap": soap,
        "method_pills_html": "".join(pills),
        "summary_sentence": summary_sentence,
    }


def _looks_like_soap(mapping: dict) -> bool:
    req_headers = mapping.get("request", {}).get("headers", {})
    if any(k.lower() == "soapaction" for k in req_headers):
        return True
    resp_headers = mapping.get("response", {}).get("headers", {})
    ctype = str(resp_headers.get("Content-Type") or resp_headers.get("content-type") or "")
    if "xml" in ctype.lower() or "soap" in ctype.lower():
        return True
    body = mapping.get("response", {}).get("body") or ""
    return "Envelope" in body[:300]


# ── per-endpoint card rendering ───────────────────────────────────────────────

def _render_card(index: int, stub, scenario, mapping: dict) -> str:
    req = mapping["request"]
    resp = mapping["response"]
    method = req["method"]
    path = req.get("urlPath") or req.get("urlPathContaining") or req.get("urlPattern") or "/"
    title = mapping["name"]
    is_soap = _looks_like_soap(mapping)
    kind_label = "SOAP" if is_soap else "REST"

    query_rows = "".join(
        f"<tr><td><code>{_esc(k)}</code></td><td>query</td><td>Must equal <code>{_esc(v.get('equalTo', ''))}</code></td></tr>"
        for k, v in (req.get("queryParameters") or {}).items()
    )
    header_rows = "".join(
        f"<tr><td><code>{_esc(k)}</code></td><td>header <span class=\"req-flag\">required</span></td>"
        f"<td>Must equal <code>{_esc(v.get('equalTo', ''))}</code>{' (case-insensitive)' if v.get('caseInsensitive') else ''}</td></tr>"
        for k, v in (req.get("headers") or {}).items()
    )
    param_rows = query_rows + header_rows
    if not param_rows:
        param_rows = '<tr><td colspan="3"><em>No query parameters or required headers — matched on method + URL alone.</em></td></tr>'

    body_pattern_html = _render_body_patterns(req.get("bodyPatterns"))

    status = resp.get("status", 200)
    resp_headers = resp.get("headers") or {}
    resp_ctype = resp_headers.get("Content-Type") or resp_headers.get("content-type") or ""
    resp_body = resp.get("body") or ""
    body_preview, truncated = _truncate(resp_body)
    has_template = "response-template" in (resp.get("transformers") or [])

    responses_rows = f'<tr><td><code>{status}</code></td><td>{_response_description(mapping, has_template)}</td></tr>'
    if resp.get("fault"):
        responses_rows = f'<tr><td colspan="2">This scenario returns a WireMock <strong>fault</strong> (<code>{_esc(resp["fault"])}</code>) instead of a normal response — used to test client-side error handling, not a real payload.</td></tr>'

    request_example = _render_request_example(method, path, req)
    try_out = _render_try_out(method, path, req)

    return f"""
    <div class="swagger-op">
      <button class="op-summary {method.lower()}" onclick="toggleOp(this)">
        <span class="method-pill {method.lower()}">{method}</span>
        <span class="op-path">{_esc(path)}</span>
        <span class="op-desc">{_esc(title)}</span>
        <span class="op-kind-tag">{kind_label}</span>
        <span class="op-chevron">▾</span>
      </button>
      <div class="op-body">
        <h5>Request example</h5>
        <div class="code-wrap"><button class="copy-btn" onclick="copyCode(this)">Copy</button><pre><code>{request_example}</code></pre></div>

        <h5>Parameters</h5>
        <table><tr><th>Name</th><th>In</th><th>Description</th></tr>{param_rows}</table>
        {body_pattern_html}

        <h5>Responses</h5>
        <table><tr><th>Code</th><th>Description</th></tr>{responses_rows}</table>
        {f'<h5>Response body preview</h5><div class="code-wrap"><button class="copy-btn" onclick="copyCode(this)">Copy</button><pre><code>{_esc(body_preview)}</code></pre></div>' if resp_body else ''}
        {f'<p class="truncate-note">Response body truncated for display — {len(resp_body):,} characters in the real mapping. Full content is in the actual <code>.json</code> file under <code>src/main/resources/mappings/</code>.</p>' if truncated else ''}

        <button class="try-btn" onclick="toggleTry(this)">Try it out</button>
        <div class="try-out-pane">{try_out}</div>
      </div>
    </div>"""


def _render_body_patterns(patterns: list[dict] | None) -> str:
    if not patterns:
        return '<p class="hint-text">No request body pattern — any well-formed body is accepted (or none, for GET-style calls).</p>'
    rows = []
    for p in patterns:
        if "matchesXPath" in p:
            ns = p.get("xPathNamespaces") or {}
            ns_str = ", ".join(f"{k}={v}" for k, v in ns.items())
            rows.append(f'Request body must match XPath <code>{_esc(p["matchesXPath"])}</code>{f" (namespaces: {_esc(ns_str)})" if ns_str else ""}.')
        elif "matchesJsonPath" in p:
            rows.append(f'Request body must match JSONPath <code>{_esc(p["matchesJsonPath"])}</code>.')
        elif "contains" in p:
            rows.append(f'Request body must contain <code>{_esc(p["contains"])}</code>.')
        elif "equalTo" in p:
            rows.append(f'Request body must equal <code>{_esc(p["equalTo"])}</code>.')
    return '<div class="callout body-pattern-callout"><strong>Body match required:</strong> ' + " ".join(rows) + "</div>"


def _response_description(mapping: dict, has_template: bool) -> str:
    base = "Success response." if int(mapping["response"].get("status", 200)) < 400 else "Error response."
    if has_template:
        base += " Contains a <code>{{...}}</code> template value echoed back from your request."
    return base


def _render_request_example(method: str, path: str, req: dict) -> str:
    lines = [f"{_esc(method)} {_esc(path)} HTTP/1.1", "Host: localhost:8080"]
    for k, v in (req.get("headers") or {}).items():
        lines.append(f"{_esc(k)}: {_esc(v.get('equalTo', ''))}")
    if req.get("bodyPatterns"):
        lines.append("")
        lines.append("<!-- body must satisfy the pattern(s) shown below -->")
    elif method in ("POST", "PUT", "PATCH"):
        lines.append("")
        lines.append("{}")
    return "\n".join(lines)


def _render_try_out(method: str, path: str, req: dict) -> str:
    headers = req.get("headers") or {}
    ps_headers = "; ".join(f'"{_esc(k)}"="{_esc(v.get("equalTo",""))}"' for k, v in headers.items())
    curl_headers = " ".join(f'-H "{_esc(k)}: {_esc(v.get("equalTo",""))}"' for k, v in headers.items())
    body_arg_ps = " -Body '{}'" if method in ("POST", "PUT", "PATCH") else ""
    body_arg_curl = ' -d "{}"' if method in ("POST", "PUT", "PATCH") else ""
    url = f"http://localhost:8080{path}"
    ps = (
        f'Invoke-RestMethod -Uri "{_esc(url)}" -Method {_esc(method)}'
        + (f" -Headers @{{{ps_headers}}}" if ps_headers else "")
        + body_arg_ps
    )
    curl = f'curl -X {_esc(method)} "{_esc(url)}"' + (f" {curl_headers}" if curl_headers else "") + body_arg_curl
    return (
        f'<h5>PowerShell</h5><div class="code-wrap"><button class="copy-btn" onclick="copyCode(this)">Copy</button><pre><code>{ps}</code></pre></div>'
        f'<h5>curl</h5><div class="code-wrap"><button class="copy-btn" onclick="copyCode(this)">Copy</button><pre><code>{curl}</code></pre></div>'
    )


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= _BODY_PREVIEW_LIMIT:
        return text, False
    return text[:_BODY_PREVIEW_LIMIT] + "\n... (truncated)", True


def _esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


_EMPTY_STATE = '<p class="hint-text">No mappings in this stub yet.</p>'

# ── page template ──────────────────────────────────────────────────────────────
# NOTE: kept as one big literal so the guide is fully self-contained (no
# external CSS/JS/fonts) and works offline straight from an extracted zip on
# an air-gapped RHEL box.

_PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project_name} — Stub Setup &amp; Service Reference</title>
<style>
  :root {{
    --bg: #f5f7fb; --surface: #ffffff; --ink: #161d2b; --ink-soft: #545f72;
    --border: #e3e8f0; --navy: #003875; --cyan: #00a9e0; --green: #16825d;
    --amber: #b7791f; --red: #c0392b; --purple: #7c5cff; --grey: #8a94a3;
    --radius: 14px; --shadow: 0 1px 2px rgba(20,30,50,.04), 0 10px 28px -8px rgba(20,30,50,.10);
    --shadow-hover: 0 4px 10px rgba(20,30,50,.06), 0 18px 40px -10px rgba(20,30,50,.16);
    --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    --sans: -apple-system, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0c1220; --surface: #131b2c; --ink: #eef1f8; --ink-soft: #9aa7bf;
      --border: #232e45; --navy: #6cb1f5; --cyan: #52d8ff; --green: #4fce9c;
      --amber: #e8b95c; --red: #ef6b5c; --purple: #a794ff; --grey: #7c88a3;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.5);
      --shadow-hover: 0 4px 10px rgba(0,0,0,.35), 0 18px 40px -10px rgba(0,0,0,.6);
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: var(--sans); background: var(--bg); color: var(--ink); line-height: 1.6; }}
  .shell {{ display: flex; min-height: 100vh; }}
  nav.toc {{ width: 260px; flex-shrink: 0; background: var(--surface); border-right: 1px solid var(--border); padding: 26px 18px; position: sticky; top: 0; height: 100vh; overflow-y: auto; }}
  nav.toc .brand {{ font-weight: 800; font-size: 1.02rem; letter-spacing: -0.01em; }}
  nav.toc .sub {{ color: var(--ink-soft); font-size: 0.76rem; margin: 2px 0 22px; }}
  nav.toc a {{ display: block; color: var(--ink-soft); text-decoration: none; font-size: 0.84rem; padding: 6px 10px; border-radius: 7px; margin-bottom: 1px; transition: background .12s, color .12s; }}
  nav.toc a:hover {{ background: var(--bg); color: var(--ink); }}
  nav.toc a.active {{ background: color-mix(in srgb, var(--navy) 12%, transparent); color: var(--navy); font-weight: 600; }}
  nav.toc .section-label {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--grey); margin: 18px 0 6px 10px; font-weight: 700; }}
  main {{ flex: 1; max-width: 1040px; padding: 0 56px 100px; }}

  .hero {{ margin: 0 -56px 40px; padding: 56px 56px 40px; background:
      radial-gradient(1100px 420px at 12% -10%, color-mix(in srgb, var(--cyan) 22%, transparent), transparent 60%),
      radial-gradient(900px 380px at 100% 0%, color-mix(in srgb, var(--purple) 16%, transparent), transparent 55%),
      var(--surface);
    border-bottom: 1px solid var(--border); }}
  .eyebrow {{ font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--cyan); }}
  h1 {{ font-size: 2.1rem; margin: 6px 0 4px; letter-spacing: -0.02em; }}
  .hero-meta {{ color: var(--ink-soft); font-size: 0.88rem; margin: 4px 0 20px; }}
  .stat-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .stat-pill {{ display: inline-flex; align-items: center; gap: 7px; background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow); border-radius: 100px; padding: 7px 14px 7px 8px; font-size: 0.82rem; font-weight: 600; color: var(--ink); }}

  h2 {{ font-size: 1.35rem; margin: 54px 0 6px; padding-top: 8px; border-top: 1px solid var(--border); letter-spacing: -0.01em; }}
  h2:first-of-type {{ border-top: none; padding-top: 0; margin-top: 8px; }}
  h3 {{ font-size: 1.05rem; margin: 28px 0 8px; }}
  h4 {{ font-size: 0.95rem; margin: 22px 0 6px; }}
  h5 {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--grey); margin: 18px 0 8px; font-weight: 700; }}
  h5:first-child {{ margin-top: 16px; }}
  p {{ color: var(--ink-soft); max-width: 74ch; }}
  .lede {{ font-size: 1.02rem; color: var(--ink-soft); max-width: 70ch; }}

  ol.steps {{ padding-left: 0; list-style: none; counter-reset: step; max-width: 72ch; }}
  ol.steps > li {{ counter-increment: step; position: relative; padding-left: 40px; margin-bottom: 14px; color: var(--ink-soft); }}
  ol.steps > li::before {{ content: counter(step); position: absolute; left: 0; top: -1px; width: 26px; height: 26px; border-radius: 50%; background: var(--navy); color: #fff; font-size: 0.8rem; font-weight: 700; display: flex; align-items: center; justify-content: center; }}
  ol.steps > li strong {{ color: var(--ink); }}

  code {{ font-family: var(--mono); font-size: 0.85em; background: var(--bg); padding: 1px 5px; border-radius: 4px; }}
  pre {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; overflow-x: auto; font-family: var(--mono); font-size: 0.82rem; color: var(--ink); margin: 0; }}
  pre code {{ background: none; padding: 0; }}
  .code-wrap {{ position: relative; margin: 8px 0 16px; }}
  .copy-btn {{ position: absolute; top: 9px; right: 9px; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; padding: 5px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--surface); color: var(--ink-soft); cursor: pointer; font-family: var(--sans); transition: all .12s; }}
  .copy-btn:hover {{ color: var(--ink); border-color: var(--cyan); }}
  .copy-btn.copied {{ color: var(--green); border-color: var(--green); }}

  .callout {{ background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--navy); border-radius: var(--radius); padding: 16px 20px; margin: 20px 0; font-size: 0.92rem; max-width: 72ch; box-shadow: var(--shadow); }}
  .callout.warn {{ border-left-color: var(--amber); }}
  .callout.tip {{ border-left-color: var(--green); }}
  .callout.bad {{ border-left-color: var(--red); }}
  .callout strong {{ color: var(--ink); }}
  .body-pattern-callout {{ border-left-color: var(--purple); max-width: 84ch; margin: 12px 0 4px; font-size: 0.85rem; padding: 12px 16px; }}
  .hint-text {{ color: var(--ink-soft); font-size: 0.85rem; font-style: italic; margin: 6px 0 4px; }}
  .truncate-note {{ font-size: 0.8rem; color: var(--grey); margin-top: -6px; }}

  table {{ width: 100%; border-collapse: collapse; margin: 6px 0 4px; font-size: 0.86rem; }}
  th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ color: var(--grey); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 700; }}

  a.crosslink {{ color: var(--cyan); text-decoration: none; font-weight: 600; }}
  a.crosslink:hover {{ text-decoration: underline; }}

  .req-flag {{ font-size: 0.66rem; font-weight: 700; color: var(--red); text-transform: uppercase; margin-left: 4px; }}

  /* Swagger-style collapsible operation blocks */
  .swagger-op {{ border: 1px solid var(--border); border-radius: var(--radius); margin: 14px 0; max-width: 88ch; overflow: hidden; background: var(--surface); box-shadow: var(--shadow); transition: box-shadow .15s; }}
  .swagger-op:hover {{ box-shadow: var(--shadow-hover); }}
  .op-summary {{ display: flex; align-items: center; gap: 14px; width: 100%; text-align: left; padding: 14px 18px; background: none; border: none; cursor: pointer; font: inherit; color: var(--ink); border-left: 6px solid var(--grey); }}
  .op-summary:hover {{ background: var(--bg); }}
  .op-summary.get {{ border-left-color: #4a90d9; }}
  .op-summary.post {{ border-left-color: var(--green); }}
  .op-summary.put {{ border-left-color: var(--amber); }}
  .op-summary.delete {{ border-left-color: var(--red); }}
  .op-summary.patch {{ border-left-color: var(--purple); }}
  .method-pill {{ font-family: var(--mono); font-weight: 700; font-size: 0.76rem; padding: 5px 12px; border-radius: 6px; color: #fff; min-width: 58px; text-align: center; flex-shrink: 0; }}
  .method-pill.sm {{ padding: 2px 8px; font-size: 0.68rem; min-width: 44px; }}
  .method-pill.get {{ background: #4a90d9; }}
  .method-pill.post {{ background: var(--green); }}
  .method-pill.put {{ background: var(--amber); }}
  .method-pill.delete {{ background: var(--red); }}
  .method-pill.patch {{ background: var(--purple); }}
  .op-path {{ font-family: var(--mono); font-size: 0.85rem; color: var(--ink); flex-shrink: 0; }}
  .op-desc {{ color: var(--ink-soft); font-size: 0.85rem; flex: 1; }}
  .op-kind-tag {{ font-size: 0.66rem; font-weight: 700; letter-spacing: 0.05em; color: var(--grey); border: 1px solid var(--border); border-radius: 100px; padding: 3px 9px; flex-shrink: 0; }}
  .op-chevron {{ color: var(--grey); transition: transform 0.18s; flex-shrink: 0; }}
  .swagger-op.open .op-chevron {{ transform: rotate(180deg); }}
  .op-body-wrap {{ display: grid; grid-template-rows: 0fr; transition: grid-template-rows .22s ease; }}
  .op-body {{ overflow: hidden; padding: 0 20px; border-top: 0 solid var(--border); max-height: 0; transition: max-height .22s ease, padding .22s ease; }}
  .swagger-op.open .op-body {{ max-height: 4000px; padding: 4px 20px 22px; border-top: 1px solid var(--border); }}

  .try-btn {{ display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 0.78rem; font-weight: 700; padding: 8px 18px; border-radius: 8px; border: 1px solid var(--green); color: var(--green); background: none; cursor: pointer; font-family: inherit; transition: all .12s; }}
  .try-btn:hover {{ background: color-mix(in srgb, var(--green) 12%, transparent); }}
  .try-out-pane {{ display: none; margin-top: 12px; }}
  .try-out-pane.open {{ display: block; }}

  @media (max-width: 860px) {{ .shell {{ flex-direction: column; }} nav.toc {{ width: 100%; height: auto; position: static; }} .hero {{ margin: 0 -20px 30px; padding: 34px 20px; }} main {{ padding: 0 20px 80px; }} }}
</style>
</head>
<body>
<div class="shell">
  <nav class="toc">
    <div class="brand">Mockingbird</div>
    <div class="sub">Stub Setup &amp; Service Reference</div>
    <a href="#overview">Overview</a>
    <a href="#prereqs">Software required</a>
    <div class="section-label">Setup</div>
    <a href="#build">Build it</a>
    <a href="#run">Run it</a>
    <a href="#verify">Verify it's up</a>
    <a href="#ports">Default &amp; custom ports</a>
    <div class="section-label">Testing the services</div>
    <a href="#project-structure">What's in the project</a>
    <a href="#service-reference">Service reference</a>
    <a href="#nft">Building NFT scripts</a>
    <div class="section-label">Known issues &amp; patterns</div>
    <a href="#collisions">Fixing mapping collisions</a>
    <a href="#ws-security">WS-Security</a>
    <a href="#troubleshooting">Troubleshooting</a>
  </nav>
  <main>
    <div class="hero">
      <div class="eyebrow">Mockingbird stub engine</div>
      <h1 id="overview">{project_name}</h1>
      <p class="hero-meta">Generated {generated_at} · Spring Boot + embedded WireMock · {endpoint_count} endpoint(s)</p>
      <div class="stat-row">{method_pills}</div>
    </div>

    <p class="lede">
      This is a real, self-contained <strong>Spring Boot</strong> application with <strong>WireMock</strong>
      embedded as a library. Everything below is generated specifically for this download — the service
      reference reflects exactly what this stub does, not a generic example.
    </p>

    <h2 id="prereqs">Software required</h2>
    <table>
      <tr><th>Software</th><th>Version</th><th>Needed for</th></tr>
      <tr><td><code>Java (JDK)</code></td><td>21</td><td>Building <em>and</em> running. A JRE-only install is not enough — Maven needs <code>javac</code> to compile.</td></tr>
      <tr><td><code>Apache Maven</code></td><td>3.9+</td><td>Building the project (<code>mvn</code> command)</td></tr>
      <tr><td>Network access</td><td>—</td><td>To your Artifactory mirror (production) or Maven Central (local testing) to download dependencies</td></tr>
    </table>
    <p>Docker is <em>not required</em> to build or run locally — <code>mvn</code> + <code>java</code> is enough. Docker only matters for the AWS deployment path (a separate, already-built Dockerfile in this project).</p>

    <h2 id="build">Build it</h2>
    <pre><code>cd path\to\extracted-stub
mvn clean package -DskipTests</code></pre>
    <p>Same command on Windows and RHEL/Linux once Java and Maven are on your <code>PATH</code>. A successful build ends with <code>BUILD SUCCESS</code> and produces exactly one runnable file:</p>
    <pre><code>target/app.jar</code></pre>

    <h3>RHEL — installing prerequisites if you don't have them</h3>
    <pre><code># Java 21 JDK
sudo dnf install -y java-21-openjdk-devel
java -version

# Maven — if not available via dnf, install from the Apache tarball:
curl -O https://dlcdn.apache.org/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.tar.gz
sudo tar xzf apache-maven-3.9.9-bin.tar.gz -C /opt
sudo ln -s /opt/apache-maven-3.9.9 /opt/maven
echo 'export PATH=/opt/maven/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
mvn -version</code></pre>

    <h2 id="run">Run it</h2>
    <p>Default run — no arguments needed:</p>
    <pre><code>java -jar target/app.jar</code></pre>
    <p>Background, on Linux, surviving logout:</p>
    <pre><code>nohup java -jar target/app.jar > stub.log 2>&1 &
disown</code></pre>

    <h4>Running as a systemd service (RHEL)</h4>
    <pre><code># /etc/systemd/system/mockingbird-stub.service
[Unit]
Description=Mockingbird Stub Engine
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/mockingbird-stub
ExecStart=/usr/bin/java -jar /opt/mockingbird-stub/target/app.jar
Restart=on-failure
User=mockingbird

[Install]
WantedBy=multi-user.target</code></pre>
    <pre><code>sudo systemctl daemon-reload
sudo systemctl enable --now mockingbird-stub
journalctl -u mockingbird-stub -f</code></pre>

    <h2 id="verify">Verify it's up</h2>
    <p>Check the startup log for a line like this — the mapping count should read <strong>{endpoint_count}</strong>:</p>
    <pre><code>WireMockConfig : Loaded {endpoint_count} stub mappings</code></pre>
    <pre><code>curl http://localhost:8081/actuator/health
# {{"status":"UP"}}</code></pre>

    <h2 id="ports">Default &amp; custom ports</h2>
    <table>
      <tr><th>Port</th><th>What's on it</th></tr>
      <tr><td><code>8080</code></td><td>Actual stub traffic — every service call below goes here.</td></tr>
      <tr><td><code>8081</code></td><td>Spring Boot Actuator only — health checks, Prometheus metrics. <strong>Not</strong> stub traffic.</td></tr>
    </table>
    <pre><code>java -jar target/app.jar --stub.port=9090 --server.port=9091</code></pre>

    <h2 id="project-structure">What's in the project</h2>
    <table>
      <tr><th>Path</th><th>What it is</th></tr>
      <tr><td><code>pom.xml</code></td><td>Maven build file — all dependencies, Java 21 target.</td></tr>
      <tr><td><code>Dockerfile</code></td><td>Only used for the AWS deploy path. Not needed for local <code>mvn</code>/<code>java</code> use.</td></tr>
      <tr><td><code>src/main/resources/mappings/*.json</code></td><td><strong>The actual contract for every service this stub serves</strong> — one file per scenario. The section below is generated directly from these files.</td></tr>
      <tr><td><code>src/main/resources/application.yml</code></td><td>Ports, WS-Security toggle, logging config.</td></tr>
    </table>

    <h2 id="service-reference">Service reference</h2>
    <p>{endpoint_summary_sentence} Every card below was generated directly from this stub's real WireMock mappings.</p>
    {service_cards}

    <h2 id="nft">Building NFT / performance test scripts</h2>
    <p>Whatever tool you use — JMeter, k6, Gatling, LoadRunner — every HTTP sampler needs the same four things, all visible in each card above: method + URL, required headers, any body pattern, and the expected response.</p>
    <div class="callout tip">
      <strong>Tip for ramping load:</strong> if a response's description mentions an echoed template
      value, vary that value per virtual user so your assertions stay meaningful instead of asserting on
      a hardcoded value.
    </div>

    <h2 id="collisions">Fixing mapping collisions</h2>
    <p>If two mappings end up with an <strong>identical</strong> request block (same method, URL, and headers) and nothing else distinguishes them, WireMock can only ever reach one of them. This happens most often with SOAP captures — several calls to the same operation and headers, differing only in the XML payload.</p>
    <div class="callout bad"><strong>Symptom:</strong> two scenarios you expect to both work — one always "wins," the other returns the wrong response no matter what you send.</div>
    <p><strong>Fix:</strong> add a <code>bodyPatterns</code> entry using a real, distinguishing element from each request's body:</p>
    <pre><code>{{
  "request": {{
    "method": "POST",
    "urlPath": "/example/operation",
    "bodyPatterns": [
      {{
        "matchesXPath": "//ns:requestId[text()='ABC123']",
        "xPathNamespaces": {{ "ns": "http://example.com/ns" }}
      }}
    ]
  }}
}}</code></pre>
    <p>For a JSON body, use <code>"matchesJsonPath"</code> instead of <code>matchesXPath</code>, or <code>"contains"</code> for a simple substring check.</p>

    <h2 id="ws-security">WS-Security</h2>
    <p>
      Set <code>SOAP_WS_SECURITY_ENABLED=true</code> (plus <code>SOAP_WS_SECURITY_USERNAME</code> /
      <code>SOAP_WS_SECURITY_PASSWORD</code>) to require a valid WS-Security <code>UsernameToken</code>
      on every SOAP request this stub serves. Enforced by <code>WsSecurityRequestFilter</code>, registered
      directly into WireMock's own request pipeline — the same one that actually serves stub traffic — so
      it genuinely sees and can reject every real call.
    </p>
    <p>Scope: a plain-text <code>Username</code> + <code>Password</code> pair against the single
    username/password configured for the whole deployment. <code>PasswordDigest</code> isn't implemented.
    Requests that don't look like SOAP are left untouched even when this is enabled.</p>

    <h2 id="troubleshooting">Troubleshooting</h2>
    <table>
      <tr><th>Symptom</th><th>Cause / fix</th></tr>
      <tr><td><code>Port 8080/8081 was already in use</code></td><td>A previous run is still alive. Stop it, or start this one on different ports (see <a class="crosslink" href="#ports">above</a>).</td></tr>
      <tr><td>Request returns <code>404 Request was not matched</code></td><td>WireMock's error body shows exactly which header/query/body pattern didn't match — compare it against the relevant card above.</td></tr>
      <tr><td>Two similar requests return the same response</td><td>Mapping collision — see <a class="crosslink" href="#collisions">above</a>.</td></tr>
      <tr><td>Build fails with a Java compiler error</td><td>You're building with a JRE, not a JDK. Install the full JDK 21.</td></tr>
    </table>

  </main>
</div>
<script>
  function toggleOp(btn) {{ btn.parentElement.classList.toggle('open'); }}
  function toggleTry(btn) {{ btn.nextElementSibling.classList.toggle('open'); }}
  function copyCode(btn) {{
    var code = btn.parentElement.querySelector('code').innerText;
    navigator.clipboard.writeText(code).then(function() {{
      var original = btn.textContent;
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(function() {{ btn.textContent = original; btn.classList.remove('copied'); }}, 1400);
    }}).catch(function() {{}});
  }}
  (function() {{
    var links = Array.prototype.slice.call(document.querySelectorAll('nav.toc a'));
    var sections = links.map(function(a) {{ return document.getElementById(a.getAttribute('href').slice(1)); }}).filter(Boolean);
    if (!('IntersectionObserver' in window) || sections.length === 0) return;
    var observer = new IntersectionObserver(function(entries) {{
      entries.forEach(function(entry) {{
        if (entry.isIntersecting) {{
          links.forEach(function(l) {{ l.classList.remove('active'); }});
          var match = links.find(function(a) {{ return a.getAttribute('href') === '#' + entry.target.id; }});
          if (match) match.classList.add('active');
        }}
      }});
    }}, {{ rootMargin: '-20% 0px -70% 0px' }});
    sections.forEach(function(s) {{ observer.observe(s); }});
  }})();
</script>
</body>
</html>
"""
