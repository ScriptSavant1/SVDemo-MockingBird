"""Sprint 23 — Microcks SSH deployer tests."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from deployer_worker.microcks import MicrocksDeployError, deploy_microcks


@pytest.fixture
def config_dir() -> Path:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "docker-compose.microcks.yml").write_text("services:\n  microcks:\n    image: microcks-uber\n")
        (p / "asyncapi.yaml").write_text("asyncapi: '2.6.0'\n")
        (p / ".env.microcks").write_text("KAFKA_BOOTSTRAP_SERVERS=localhost:9092\n")
        yield p


@pytest.fixture
def mock_ssh():
    with patch("deployer_worker.microcks.paramiko.SSHClient") as MockClient:
        client = MagicMock()
        MockClient.return_value = client

        sftp = MagicMock()
        client.open_sftp.return_value = sftp

        # exec_command returns (stdin, stdout, stderr) — stdout must have channel.recv_exit_status()
        def make_exec(exit_code=0, stdout_text="", stderr_text=""):
            stdin = MagicMock()
            stdout = MagicMock()
            stdout.channel.recv_exit_status.return_value = exit_code
            stdout.read.return_value = stdout_text.encode()
            stderr = MagicMock()
            stderr.read.return_value = stderr_text.encode()
            return stdin, stdout, stderr

        client.exec_command.side_effect = [
            make_exec(),  # mkdir
            make_exec(),  # docker-compose pull
            make_exec(),  # docker-compose up -d
        ]

        yield client, sftp


# ── happy path ────────────────────────────────────────────────────────────────

def test_deploy_connects_to_ec2(config_dir: Path, mock_ssh) -> None:
    client, _ = mock_ssh
    deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)
    client.connect.assert_called_once_with("10.0.0.1", username="ec2-user", key_filename="/secrets/key.pem", timeout=30)


def test_deploy_creates_remote_directory(config_dir: Path, mock_ssh) -> None:
    client, _ = mock_ssh
    deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)
    mkdir_call = client.exec_command.call_args_list[0]
    assert "mkdir" in mkdir_call[0][0]
    assert "/opt/microcks" in mkdir_call[0][0]


def test_deploy_uploads_compose_file(config_dir: Path, mock_ssh) -> None:
    _, sftp = mock_ssh
    deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)
    uploaded_filenames = [call_args[0][1] for call_args in sftp.put.call_args_list]
    assert any("docker-compose.microcks.yml" in f for f in uploaded_filenames)


def test_deploy_uploads_asyncapi_spec(config_dir: Path, mock_ssh) -> None:
    _, sftp = mock_ssh
    deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)
    uploaded_filenames = [call_args[0][1] for call_args in sftp.put.call_args_list]
    assert any("asyncapi.yaml" in f for f in uploaded_filenames)


def test_deploy_runs_docker_compose_up(config_dir: Path, mock_ssh) -> None:
    client, _ = mock_ssh
    deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)
    commands = [c[0][0] for c in client.exec_command.call_args_list]
    assert any("up -d" in cmd for cmd in commands)


# ── error handling ────────────────────────────────────────────────────────────

def test_missing_compose_file_raises_before_ssh(config_dir: Path) -> None:
    (config_dir / "docker-compose.microcks.yml").unlink()
    with pytest.raises(MicrocksDeployError, match="docker-compose.microcks.yml"):
        deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)


def test_missing_asyncapi_file_raises_before_ssh(config_dir: Path) -> None:
    (config_dir / "asyncapi.yaml").unlink()
    with pytest.raises(MicrocksDeployError, match="asyncapi.yaml"):
        deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)


def test_ssh_command_failure_raises_error(config_dir: Path) -> None:
    with patch("deployer_worker.microcks.paramiko.SSHClient") as MockClient:
        client = MagicMock()
        MockClient.return_value = client

        # mkdir fails
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 1
        stdout.read.return_value = b""
        stderr = MagicMock()
        stderr.read.return_value = b"permission denied"
        client.exec_command.return_value = (MagicMock(), stdout, stderr)

        with pytest.raises(MicrocksDeployError, match="exit 1"):
            deploy_microcks("10.0.0.1", "/secrets/key.pem", config_dir)
