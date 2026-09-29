"""Shared HTTP transport for the core.

Owns header building, error mapping, and the one-shot 401 refresh (mirrors the
hand-written ``kitefrost`` SDK ``_transport`` + ``http.ts``). A single instance
is shared across every per-pack resource client so they pool one auth provider.
"""

from __future__ import annotations

from typing import Any

import httpx

from .auth import AuthProvider
from .exceptions import (
    AuthError,
    KiteFrostError,
    NotFoundError,
    RateLimited,
    ServerError,
    ValidationError,
)
from .version import CORE_VERSION

DEFAULT_BASE_URL = "https://api.kitefrost.ai"

#: Environment override for the API origin. FND-20260923-CC7: the default host does
#: not serve every environment (alpha testers run against a staging API), and the
#: SDK offered no way to repoint it short of editing code. Precedence: an explicit
#: `base_url=` argument, then this variable, then DEFAULT_BASE_URL.
BASE_URL_ENV = "KITEFROST_BASE_URL"


def resolve_base_url(base_url: str | None) -> str:
    """Explicit argument > KITEFROST_BASE_URL > DEFAULT_BASE_URL."""
    if base_url:
        return base_url
    import os

    return os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
DEFAULT_TIMEOUT = 30.0


def _raise_for_response(response: httpx.Response) -> None:
    """Map an error response to a typed core exception."""
    if response.is_success:
        return

    status = response.status_code
    body: dict[str, Any] = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            body = parsed
        detail = body.get("detail") or body.get("error") or body.get("message") or response.text
    except Exception:
        detail = response.text

    feedback_id = body.get("feedback_id") if isinstance(body, dict) else None

    if status in (401, 403):
        raise AuthError(detail, status_code=status, feedback_id=feedback_id)
    if status == 404:
        raise NotFoundError(detail, status_code=404, feedback_id=feedback_id)
    if status == 422:
        raise ValidationError(detail, status_code=422, feedback_id=feedback_id)
    if status == 429:
        retry_after: int | None = None
        raw = response.headers.get("Retry-After")
        if raw is not None:
            try:
                retry_after = int(raw)
            except ValueError:
                pass
        raise RateLimited(detail, retry_after=retry_after, feedback_id=feedback_id)
    if status >= 500:
        raise ServerError(detail, status_code=status, feedback_id=feedback_id)
    raise KiteFrostError(detail, status_code=status, feedback_id=feedback_id)


class Transport:
    """Synchronous HTTP transport with one-shot 401 refresh."""

    def __init__(
        self,
        auth: AuthProvider,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._auth = auth
        self._user_agent = user_agent or f"kitefrost-core/{CORE_VERSION}"
        # A single httpx.Client = one connection pool shared by all resources.
        self._client = client or httpx.Client(base_url=resolve_base_url(base_url).rstrip("/"), timeout=timeout)

    def _headers(self, auth_header: str) -> dict[str, str]:
        return {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self._client.request(
            method,
            path,
            json=json,
            params=params,
            headers=self._headers(self._auth.auth_header()),
        )

        if response.status_code == 401:
            refreshed = self._auth.refresh()
            if refreshed:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=self._headers(refreshed),
                )

        _raise_for_response(response)

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, json=json or {})

    def patch(self, path: str, json: dict[str, Any]) -> Any:
        return self.request("PATCH", path, json=json)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def close(self) -> None:
        self._client.close()
