"""Sprint 19 — metrics/reports endpoints tests.

Covers:
  GET  /api/v1/projects/{project_id}/deployments/{deployment_id}/reports
    — returns REPORT jobs for the deployment, newest first
    — returns empty list when no reports exist
    — 404 for unknown deployment
  GET  /api/v1/jobs/{job_id}/download?format=pdf|excel|ppt
    — 400 if job is not a REPORT type
    — 400 if job status is not DONE
    — 404 if S3 key absent from result
    — 200 with presigned URL when job is DONE and key exists
  POST /api/v1/projects/{project_id}/deployments/{deployment_id}/report
    — verifies deployment_id is persisted on the Job record
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from project_service.models import Deployment, Job, Project, Stub, User


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_project(db_session, user: User) -> Project:
    p = Project(name="Test Project", team="QA", created_by=user.id)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _make_stub(db_session, project: Project) -> Stub:
    s = Stub(project_id=project.id, name="Payment API", format="level-1-txt",
             source_file_key="stubs/key.txt", generated_at=datetime.now(timezone.utc))
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _make_deployment(db_session, project: Project, stub: Stub, status: str = "LIVE") -> Deployment:
    d = Deployment(project_id=project.id, stub_id=stub.id, status=status, target_type="AWS",
                   stub_url="https://stub.internal:8080")
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def _make_report_job(
    db_session,
    project: Project,
    deployment: Deployment,
    status: str = "DONE",
    result: dict | None = None,
    created_at: datetime | None = None,
) -> Job:
    j = Job(
        type="REPORT",
        status=status,
        project_id=project.id,
        stub_id=deployment.stub_id,
        deployment_id=deployment.id,
        payload={"deployment_id": str(deployment.id), "report_period_hours": 24},
        result=result,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(j)
    db_session.commit()
    db_session.refresh(j)
    return j


# ── list_reports ───────────────────────────────────────────────────────────────

class TestListReports:
    def test_returns_report_jobs_newest_first(self, sv_client, db_session, sv_user):
        from datetime import timedelta
        p = _make_project(db_session, sv_user)
        s = _make_stub(db_session, p)
        d = _make_deployment(db_session, p, s)
        now = datetime.now(timezone.utc)

        j1 = _make_report_job(db_session, p, d, status="DONE", created_at=now - timedelta(minutes=5))
        j2 = _make_report_job(db_session, p, d, status="QUEUED", created_at=now)

        resp = sv_client.get(f"/api/v1/projects/{p.id}/deployments/{d.id}/reports")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        # j2 was created after j1, so should appear first (newest first)
        assert str(j2.id) == ids[0]
        assert str(j1.id) == ids[1]

    def test_returns_empty_list_when_no_reports(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        s = _make_stub(db_session, p)
        d = _make_deployment(db_session, p, s)

        resp = sv_client.get(f"/api/v1/projects/{p.id}/deployments/{d.id}/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_404_for_unknown_deployment(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        unknown_id = uuid.uuid4()
        resp = sv_client.get(f"/api/v1/projects/{p.id}/deployments/{unknown_id}/reports")
        assert resp.status_code == 404

    def test_does_not_return_non_report_jobs(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        s = _make_stub(db_session, p)
        d = _make_deployment(db_session, p, s)

        deploy_job = Job(
            type="DEPLOY", status="DONE", project_id=p.id, stub_id=s.id,
            deployment_id=d.id, payload={},
        )
        db_session.add(deploy_job)
        db_session.commit()

        resp = sv_client.get(f"/api/v1/projects/{p.id}/deployments/{d.id}/reports")
        assert resp.status_code == 200
        assert resp.json() == []


# ── download_report ────────────────────────────────────────────────────────────

class TestDownloadReport:
    def test_400_when_not_a_report_job(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        parse_job = Job(type="PARSE", status="DONE", project_id=p.id, payload={})
        db_session.add(parse_job)
        db_session.commit()

        resp = sv_client.get(f"/api/v1/jobs/{parse_job.id}/download?format=pdf")
        assert resp.status_code == 400

    def test_400_when_job_not_done(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        s = _make_stub(db_session, p)
        d = _make_deployment(db_session, p, s)
        j = _make_report_job(db_session, p, d, status="RUNNING")

        resp = sv_client.get(f"/api/v1/jobs/{j.id}/download?format=pdf")
        assert resp.status_code == 400

    def test_404_when_s3_key_absent(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        s = _make_stub(db_session, p)
        d = _make_deployment(db_session, p, s)
        j = _make_report_job(db_session, p, d, status="DONE",
                             result={"pdf_key": None, "excel_key": None, "ppt_key": None})

        resp = sv_client.get(f"/api/v1/jobs/{j.id}/download?format=pdf")
        assert resp.status_code == 404

    def test_returns_presigned_url_for_done_job(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        s = _make_stub(db_session, p)
        d = _make_deployment(db_session, p, s)
        j = _make_report_job(db_session, p, d, status="DONE",
                             result={"pdf_key": "stubs/proj/dep/report.pdf",
                                     "excel_key": "stubs/proj/dep/report.xlsx",
                                     "ppt_key": "stubs/proj/dep/report.pptx"})

        fake_url = "https://s3.amazonaws.com/bucket/stubs/proj/dep/report.pdf?X-Amz-Signature=abc"
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = fake_url

        with patch("project_service.routers.jobs.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3
            resp = sv_client.get(f"/api/v1/jobs/{j.id}/download?format=pdf")

        assert resp.status_code == 200
        body = resp.json()
        assert body["url"] == fake_url
        assert body["format"] == "pdf"
        assert body["expires_in_seconds"] == 900

    def test_422_for_invalid_format(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        resp = sv_client.get(f"/api/v1/jobs/{uuid.uuid4()}/download?format=csv")
        assert resp.status_code == 422


# ── trigger_report stores deployment_id ───────────────────────────────────────

class TestTriggerReportStoresDeploymentId:
    def test_deployment_id_persisted_on_job(self, sv_client, db_session, sv_user):
        p = _make_project(db_session, sv_user)
        s = _make_stub(db_session, p)
        d = _make_deployment(db_session, p, s, status="LIVE")

        with patch("project_service.routers.deploy.get_sqs_client"):
            resp = sv_client.post(f"/api/v1/projects/{p.id}/deployments/{d.id}/report")

        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        job = db_session.get(Job, uuid.UUID(job_id))
        assert job is not None
        assert job.deployment_id == d.id
