"""Unit tests for the authoring-core SDK methods.

Uses pytest-httpx to intercept httpx requests - no real network calls.
Mirrors the mocked-HTTP pattern in test_sdk.py, with sync + async parity.
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

NOTE_RESPONSE = {
    "id": "note_001",
    "project_id": PROJECT_ID,
    "title": "Plot hook",
    "body": "The duke is missing.",
    "note_type": "lore",
    "pinned": False,
    "tags": ["mystery"],
}

QUEST_RESPONSE = {
    "id": "quest_001",
    "project_id": PROJECT_ID,
    "title": "Find the duke",
    "status": "offered",
}

CHECKPOINT_RESPONSE = {
    "id": "chk_001",
    "project_id": PROJECT_ID,
    "name": "before-dragon-fight",
}


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


# ---------------------------------------------------------------------------
# Notes - sync
# ---------------------------------------------------------------------------


def test_create_note(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes",
        json=NOTE_RESPONSE,
        status_code=201,
    )
    note = project.create_note("Plot hook", body="The duke is missing.", note_type="lore",
                               tags=["mystery"])
    assert note["id"] == "note_001"
    body = last_body(httpx_mock)
    assert body["title"] == "Plot hook"
    assert body["body"] == "The duke is missing."
    assert body["note_type"] == "lore"
    assert body["pinned"] is False
    assert body["tags"] == ["mystery"]


def test_list_notes(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes",
        json=[NOTE_RESPONSE],
        status_code=200,
    )
    notes = project.list_notes()
    assert isinstance(notes, list)
    assert notes[0]["id"] == "note_001"


def test_get_note(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes/note_001",
        json=NOTE_RESPONSE,
        status_code=200,
    )
    note = project.get_note("note_001")
    assert note["id"] == "note_001"


def test_update_note(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="PATCH",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes/note_001",
        json={**NOTE_RESPONSE, "pinned": True},
        status_code=200,
    )
    note = project.update_note("note_001", pinned=True)
    assert note["pinned"] is True
    assert last_body(httpx_mock) == {"pinned": True}


def test_delete_note(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes/note_001",
        status_code=204,
    )
    assert project.delete_note("note_001") is None
    request = httpx_mock.get_requests()[-1]
    assert request.method == "DELETE"
    assert str(request.url).endswith(f"/v1/projects/{PROJECT_ID}/notes/note_001")


# ---------------------------------------------------------------------------
# Quests - sync
# ---------------------------------------------------------------------------


def test_create_quest(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/quests",
        json=QUEST_RESPONSE,
        status_code=201,
    )
    quest = project.create_quest("Find the duke", summary="He vanished.", npc_id="duke")
    assert quest["id"] == "quest_001"
    body = last_body(httpx_mock)
    assert body["title"] == "Find the duke"
    assert body["summary"] == "He vanished."
    assert body["status"] == "offered"
    assert body["npc_id"] == "duke"


def test_list_quests(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/quests",
        json=[QUEST_RESPONSE],
        status_code=200,
    )
    quests = project.list_quests()
    assert quests[0]["id"] == "quest_001"


# Pack-catalogue / selector-prompt SDK methods were removed (pack discovery is
# an AI-agent REST/MCP concern, not part of the human dev-time SDK), so there
# are no list_packs / packs_selector_prompt tests here.


# ---------------------------------------------------------------------------
# Feedback - sync
# ---------------------------------------------------------------------------


def test_submit_feedback(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/feedback",
        json={"feedback_id": "fb_001", "received_at": "2026-01-01T00:00:00Z"},
        status_code=202,
    )
    result = project.submit_feedback("bug_report", {"text": "broken"}, context={"page": "x"})
    assert result["feedback_id"] == "fb_001"
    body = last_body(httpx_mock)
    assert body["schema_version"] == "1"
    assert body["signal"] == "bug_report"
    assert body["payload"] == {"text": "broken"}
    assert body["context"] == {"page": "x"}


def test_feedback_schema(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/feedback/schema.json",
        json={"schema_version": "1"},
        status_code=200,
    )
    schema = project.feedback_schema()
    assert schema["schema_version"] == "1"


# ---------------------------------------------------------------------------
# Import / continuity / export - sync
# ---------------------------------------------------------------------------


def test_import_vtt(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/import/vtt",
        json={"entities": []},
        status_code=200,
    )
    result = project.import_vtt("foundry", {"actors": []})
    assert result == {"entities": []}
    body = last_body(httpx_mock)
    assert body["format"] == "foundry"
    assert body["payload"] == {"actors": []}


def test_check_continuity(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/game-narrative/continuity/check",
        json={"findings": [], "generated_at": "2026-01-01T00:00:00Z"},
        status_code=200,
    )
    report = project.check_continuity()
    assert report["findings"] == []
    assert last_body(httpx_mock) == {}


def test_export(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/export",
        json={"format": "ink", "content": "=== start ===", "pack_name": "game-narrative",
              "entity_id": None, "warnings": []},
        status_code=200,
    )
    result = project.export("ink")
    assert result["format"] == "ink"
    body = last_body(httpx_mock)
    assert body["format"] == "ink"
    assert body["entity_id"] is None
    assert body["options"] is None


def test_export_full(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/export/full",
        content=b"PK\x03\x04zipbytes",
        status_code=200,
    )
    data = project.export_full()
    assert data == b"PK\x03\x04zipbytes"


# ---------------------------------------------------------------------------
# Checkpoints - sync
# ---------------------------------------------------------------------------


def test_checkpoint(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/checkpoints",
        json=CHECKPOINT_RESPONSE,
        status_code=201,
    )
    chk = project.checkpoint("before-dragon-fight", description="pre-boss")
    assert chk["id"] == "chk_001"
    body = last_body(httpx_mock)
    assert body["name"] == "before-dragon-fight"
    assert body["description"] == "pre-boss"


def test_checkpoints(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/checkpoints?limit=50&offset=0",
        json={"checkpoints": [CHECKPOINT_RESPONSE], "total": 1},
        status_code=200,
    )
    result = project.checkpoints()
    assert result["total"] == 1


def test_restore(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/checkpoints/chk_001/restore",
        json={"checkpoint_id": "chk_001", "events_reverted": 3},
        status_code=200,
    )
    result = project.restore("chk_001")
    assert result["events_reverted"] == 3
    assert last_body(httpx_mock) == {}


# ---------------------------------------------------------------------------
# Async parity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_create_note(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes",
        json=NOTE_RESPONSE,
        status_code=201,
    )
    note = await project.create_note("Plot hook")
    assert note["id"] == "note_001"
    await project.close()


@pytest.mark.asyncio
async def test_async_list_notes(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes",
        json=[NOTE_RESPONSE],
        status_code=200,
    )
    notes = await project.list_notes()
    assert notes[0]["id"] == "note_001"
    await project.close()


@pytest.mark.asyncio
async def test_async_get_note(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes/note_001",
        json=NOTE_RESPONSE,
        status_code=200,
    )
    note = await project.get_note("note_001")
    assert note["id"] == "note_001"
    await project.close()


@pytest.mark.asyncio
async def test_async_update_note(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="PATCH",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes/note_001",
        json={**NOTE_RESPONSE, "pinned": True},
        status_code=200,
    )
    note = await project.update_note("note_001", pinned=True)
    assert note["pinned"] is True
    await project.close()


@pytest.mark.asyncio
async def test_async_delete_note(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/notes/note_001",
        status_code=204,
    )
    assert await project.delete_note("note_001") is None
    await project.close()


@pytest.mark.asyncio
async def test_async_create_quest(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/quests",
        json=QUEST_RESPONSE,
        status_code=201,
    )
    quest = await project.create_quest("Find the duke")
    assert quest["id"] == "quest_001"
    await project.close()


@pytest.mark.asyncio
async def test_async_list_quests(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/quests",
        json=[QUEST_RESPONSE],
        status_code=200,
    )
    quests = await project.list_quests()
    assert quests[0]["id"] == "quest_001"
    await project.close()


@pytest.mark.asyncio
async def test_async_submit_feedback(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/feedback",
        json={"feedback_id": "fb_001", "received_at": "2026-01-01T00:00:00Z"},
        status_code=202,
    )
    result = await project.submit_feedback("quality_rating", {"score": 5})
    assert result["feedback_id"] == "fb_001"
    await project.close()


@pytest.mark.asyncio
async def test_async_feedback_schema(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/feedback/schema.json",
        json={"schema_version": "1"},
        status_code=200,
    )
    schema = await project.feedback_schema()
    assert schema["schema_version"] == "1"
    await project.close()


@pytest.mark.asyncio
async def test_async_import_vtt(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/import/vtt",
        json={"entities": []},
        status_code=200,
    )
    result = await project.import_vtt("roll20", {"actors": []})
    assert result == {"entities": []}
    await project.close()


@pytest.mark.asyncio
async def test_async_check_continuity(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/game-narrative/continuity/check",
        json={"findings": [], "generated_at": "2026-01-01T00:00:00Z"},
        status_code=200,
    )
    report = await project.check_continuity()
    assert report["findings"] == []
    await project.close()


@pytest.mark.asyncio
async def test_async_export(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/export",
        json={"format": "yarn", "content": "title: start", "pack_name": "game-narrative",
              "entity_id": None, "warnings": []},
        status_code=200,
    )
    result = await project.export("yarn")
    assert result["format"] == "yarn"
    await project.close()


@pytest.mark.asyncio
async def test_async_export_full(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/export/full",
        content=b"PK\x03\x04zipbytes",
        status_code=200,
    )
    data = await project.export_full()
    assert data == b"PK\x03\x04zipbytes"
    await project.close()


@pytest.mark.asyncio
async def test_async_checkpoint(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/checkpoints",
        json=CHECKPOINT_RESPONSE,
        status_code=201,
    )
    chk = await project.checkpoint("before-dragon-fight")
    assert chk["id"] == "chk_001"
    await project.close()


@pytest.mark.asyncio
async def test_async_checkpoints(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/checkpoints?limit=50&offset=0",
        json={"checkpoints": [CHECKPOINT_RESPONSE], "total": 1},
        status_code=200,
    )
    result = await project.checkpoints()
    assert result["total"] == 1
    await project.close()


@pytest.mark.asyncio
async def test_async_restore(httpx_mock: HTTPXMock) -> None:
    project = await make_async_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/checkpoints/chk_001/restore",
        json={"checkpoint_id": "chk_001", "events_reverted": 3},
        status_code=200,
    )
    result = await project.restore("chk_001")
    assert result["events_reverted"] == 3
    await project.close()
