"""Single auth provider for the shared core.

The Option-A DX win (D-PPI-SDK-BUNDLING): when a customer installs more than one
per-pack SDK, they share ONE AuthProvider instance (one credential + one
in-flight refresh) instead of each pack carrying its own token state.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class AuthProvider(Protocol):
    """Supplies the Authorization header and a one-shot refresh after a 401."""

    def auth_header(self) -> str:
        """Return the current ``Authorization`` header value."""
        ...

    def refresh(self) -> str | None:
        """Force a one-shot credential refresh and return the new header.

        Returns ``None`` when this provider cannot refresh (static API keys),
        so the transport surfaces the 401 unchanged.
        """
        ...


class ApiKeyAuth:
    """Static API-key auth. Cannot refresh; a 401 is surfaced as AuthError."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def auth_header(self) -> str:
        return f"Bearer {self._api_key}"

    def refresh(self) -> str | None:
        return None


class RefreshableTokenAuth:
    """Bearer-token auth with one-shot refresh via a caller-supplied callback."""

    def __init__(self, initial_token: str, refresh_fn: Callable[[], str]) -> None:
        self._token = initial_token
        self._refresh_fn = refresh_fn

    def auth_header(self) -> str:
        return f"Bearer {self._token}"

    def refresh(self) -> str | None:
        # Not concurrency-coalesced (unlike the TS RefreshableTokenAuth's inflight
        # promise): the sync httpx.Client model serializes requests, so parallel
        # 401s cannot occur. If an async Python transport is ever added, wrap
        # refresh_fn so concurrent 401s share one refresh.
        self._token = self._refresh_fn()
        return f"Bearer {self._token}"
