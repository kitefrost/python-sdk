"""Synchronous KiteFrost Project client."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from ._telemetry import (
    _resolve_report_errors,
    send_telemetry_sync,
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

# Canonical entity types → project-scoped pack-prefix paths. The SDK
# always targets the ``generic`` pack because every tenant pack exposes
# the same five universal canonical types via aliases, so a
# ``game-narrative`` tenant can still post to the generic pack path and
# the server stores the row under the canonical type regardless of
# which pack URL was used. The literal paths are spelled out (instead of
# built with an f-string) so the SDK-parity scanner can match them
# against the OpenAPI route table.
_ENTITY_PATHS: dict[str, str] = {
    "npc": "/generic/npcs",
    "location": "/generic/locations",
    "faction": "/generic/factions",
    "item": "/generic/items",
    "player": "/generic/players",
}


def _entity_path(canonical_type: str) -> str:
    """Return the project-scoped pack-prefix path for an entity upsert.

    Raises :class:`ValueError` for unknown canonical types so callers
    get a fast client-side error instead of a 422 round-trip.
    """
    try:
        return _ENTITY_PATHS[canonical_type]
    except KeyError:
        raise ValueError(
            f"Unknown entity type {canonical_type!r}. Expected one of: {sorted(_ENTITY_PATHS)}."
        ) from None


class _EntityTypeResource:
    """Flat per-type entity accessor (sync).

    Reached as ``project.npcs`` / ``project.places`` / ``project.factions`` /
    ``project.items`` / ``project.players``.  These are flat per-type
    accessors (NOT pack-vocabulary grouping); each binds one canonical type
    and exposes create, list and get that target the same generic-pack path the
    lower-level :meth:`Project.entity` upsert uses.
    """

    def __init__(self, project: "Project", canonical_type: str) -> None:
        self._project = project
        self._type = canonical_type

    def create(self, entity_id: str, *, name: str, **properties: Any) -> Entity:
        """Upsert an entity of this resource's canonical type.

        Delegates to :meth:`Project.entity` so the request shape is identical
        to the generic upsert.
        """
        return self._project.entity(entity_id, type=self._type, name=name, **properties)

    def list(self) -> dict[str, Any]:
        """List entities of this type for the project."""
        return self._project._get(_entity_path(self._type))

    def get(self, entity_id: str) -> dict[str, Any]:
        """Fetch a single entity of this type by external id."""
        return self._project._get(f"{_entity_path(self._type)}/{entity_id}")


class Project:
    """Synchronous client for a single KiteFrost project.

    Creates the project on the API if it does not already exist (upsert
    semantics - safe to call multiple times with the same name).

    Args:
        project_name: Human-readable project identifier (e.g. ``"medieval-rpg"``).
        api_key: KiteFrost API key (``sk_...`` for server-side use,
            ``pk_...`` for client-side use).
        base_url: Override the default API base URL.
        timeout: HTTP request timeout in seconds (default 30).
        auto_create: When ``True`` (default), the project is created on the
            KiteFrost API at construction time.  Set to ``False`` to skip
            the network call and manage project lifecycle yourself.

    Example::

        import kitefrost

        project = kitefrost.Project("medieval-rpg", api_key="sk_...")
        blacksmith = project.entity("blacksmith", type="npc", name="Gideon")
        project.event("player.bought_sword", entity=blacksmith, player="alice",
                    details="haggled to 35 gold")
        response = project.generate(entity=blacksmith, player="alice",
                                  prompt="Player returns after slaying dragon")
        print(response.text)
    """

    def __init__(
        self,
        project_name: str,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        auto_create: bool = True,
        report_errors: bool = True,
        report_context: bool = False,
    ) -> None:
        self.project_name = project_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._report_errors = _resolve_report_errors(report_errors)
        self._report_context = report_context
        self._http = httpx.Client(
            headers=_default_headers(api_key),
            timeout=timeout,
        )
        self._project_id: str | None = None

        # Flat per-type entity accessors (entity-api-shape decision):
        # project.npcs / project.places / project.factions / project.items / project.players
        self.npcs = _EntityTypeResource(self, "npc")
        self.places = _EntityTypeResource(self, "location")
        self.factions = _EntityTypeResource(self, "faction")
        self.items = _EntityTypeResource(self, "item")
        self.players = _EntityTypeResource(self, "player")

        if self._report_errors:
            warn_telemetry_enabled_once(api_key)

        if auto_create:
            self._ensure_project()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_telemetry(self, exc: KiteFrostError) -> None:
        """Fire-and-forget telemetry for a caught error."""
        if self._report_errors:
            send_telemetry_sync(exc, self._base_url, self._report_context, api_key=self._api_key)

    def _ensure_project(self) -> str:
        """Create or fetch the project and cache its server-side ID."""
        if self._project_id is not None:
            return self._project_id

        url = f"{self._base_url}/v1/projects"
        payload: dict[str, Any] = {"name": self.project_name}
        try:
            response = self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        data: dict[str, Any] = response.json()
        self._project_id = data["id"]
        return self._project_id  # type: ignore[return-value]

    def _project_url(self, path: str = "") -> str:
        pid = self._project_id or self._ensure_project()
        return f"{self._base_url}/v1/projects/{pid}{path}"

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._project_url(path)
        try:
            response = self._http.get(url, params=params)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._project_url(path)
        try:
            response = self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    def _patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._project_url(path)
        try:
            response = self._http.patch(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    def _delete(self, path: str) -> None:
        url = self._project_url(path)
        try:
            response = self._http.delete(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise

    def _get_bytes(self, path: str) -> bytes:
        """GET project-scoped raw bytes (e.g. a zip export)."""
        url = self._project_url(path)
        try:
            response = self._http.get(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.content

    def _post_bytes(self, path: str, payload: dict[str, Any]) -> bytes:
        """POST project-scoped, returning raw bytes (e.g. a zip export)."""
        url = self._project_url(path)
        try:
            response = self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.content

    def _abs_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET against an absolute path (not project-scoped)."""
        url = f"{self._base_url}{path}"
        try:
            response = self._http.get(url, params=params)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    def _abs_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST against an absolute path (not project-scoped)."""
        url = f"{self._base_url}{path}"
        try:
            response = self._http.post(url, json=payload)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    def _abs_delete(self, path: str) -> dict[str, Any]:
        """DELETE against an absolute path (not project-scoped)."""
        url = f"{self._base_url}{path}"
        try:
            response = self._http.delete(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a raw GraphQL query/mutation against ``POST /v1/graphql``.

        Escape hatch for the GraphQL API (complex nested reads, typed pack
        mutations, real-time subscriptions). KiteFrost ships no separate
        GraphQL SDK: fetch the schema from ``GET /v1/graphql/schema`` and run
        your own codegen (graphql-codegen, gql) for typed clients. This method
        is thin transport - the same auth, retries and error envelope as the
        REST helpers.

        Args:
            query: A GraphQL document (query or mutation).
            variables: Optional GraphQL variables object.

        Returns:
            The raw GraphQL response envelope: ``{"data": ..., "errors": ...}``.
            GraphQL errors are returned in-band (HTTP 200) in ``errors``.
        """
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        return self._abs_post("/v1/graphql", payload)

    def entity(
        self,
        entity_id: str,
        *,
        type: str,
        name: str,
        **properties: Any,
    ) -> Entity:
        """Upsert an entity (NPC, location, faction, item, player, etc.).

        Args:
            entity_id: Stable external identifier (e.g. ``"blacksmith-gideon"``).
            type: Entity type: ``"npc"``, ``"location"``, ``"faction"``,
                ``"item"``, or ``"player"``.
            name: Human-readable display name.
            **properties: Arbitrary key-value properties stored on the entity.

        Returns:
            :class:`~kitefrost.models.Entity` with the server-assigned ``id``.
        """
        path = _entity_path(type)
        payload: dict[str, Any] = {
            "external_id": entity_id,
            "name": name,
            "properties": properties,
        }
        data = self._post(path, payload)
        return Entity._from_dict(data)

    def event(
        self,
        event_type: str,
        *,
        entity: "Entity | str | None" = None,
        player: str | None = None,
        **data: Any,
    ) -> Event:
        """Record an immutable event in the project timeline.

        Args:
            event_type: Dot-namespaced event type (e.g. ``"player.bought_sword"``).
            entity: The entity involved - pass an :class:`~kitefrost.models.Entity`
                returned by :meth:`entity`, or a string ``external_id``.
            player: Player identifier string.
            **data: Arbitrary event payload stored in the ``data`` field.

        Returns:
            :class:`~kitefrost.models.Event` with the server-assigned ``id``.
        """
        payload: dict[str, Any] = {
            "type": event_type,
            "data": data,
        }
        if entity is not None:
            payload["entity_id"] = _resolve_entity_id(entity)
        if player is not None:
            payload["player_id"] = _resolve_player_id(player)

        result = self._post("/events", payload)
        return Event._from_dict(result)

    def context(
        self,
        *,
        query: str | None = None,
        entity_id: str | None = None,
        player_id: str | None = None,
    ) -> ContextResult:
        """Query assembled project context for a generation request.

        This is the "money endpoint" - it retrieves relevant events, facts,
        and entity state for a given perspective.

        Args:
            query: Natural language or structured query string.
            entity_id: Filter to a specific entity's perspective.
            player_id: Filter to events involving this player.

        Returns:
            :class:`~kitefrost.models.ContextResult`.
        """
        params: dict[str, Any] = {}
        if query is not None:
            params["query"] = query
        if entity_id is not None:
            params["entity_id"] = entity_id
        if player_id is not None:
            params["player_id"] = player_id

        data = self._get("/context", params=params or None)
        return ContextResult._from_dict(data)

    def generate(
        self,
        *,
        entity: "Entity | str",
        player: str,
        prompt: str,
        type: str = "dialogue",
    ) -> GenerateResponse:
        """Generate context-aware content for an entity/player interaction.

        Args:
            entity: The entity speaking or acting - pass an
                :class:`~kitefrost.models.Entity` or a string ``external_id``.
            player: Player identifier string.
            prompt: The situation description / generation prompt.
            type: Content type: ``"dialogue"`` (default), ``"narration"``,
                or ``"summary"``.

        Returns:
            :class:`~kitefrost.models.GenerateResponse` with ``.text``.
        """
        payload: dict[str, Any] = {
            "entity_id": _resolve_entity_id(entity),
            "player_id": _resolve_player_id(player),
            "prompt": prompt,
            "type": type,
        }
        data = self._post("/generate", payload)
        return GenerateResponse._from_dict(data)

    def tell(self, statement: str) -> TellResponse:
        """Ingest a natural-language statement into project memory.

        The engine parses the statement, extracts entities and relationships,
        and persists them as structured events and facts.

        Args:
            statement: A plain-English description of something that happened
                (e.g. ``"Alice bought a sword from Gideon for 35 gold."``).

        Returns:
            :class:`~kitefrost.models.TellResponse` with ``.understood``,
            ``.actions``, ``.entities_referenced``, and ``.tokens_used``.

        Example::

            result = project.tell("Alice bought a sword from Gideon for 35 gold.")
            print(result.understood)         # True
            print(result.actions)            # [{"type": "event.recorded", ...}]
            print(result.entities_referenced)  # ["alice", "gideon"]
        """
        data = self._post("/tell", {"statement": statement})
        return TellResponse._from_dict(data)

    def ask(
        self,
        question: str,
        *,
        respond_as: str | None = None,
    ) -> AskResponse:
        """Ask a natural-language question about project memory.

        The engine retrieves relevant context and returns a factual answer.
        Optionally voices the answer in character as a specific entity.

        Args:
            question: A plain-English question about the project state
                (e.g. ``"What does Gideon know about Alice?"``).
            respond_as: External entity ID whose perspective and voice to use
                when generating ``in_character``.  Pass ``None`` (default)
                for a plain factual answer with no character voice.

        Returns:
            :class:`~kitefrost.models.AskResponse` with ``.answer``,
            ``.in_character``, ``.context_used``, and ``.tokens_used``.

        Example::

            response = project.ask(
                "What does Gideon know about Alice?",
                respond_as="gideon",
            )
            print(response.answer)       # Factual summary
            print(response.in_character) # In-character response as Gideon
        """
        payload: dict[str, Any] = {"question": question}
        if respond_as is not None:
            payload["respond_as"] = respond_as
        data = self._post("/ask", payload)
        return AskResponse._from_dict(data)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def define_schema(
        self,
        entity_type: str,
        required_properties: dict[str, Any] | None = None,
        optional_properties: dict[str, Any] | None = None,
    ) -> SchemaDefinition:
        """Define required and optional property specs for an entity type.

        Once defined, :meth:`entity` calls for that type are validated against
        the schema before being stored. Calling again with the same
        *entity_type* replaces the existing schema.

        Args:
            entity_type: The entity type to constrain (e.g. ``"character"``).
            required_properties: Dict mapping property names to spec dicts.
                Each spec must have a ``"type"`` key. Optional constraint keys:
                ``min``, ``max`` (integer/number), ``enum``, ``minLength``,
                ``maxLength`` (string).
            optional_properties: Same format as *required_properties* but
                validation only fires when the property is present.

        Returns:
            :class:`~kitefrost.models.SchemaDefinition` with the stored schema.

        Raises:
            :class:`~kitefrost.exceptions.ValidationError`: If the schema
                definition itself is invalid.

        Example::

            project.define_schema(
                "character",
                required_properties={
                    "strength": {"type": "integer", "min": 1, "max": 30},
                    "class": {"type": "string", "enum": ["fighter", "wizard"]},
                    "hp": {"type": "object"},
                },
                optional_properties={
                    "backstory": {"type": "string"},
                },
            )
        """
        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "required_properties": required_properties or {},
            "optional_properties": optional_properties or {},
        }
        data = self._post("/schemas", payload)
        return SchemaDefinition._from_dict(data)

    def get_schema(self, entity_type: str) -> SchemaDefinition:
        """Get the schema for a specific entity type.

        Args:
            entity_type: The entity type to look up.

        Returns:
            :class:`~kitefrost.models.SchemaDefinition`.

        Raises:
            :class:`~kitefrost.exceptions.ProjectNotFound`: If the entity type
                has no schema defined.
        """
        data = self._get(f"/schemas/{entity_type}")
        return SchemaDefinition._from_dict(data)

    def list_schemas(self) -> list[SchemaDefinition]:
        """List all entity schemas defined for this project.

        Returns:
            List of :class:`~kitefrost.models.SchemaDefinition` objects.
        """
        data = self._get("/schemas")
        schemas_raw: list[dict[str, Any]] = data.get("schemas", [])
        return [SchemaDefinition._from_dict(s) for s in schemas_raw]

    # ------------------------------------------------------------------
    # Job queue
    # ------------------------------------------------------------------

    def submit_job(
        self,
        project_id: str,
        *,
        type: str = "generate",
        prompt: str,
        **kwargs: Any,
    ) -> Job:
        """Submit an asynchronous generation job for a project.

        Posts to ``POST /v1/projects/{project_id}/generate`` and returns a
        :class:`~kitefrost.models.Job` immediately with ``status="queued"``.
        Poll the returned job with :meth:`poll_job` or :meth:`get_job`.

        Args:
            project_id: Server-side project ID (``prj_...``).
            type: Job type - ``"generate"`` (default), ``"summarise"``, etc.
            prompt: The generation prompt.
            **kwargs: Additional payload fields forwarded to the API.

        Returns:
            :class:`~kitefrost.models.Job` with ``status="queued"``.
        """
        payload: dict[str, Any] = {"type": type, "prompt": prompt, **kwargs}
        url = f"{self._base_url}/v1/projects/{project_id}/generate"
        response = self._http.post(url, json=payload)
        _raise_for_response(response, url)
        return Job._from_dict(response.json())

    def get_job(self, job_id: str) -> Job:
        """Fetch the current state of a job.

        Args:
            job_id: The server-assigned job identifier.

        Returns:
            :class:`~kitefrost.models.Job` with the latest status.
        """
        data = self._abs_get(f"/v1/jobs/{job_id}")
        return Job._from_dict(data)

    def list_jobs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Job]:
        """List jobs across all projects for this API key.

        Args:
            limit: Maximum number of jobs to return (default 20).
            offset: Pagination offset (default 0).
            status: Optional filter - ``"queued"``, ``"processing"``,
                ``"completed"``, ``"failed"``, or ``"cancelled"``.

        Returns:
            List of :class:`~kitefrost.models.Job` objects.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        data = self._abs_get("/v1/jobs", params=params)
        jobs_raw: list[dict[str, Any]] = data.get("jobs", [])
        return [Job._from_dict(j) for j in jobs_raw]

    def cancel_job(self, job_id: str) -> Job:
        """Cancel a queued or processing job.

        Args:
            job_id: The server-assigned job identifier.

        Returns:
            :class:`~kitefrost.models.Job` with ``status="cancelled"``.
        """
        data = self._abs_delete(f"/v1/jobs/{job_id}")
        return Job._from_dict(data)

    def poll_job(
        self,
        job_id: str,
        *,
        interval: float = 2.0,
        timeout: float = 600.0,
    ) -> Job:
        """Poll a job until it reaches a terminal status.

        Calls :meth:`get_job` repeatedly at *interval* seconds until the job
        status is one of ``"completed"``, ``"failed"``, or ``"cancelled"``,
        or until *timeout* seconds elapse.

        Args:
            job_id: The server-assigned job identifier.
            interval: Seconds between poll attempts (default 2.0).
            timeout: Maximum seconds to wait before raising
                :class:`TimeoutError` (default 600).

        Returns:
            :class:`~kitefrost.models.Job` in terminal status.

        Raises:
            TimeoutError: If the job does not reach a terminal status within
                *timeout* seconds.
        """
        _TERMINAL = {"completed", "failed", "cancelled"}
        deadline = time.monotonic() + timeout
        while True:
            job = self.get_job(job_id)
            if job.status in _TERMINAL:
                return job
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Job {job_id!r} did not complete within {timeout}s "
                    f"(last status: {job.status!r})"
                )
            time.sleep(min(interval, remaining))

    def stream_job(self, job_id: str) -> "Iterator[dict[str, Any]]":
        """Stream job progress events via Server-Sent Events.

        Connects to ``GET /v1/jobs/{job_id}/stream`` and yields parsed SSE
        events as dicts with ``"event"`` and ``"data"`` keys. The stream
        closes when the job reaches a terminal status.

        Args:
            job_id: The server-assigned job identifier.

        Yields:
            Dict with ``event`` (str) and ``data`` (dict) keys for each
            SSE event received.

        Example::

            for event in project.stream_job("job_abc123"):
                print(event["event"], event["data"])
        """
        import json as _json

        url = f"{self._base_url}/v1/jobs/{job_id}/stream"
        headers = _default_headers(self._api_key)
        headers["Accept"] = "text/event-stream"

        with httpx.stream("GET", url, headers=headers, timeout=None) as response:
            _raise_for_response(response, url)
            current_event = "message"
            current_data = ""

            for line in response.iter_lines():
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

    def remember(
        self,
        entity_id: str,
        event_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Record a free-text memory for an entity.

        Convenience wrapper around :meth:`event` that stores a narrative
        event associated with the given entity.

        Args:
            entity_id: External entity identifier (e.g. ``"blacksmith"``).
            event_text: Human-readable description of what happened.
            metadata: Optional extra key-value pairs stored in the event data.

        Returns:
            :class:`~kitefrost.models.Event` with the server-assigned ``id``.

        Example::

            project.remember("blacksmith", "Sold a legendary sword to Alice")
        """
        data_payload: dict[str, Any] = {"text": event_text}
        if metadata:
            data_payload.update(metadata)
        return self.event("memory", entity=entity_id, **data_payload)

    def recall(
        self,
        entity_id: str,
        *,
        limit: int = 10,
    ) -> ContextResult:
        """Retrieve memories for a single entity.

        Convenience wrapper around :meth:`context` that filters to one
        entity's perspective.

        Args:
            entity_id: External entity identifier to recall memories for.
            limit: Maximum number of events to return (default 10).

        Returns:
            :class:`~kitefrost.models.ContextResult` scoped to the entity.

        Example::

            ctx = project.recall("blacksmith")
            print(ctx.summary)
        """
        params: dict[str, Any] = {"entity_id": entity_id, "limit": str(limit)}
        data = self._get("/context", params=params)
        return ContextResult._from_dict(data)

    def create_npc(
        self,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> Entity:
        """Create an NPC entity.

        Convenience wrapper around :meth:`entity` with ``type="npc"``
        and an auto-generated ``entity_id`` derived from the name.

        Args:
            name: Human-readable NPC name (e.g. ``"Gideon the Blacksmith"``).
            properties: Optional dict of NPC properties (personality, location, etc.).

        Returns:
            :class:`~kitefrost.models.Entity` with the server-assigned ``id``.

        Example::

            npc = project.create_npc("Gideon", properties={"personality": "gruff"})
        """
        entity_id = name.lower().replace(" ", "-")
        props = properties or {}
        return self.entity(entity_id, type="npc", name=name, **props)

    def npc_respond(
        self,
        entity_id: str,
        player_action: str,
        *,
        model: str | None = None,
    ) -> GenerateResponse:
        """Generate an NPC response to a player action.

        Convenience wrapper around :meth:`generate` with an NPC-focused
        prompt format.

        Args:
            entity_id: External NPC entity identifier.
            player_action: Description of what the player did or said.
            model: Optional model override (passed as generation type).

        Returns:
            :class:`~kitefrost.models.GenerateResponse` with ``.text``.

        Example::

            response = project.npc_respond("blacksmith", "Player asks about rare weapons")
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
        return self.generate(**kwargs)

    # ------------------------------------------------------------------
    # Authoring core - notes
    # ------------------------------------------------------------------

    def create_note(
        self,
        title: str,
        body: str = "",
        note_type: str | None = None,
        pinned: bool = False,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a project note.

        Posts to ``POST /v1/projects/{project_id}/notes`` and returns the
        created note as a dict.
        """
        payload: dict[str, Any] = {
            "title": title,
            "body": body,
            "note_type": note_type,
            "pinned": pinned,
            "tags": tags,
        }
        return self._post("/notes", payload)

    def list_notes(self) -> list[dict[str, Any]]:
        """List all notes for this project.

        Gets ``GET /v1/projects/{project_id}/notes`` and returns a list.
        """
        url = self._project_url("/notes")
        try:
            response = self._http.get(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    def get_note(self, note_id: str) -> dict[str, Any]:
        """Fetch a single note by ID.

        Gets ``GET /v1/projects/{project_id}/notes/{note_id}``.
        """
        return self._get(f"/notes/{note_id}")

    def update_note(self, note_id: str, **fields: Any) -> dict[str, Any]:
        """Update fields on a note.

        Patches ``PATCH /v1/projects/{project_id}/notes/{note_id}`` with the
        supplied keyword fields.
        """
        return self._patch(f"/notes/{note_id}", fields)

    def delete_note(self, note_id: str) -> None:
        """Delete a note.

        Deletes ``DELETE /v1/projects/{project_id}/notes/{note_id}``.
        """
        self._delete(f"/notes/{note_id}")

    # ------------------------------------------------------------------
    # Authoring core - quests
    # ------------------------------------------------------------------

    def create_quest(
        self,
        title: str,
        summary: str | None = None,
        status: str = "offered",
        objectives: list[Any] | None = None,
        tags: list[str] | None = None,
        **links: Any,
    ) -> dict[str, Any]:
        """Create a quest.

        Posts to ``POST /v1/projects/{project_id}/quests`` and returns the
        created quest as a dict.  Extra keyword arguments are passed through
        as link fields.
        """
        payload: dict[str, Any] = {
            "title": title,
            "summary": summary,
            "status": status,
            "objectives": objectives,
            "tags": tags,
            **links,
        }
        return self._post("/quests", payload)

    def list_quests(self) -> list[dict[str, Any]]:
        """List quests for this project.

        Gets ``GET /v1/projects/{project_id}/quests`` and returns a list.
        """
        url = self._project_url("/quests")
        try:
            response = self._http.get(url)
            _raise_for_response(response, url)
        except KiteFrostError as exc:
            self._send_telemetry(exc)
            raise
        return response.json()  # type: ignore[no-any-return]

    # Pack-catalogue / selector-prompt methods intentionally NOT exposed on the
    # SDK: the SDK is a human developer's dev-time authoring tool (the caller
    # already knows their pack), whereas pack DISCOVERY (list all packs, pick
    # one) is an AI-agent runtime concern served by the REST + MCP surface
    # (GET /v1/packs, /v1/packs/selector-prompt) directly. See
    # docs/conventions/pack-flavored-rest-urls.md.

    # ------------------------------------------------------------------
    # Feedback (absolute)
    # ------------------------------------------------------------------

    def submit_feedback(
        self,
        signal: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit a feedback signal.

        Posts to ``POST /v1/feedback`` and returns
        ``{feedback_id, received_at}``.

        Args:
            signal: One of ``"error_telemetry"``, ``"bug_report"``, or
                ``"quality_rating"``.
            payload: Signal-specific payload.
            context: Optional context dict.
        """
        body: dict[str, Any] = {
            "schema_version": "1",
            "signal": signal,
            "payload": payload,
        }
        if context is not None:
            body["context"] = context
        return self._abs_post("/v1/feedback", body)

    def feedback_schema(self) -> dict[str, Any]:
        """Fetch the feedback JSON schema.

        Gets ``GET /v1/feedback/schema.json``.
        """
        return self._abs_get("/v1/feedback/schema.json")

    # ------------------------------------------------------------------
    # Import / continuity / export
    # ------------------------------------------------------------------

    def import_vtt(self, format: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Parse-only import from a VTT export (Pro-gated, ttrpg-gm).

        Posts to ``POST /v1/projects/{project_id}/import/vtt``. Flat canonical
        method per docs/conventions/pack-flavored-rest-urls.md (the pack lives
        in the URL, not the SDK function name).

        Args:
            format: One of ``"foundry"``, ``"foundry_json"``, or ``"roll20"``.
            payload: The VTT export payload to parse.
        """
        body: dict[str, Any] = {"format": format, "payload": payload}
        return self._post("/import/vtt", body)

    def check_continuity(self) -> dict[str, Any]:
        """Run a free continuity check on the project (game-narrative).

        Posts to ``POST /v1/projects/{project_id}/game-narrative/continuity/check``
        and returns the consistency report ``{findings, generated_at}``. Flat
        canonical method per docs/conventions/pack-flavored-rest-urls.md.
        """
        return self._post("/game-narrative/continuity/check", {})

    def export(
        self,
        format: str,
        entity_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Export project content in a target format.

        Posts to ``POST /v1/projects/{project_id}/export`` and returns
        ``{format, content, pack_name, entity_id, warnings}``.

        Args:
            format: Target format, e.g. ``"ink"``, ``"yarn"``,
                ``"unity_json"``, or ``"json"``.
            entity_id: Optional entity to scope the export to.
            options: Optional format-specific options.
        """
        body: dict[str, Any] = {
            "format": format,
            "entity_id": entity_id,
            "options": options,
        }
        return self._post("/export", body)

    def export_full(self) -> bytes:
        """Export the full project as a zip archive.

        Posts to ``POST /v1/projects/{project_id}/export/full`` and returns
        the raw zip bytes.
        """
        return self._post_bytes("/export/full", {})

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def checkpoint(self, name: str, description: str | None = None) -> dict[str, Any]:
        """Create a named checkpoint (snapshot) of the project state.

        Posts to ``POST /v1/projects/{project_id}/checkpoints``.

        Args:
            name: Stable checkpoint name (e.g. ``"before-dragon-fight"``).
            description: Optional notes about the project state.
        """
        payload: dict[str, Any] = {"name": name, "description": description}
        return self._post("/checkpoints", payload)

    def checkpoints(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List checkpoints for this project, newest first.

        Gets ``GET /v1/projects/{project_id}/checkpoints``.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        return self._get("/checkpoints", params=params)

    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        """Restore the project to a previously created checkpoint.

        Posts to ``POST /v1/projects/{project_id}/checkpoints/{checkpoint_id}/restore``.
        """
        return self._post(f"/checkpoints/{checkpoint_id}/restore", {})

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
