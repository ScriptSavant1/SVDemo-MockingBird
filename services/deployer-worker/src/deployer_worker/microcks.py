"""Microcks SSH deployer (Sprint 23).

Used when the DEPLOY payload carries engine_type == "MICROCKS".
Unlike WireMock/Kafka engines (which require a GitLab CI Kaniko build),
Microcks runs from a pre-built Docker image pulled from the Artifactory
mirror — there is no build step. The deployer:

  1. Downloads the microcks-config.zip from S3 and extracts it locally.
  2. SSH-copies docker-compose.microcks.yml + asyncapi.yaml to the EC2.
  3. Runs docker-compose up -d on the EC2 via SSH.
  4. Health-checks port 8080 (reuses existing wait_for_ec2_healthy).

All SSH operations use Paramiko with the project's EC2 key pair.
"""
from __future__ import annotations

import logging
from pathlib import Path

import paramiko

logger = logging.getLogger(__name__)

_DEFAULT_SSH_USER = "ec2-user"
_REMOTE_DIR = "/opt/microcks"

# Files that must be present in the extracted config directory
_REQUIRED_FILES = ("docker-compose.microcks.yml", "asyncapi.yaml")


class MicrocksDeployError(Exception):
    pass


def deploy_microcks(
    ec2_ip: str,
    ssh_key_path: str,
    config_dir: Path,
    ssh_user: str = _DEFAULT_SSH_USER,
) -> None:
    """Upload Microcks config files to EC2 and start the container.

    Args:
        ec2_ip:       Public IP of the provisioned EC2 instance.
        ssh_key_path: Path to the .pem key file for the EC2 key pair.
        config_dir:   Local directory containing docker-compose.microcks.yml,
                      asyncapi.yaml and (optionally) .env.microcks.
        ssh_user:     SSH login user (default ec2-user for Amazon Linux 2).

    Raises:
        MicrocksDeployError: if any SSH command fails.
    """
    for filename in _REQUIRED_FILES:
        if not (config_dir / filename).exists():
            raise MicrocksDeployError(f"Required file missing from config_dir: {filename}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(ec2_ip, username=ssh_user, key_filename=ssh_key_path, timeout=30)
        logger.info("SSH connected to EC2 %s as %s", ec2_ip, ssh_user)

        _exec(client, f"mkdir -p {_REMOTE_DIR}")

        sftp = client.open_sftp()
        try:
            for filename in _REQUIRED_FILES:
                local_path = config_dir / filename
                remote_path = f"{_REMOTE_DIR}/{filename}"
                sftp.put(str(local_path), remote_path)
                logger.debug("Uploaded %s → %s:%s", local_path, ec2_ip, remote_path)

            env_path = config_dir / ".env.microcks"
            if env_path.exists():
                sftp.put(str(env_path), f"{_REMOTE_DIR}/.env")
        finally:
            sftp.close()

        logger.info("Pulling Microcks image on EC2 %s", ec2_ip)
        _exec(client, f"cd {_REMOTE_DIR} && docker-compose -f docker-compose.microcks.yml pull")

        logger.info("Starting Microcks on EC2 %s", ec2_ip)
        _exec(client, f"cd {_REMOTE_DIR} && docker-compose -f docker-compose.microcks.yml up -d")

        logger.info("Microcks deployed successfully on EC2 %s", ec2_ip)

    except paramiko.SSHException as exc:
        raise MicrocksDeployError(f"SSH error deploying Microcks to {ec2_ip}: {exc}") from exc
    finally:
        client.close()


def _exec(client: paramiko.SSHClient, cmd: str) -> str:
    """Run a command over SSH; raise MicrocksDeployError on non-zero exit."""
    _, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if exit_code != 0:
        raise MicrocksDeployError(
            f"SSH command failed (exit {exit_code}): {cmd!r}\nstderr: {err.strip()}"
        )
    return out
