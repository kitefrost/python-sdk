"""Data models returned by the KiteFrost SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    """A project entity (NPC, location, faction, item, or player).

    Returned by :meth:`Project.entity`.
    """

    id: str
    external_id: str
    project_id: str
    type: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Entity":
        return cls(
            id=data.get("id", ""),
            external_id=data.get("external_id", ""),
            project_id=data.get("project_id") or data.get("project_id", ""),
            type=data.get("type", ""),
            name=data.get("name", ""),
            properties=data.get("properties", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class Event:
    """An immutable event record in the project timeline.

    Returned by :meth:`Project.event`.
    """

    id: str
    project_id: str
    type: str
    entity_id: str | None = None
    player_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            id=data.get("id", ""),
            project_id=data.get("project_id") or data.get("project_id", ""),
            type=data.get("type", ""),
            entity_id=data.get("entity_id"),
            player_id=data.get("player_id"),
            data=data.get("data", {}),
            created_at=data.get("created_at", ""),
        )


@dataclass
class ContextResult:
    """Project context assembled for a generation request.

    Returned by :meth:`Project.context`.
    """

    entity: dict[str, Any] = field(default_factory=dict)
    relevant_events: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "ContextResult":
        return cls(
            entity=data.get("entity", {}),
            relevant_events=data.get("relevant_events", []),
            facts=data.get("facts", []),
            summary=data.get("summary", ""),
        )


@dataclass
class GenerateResponse:
    """The response from a generation request.

    Returned by :meth:`Project.generate`.

    Attributes:
        text: The generated content (dialogue, narration, summary, etc.).
        context_used: Metadata about how much project context was used.
        tokens_used: Token usage breakdown (``input``, ``output`` keys).
    """

    text: str
    context_used: dict[str, Any] = field(default_factory=dict)
    tokens_used: dict[str, int] = field(default_factory=dict)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "GenerateResponse":
        return cls(
            text=data.get("content", ""),
            context_used=data.get("context_used", {}),
            tokens_used=data.get("tokens_used", {}),
        )


@dataclass
class TellResponse:
    """The response from a natural-language tell() request.

    Returned by :meth:`Project.tell` and :meth:`AsyncProject.tell`.

    Attributes:
        understood: Whether the engine successfully parsed the statement.
        actions: List of actions that were parsed and persisted (e.g. entity
            upserts, events recorded).
        entities_referenced: External IDs of entities mentioned in the statement.
        tokens_used: Token usage breakdown (``input``, ``output`` keys).
    """

    understood: bool
    actions: list[dict[str, Any]] = field(default_factory=list)
    entities_referenced: list[str] = field(default_factory=list)
    tokens_used: dict[str, int] = field(default_factory=dict)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "TellResponse":
        return cls(
            understood=data.get("understood", True),
            actions=data.get("actions", []),
            entities_referenced=data.get("entities_referenced", []),
            tokens_used=data.get("tokens_used", {}),
        )


@dataclass
class AskResponse:
    """The response from a natural-language ask() request.

    Returned by :meth:`Project.ask` and :meth:`AsyncProject.ask`.

    Attributes:
        answer: Factual summary answer drawn from project memory.
        in_character: In-character response voiced by the ``respond_as`` entity,
            or ``None`` if no entity was specified.
        context_used: Metadata about how much project context was consulted.
        tokens_used: Token usage breakdown (``input``, ``output`` keys).
    """

    answer: str
    in_character: str | None = None
    context_used: dict[str, Any] = field(default_factory=dict)
    tokens_used: dict[str, int] = field(default_factory=dict)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "AskResponse":
        return cls(
            answer=data.get("answer", ""),
            in_character=data.get("in_character"),
            context_used=data.get("context_used", {}),
            tokens_used=data.get("tokens_used", {}),
        )


@dataclass
class Job:
    """An asynchronous job submitted to the KiteFrost API.

    Returned by :meth:`Project.submit_job`, :meth:`Project.get_job`,
    :meth:`Project.cancel_job`, and :meth:`Project.poll_job`.

    Attributes:
        id: Server-assigned job identifier.
        status: Current job status: ``"queued"``, ``"processing"``,
            ``"completed"``, ``"failed"``, or ``"cancelled"``.
        project_id: The project this job belongs to.
        type: Job type (e.g. ``"generate"``).
        result: Output payload once the job completes, or ``None``.
        error: Human-readable error message if the job failed, or ``None``.
        created_at: ISO-8601 timestamp of when the job was enqueued.
        completed_at: ISO-8601 timestamp of when the job finished, or ``None``.
    """

    id: str
    status: str  # queued, processing, completed, failed, cancelled
    project_id: str
    type: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Job":
        # Accept either ``project_id`` (new v1 API) or ``project_id`` (legacy
        # wire-format from pre-rename servers) so the client stays
        # compatible with both during the rollover window.
        project_id = data.get("project_id") or data.get("project_id", "")
        return cls(
            id=data.get("id", ""),
            status=data.get("status", ""),
            project_id=project_id,
            type=data.get("type", ""),
            result=data.get("result"),
            error=data.get("error"),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass
class SchemaDefinition:
    """An entity schema stored for a project.

    Returned by :meth:`Project.define_schema`, :meth:`Project.get_schema`, and
    each entry in :meth:`Project.list_schemas`.

    Attributes:
        project_id: The project this schema belongs to.
        entity_type: The entity type this schema governs.
        required_properties: Property specs that must be present on upsert.
        optional_properties: Property specs that are validated only when present.
        created_at: ISO-8601 timestamp of when the schema was defined.
    """

    project_id: str
    entity_type: str
    required_properties: dict[str, Any] = field(default_factory=dict)
    optional_properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "SchemaDefinition":
        return cls(
            project_id=data.get("project_id") or data.get("project_id", ""),
            entity_type=data.get("entity_type", ""),
            required_properties=data.get("required_properties", {}),
            optional_properties=data.get("optional_properties", {}),
            created_at=data.get("created_at") or "",
        )
