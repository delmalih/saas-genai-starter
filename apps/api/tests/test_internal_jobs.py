import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from src.core.config import get_settings
from src.core.queue import CloudTasksQueue
from src.domains.jobs.router import JOB_HANDLERS, verify_internal_job_token

PAYLOAD = {"document_id": "d-1", "tenant_id": "t-1", "user_id": "u-1"}


@pytest.fixture
def jobs_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(
        settings, "jobs_service_account_email", "queue@demo.iam.gserviceaccount.com"
    )
    monkeypatch.setattr(settings, "internal_jobs_base_url", "https://api.demo.example")


async def test_missing_token_is_403(client: httpx.AsyncClient, jobs_configured: None) -> None:
    response = await client.post("/internal/jobs/ingest_document_job", json=PAYLOAD)
    assert response.status_code == 403


async def test_garbage_token_is_403(client: httpx.AsyncClient, jobs_configured: None) -> None:
    response = await client.post(
        "/internal/jobs/ingest_document_job",
        json=PAYLOAD,
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 403


async def test_unconfigured_endpoint_is_403_even_with_token(
    client: httpx.AsyncClient,
) -> None:
    # No JOBS_SERVICE_ACCOUNT_EMAIL configured (local default) → closed.
    response = await client.post(
        "/internal/jobs/ingest_document_job",
        json=PAYLOAD,
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 403


async def test_valid_token_runs_the_job(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    jobs_configured: None,
) -> None:
    app.dependency_overrides[verify_internal_job_token] = lambda: None
    calls: list[dict[str, Any]] = []

    async def fake_job(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setitem(JOB_HANDLERS, "ingest_document_job", fake_job)

    response = await client.post("/internal/jobs/ingest_document_job", json=PAYLOAD)
    assert response.status_code == 200
    assert calls == [PAYLOAD]


async def test_unknown_job_is_404(client: httpx.AsyncClient, app: FastAPI) -> None:
    app.dependency_overrides[verify_internal_job_token] = lambda: None
    response = await client.post("/internal/jobs/nuke_everything", json={})
    assert response.status_code == 404


async def test_cloud_tasks_queue_builds_the_push_task(
    monkeypatch: pytest.MonkeyPatch, jobs_configured: None
) -> None:
    settings = get_settings()
    monkeypatch.setattr(
        settings, "cloud_tasks_queue", "projects/demo/locations/us-east1/queues/jobs"
    )
    created: list[dict[str, Any]] = []

    class FakeClient:
        def create_task(self, parent: str, task: dict[str, Any]) -> None:
            created.append({"parent": parent, "task": task})

    queue = CloudTasksQueue(client=FakeClient())
    await queue.enqueue("ingest_document_job", **PAYLOAD)

    assert created[0]["parent"] == "projects/demo/locations/us-east1/queues/jobs"
    http_request = created[0]["task"]["http_request"]
    assert http_request["url"] == "https://api.demo.example/internal/jobs/ingest_document_job"
    assert json.loads(http_request["body"]) == PAYLOAD
    oidc = http_request["oidc_token"]
    assert oidc["service_account_email"] == "queue@demo.iam.gserviceaccount.com"
    assert oidc["audience"] == "https://api.demo.example"
