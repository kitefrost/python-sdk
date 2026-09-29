"""Unit tests for job queue methods on Project and AsyncProject.

Uses pytest-httpx to intercept httpx requests - no real network calls.
"""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

import kitefrost
from kitefrost import AsyncProject, Job, Project
from kitefrost.exceptions import ServerError

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PROJECT_ID = "prj_abc123"
API_KEY = "sk_test_key"
BASE_URL = "http://test.kitefrost.ai"
PROJECT_NAME = "medieval-rpg"

PROJECT_RESPONSE = {"id": PROJECT_ID, "name": PROJECT_NAME, "created_at": "2026-01-01T00:00:00Z"}

JOB_QUEUED = {
    "id": "job_001",
    "status": "queued",
    "project_id": PROJECT_ID,
    "type": "generate",
    "result": None,
    "error": None,
    "created_at": "2026-01-01T00:00:00Z",
    "completed_at": None,
}

JOB_COMPLETED = {
    **JOB_QUEUED,
    "status": "completed",
    "result": {"text": "Ah, the Dragon Slayer returns!"},
    "completed_at": "2026-01-01T00:00:05Z",
}

JOB_FAILED = {
    **JOB_QUEUED,
    "status": "failed",
    "error": "LLM quota exceeded",
    "completed_at": "2026-01-01T00:00:03Z",
}

JOB_CANCELLED = {
    **JOB_QUEUED,
    "status": "cancelled",
    "completed_at": "2026-01-01T00:00:02Z",
}


def make_project(httpx_mock: HTTPXMock) -> Project:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    return Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------


def test_job_from_dict_complete() -> None:
    job = Job._from_dict(JOB_COMPLETED)
    assert job.id == "job_001"
    assert job.status == "completed"
    assert job.project_id == PROJECT_ID
    assert job.type == "generate"
    assert job.result == {"text": "Ah, the Dragon Slayer returns!"}
    assert job.error is None
    assert job.created_at == "2026-01-01T00:00:00Z"
    assert job.completed_at == "2026-01-01T00:00:05Z"


def test_job_from_dict_minimal() -> None:
    """_from_dict handles missing optional fields gracefully."""
    job = Job._from_dict(
        {"id": "j1", "status": "queued", "project_id": "prj_1", "type": "generate"}
    )
    assert job.id == "j1"
    assert job.result is None
    assert job.error is None
    assert job.created_at is None
    assert job.completed_at is None


def test_job_exported_from_package() -> None:
    assert kitefrost.Job is Job


# ---------------------------------------------------------------------------
# Sync Project - submit_job()
# ---------------------------------------------------------------------------


def test_submit_job_posts_to_project_generate(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=JOB_QUEUED,
        status_code=202,
    )
    job = project.submit_job(PROJECT_ID, prompt="Player returns after slaying dragon")
    assert isinstance(job, Job)
    assert job.id == "job_001"
    assert job.status == "queued"
    assert job.type == "generate"


def test_submit_job_sends_correct_payload(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=JOB_QUEUED,
        status_code=202,
    )
    project.submit_job(
        PROJECT_ID, type="summarise", prompt="Summarise quest progress", entity_id="ent_001"
    )
    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["type"] == "summarise"
    assert body["prompt"] == "Summarise quest progress"
    assert body["entity_id"] == "ent_001"


def test_submit_job_default_type_is_generate(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=JOB_QUEUED,
        status_code=202,
    )
    project.submit_job(PROJECT_ID, prompt="hello")
    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["type"] == "generate"


# ---------------------------------------------------------------------------
# Sync Project - get_job()
# ---------------------------------------------------------------------------


def test_get_job_returns_job(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json=JOB_COMPLETED,
        status_code=200,
    )
    job = project.get_job("job_001")
    assert isinstance(job, Job)
    assert job.id == "job_001"
    assert job.status == "completed"
    assert job.result == {"text": "Ah, the Dragon Slayer returns!"}


def test_get_job_failed_status(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json=JOB_FAILED,
        status_code=200,
    )
    job = project.get_job("job_001")
    assert job.status == "failed"
    assert job.error == "LLM quota exceeded"


# ---------------------------------------------------------------------------
# Sync Project - list_jobs()
# ---------------------------------------------------------------------------


def test_list_jobs_default_params(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs?limit=20&offset=0",
        json={"jobs": [JOB_QUEUED, JOB_COMPLETED]},
        status_code=200,
    )
    jobs = project.list_jobs()
    assert len(jobs) == 2
    assert all(isinstance(j, Job) for j in jobs)
    assert jobs[0].status == "queued"
    assert jobs[1].status == "completed"


def test_list_jobs_with_status_filter(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs?limit=10&offset=5&status=completed",
        json={"jobs": [JOB_COMPLETED]},
        status_code=200,
    )
    jobs = project.list_jobs(limit=10, offset=5, status="completed")
    assert len(jobs) == 1
    assert jobs[0].status == "completed"


def test_list_jobs_empty(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs?limit=20&offset=0",
        json={"jobs": []},
        status_code=200,
    )
    jobs = project.list_jobs()
    assert jobs == []


# ---------------------------------------------------------------------------
# Sync Project - cancel_job()
# ---------------------------------------------------------------------------


