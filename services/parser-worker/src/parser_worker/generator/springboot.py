"""Generates a complete Spring Boot + WireMock project from parsed stubs.

Output directory structure:
    output/
    ├── pom.xml                 Maven build (all deps from Artifactory)
    ├── settings.xml            Artifactory mirror config
    ├── Dockerfile              Java 21 base image
    ├── docker-compose.yml      For local testing
    ├── nginx.conf              TLS termination in front of WireMock — only
    │                            actually started (by entrypoint.sh) when the
    │                            project's protocol is HTTPS/BOTH. See
    │                            generator/springboot.py's mtls_enabled param.
    ├── entrypoint.sh           Starts nginx (when applicable) + the jar
    ├── STUB_ENGINE_SETUP_GUIDE.html   Build/run instructions + per-endpoint
    │                                   service reference — self-contained,
    │                                   readable straight from the extracted zip
    └── src/main/
        ├── java/com/mockingbird/stubs/
        │   ├── StubApplication.java
        │   └── WireMockConfig.java
        └── resources/
            ├── application.yml
            ├── mappings/       WireMock JSON mapping files (baked into the JAR
            │                    via classpath — see WireMockConfig.java)
            └── lookup-tables/  Data files for stubs with too many same-URL
                                 captures for static mappings to be the right
                                 fit — see generator/lookup_table.py and
                                 DynamicLookupRequestFilter.java. Empty unless
                                 a stub actually crosses that threshold.

Mappings are written directly to src/main/resources/mappings/ — there is no
separate top-level mappings/ copy. Nothing in the Docker build or
docker-compose.yml reads a top-level copy (the runtime only ever loads
classpath resources), so an earlier version of this generator that produced
both was shipping a dead, confusing duplicate in every downloaded project.

Two entry points share one in-memory file build (build_springboot_project_files):
    generate_springboot_project      writes real files under output_dir — for a
                                      local `mvn package` / CLI workflow that
                                      needs an actual directory on disk.
    generate_springboot_project_zip  returns the project as ZIP bytes directly,
                                      never touching the filesystem — for a hot
                                      request path (e.g. ingestion-service's
                                      upload handler, which used to write every
                                      file to a real temp directory, read them
                                      all back with rglob to build a ZIP, then
                                      delete the directory — real disk I/O for
                                      every one of potentially hundreds of
                                      generated files, on every upload, purely
                                      to immediately re-read and discard them).
"""
from __future__ import annotations

import importlib.resources as _pkg
import io
import re
import zipfile
from pathlib import Path
from typing import Optional

from ..models import ParsedFile
from .lookup_table import build_lookup_table_files
from .setup_guide import generate_setup_guide_html
from .wiremock import build_wiremock_mapping_files

_SAFE_ID_RE = re.compile(r'[^\w-]')

_JAVA_PKG = "src/main/java/com/mockingbird/stubs"
_STATIC_FILES = (
    "settings.xml",
    "entrypoint.sh",
    f"{_JAVA_PKG}/StubApplication.java",
    f"{_JAVA_PKG}/WireMockConfig.java",
    f"{_JAVA_PKG}/WsSecurityRequestFilter.java",   # SOAP WS-Security
    f"{_JAVA_PKG}/WsdlConfig.java",                 # WSDL serving
    f"{_JAVA_PKG}/DynamicLookupRequestFilter.java",  # same-URL lookup-table engine
    "src/main/resources/application.yml",
    "src/main/resources/wsdl/service.wsdl",
)

# nginx.conf ships two placeholders ({{MTLS_SERVER_DIRECTIVES}},
# {{MTLS_PROXY_HEADERS}}) that only resolve to real directives when the
# project has mTLS enabled — see build_springboot_project_files.
_MTLS_SERVER_DIRECTIVES = """\
        ssl_client_certificate /etc/nginx/certs/ca-bundle.pem;
        ssl_verify_client on;
        ssl_verify_depth 2;"""

