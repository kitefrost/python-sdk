"""Single configuration entry for the shared core.

Constructing one ``KiteFrostCore`` yields ONE auth provider + one Transport
(one httpx connection pool) that every shared-core resource client reuses.
Per-pack SDKs accept an existing ``KiteFrostCore`` instance so a customer
running multiple packs shares a single auth provider / connection pool - the
Option-A DX win (D-PPI-SDK-BUNDLING).
"""

from __future__ import annotations

import httpx

from .auth import ApiKeyAuth, AuthProvider
from .resources import (
    AuthResource,
    BillingResource,
    ByokResource,
    ContextResource,
    EventsResource,
    HealthResource,
    KeysResource,
    ProjectsResource,
    WebhooksResource,
)
from .transport import DEFAULT_TIMEOUT, Transport
from .version import CORE_VERSION


class KiteFrostCore:
    """Shared-core entry point. Provide ``api_key`` OR an ``auth`` provider."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        auth: AuthProvider | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
        user_agent: str | None = None,
    ) -> None:
        if api_key is None and auth is None:
            raise ValueError("KiteFrostCore requires either `api_key` or `auth`.")

        self.version = CORE_VERSION
        auth_provider: AuthProvider = auth if auth is not None else ApiKeyAuth(api_key)  # type: ignore[arg-type]

        self.transport = Transport(
            auth=auth_provider,
            base_url=base_url,
            timeout=timeout,
            client=http_client,
            user_agent=user_agent or f"kitefrost-core/{CORE_VERSION}",
        )

        self.auth = AuthResource(self.transport)
        self.keys = KeysResource(self.transport)
        self.billing = BillingResource(self.transport)
        self.projects = ProjectsResource(self.transport)
        self.events = EventsResource(self.transport)
        self.context = ContextResource(self.transport)
        self.byok = ByokResource(self.transport)
        self.webhooks = WebhooksResource(self.transport)
        self.health = HealthResource(self.transport)

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "KiteFrostCore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
