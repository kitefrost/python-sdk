"""Unit tests for the kitefrost-core shared runtime.

Uses httpx.MockTransport so no network is touched. Covers the smoke path
(auth + core endpoint), one-shot 401 refresh, static-key 401 surfacing, and
error mapping.
"""

from __future__ import annotations

import httpx
import pytest

from kitefrost_core import (
    CORE_VERSION,
    ApiKeyAuth,
    AuthError,
    KiteFrostCore,
    RateLimited,
    RefreshableTokenAuth,
    ValidationError,
    assert_core_version_compatible,
)


def _make_core(handler, auth=None, api_key="sk_test"):
    mock = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://api.example", transport=mock)
    if auth is not None:
        return KiteFrostCore(auth=auth, http_client=client)
    return KiteFrostCore(api_key=api_key, http_client=client)


def test_version_stamp_and_compat():
    # Must equal the version this package publishes as, not a literal (a literal
    # broke on every version bump).
    import re
    from pathlib import Path

    toml = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert CORE_VERSION == re.search(r'^version\s*=\s*"([^"]+)"', toml, re.M).group(1)
    assert_core_version_compatible(1)
    with pytest.raises(RuntimeError, match="version skew"):
        assert_core_version_compatible(2)


def test_requires_api_key_or_auth():
    with pytest.raises(ValueError, match="requires either"):
        KiteFrostCore()


def test_smoke_core_only_health_call():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"status": "ok"})

    core = _make_core(handler)
    assert core.health.check() == {"status": "ok"}
    # FND-20260829-193: the API only ever served /health at the root, never
    # /v1/health. resources.py was fixed to call '/health'; this assertion
    # was left asserting the old (404-ing) path.
    assert seen["url"] == "https://api.example/health"
    assert seen["auth"] == "Bearer sk_test"


def test_one_shot_401_refresh_retries():
    calls = {"n": 0}
    refreshes = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.headers.get("Authorization") == "Bearer stale":
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    def refresh_fn():
        refreshes["n"] += 1
        return "fresh"

    auth = RefreshableTokenAuth("stale", refresh_fn)
    core = _make_core(handler, auth=auth)
    assert core.billing.usage() == {"ok": True}
    assert calls["n"] == 2
    assert refreshes["n"] == 1


def test_static_key_401_surfaces_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    core = _make_core(handler, auth=ApiKeyAuth("nope"))
    with pytest.raises(AuthError):
        core.auth.whoami()


def test_error_mapping_422_and_429():
    def handler_422(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "bad payload"})

    core = _make_core(handler_422)
    with pytest.raises(ValidationError):
        core.projects.list()

    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow"}, headers={"Retry-After": "7"})

    core = _make_core(handler_429)
    with pytest.raises(RateLimited) as exc:
        core.events.send({"kind": "x"})
    assert exc.value.retry_after == 7


# FND-20260923-CC7 - the API origin must be repointable without editing code.
def test_base_url_precedence_explicit_env_default(monkeypatch):
    from kitefrost_core.transport import DEFAULT_BASE_URL, resolve_base_url

    monkeypatch.delenv("KITEFROST_BASE_URL", raising=False)
    assert resolve_base_url(None) == DEFAULT_BASE_URL

    monkeypatch.setenv("KITEFROST_BASE_URL", "https://api.example.test")
    assert resolve_base_url(None) == "https://api.example.test"

    # an explicit argument still wins over the environment
    assert resolve_base_url("https://example.test") == "https://example.test"


def test_client_honours_env_base_url(monkeypatch):
    from kitefrost_core import KiteFrostCore

    monkeypatch.setenv("KITEFROST_BASE_URL", "https://api.example.test")
    client = KiteFrostCore(api_key="sk_test")
    assert str(client.transport._client.base_url).rstrip("/") == "https://api.example.test"


# FND-20260923-7A0 - a structured error detail must still print.
def test_exception_str_with_dict_detail():
    from kitefrost_core.exceptions import AuthError, KiteFrostError, RateLimited

    detail = {"message": "Too many requests", "code": "rate_limited"}
    e = RateLimited(detail, retry_after=3)
    assert str(e) == "Too many requests"
    assert e.detail == detail and e.retry_after == 3
    assert str(KiteFrostError({"code": "x"})) == "{'code': 'x'}"  # no message key -> repr
    assert str(AuthError("plain", status_code=401)) == "plain"