_MTLS_PROXY_HEADERS = """\
            proxy_set_header X-SSL-Client-CN $ssl_client_s_dn_cn;
            proxy_set_header X-SSL-Client-Verify $ssl_client_verify;"""


def _stub_engine_dir() -> Path:
    """Return the path to bundled stub-engine templates inside the package.

    Works for both editable installs (pip install -e .) and wheel installs,
    because the templates/ directory is declared as package-data in pyproject.toml.
    """
    return Path(str(_pkg.files("parser_worker").joinpath("templates/stub-engine")))


def build_springboot_project_files(
    parsed: ParsedFile,
    project_id: str = "",
    project_name: str = "",
    mtls_enabled: bool = False,
    protocol: str = "HTTP",
) -> dict[str, bytes]:
    """Build the full Spring Boot project as {relative_path: content_bytes},
    entirely in memory — no filesystem writes, and only the read-only
    template package resources are touched on disk. Both
    generate_springboot_project (disk) and generate_springboot_project_zip
    (ZIP bytes) are thin wrappers around this single build.

    protocol/mtls_enabled come from the stub's TLS settings (see
    project-service migration 006). Which protocol actually runs is still a
    *deploy-time* decision in the sense that STUB_PROTOCOL is a normal env
    var entrypoint.sh reads at container startup, not something compiled
    into the jar — but the Dockerfile/docker-compose.yml now bake in this
    stub's actual selection as the env var's *default*, via a
    {{STUB_PROTOCOL}}/{{MTLS_ENABLED}} placeholder (same pattern as
    pom.xml's {{project_id}}). Without this, a plain `docker run` or
    `docker compose up` on a downloaded HTTPS stub would silently serve
    HTTP, because the template's old hardcoded default was always HTTP
    regardless of what the stub was actually configured for — still
    overridable via `-e`/a shell env var, just no longer silently wrong by
    default. mtls_enabled additionally bakes nginx.conf's
    ssl_verify_client directives at generate time (that part genuinely
    can't be a runtime toggle, since it changes what nginx's config parses
    as valid).
    """
    if not project_id:
        project_id = _to_id(parsed.stubs[0].name if parsed.stubs else "stub")
    if not project_name:
        project_name = parsed.stubs[0].name if parsed.stubs else "Stub"

    files: dict[str, bytes] = {}

    # 1. Static template files, read once from the package's template dir.
    for relative_path in _STATIC_FILES:
        content = _read_template_bytes(relative_path)
        if content is not None:
            files[relative_path] = content

    # 1b. Dockerfile / docker-compose.yml — static except for the
    # STUB_PROTOCOL/MTLS_ENABLED defaults, filled in with this stub's
    # actual configured values (same placeholder-substitution pattern as
    # pom.xml's {{project_id}} below).
    for relative_path in ("Dockerfile", "docker-compose.yml"):
        raw = _read_template_bytes(relative_path)
        if raw is not None:
            text = raw.decode("utf-8")
            text = text.replace("{{STUB_PROTOCOL}}", protocol)
            text = text.replace("{{MTLS_ENABLED}}", "true" if mtls_enabled else "false")
            files[relative_path] = text.encode("utf-8")

    # 1c. nginx.conf — static except for its mTLS placeholders, filled in
    # here the same way pom.xml's {{project_id}} placeholder is below.
    nginx_conf_bytes = _read_template_bytes("nginx.conf")
    if nginx_conf_bytes is not None:
        nginx_conf_text = nginx_conf_bytes.decode("utf-8")
        if mtls_enabled:
            nginx_conf_text = nginx_conf_text.replace("{{MTLS_SERVER_DIRECTIVES}}", _MTLS_SERVER_DIRECTIVES)
            nginx_conf_text = nginx_conf_text.replace("{{MTLS_PROXY_HEADERS}}", _MTLS_PROXY_HEADERS)
        else:
            nginx_conf_text = nginx_conf_text.replace("{{MTLS_SERVER_DIRECTIVES}}", "")
            nginx_conf_text = nginx_conf_text.replace("{{MTLS_PROXY_HEADERS}}", "")
        files["nginx.conf"] = nginx_conf_text.encode("utf-8")

    # 2. Setup guide — generated fresh for THIS stub, not a copied static
    # file. The service-reference section reflects this stub's actual
    # mappings, and now also this stub's actual protocol/mTLS setting.
    files["STUB_ENGINE_SETUP_GUIDE.html"] = generate_setup_guide_html(
        parsed, project_name, protocol=protocol, mtls_enabled=mtls_enabled,
    ).encode("utf-8")

    # 3. pom.xml — project-specific placeholders filled in
    pom_bytes = _read_template_bytes("pom.xml")
    if pom_bytes is not None:
        pom_text = pom_bytes.decode("utf-8")
        pom_text = pom_text.replace("{{project_id}}", project_id).replace("{{project_name}}", project_name)
        files["pom.xml"] = pom_text.encode("utf-8")

    # 4. WireMock mapping JSON files, at their final classpath location —
    # no top-level mappings/ copy (see module docstring).
    for relative_path, content in build_wiremock_mapping_files(parsed).items():
        files[f"src/main/resources/{relative_path}"] = content.encode("utf-8")

    # 5. Dynamic lookup-table data files for any stub with enough same-URL
    # captures to skip static per-scenario mappings entirely — see
    # generator/lookup_table.py and DynamicLookupRequestFilter.java.
    for relative_path, content in build_lookup_table_files(parsed).items():
        files[f"src/main/resources/{relative_path}"] = content.encode("utf-8")

    return files


