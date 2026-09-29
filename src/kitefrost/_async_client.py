"""Asynchronous KiteFrost Project client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ._client import _entity_path
from ._telemetry import (
    _resolve_report_errors,
    send_telemetry_async,
    warn_telemetry_enabled_once,
)
from ._transport import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    _default_headers,
    _raise_for_response,
    _resolve_entity_id,
    _resolve_player_id,
)
from .exceptions import KiteFrostError
from .models import (
    AskResponse,
    ContextResult,
    Entity,
    Event,
    GenerateResponse,
    Job,
    SchemaDefinition,
    TellResponse,
)


class _AsyncEntityTypeResource:
    """Flat per-type entity accessor (async).

    Async equivalent of :class:`_EntityTypeResource`.  Reached as
    ``project.npcs`` / ``project.places`` / ``project.factions`` /
    ``project.items`` / ``project.players``.  Flat per-type accessors (NOT
    pack-vocabulary grouping); each binds one canonical type and exposes
    create, list and get against the generic-pack entity path.
    """

    def __init__(self, project: "AsyncProject", canonical_type: str) -> None:
        self._project = project
        self._type = canonical_type

    async def create(self, entity_id: str, *, name: str, **properties: Any) -> Entity:
        """Upsert an entity of this resource's canonical type.

        Delegates to :meth:`AsyncProject.entity` so the request shape is
        identical to the generic upsert.
        """
        return await self._project.entity(entity_id, type=self._type, name=name, **properties)

    async def list(self) -> dict[str, Any]:
        """List entities of this type for the project."""
        return await self._project._get(_entity_path(self._type))

    async def get(self, entity_id: str) -> dict[str, Any]:
        """Fetch a single entity of this type by external id."""
        return await self._project._get(f"{_entity_path(self._type)}/{entity_id}")


class AsyncProject:
    """Asynchronous client for a single KiteFrost project.

    Identical API to :class:`~kitefrost.Project` but every method is a
    coroutine.  Use inside ``async def`` functions or frameworks such as
    FastAPI, Starlette, or asyncio.

    Example::

        import asyncio
        import kitefrost

        async def main():
            project = kitefrost.AsyncProject("medieval-rpg", api_key="sk_...")
            await project.init()   # explicit async init instead of auto_create
            blacksmith = await project.entity("blacksmith", type="npc", name="Gideon")
            await project.event("player.bought_sword", entity=blacksmith, player="alice",
                              details="haggled to 35 gold")
            response = await project.generate(
                entity=blacksmith, player="alice",
                prompt="Player returns after slaying dragon"
            )
            print(response.text)

        asyncio.run(main())

    Or as an async context manager::

        async with kitefrost.AsyncProject("medieval-rpg", api_key="sk_...") as project:
            await project.init()
            ...
    """

    def __init__(
        self,
        project_name: str,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        report_errors: bool = True,
        report_context: bool = False,
    ) -> None:
        self.project_name = project_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._report_errors = _resolve_report_errors(report_errors)
        self._report_context = report_context
        self._http = httpx.AsyncClient(
            headers=_default_headers(api_key),
            timeout=timeout,
        )
        self._project_id: str | None = None

        # Flat per-type entity accessors (entity-api-shape decision):
        # project.npcs / project.places / project.factions / project.items / project.players
        self.npcs = _AsyncEntityTypeResource(self, "npc")
        self.places = _AsyncEntityTypeResource(self, "location")
        self.factions = _AsyncEntityTypeResource(self, "faction")
        self.items = _AsyncEntityTypeResource(self, "item")
        self.players = _AsyncEntityTypeResource(self, "player")

        if self._report_errors:
            warn_telemetry_enabled_once(api_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_telemetry(self, exc: KiteFrostError) -> None:
        """Fire-and-forget async telemetry for a caught error."""
        if self._report_errors:
            await send_telemetry_async(
                exc, self._base_url, self._report_context, api_key=self._api_key
            )

    async def init(self) -> "AsyncProject":
        """Create or fetch the project.  Call once after construction."""
        await self._ensure_project()
        return self

    async def _ensure_project(self) -> str:
        if self._project_id is not None:
            return self._project_id

        url = f"{self._base_url}/v1/projects"
        payload: dict[str, Any] = {"name": self.project_name}
        try:
            response = await self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        data: dict[str, Any] = response.json()
        self._project_id = data["id"]
        return self._project_id  # type: ignore[return-value]

    def _project_url(self, path: str = "") -> str:
        assert self._project_id, "Call await project.init() before using AsyncProject."
        return f"{self._base_url}/v1/projects/{self._project_id}{path}"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._project_url(path)
        try:
            response = await self._http.get(url, params=params)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._project_url(path)
        try:
            response = await self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    async def _patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._project_url(path)
        try:
            response = await self._http.patch(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    async def _delete(self, path: str) -> None:
        url = self._project_url(path)
        try:
            response = await self._http.delete(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise

    async def _get_bytes(self, path: str) -> bytes:
        """GET project-scoped raw bytes (e.g. a zip export)."""
        url = self._project_url(path)
        try:
            response = await self._http.get(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.content

    async def _post_bytes(self, path: str, payload: dict[str, Any]) -> bytes:
        """POST project-scoped, returning raw bytes (e.g. a zip export)."""
        url = self._project_url(path)
        try:
            response = await self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.content

    async def _abs_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET against an absolute path (not project-scoped)."""
        url = f"{self._base_url}{path}"
        try:
            response = await self._http.get(url, params=params)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    async def _abs_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST against an absolute path (not project-scoped)."""
        url = f"{self._base_url}{path}"
        try:
            response = await self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    async def _abs_delete(self, path: str) -> dict[str, Any]:
        """DELETE against an absolute path (not project-scoped)."""
        url = f"{self._base_url}{path}"
        try:
            response = await self._http.delete(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a raw GraphQL query/mutation. See :meth:`Project.graphql`."""
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        return await self._abs_post("/v1/graphql", payload)

    async def entity(
        self,
        entity_id: str,
        *,
        type: str,
        name: str,
        **properties: Any,
    ) -> Entity:
        """Upsert an entity.  See :meth:`Project.entity` for full docs."""
        path = _entity_path(type)
        payload: dict[str, Any] = {
            "external_id": entity_id,
            "name": name,
            "properties": properties,
        }
        data = await self._post(path, payload)
        return Entity._from_dict(data)

    async def event(
        self,
        event_type: str,
        *,
        entity: "Entity | str | None" = None,
        player: str | None = None,
        **data: Any,
    ) -> Event:
        """Record an immutable event.  See :meth:`Project.event` for full docs."""
        payload: dict[str, Any] = {
            "type": event_type,
            "data": data,
        }
        if entity is not None:
            payload["entity_id"] = _resolve_entity_id(entity)
        if player is not None:
            payload["player_id"] = _resolve_player_id(player)

        result = await self._post("/events", payload)
        return Event._from_dict(result)

    async def context(
        self,
        *,
        query: str | None = None,
        entity_id: str | None = None,
        player_id: str | None = None,
    ) -> ContextResult:
        """Query project context.  See :meth:`Project.context` for full docs."""
        params: dict[str, Any] = {}
        if query is not None:
            params["query"] = query
        if entity_id is not None:
            params["entity_id"] = entity_id
        if player_id is not None:
            params["player_id"] = player_id

        data = await self._get("/context", params=params or None)
        return ContextResult._from_dict(data)

    async def generate(
        self,
        *,
        entity: "Entity | str",
        player: str,
        prompt: str,
        type: str = "dialogue",
    ) -> GenerateResponse:
        """Generate context-aware content.  See :meth:`Project.generate` for full docs."""
        payload: dict[str, Any] = {
            "entity_id": _resolve_entity_id(entity),
            "player_id": _resolve_player_id(player),
            "prompt": prompt,
            "type": type,
        }
        data = await self._post("/generate", payload)
        return GenerateResponse._from_dict(data)

    async def tell(self, statement: str) -> TellResponse:
        """Ingest a natural-language statement into project memory.

        See :meth:`Project.tell` for full documentation.

        Example::

            result = await project.tell("Alice bought a sword from Gideon for 35 gold.")
            print(result.understood)
            print(result.actions)
        """
        data = await self._post("/tell", {"statement": statement})
        return TellResponse._from_dict(data)

    async def ask(
        self,
        question: str,
        *,
        respond_as: str | None = None,
    ) -> AskResponse:
        """Ask a natural-language question about project memory.

        See :meth:`Project.ask` for full documentation.

        Example::

            response = await project.ask(
                "What does Gideon know about Alice?",
                respond_as="gideon",
            )
            print(response.answer)
            print(response.in_character)
        """
        payload: dict[str, Any] = {"question": question}
        if respond_as is not None:
            payload["respond_as"] = respond_as
        data = await self._post("/ask", payload)
        return AskResponse._from_dict(data)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    async def define_schema(
        self,
        entity_type: str,
        required_properties: dict[str, Any] | None = None,
        optional_properties: dict[str, Any] | None = None,
    ) -> SchemaDefinition:
        """Define required and optional property specs for an entity type.

        See :meth:`Project.define_schema` for full documentation.

        Example::

            await project.define_schema(
                "character",
                required_properties={
                    "strength": {"type": "integer", "min": 1, "max": 30},
                    "class": {"type": "string", "enum": ["fighter", "wizard"]},
                },
            )
        """
        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "required_properties": required_properties or {},
            "optional_properties": optional_properties or {},
        }
        data = await self._post("/schemas", payload)
        return SchemaDefinition._from_dict(data)

    async def get_schema(self, entity_type: str) -> SchemaDefinition:
        """Get the schema for a specific entity type.

        See :meth:`Project.get_schema` for full documentation.
        """
        data = await self._get(f"/schemas/{entity_type}")
        return SchemaDefinition._from_dict(data)

    async def list_schemas(self) -> list[SchemaDefinition]:
        """List all entity schemas defined for this project.

        See :meth:`Project.list_schemas` for full documentation.
        """
        data = await self._get("/schemas")
        schemas_raw: list[dict[str, Any]] = data.get("schemas", [])
        return [SchemaDefinition._from_dict(s) for s in schemas_raw]

    # ------------------------------------------------------------------
    # Job queue
    # ------------------------------------------------------------------

    async def submit_job(
        self,
        project_id: str,
        *,
        type: str = "generate",
        prompt: str,
        **kwargs: Any,
    ) -> Job:
        """Submit an asynchronous generation job for a project.

        See :meth:`Project.submit_job` for full documentation.
        """
        payload: dict[str, Any] = {"type": type, "prompt": prompt, **kwargs}
        url = f"{self._base_url}/v1/projects/{project_id}/generate"
        response = await self._http.post(url, json=payload)
        _raise_for_response(response, url)
        return Job._from_dict(response.json())

    async def get_job(self, job_id: str) -> Job:
        """Fetch the current state of a job.

        See :meth:`Project.get_job` for full documentation.
        """
        data = await self._abs_get(f"/v1/jobs/{job_id}")
        return Job._from_dict(data)

    async def list_jobs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Job]:
        """List jobs across all projects for this API key.

        See :meth:`Project.list_jobs` for full documentation.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        data = await self._abs_get("/v1/jobs", params=params)
        jobs_raw: list[dict[str, Any]] = data.get("jobs", [])
        return [Job._from_dict(j) for j in jobs_raw]

    async def cancel_job(self, job_id: str) -> Job:
        """Cancel a queued or processing job.

        See :meth:`Project.cancel_job` for full documentation.
        """
        data = await self._abs_delete(f"/v1/jobs/{job_id}")
        return Job._from_dict(data)

    async def poll_job(
        self,
        job_id: str,
        *,
        interval: float = 2.0,
        timeout: float = 600.0,
    ) -> Job:
        """Poll a job until it reaches a terminal status.

        See :meth:`Project.poll_job` for full documentation.

        Raises:
            TimeoutError: If the job does not reach a terminal status within
                *timeout* seconds.
        """
        _TERMINAL = {"completed", "failed", "cancelled"}
        import time

        deadline = time.monotonic() + timeout
        while True:
            job = await self.get_job(job_id)
            if job.status in _TERMINAL:
                return job
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Job {job_id!r} did not complete within {timeout}s "
                    f"(last status: {job.status!r})"
                )
            await asyncio.sleep(min(interval, remaining))

    async def stream_job(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        """Stream job progress events via Server-Sent Events.

        Async version of :meth:`Project.stream_job`. Connects to
        ``GET /v1/jobs/{job_id}/stream`` and yields parsed SSE events.

        Args:
            job_id: The server-assigned job identifier.

        Yields:
            Dict with ``event`` (str) and ``data`` (dict) keys.
        """
        import json as _json

        url = f"{self._base_url}/v1/jobs/{job_id}/stream"
        headers = _default_headers(self._api_key)
        headers["Accept"] = "text/event-stream"

        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, headers=headers, timeout=None) as response:
                _raise_for_response(response, url)
                current_event = "message"
                current_data = ""

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data += line[5:].strip()
                    elif line == "":
                        if current_data:
                            try:
                                data = _json.loads(current_data)
                            except _json.JSONDecodeError:
                                data = {"raw": current_data}
                            yield {"event": current_event, "data": data}
                        current_event = "message"
                        current_data = ""

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def remember(
        self,
        entity_id: str,
        event_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Record a free-text memory for an entity.

        Async version of :meth:`Project.remember`.

        Args:
            entity_id: External entity identifier (e.g. ``"blacksmith"``).
            event_text: Human-readable description of what happened.
            metadata: Optional extra key-value pairs stored in the event data.

        Returns:
            :class:`~kitefrost.models.Event` with the server-assigned ``id``.

        Example::

            await project.remember("blacksmith", "Sold a legendary sword to Alice")
        """
        data_payload: dict[str, Any] = {"text": event_text}
        if metadata:
            data_payload.update(metadata)
        return await self.event("memory", entity=entity_id, **data_payload)

    async def recall(
        self,
        entity_id: str,
        *,
        limit: int = 10,
    ) -> ContextResult:
        """Retrieve memories for a single entity.

        Async version of :meth:`Project.recall`.

        Args:
            entity_id: External entity identifier to recall memories for.
            limit: Maximum number of events to return (default 10).

        Returns:
            :class:`~kitefrost.models.ContextResult` scoped to the entity.

        Example::

            ctx = await project.recall("blacksmith")
            print(ctx.summary)
        """
        params: dict[str, Any] = {"entity_id": entity_id, "limit": str(limit)}
        data = await self._get("/context", params=params)
        return ContextResult._from_dict(data)

    async def create_npc(
        self,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> Entity:
        """Create an NPC entity.

        Async version of :meth:`Project.create_npc`.

        Args:
            name: Human-readable NPC name (e.g. ``"Gideon the Blacksmith"``).
            properties: Optional dict of NPC properties (personality, location, etc.).

        Returns:
            :class:`~kitefrost.models.Entity` with the server-assigned ``id``.

        Example::

            npc = await project.create_npc("Gideon", properties={"personality": "gruff"})
        """
        entity_id = name.lower().replace(" ", "-")
        props = properties or {}
        return await self.entity(entity_id, type="npc", name=name, **props)

    async def npc_respond(
        self,
        entity_id: str,
        player_action: str,
        *,
        model: str | None = None,
    ) -> GenerateResponse:
        """Generate an NPC response to a player action.

        Async version of :meth:`Project.npc_respond`.

        Args:
            entity_id: External NPC entity identifier.
            player_action: Description of what the player did or said.
            model: Optional model override (passed as generation type).

        Returns:
            :class:`~kitefrost.models.GenerateResponse` with ``.text``.

        Example::

            response = await project.npc_respond("blacksmith", "Player asks about rare weapons")
            print(response.text)
        """
        prompt = (
            f"The player does the following: {player_action}. Respond in character as this NPC."
        )
        kwargs: dict[str, Any] = {
            "entity": entity_id,
            "player": "default",
            "prompt": prompt,
        }
        if model is not None:
            kwargs["type"] = model
        return await self.generate(**kwargs)

    # ------------------------------------------------------------------
    # Authoring core - notes
    # ------------------------------------------------------------------

    async def create_note(
        self,
        title: str,
        body: str = "",
        note_type: str | None = None,
        pinned: bool = False,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a project note.  See :meth:`Project.create_note` for full docs."""
        payload: dict[str, Any] = {
            "title": title,
            "body": body,
            "note_type": note_type,
            "pinned": pinned,
            "tags": tags,
        }
        return await self._post("/notes", payload)

    async def list_notes(self) -> list[dict[str, Any]]:
        """List all notes.  See :meth:`Project.list_notes` for full docs."""
        url = self._project_url("/notes")
        try:
            response = await self._http.get(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    async def get_note(self, note_id: str) -> dict[str, Any]:
        """Fetch a single note.  See :meth:`Project.get_note` for full docs."""
        return await self._get(f"/notes/{note_id}")

    async def update_note(self, note_id: str, **fields: Any) -> dict[str, Any]:
        """Update fields on a note.  See :meth:`Project.update_note` for full docs."""
        return await self._patch(f"/notes/{note_id}", fields)

    async def delete_note(self, note_id: str) -> None:
        """Delete a note.  See :meth:`Project.delete_note` for full docs."""
        await self._delete(f"/notes/{note_id}")

    # ------------------------------------------------------------------
    # Authoring core - quests
    # ------------------------------------------------------------------

    async def create_quest(
        self,
        title: str,
        summary: str | None = None,
        status: str = "offered",
        objectives: list[Any] | None = None,
        tags: list[str] | None = None,
        **links: Any,
    ) -> dict[str, Any]:
        """Create a quest.  See :meth:`Project.create_quest` for full docs."""
        payload: dict[str, Any] = {
            "title": title,
            "summary": summary,
            "status": status,
            "objectives": objectives,
            "tags": tags,
            **links,
        }
        return await self._post("/quests", payload)

    async def list_quests(self) -> list[dict[str, Any]]:
        """List quests.  See :meth:`Project.list_quests` for full docs."""
        url = self._project_url("/quests")
        try:
            response = await self._http.get(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            await self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    # Pack-catalogue / selector-prompt methods intentionally NOT exposed on the
    # SDK (see the sync client): pack DISCOVERY is an AI-agent runtime concern
    # served by REST + MCP, not the human dev-time SDK.

    # ------------------------------------------------------------------
    # Feedback (absolute)
    # ------------------------------------------------------------------

    async def submit_feedback(
        self,
        signal: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit a feedback signal.  See :meth:`Project.submit_feedback` for full docs."""
        body: dict[str, Any] = {
            "schema_version": "1",
            "signal": signal,
            "payload": payload,
        }
        if context is not None:
            body["context"] = context
        return await self._abs_post("/v1/feedback", body)

    async def feedback_schema(self) -> dict[str, Any]:
        """Fetch the feedback JSON schema.  See :meth:`Project.feedback_schema`."""
        return await self._abs_get("/v1/feedback/schema.json")

    # ------------------------------------------------------------------
    # Import / continuity / export
    # ------------------------------------------------------------------

    async def import_vtt(self, format: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Parse-only VTT import (Pro-gated, ttrpg-gm).  See :meth:`Project.import_vtt`."""
        body: dict[str, Any] = {"format": format, "payload": payload}
        return await self._post("/import/vtt", body)

    async def check_continuity(self) -> dict[str, Any]:
        """Run a free continuity check (game-narrative).  See :meth:`Project.check_continuity`."""
        return await self._post("/game-narrative/continuity/check", {})

    async def export(
        self,
        format: str,
        entity_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Export project content.  See :meth:`Project.export` for full docs."""
        body: dict[str, Any] = {
            "format": format,
            "entity_id": entity_id,
            "options": options,
        }
        return await self._post("/export", body)

    async def export_full(self) -> bytes:
        """Export the full project as a zip.  See :meth:`Project.export_full`."""
        return await self._post_bytes("/export/full", {})

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    async def checkpoint(self, name: str, description: str | None = None) -> dict[str, Any]:
        """Create a named checkpoint.  See :meth:`Project.checkpoint` for full docs."""
        payload: dict[str, Any] = {"name": name, "description": description}
        return await self._post("/checkpoints", payload)

    async def checkpoints(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List checkpoints, newest first.  See :meth:`Project.checkpoints`."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        return await self._get("/checkpoints", params=params)

    async def restore(self, checkpoint_id: str) -> dict[str, Any]:
        """Restore to a checkpoint.  See :meth:`Project.restore` for full docs."""
        return await self._post(f"/checkpoints/{checkpoint_id}/restore", {})

    async def close(self) -> None:
        """Close the underlying async HTTP connection pool."""
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncProject":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
