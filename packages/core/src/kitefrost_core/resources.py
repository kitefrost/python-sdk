"""Shared-core resource clients.

These cover the SHARED_TAGS surface (src/engine/api/pack_manifest.py: auth,
keys, billing, projects, events, context, byok, webhooks, health, ...) that is
identical across every pack and is therefore owned by the core, NOT generated
per pack (PPI-3). Pack-specific resources are generated on top by STREAM-003
TASK-003. NO pack-specific code lives here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .transport import Transport


class _BaseResource:
    def __init__(self, transport: Transport) -> None:
        self._t = transport


class AuthResource(_BaseResource):
    """auth tag - whoami / token introspection."""

    def whoami(self) -> Any:
        return self._t.get("/v1/auth/whoami")


class KeysResource(_BaseResource):
    """keys tag - API key management."""

    def list(self) -> Any:
        return self._t.get("/v1/keys")

    def create(self, body: dict[str, Any]) -> Any:
        return self._t.post("/v1/keys", body)

    def revoke(self, key_id: str) -> Any:
        return self._t.delete(f"/v1/keys/{quote(key_id)}")


class BillingResource(_BaseResource):
    """billing tag - usage + balance."""

    def usage(self) -> Any:
        return self._t.get("/v1/billing/usage")


class ProjectsResource(_BaseResource):
    """projects tag - project lifecycle (shared across all packs)."""

    def list(self) -> Any:
        return self._t.get("/v1/projects")

    def get(self, project_id: str) -> Any:
        return self._t.get(f"/v1/projects/{quote(project_id)}")

    def create(self, body: dict[str, Any]) -> Any:
        return self._t.post("/v1/projects", body)


class EventsResource(_BaseResource):
    """events tag - client/telemetry event ingestion."""

    def send(self, body: dict[str, Any]) -> Any:
        return self._t.post("/v1/events", body)


class ContextResource(_BaseResource):
    """context tag - shared context retrieval."""

    def get(self, project_id: str, params: dict[str, Any] | None = None) -> Any:
        return self._t.get(f"/v1/projects/{quote(project_id)}/context", params=params)


class ByokResource(_BaseResource):
    """byok tag - bring-your-own-key provider credentials."""

    def list(self) -> Any:
        return self._t.get("/v1/byok")

    def set(self, body: dict[str, Any]) -> Any:
        return self._t.post("/v1/byok", body)


class WebhooksResource(_BaseResource):
    """webhooks tag - webhook subscription management."""

    def list(self) -> Any:
        return self._t.get("/v1/webhooks")

    def create(self, body: dict[str, Any]) -> Any:
        return self._t.post("/v1/webhooks", body)

    def delete(self, webhook_id: str) -> Any:
        return self._t.delete(f"/v1/webhooks/{quote(webhook_id)}")


class HealthResource(_BaseResource):
    """health tag - liveness probe (the canonical core smoke endpoint)."""

    def check(self) -> Any:
        # Liveness probe is served at the root `/health` (the API does NOT
        # expose `/v1/health` - that 404s). Found by tests/sdk_live.
        return self._t.get("/health")
