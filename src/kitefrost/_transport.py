"""Shared HTTP transport helpers (error mapping, request building)."""

from __future__ import annotations

from typing import Any

import httpx

from .exceptions import (
    _CODE_TO_EXCEPTION,
    AuthError,
    EntityNotFound,
    EntitySchemaError,
    KiteFrostError,
    ProjectNotFound,
    RateLimited,
    ServerError,
    ValidationError,
)

DEFAULT_BASE_URL = "https://api.kitefrost.ai"
DEFAULT_TIMEOUT = 30.0
_SDK_VERSION = "1.0.0"


def _default_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"kitefrost-python/{_SDK_VERSION}",
    }


def _raise_for_response(response: httpx.Response, path: str) -> None:
    """Map error responses to typed SDK exceptions.

    Checks the ``code`` field in the response body first (code-first lookup),
    falling back to HTTP status code mapping for backwards compatibility.
    """
    if response.is_success:
        return

    status = response.status_code
    body: dict[str, Any] = {}
    try:
        body = response.json()
        detail: str = (
            body.get("detail") or body.get("error") or body.get("message") or response.text
        )
    except Exception:
        detail = response.text

    # Code-first: check the machine-readable code field before HTTP status
    error_code: str | None = body.get("code") if isinstance(body, dict) else None
    feedback_id: str | None = body.get("feedback_id") if isinstance(body, dict) else None
    if error_code and error_code in _CODE_TO_EXCEPTION:
        exc_cls = _CODE_TO_EXCEPTION[error_code]
        if exc_cls is RateLimited:
            retry_after: int | None = None
            raw = response.headers.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    pass
            raise RateLimited(detail, retry_after=retry_after, feedback_id=feedback_id)
        raise exc_cls(detail, status_code=status, feedback_id=feedback_id)

    # Fall back to HTTP-status-based mapping
    if status in (401, 403):
        raise AuthError(detail, status_code=status, feedback_id=feedback_id)

    if status == 404:
        # Differentiate between project-not-found and entity-not-found.
        # Entity routes are pack-prefix paths (e.g. /generic/npcs); the
        # error-detail check is the disambiguator when the URL alone
        # isn't enough (a 404 on /projects/{pid}/<anything> could be
        # either the project or the entity under it).
        if "entity" in detail.lower():
            raise EntityNotFound(detail, status_code=404, feedback_id=feedback_id)
        raise ProjectNotFound(detail, status_code=404, feedback_id=feedback_id)

    if status == 422:
        # If the detail is a dict with an "errors" list, it's an entity schema violation
        try:
            body_detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(body_detail, dict) and "errors" in body_detail:
                message = body_detail.get("message", "Schema validation failed")
                errors: list[str] = body_detail.get("errors", [])
                # Extract entity_type from the message if possible
                import re as _re

                m = _re.search(r"type '([^']+)'", message)
                entity_type = m.group(1) if m else ""
                raise EntitySchemaError(
                    message,
                    entity_type=entity_type,
                    errors=errors,
                    feedback_id=feedback_id,
                )
        except EntitySchemaError:
            raise
        except Exception:
            pass
        raise ValidationError(detail, status_code=422, feedback_id=feedback_id)

    if status == 429:
        retry_after_fallback: int | None = None
        raw = response.headers.get("Retry-After")
        if raw is not None:
            try:
                retry_after_fallback = int(raw)
            except ValueError:
                pass
        raise RateLimited(
            detail,
            retry_after=retry_after_fallback,
            feedback_id=feedback_id,
        )

    if status >= 500:
        raise ServerError(detail, status_code=status, feedback_id=feedback_id)

    raise KiteFrostError(detail, status_code=status, feedback_id=feedback_id)


def _resolve_entity_id(entity: Any) -> str:
    """Accept either a string external_id or an Entity object."""
    from .models import Entity  # local import to avoid circular

    if isinstance(entity, Entity):
        return entity.external_id
    return str(entity)


def _resolve_player_id(player: Any) -> str:
    return str(player)
