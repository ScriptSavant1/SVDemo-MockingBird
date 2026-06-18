"""GitLab API client for the deployer-worker.

Used to trigger Kaniko Docker image builds via GitLab CI pipelines on the
shared stub-builder project. The deployer-worker passes the S3 key of the
generated stub-engine.zip and a target image tag as pipeline variables.

The stub-builder project's .gitlab-ci.yml downloads the zip from S3,
runs Kaniko to build the image, and pushes it to GitLab Container Registry.
"""
from __future__ import annotations

import time
from typing import Optional

import requests


class GitLabError(Exception):
    pass


TERMINAL_STATUSES = {"success", "failed", "canceled", "skipped"}


class GitLabClient:
    def __init__(self, url: str, token: str, timeout: int = 30):
        self._base = url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"PRIVATE-TOKEN": token})
        self._timeout = timeout

    def trigger_pipeline(
        self,
        project_id: str,
        ref: str = "main",
        variables: Optional[dict[str, str]] = None,
    ) -> str:
        """Trigger a pipeline on the stub-builder project. Returns pipeline ID."""
        payload: dict = {"ref": ref}
        if variables:
            payload["variables"] = [{"key": k, "value": v} for k, v in variables.items()]

        resp = self._session.post(
            f"{self._base}/api/v4/projects/{project_id}/pipeline",
            json=payload,
            timeout=self._timeout,
        )
        if not resp.ok:
            raise GitLabError(f"GitLab API error {resp.status_code}: {resp.text}")
        return str(resp.json()["id"])

    def get_pipeline_status(self, project_id: str, pipeline_id: str) -> str:
        """Return the pipeline's current status string."""
        resp = self._session.get(
            f"{self._base}/api/v4/projects/{project_id}/pipelines/{pipeline_id}",
            timeout=self._timeout,
        )
        if not resp.ok:
            raise GitLabError(f"GitLab API error {resp.status_code}: {resp.text}")
        return resp.json()["status"]

    def wait_for_pipeline(
        self,
        project_id: str,
        pipeline_id: str,
        timeout_seconds: int = 600,
        poll_interval: int = 15,
    ) -> str:
        """Poll until the pipeline reaches a terminal status. Returns final status."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status = self.get_pipeline_status(project_id, pipeline_id)
            if status in TERMINAL_STATUSES:
                return status
            time.sleep(poll_interval)
        return "timeout"