def test_cancel_job_returns_cancelled(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json=JOB_CANCELLED,
        status_code=200,
    )
    job = project.cancel_job("job_001")
    assert isinstance(job, Job)
    assert job.status == "cancelled"


def test_cancel_job_sends_delete(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/v1/jobs/job_999",
        json={**JOB_CANCELLED, "id": "job_999"},
        status_code=200,
    )
    project.cancel_job("job_999")
    requests = httpx_mock.get_requests()
    delete_reqs = [r for r in requests if r.method == "DELETE"]
    assert len(delete_reqs) == 1
    assert "/v1/jobs/job_999" in str(delete_reqs[0].url)


# ---------------------------------------------------------------------------
# Sync Project - poll_job()
# ---------------------------------------------------------------------------


def test_poll_job_returns_immediately_if_terminal(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json=JOB_COMPLETED,
        status_code=200,
    )
    job = project.poll_job("job_001", interval=0.01, timeout=5.0)
    assert job.status == "completed"


def test_poll_job_polls_until_complete(httpx_mock: HTTPXMock) -> None:
    """poll_job retries when status is non-terminal."""
    project = make_project(httpx_mock)
    # First two calls return queued/processing, third returns completed
    for status in ("queued", "processing"):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/v1/jobs/job_001",
            json={**JOB_QUEUED, "status": status},
            status_code=200,
        )
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json=JOB_COMPLETED,
        status_code=200,
    )
    job = project.poll_job("job_001", interval=0.01, timeout=5.0)
    assert job.status == "completed"
    # Verify three GET /v1/jobs/job_001 requests were made
    get_jobs = [r for r in httpx_mock.get_requests() if "/v1/jobs/" in str(r.url)]
    assert len(get_jobs) == 3


def test_poll_job_returns_on_failed(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json=JOB_FAILED,
        status_code=200,
    )
    job = project.poll_job("job_001", interval=0.01, timeout=5.0)
    assert job.status == "failed"


@pytest.mark.httpx_mock(can_send_already_matched_responses=True)
def test_poll_job_timeout(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    # Always return processing - reused on every poll
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json={**JOB_QUEUED, "status": "processing"},
        status_code=200,
    )
    with pytest.raises(TimeoutError, match="job_001"):
        project.poll_job("job_001", interval=0.01, timeout=0.05)


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


def test_get_job_propagates_server_error(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/jobs/job_001",
        json={"detail": "Internal error"},
        status_code=500,
    )
    with pytest.raises(ServerError):
        project.get_job("job_001")


# ---------------------------------------------------------------------------
# Async Project - job methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_submit_job(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    await project.init()

    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=JOB_QUEUED,
        status_code=202,
    )
    job = await project.submit_job(PROJECT_ID, prompt="Player returns after slaying dragon")
    assert isinstance(job, Job)
    assert job.status == "queued"
    await project.close()


@pytest.mark.asyncio
async def test_async_get_job(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    async with AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        await project.init()
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/v1/jobs/job_001",
            json=JOB_COMPLETED,
            status_code=200,
        )
        job = await project.get_job("job_001")
    assert job.status == "completed"
    assert job.result == {"text": "Ah, the Dragon Slayer returns!"}


@pytest.mark.asyncio
async def test_async_list_jobs(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    async with AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        await project.init()
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/v1/jobs?limit=20&offset=0",
            json={"jobs": [JOB_QUEUED, JOB_COMPLETED]},
            status_code=200,
        )
        jobs = await project.list_jobs()
    assert len(jobs) == 2
    assert jobs[0].status == "queued"


@pytest.mark.asyncio
async def test_async_list_jobs_with_filter(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    async with AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        await project.init()
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/v1/jobs?limit=5&offset=0&status=failed",
            json={"jobs": [JOB_FAILED]},
            status_code=200,
        )
        jobs = await project.list_jobs(limit=5, status="failed")
    assert len(jobs) == 1
    assert jobs[0].status == "failed"


@pytest.mark.asyncio
async def test_async_cancel_job(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    async with AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        await project.init()
        httpx_mock.add_response(
            method="DELETE",
            url=f"{BASE_URL}/v1/jobs/job_001",
            json=JOB_CANCELLED,
            status_code=200,
        )
        job = await project.cancel_job("job_001")
    assert job.status == "cancelled"


@pytest.mark.asyncio
async def test_async_poll_job_completes(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    async with AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        await project.init()
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/v1/jobs/job_001",
            json={**JOB_QUEUED, "status": "processing"},
            status_code=200,
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/v1/jobs/job_001",
            json=JOB_COMPLETED,
            status_code=200,
        )
        job = await project.poll_job("job_001", interval=0.01, timeout=5.0)
    assert job.status == "completed"


@pytest.mark.asyncio
@pytest.mark.httpx_mock(can_send_already_matched_responses=True)
async def test_async_poll_job_timeout(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    async with AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        await project.init()
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/v1/jobs/job_001",
            json={**JOB_QUEUED, "status": "processing"},
            status_code=200,
        )
        with pytest.raises(TimeoutError, match="job_001"):
            await project.poll_job("job_001", interval=0.01, timeout=0.05)