def generate_springboot_project(
    parsed: ParsedFile,
    output_dir: Path,
    project_id: str = "",
    project_name: str = "",
    mtls_enabled: bool = False,
    protocol: str = "HTTP",
) -> Path:
    """Write a complete Spring Boot project ready for 'docker build'.

    Args:
        parsed:       ParsedFile produced by any parser.
        output_dir:   Root directory for the generated project.
        project_id:   Short identifier used in artifact ID (e.g., 'payment-api').
        project_name: Human-readable name (e.g., 'Payment Processing API').
        mtls_enabled: Whether nginx.conf should require+verify client certs
                      (see build_springboot_project_files docstring).
        protocol:     HTTP/HTTPS/BOTH — baked in as this stub's default
                      STUB_PROTOCOL in the Dockerfile/docker-compose.yml.

    Returns:
        output_dir (the generated project root).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    files = build_springboot_project_files(
        parsed, project_id, project_name, mtls_enabled=mtls_enabled, protocol=protocol,
    )
    for relative_path, content in files.items():
        path = output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return output_dir


def generate_springboot_project_zip(
    parsed: ParsedFile,
    project_id: str = "",
    project_name: str = "",
    mtls_enabled: bool = False,
    protocol: str = "HTTP",
) -> bytes:
    """Return the full Spring Boot project as ZIP bytes — no filesystem
    access at all beyond reading the (read-only) bundled templates. Use this
    instead of generate_springboot_project + manually zipping a temp
    directory: that pattern costs one real disk write and one real disk read
    per generated file (potentially hundreds, for a stub with many
    scenarios) purely to immediately discard the directory afterwards.
    """
    buf = io.BytesIO()
    files = build_springboot_project_files(
        parsed, project_id, project_name, mtls_enabled=mtls_enabled, protocol=protocol,
    )
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for relative_path, content in files.items():
            zf.writestr(relative_path, content)
    return buf.getvalue()


def _read_template_bytes(relative_path: str) -> Optional[bytes]:
    src = _stub_engine_dir() / relative_path
    return src.read_bytes() if src.exists() else None


def _to_id(name: str) -> str:
    return _SAFE_ID_RE.sub("-", name.lower()).strip("-")[:50]
