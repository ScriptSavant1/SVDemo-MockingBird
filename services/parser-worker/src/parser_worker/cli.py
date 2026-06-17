"""sv-gen CLI — parse a stub definition file and generate a deployable Spring Boot project."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .detector import detect_and_parse
from .generator.springboot import generate_springboot_project


@click.command()
@click.version_option(version="0.1.0", prog_name="sv-gen")
@click.option("--input", "-i", "input_file", required=True, type=click.Path(exists=True),
              help="Stub definition file (.txt, .json, Postman collection, or OpenAPI spec)")
@click.option("--output", "-o", "output_dir", required=True, type=click.Path(),
              help="Output directory for the generated Spring Boot project")
@click.option("--project-id", default="", help="Short ID for the project (e.g. payment-api). Auto-derived if omitted.")
@click.option("--project-name", default="", help="Human-readable project name. Auto-derived if omitted.")
@click.option("--mappings-only", is_flag=True,
              help="Generate only WireMock mapping JSON files (skip Spring Boot project scaffold)")
@click.option("--dry-run", is_flag=True,
              help="Validate only — show summary without writing any files")
def main(
    input_file: str,
    output_dir: str,
    project_id: str,
    project_name: str,
    mappings_only: bool,
    dry_run: bool,
) -> None:
    """sv-gen — Mockingbird stub generator.

    Reads a stub definition file, validates it, and generates a complete
    Spring Boot + WireMock project ready for 'docker build'.

    Examples:

        sv-gen --input payment.txt --output ./payment-stub

        sv-gen --input customer.json --output ./customer-stub --project-id customer-api

        sv-gen --input payment.txt --output ./payment-stub --dry-run

        sv-gen --input payment.txt --output ./payment-stub --mappings-only
    """
    input_path = Path(input_file)
    output_path = Path(output_dir)

    click.echo(f"  Reading: {input_path.name}")

    parser, validation_result, parsed_file = detect_and_parse(input_path)

    if not validation_result.valid:
        click.echo(click.style("  INVALID", fg="red", bold=True))
        for error in validation_result.errors:
            click.echo(click.style(f"  ERROR   {error}", fg="red"))
        sys.exit(1)

    format_label = validation_result.format_detected or (parser.format_name if parser else "unknown")
    click.echo(click.style("  VALID", fg="green", bold=True) + f"   [{format_label}]  {validation_result.summary}")

    for warning in (validation_result.warnings or []):
        click.echo(click.style(f"  WARN    {warning}", fg="yellow"))

    if dry_run:
        click.echo("  Dry run — no files written.")
        return

    if parsed_file is None:
        click.echo(click.style("  Unexpected: parse failed after validation passed.", fg="red"))
        sys.exit(1)

    if mappings_only:
        from .generator.wiremock import generate_wiremock_mappings
        output_path.mkdir(parents=True, exist_ok=True)
        created = generate_wiremock_mappings(parsed_file, output_path)
        click.echo(f"\n  Generated {len(created)} WireMock mapping(s) → {output_path / 'mappings'}/")
        for path in created:
            click.echo(f"    {path.name}")
    else:
        generate_springboot_project(parsed_file, output_path, project_id, project_name)
        _print_project_summary(parsed_file, output_path)

    _write_manifest(parsed_file, output_path)


def _print_project_summary(parsed_file: object, output_dir: Path) -> None:
    from .models import ParsedFile
    if not isinstance(parsed_file, ParsedFile):
        return

    total_scenarios = sum(len(s.scenarios) for s in parsed_file.stubs)
    click.echo(f"\n  Generated Spring Boot project → {output_dir}/")
    click.echo(f"  {len(parsed_file.stubs)} stub(s)   {total_scenarios} scenario(s)")
    click.echo("")
    click.echo("  To build and run locally:")
    click.echo(f"    cd {output_dir}")
    click.echo("    docker compose up --build")
    click.echo("")
    click.echo("  Stub will be available at:  http://localhost:8080")
    click.echo("  Metrics (Prometheus):        http://localhost:8081/actuator/prometheus")
    click.echo("  Health check:                http://localhost:8081/actuator/health")
    click.echo("")
    click.echo("  To deploy to EC2 via Mockingbird platform:")
    click.echo("    Upload this directory to the Mockingbird portal and click Deploy.")


def _write_manifest(parsed_file: object, output_dir: Path) -> None:
    from .models import ParsedFile
    if not isinstance(parsed_file, ParsedFile):
        return
    manifest = {
        "mockingbird_version": "1.0",
        "format": parsed_file.format,
        "source": parsed_file.source_file,
        "stubs": [
            {
                "name": stub.name,
                "team": stub.team,
                "method": stub.request.method.value,
                "url": stub.request.url,
                "scenarios": [
                    {"name": s.name, "status": s.status, "match_type": s.match.type.value}
                    for s in stub.scenarios
                ],
            }
            for stub in parsed_file.stubs
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
