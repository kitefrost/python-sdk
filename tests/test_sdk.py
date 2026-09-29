"""Unit tests for the kitefrost Python SDK.

Uses pytest-httpx to intercept httpx requests - no real network calls.
"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

import kitefrost
from kitefrost import (
    AsyncProject,
    AuthError,
    Project,
    ProjectNotFound,
    RateLimited,
    ServerError,
)
from kitefrost.models import ContextResult, Entity, Event, GenerateResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = "prj_abc123"
API_KEY = "sk_test_key"
BASE_URL = "http://test.kitefrost.ai"
PROJECT_NAME = "medieval-rpg"

PROJECT_RESPONSE = {"id": PROJECT_ID, "name": PROJECT_NAME, "created_at": "2026-01-01T00:00:00Z"}

ENTITY_RESPONSE = {
    "id": "ent_xyz789",
    "external_id": "blacksmith",
    "project_id": PROJECT_ID,
    "type": "npc",
    "name": "Gideon",
    "properties": {"personality": "gruff but kind"},
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

EVENT_RESPONSE = {
    "id": "evt_001",
    "project_id": PROJECT_ID,
    "type": "player.bought_sword",
    "entity_id": "ent_xyz789",
    "player_id": "alice",
    "data": {"details": "haggled to 35 gold"},
    "created_at": "2026-01-01T00:00:00Z",
}

CONTEXT_RESPONSE = {
    "entity": {"name": "Gideon", "role": "merchant"},
    "relevant_events": [{"type": "player.bought_sword", "data": {}}],
    "facts": [],
    "summary": "Gideon has met alice once.",
}

GENERATE_RESPONSE = {
    "content": "Ah, the Dragon Slayer returns!",
    "context_used": {"events_referenced": 1},
    "tokens_used": {"input": 200, "output": 30},
}


def make_project(httpx_mock: HTTPXMock) -> Project:
    """Helper: create a Project with a mocked POST /v1/projects call."""
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects",
        json=PROJECT_RESPONSE,
        status_code=201,
    )
    return Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)


# ---------------------------------------------------------------------------
# Sync Project - construction
# ---------------------------------------------------------------------------


def test_project_creates_on_init(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    assert project._project_id == PROJECT_ID


def test_project_no_auto_create(httpx_mock: HTTPXMock) -> None:
    """auto_create=False skips the initial POST."""
    project = Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, auto_create=False)
    assert project._project_id is None
    # No requests should have been made
    assert httpx_mock.get_requests() == []


def test_project_context_manager(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    with Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        assert project._project_id == PROJECT_ID


# ---------------------------------------------------------------------------
# Sync Project - entity()
# ---------------------------------------------------------------------------


def test_entity_upsert(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json=ENTITY_RESPONSE,
        status_code=201,
    )
    entity = project.entity("blacksmith", type="npc", name="Gideon", personality="gruff but kind")
    assert isinstance(entity, Entity)
    assert entity.id == "ent_xyz789"
    assert entity.external_id == "blacksmith"
    assert entity.type == "npc"
    assert entity.name == "Gideon"
    assert entity.properties["personality"] == "gruff but kind"


def test_entity_request_payload(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json=ENTITY_RESPONSE,
        status_code=201,
    )
    project.entity("blacksmith", type="npc", name="Gideon", location="village-square")
    request = httpx_mock.get_requests()[-1]
    import json

    body = json.loads(request.content)
    assert body["external_id"] == "blacksmith"
    # `type` is no longer in the body - the canonical type is encoded
    # in the URL path (/generic/npcs).
    assert "type" not in body
    assert body["name"] == "Gideon"
    assert body["properties"]["location"] == "village-square"


# ---------------------------------------------------------------------------
# Sync Project - graphql() escape hatch
# ---------------------------------------------------------------------------


def test_graphql_escape_hatch(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/graphql",
        json={"data": {"project": {"id": "p1"}}},
        status_code=200,
    )
    out = project.graphql("query($id:String!){project(id:$id){id}}", {"id": "p1"})
    assert out["data"]["project"]["id"] == "p1"

    import json

    request = httpx_mock.get_requests()[-1]
    assert request.url.path == "/v1/graphql"
    body = json.loads(request.content)
    assert body["query"].startswith("query")
    assert body["variables"] == {"id": "p1"}


def test_graphql_omits_variables_when_none(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/graphql", json={"data": {}}, status_code=200
    )
    project.graphql("{ __typename }")

    import json

    body = json.loads(httpx_mock.get_requests()[-1].content)
    assert "variables" not in body


# ---------------------------------------------------------------------------
# Sync Project - event()
# ---------------------------------------------------------------------------


def test_event_records(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/events",
        json=EVENT_RESPONSE,
        status_code=201,
    )
    event = project.event(
        "player.bought_sword", entity="blacksmith", player="alice", details="haggled to 35 gold"
    )
    assert isinstance(event, Event)
    assert event.id == "evt_001"
    assert event.type == "player.bought_sword"


def test_event_accepts_entity_object(httpx_mock: HTTPXMock) -> None:
    """event() accepts an Entity object and uses its external_id."""
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/events",
        json=EVENT_RESPONSE,
        status_code=201,
    )
    entity = Entity._from_dict(ENTITY_RESPONSE)
    project.event("player.bought_sword", entity=entity, player="alice")
    request = httpx_mock.get_requests()[-1]
    import json

    body = json.loads(request.content)
    assert body["entity_id"] == "blacksmith"


def test_event_without_entity_or_player(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    project_event = {
        **EVENT_RESPONSE,
        "type": "project.dragon_slain",
        "entity_id": None,
        "player_id": None,
    }
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/events",
        json=project_event,
        status_code=201,
    )
    event = project.event("project.dragon_slain", details="mountain peak")
    assert event.type == "project.dragon_slain"


# ---------------------------------------------------------------------------
# Sync Project - context()
# ---------------------------------------------------------------------------


def test_context_query(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    # Use a URL-matching callback to avoid strict query-param matching
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/context?query=blacksmith+knowledge&entity_id=ent_xyz789",
        json=CONTEXT_RESPONSE,
        status_code=200,
    )
    ctx = project.context(query="blacksmith knowledge", entity_id="ent_xyz789")
    assert isinstance(ctx, ContextResult)
    assert ctx.summary == "Gideon has met alice once."
    assert ctx.entity["name"] == "Gideon"


# ---------------------------------------------------------------------------
# Sync Project - generate()
# ---------------------------------------------------------------------------


def test_generate_returns_response(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=GENERATE_RESPONSE,
        status_code=200,
    )
    response = project.generate(
        entity="blacksmith", player="alice", prompt="Player returns after slaying dragon"
    )
    assert isinstance(response, GenerateResponse)
    assert response.text == "Ah, the Dragon Slayer returns!"
    assert response.tokens_used["input"] == 200


def test_generate_accepts_entity_object(httpx_mock: HTTPXMock) -> None:
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=GENERATE_RESPONSE,
        status_code=200,
    )
    entity = Entity._from_dict(ENTITY_RESPONSE)
    response = project.generate(entity=entity, player="alice", prompt="Player returns")
    assert response.text == "Ah, the Dragon Slayer returns!"
    import json

    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["entity_id"] == "blacksmith"


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------


def test_auth_error_on_401(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects",
        json={"detail": "Unauthorized"},
        status_code=401,
    )
    with pytest.raises(AuthError) as exc_info:
        Project(PROJECT_NAME, api_key="bad_key", base_url=BASE_URL, report_errors=False)
    assert exc_info.value.status_code == 401


def test_auth_error_on_403(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects",
        json={"detail": "Forbidden"},
        status_code=403,
    )
    with pytest.raises(AuthError):
        Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)


def test_project_not_found_on_404(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json={"detail": "Project not found"},
        status_code=404,
    )
    with pytest.raises(ProjectNotFound):
        project.entity("x", type="npc", name="X")


def test_rate_limited_on_429(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json={"detail": "Too many requests"},
        status_code=429,
        headers={"Retry-After": "10"},
    )
    with pytest.raises(RateLimited) as exc_info:
        project.generate(entity="x", player="alice", prompt="hi")
    assert exc_info.value.retry_after == 10


def test_server_error_on_500(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json={"detail": "Internal server error"},
        status_code=500,
    )
    with pytest.raises(ServerError):
        project.generate(entity="x", player="alice", prompt="hi")


# ---------------------------------------------------------------------------
# Async Project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_project_entity(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    await project.init()

    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json=ENTITY_RESPONSE,
        status_code=201,
    )
    entity = await project.entity("blacksmith", type="npc", name="Gideon")
    assert entity.id == "ent_xyz789"
    await project.close()


@pytest.mark.asyncio
async def test_async_project_generate(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    async with AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL) as project:
        await project.init()
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
            json=GENERATE_RESPONSE,
            status_code=200,
        )
        response = await project.generate(
            entity="blacksmith", player="alice", prompt="Player returns"
        )
    assert response.text == "Ah, the Dragon Slayer returns!"


@pytest.mark.asyncio
async def test_async_project_auth_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects",
        json={"detail": "Unauthorized"},
        status_code=401,
    )
    project = AsyncProject(PROJECT_NAME, api_key="bad_key", base_url=BASE_URL, report_errors=False)
    with pytest.raises(AuthError):
        await project.init()
    await project.close()


# ---------------------------------------------------------------------------
# Hello project pattern smoke test (sync)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Sync Project - convenience methods
# ---------------------------------------------------------------------------


def test_remember(httpx_mock: HTTPXMock) -> None:
    """remember() wraps event() with type='memory' and text in data."""
    project = make_project(httpx_mock)
    remember_response = {
        **EVENT_RESPONSE,
        "type": "memory",
        "data": {"text": "Sold a legendary sword to Alice"},
    }
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/events",
        json=remember_response,
        status_code=201,
    )
    event = project.remember("blacksmith", "Sold a legendary sword to Alice")
    assert isinstance(event, Event)
    # Verify the request payload
    import json

    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["type"] == "memory"
    assert body["entity_id"] == "blacksmith"
    assert body["data"]["text"] == "Sold a legendary sword to Alice"


def test_remember_with_metadata(httpx_mock: HTTPXMock) -> None:
    """remember() passes metadata into the event data."""
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/events",
        json=EVENT_RESPONSE,
        status_code=201,
    )
    project.remember("blacksmith", "Sold a sword", metadata={"importance": "high"})
    import json

    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["data"]["text"] == "Sold a sword"
    assert body["data"]["importance"] == "high"


def test_recall(httpx_mock: HTTPXMock) -> None:
    """recall() wraps context() filtered to one entity."""
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/context?entity_id=blacksmith&limit=5",
        json=CONTEXT_RESPONSE,
        status_code=200,
    )
    ctx = project.recall("blacksmith", limit=5)
    assert isinstance(ctx, ContextResult)
    assert ctx.summary == "Gideon has met alice once."


def test_create_npc(httpx_mock: HTTPXMock) -> None:
    """create_npc() wraps entity() with type='npc' and derived entity_id."""
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json=ENTITY_RESPONSE,
        status_code=201,
    )
    entity = project.create_npc("Gideon the Blacksmith", properties={"personality": "gruff"})
    assert isinstance(entity, Entity)
    import json

    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["external_id"] == "gideon-the-blacksmith"
    # `type` is no longer in the body - it's encoded in the URL path.
    assert "type" not in body
    assert body["name"] == "Gideon the Blacksmith"
    assert body["properties"]["personality"] == "gruff"


def test_create_npc_no_properties(httpx_mock: HTTPXMock) -> None:
    """create_npc() works without properties."""
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json=ENTITY_RESPONSE,
        status_code=201,
    )
    entity = project.create_npc("Gideon")
    assert isinstance(entity, Entity)
    import json

    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["external_id"] == "gideon"
    assert "type" not in body


def test_npc_respond(httpx_mock: HTTPXMock) -> None:
    """npc_respond() wraps generate() with NPC-focused prompt."""
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=GENERATE_RESPONSE,
        status_code=200,
    )
    response = project.npc_respond("blacksmith", "Player asks about rare weapons")
    assert isinstance(response, GenerateResponse)
    assert response.text == "Ah, the Dragon Slayer returns!"
    import json

    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["entity_id"] == "blacksmith"
    assert "Player asks about rare weapons" in body["prompt"]
    assert "Respond in character as this NPC" in body["prompt"]
    assert body["player_id"] == "default"


def test_npc_respond_with_model(httpx_mock: HTTPXMock) -> None:
    """npc_respond() passes model as type override."""
    project = make_project(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=GENERATE_RESPONSE,
        status_code=200,
    )
    project.npc_respond("blacksmith", "Player asks about swords", model="narration")
    import json

    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["type"] == "narration"


# ---------------------------------------------------------------------------
# Async Project - convenience methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_remember(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    await project.init()
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/events",
        json=EVENT_RESPONSE,
        status_code=201,
    )
    event = await project.remember("blacksmith", "Sold a sword")
    assert isinstance(event, Event)
    await project.close()


@pytest.mark.asyncio
async def test_async_recall(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    await project.init()
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/context?entity_id=blacksmith&limit=10",
        json=CONTEXT_RESPONSE,
        status_code=200,
    )
    ctx = await project.recall("blacksmith")
    assert isinstance(ctx, ContextResult)
    assert ctx.summary == "Gideon has met alice once."
    await project.close()


@pytest.mark.asyncio
async def test_async_create_npc(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    await project.init()
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json=ENTITY_RESPONSE,
        status_code=201,
    )
    entity = await project.create_npc("Gideon")
    assert isinstance(entity, Entity)
    await project.close()


@pytest.mark.asyncio
async def test_async_npc_respond(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    project = AsyncProject(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    await project.init()
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=GENERATE_RESPONSE,
        status_code=200,
    )
    response = await project.npc_respond("blacksmith", "Player asks about rare weapons")
    assert response.text == "Ah, the Dragon Slayer returns!"
    await project.close()


# ---------------------------------------------------------------------------
# Hello project pattern smoke test (sync)
# ---------------------------------------------------------------------------


def test_hello_world_pattern(httpx_mock: HTTPXMock) -> None:
    """Verifies the exact hello project pattern from the task spec runs end-to-end."""
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/v1/projects", json=PROJECT_RESPONSE, status_code=201
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generic/npcs",
        json=ENTITY_RESPONSE,
        status_code=201,
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/events",
        json=EVENT_RESPONSE,
        status_code=201,
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/projects/{PROJECT_ID}/generate",
        json=GENERATE_RESPONSE,
        status_code=200,
    )

    project = kitefrost.Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL)
    project.entity("blacksmith", type="npc", name="Gideon", personality="gruff but kind")
    project.event(
        "player.bought_sword", entity="blacksmith", player="alice", details="haggled to 35 gold"
    )
    response = project.generate(
        entity="blacksmith", player="alice", prompt="Player returns after slaying dragon"
    )
    assert response.text == "Ah, the Dragon Slayer returns!"
