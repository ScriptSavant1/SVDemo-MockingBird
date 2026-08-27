"""Generates a complete Spring Boot + WireMock project from parsed stubs.

Output directory structure:
    output/
    ├── pom.xml                 Maven build (all deps from Artifactory)
    ├── settings.xml            Artifactory mirror config
    ├── Dockerfile              Java 21 base image
    ├── docker-compose.yml      For local testing
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
"""
from __future__ import annotations

import importlib.resources as _pkg
import re
import shutil
from pathlib import Path

from ..models import ParsedFile
from .lookup_table import generate_lookup_tables
from .setup_guide import generate_setup_guide_html
from .wiremock import generate_wiremock_mappings

_SAFE_ID_RE = re.compile(r'[^\w-]')


def _stub_engine_dir() -> Path:
    """Return the path to bundled stub-engine templates inside the package.

    Works for both editable installs (pip install -e .) and wheel installs,
    because the templates/ directory is declared as package-data in pyproject.toml.
    """
    return Path(str(_pkg.files("parser_worker").joinpath("templates/stub-engine")))


def generate_springboot_project(
    parsed: ParsedFile,
    output_dir: Path,
    project_id: str = "",
    project_name: str = "",
) -> Path:
    """Write a complete Spring Boot project ready for 'docker build'.

    Args:
        parsed:       ParsedFile produced by any parser.
        output_dir:   Root directory for the generated project.
        project_id:   Short identifier used in artifact ID (e.g., 'payment-api').
        project_name: Human-readable name (e.g., 'Payment Processing API').

    Returns:
        output_dir (the generated project root).
    """
    if not project_id:
        project_id = _to_id(parsed.stubs[0].name if parsed.stubs else "stub")
    if not project_name:
        project_name = parsed.stubs[0].name if parsed.stubs else "Stub"

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Static template files
    _copy("Dockerfile", output_dir)
    _copy("docker-compose.yml", output_dir)
    _copy("settings.xml", output_dir)

    # Setup guide — generated fresh for THIS stub, not a copied static file.
    # The service-reference section reflects this stub's actual mappings.
    guide_html = generate_setup_guide_html(parsed, project_name)
    (output_dir / "STUB_ENGINE_SETUP_GUIDE.html").write_text(guide_html, encoding="utf-8")

    # 2. pom.xml — project-specific placeholders filled in
    _write_pom(output_dir, project_id, project_name)

    # 3. Java source files
    java_pkg = "src/main/java/com/mockingbird/stubs"
    (output_dir / java_pkg).mkdir(parents=True, exist_ok=True)
    _copy(f"{java_pkg}/StubApplication.java", output_dir)
    _copy(f"{java_pkg}/WireMockConfig.java", output_dir)
    _copy(f"{java_pkg}/WsSecurityRequestFilter.java", output_dir)  # SOAP WS-Security
    _copy(f"{java_pkg}/WsdlConfig.java", output_dir)                # WSDL serving
    _copy(f"{java_pkg}/DynamicLookupRequestFilter.java", output_dir)  # same-URL lookup-table engine

    # 4. Application config + WSDL placeholder
    (output_dir / "src/main/resources").mkdir(parents=True, exist_ok=True)
    _copy("src/main/resources/application.yml", output_dir)
    (output_dir / "src/main/resources/wsdl").mkdir(parents=True, exist_ok=True)
    _copy("src/main/resources/wsdl/service.wsdl", output_dir)

    # 5. WireMock mapping JSON files, written straight to their final classpath
    # location — no top-level mappings/ copy (see module docstring).
    generate_wiremock_mappings(parsed, output_dir / "src/main/resources")

    # 6. Dynamic lookup-table data files for any stub with enough same-URL
    # captures to skip static per-scenario mappings entirely — see
    # generator/lookup_table.py and DynamicLookupRequestFilter.java.
    generate_lookup_tables(parsed, output_dir / "src/main/resources")

    return output_dir


def _copy(relative_path: str, output_dir: Path) -> None:
    src = _stub_engine_dir() / relative_path
    if src.exists():
        dst = output_dir / relative_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _write_pom(output_dir: Path, project_id: str, project_name: str) -> None:
    src = _stub_engine_dir() / "pom.xml"
    if not src.exists():
        return
    content = src.read_text(encoding="utf-8")
    content = content.replace("{{project_id}}", project_id)
    content = content.replace("{{project_name}}", project_name)
    (output_dir / "pom.xml").write_text(content, encoding="utf-8")


def _to_id(name: str) -> str:
    return _SAFE_ID_RE.sub("-", name.lower()).strip("-")[:50]
