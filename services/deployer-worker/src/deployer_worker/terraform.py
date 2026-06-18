"""Terraform runner for deployer-worker.

Wraps terraform CLI (subprocess) to provision and destroy per-project EC2
instances. Terraform state is stored in S3 with DynamoDB locking.

The Terraform module lives in terraform/stub-ec2/ relative to the repo root.
In production the deployer-worker ECS task has the module baked into its
Docker image at /app/terraform/stub-ec2.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


class TerraformError(Exception):
    pass


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        raise TerraformError(
            f"terraform {args[1]} failed (exit {result.returncode}):\n{result.stderr}"
        )
    return result.stdout


def _backend_args(state_bucket: str, state_key: str, aws_region: str, locks_table: str) -> list[str]:
    return [
        f"-backend-config=bucket={state_bucket}",
        f"-backend-config=key={state_key}",
        f"-backend-config=region={aws_region}",
        f"-backend-config=dynamodb_table={locks_table}",
    ]


def apply(
    terraform_dir: Path,
    variables: dict,
    state_bucket: str,
    state_key: str,
    aws_region: str,
    locks_table: str = "mockingbird-terraform-locks",
) -> dict:
    """Run terraform init + apply. Returns parsed terraform output dict."""
    # Write variables to auto.tfvars.json (terraform picks this up automatically)
    tfvars = terraform_dir / "terraform.auto.tfvars.json"
    tfvars.write_text(json.dumps(variables, indent=2))

    backend = _backend_args(state_bucket, state_key, aws_region, locks_table)
    _run(["terraform", "init", "-input=false", "-reconfigure"] + backend, cwd=terraform_dir)
    _run(["terraform", "apply", "-auto-approve", "-input=false"], cwd=terraform_dir)

    output_json = _run(["terraform", "output", "-json"], cwd=terraform_dir)
    return json.loads(output_json)


def destroy(
    terraform_dir: Path,
    state_bucket: str,
    state_key: str,
    aws_region: str,
    locks_table: str = "mockingbird-terraform-locks",
) -> None:
    """Run terraform init + destroy. Used for suspension (EC2 terminated, state removed)."""
    backend = _backend_args(state_bucket, state_key, aws_region, locks_table)
    _run(["terraform", "init", "-input=false", "-reconfigure"] + backend, cwd=terraform_dir)
    _run(["terraform", "destroy", "-auto-approve", "-input=false"], cwd=terraform_dir)
