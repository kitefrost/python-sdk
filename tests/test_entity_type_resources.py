"""Unit tests for flat per-type entity resource accessors.

Covers project.npcs / places / factions / items / players (create/list/get)
on both Project and AsyncProject. Uses pytest-httpx - no real network.
"""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from kitefrost import AsyncProject, Project

PROJECT_ID = "prj_abc123"
API_KEY = "sk_test_key"
BASE_URL = "http://test.kitefrost.ai"
PROJECT_NAME = "medieval-rpg"

PROJECT_RESPONSE = {"id": PROJECT_ID, "name": PROJECT_NAME, "created_at": "2026-01-01T00:00:00Z"}

# accessor name -> (canonical type, plural path tail)
TYPES = [
    ("npcs", "npc", "npcs"),
    ("places", "location", "locations"),
    ("factions", "faction", "factions"),
    ("items", "item", "items"),
    ("players", "player", "players"),
]


def make_project(httpx_mock: HTTPXMock) -> Project:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects",
        json=PROJECT_RESPONSE,
        status_code=201,
    )
    return Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)


async def make_async_project(httpx_mock: HTTPXMock) -> AsyncProject:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects",
        json=PROJECT_RESPONSE,
        status_code=201,
    )
    project = AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
    await project.init()
    return project


def last_body(httpx_mock: HTTPXMock) -> dict:
    return json.loads(httpx_mock.get_requests()[-1].content)


def entity_response(external_id: str, name: str) -> dict:
    return {
        "id": "ent_001",
        "project_id": PROJECT_ID,
        "external_id": external_id,
        "name": name,
        "properties": {},
    }


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accessor,canonical,plural", TYPES)
def test_resource_create(httpx_mock: HTTPXMock, accessor: str, canonical: str, plural: str) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/{plural}",
        json=entity_response("ent-1", "Gideon"),
    )
    resource = getattr(project, accessor)
    entity = resource.create("ent-1", name="Gideon", mood="gruff")

    assert entity.external_id == "ent-1"
    body = last_body(httpx_mock)
    assert body == {
        "external_id": "ent-1",
        "name": "Gideon",
        "properties": {"mood": "gruff"},
    }


@pytest.mark.parametrize("accessor,canonical,plural", TYPES)
def test_resource_list(httpx_mock: HTTPXMock, accessor: str, canonical: str, plural: str) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/{plural}",
        json={"items": []},
    )
    result = getattr(project, accessor).list()

    assert result == {"items": []}
    assert httpx_mock.get_requests()[-1].method == "GET"


@pytest.mark.parametrize("accessor,canonical,plural", TYPES)
def test_resource_get(httpx_mock: HTTPXMock, accessor: str, canonical: str, plural: str) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/{plural}/ent-1",
        json=entity_response("ent-1", "Gideon"),
    )
    result = getattr(project, accessor).get("ent-1")

    assert result["external_id"] == "ent-1"
    assert httpx_mock.get_requests()[-1].method == "GET"


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("accessor,canonical,plural", TYPES)
async def test_async_resource_create(
    httpx_mock: HTTPXMock, accessor: str, canonical: str, plural: str
) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/{plural}",
        json=entity_response("ent-1", "Gideon"),
    )
    entity = await getattr(project, accessor).create("ent-1", name="Gideon", mood="gruff")

    assert entity.external_id == "ent-1"
    body = last_body(httpx_mock)
    assert body == {
        "external_id": "ent-1",
        "name": "Gideon",
        "properties": {"mood": "gruff"},
    }
    await project.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("accessor,canonical,plural", TYPES)
async def test_async_resource_list(
    httpx_mock: HTTPXMock, accessor: str, canonical: str, plural: str
) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/{plural}",
        json={"items": []},
    )
    result = await getattr(project, accessor).list()

    assert result == {"items": []}
    assert httpx_mock.get_requests()[-1].method == "GET"
    await project.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("accessor,canonical,plural", TYPES)
async def test_async_resource_get(
    httpx_mock: HTTPXMock, accessor: str, canonical: str, plural: str
) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/{plural}/ent-1",
        json=entity_response("ent-1", "Gideon"),
    )
    result = await getattr(project, accessor).get("ent-1")

    assert result["external_id"] == "ent-1"
    assert httpx_mock.get_requests()[-1].method == "GET"
    await project.close()
