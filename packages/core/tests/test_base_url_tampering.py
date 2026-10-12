"""KITEFROST_BASE_URL tampering - what a rogue API host can get out of the SDK.

The env var repoints every SDK request (explicit ``base_url=`` > KITEFROST_BASE_URL >
production). It is read on the SDK user's machine only: our API never sees it and
never calls it, so pointing it at your own server cannot make *our* server send you
anything. The threat runs the other way - whoever controls the variable (a tester's
typo, a malicious ``.env`` in a cloned starter repo, a lookalike "staging" URL posted
in a channel) receives the user's credentials and payloads, and controls every
response the SDK parses.

These tests stand up a real local HTTP server as the rogue host and record exactly
what arrives. Two kinds of test:

* **Pins** (pass today) - document what a rogue host receives and which defences
  already hold (no redirect following, minimal headers).
* **Fixed gaps** - protections that were missing when this file was written
  (2026-10-12) and landed in core 1.x the same day: unsafe schemes and embedded
  credentials are refused, foreign hosts warn with their real name, and server
  error text cannot inject control characters.
"""

from __future__ import annotations

import json
import threading
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from kitefrost_core import AuthError, KiteFrostCore, KiteFrostError, RefreshableTokenAuth

API_KEY = "sk_live_victim_key_0123456789"


class _Rogue:
    """A local HTTP server that records every request and replays a scripted reply."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.status = 200
        self.body: bytes = b"{}"
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        rogue = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                rogue.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": raw,
                    }
                )
                self.send_response(rogue.status)
                for k, v in rogue.headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(rogue.body)))
                self.end_headers()
                self.wfile.write(rogue.body)

            do_GET = do_POST = do_PATCH = do_DELETE = _handle

            def log_message(self, *args: Any) -> None:  # keep test output clean
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def rogue():
    server = _Rogue()
    yield server
    server.close()


@pytest.fixture
def second_rogue():
    server = _Rogue()
    yield server
    server.close()


@pytest.fixture
def core_via_env(monkeypatch, rogue):
    """A core configured ONLY through the env var, the way a tester is told to do it."""
    monkeypatch.setenv("KITEFROST_BASE_URL", rogue.url)
    core = KiteFrostCore(api_key=API_KEY)
    yield core
    core.close()


# --------------------------------------------------------------------------- pins


def test_env_var_routes_the_api_key_to_whatever_host_it_names(rogue, core_via_env):
    """THREAT PIN: the variable is a credential-routing switch.

    Whoever sets KITEFROST_BASE_URL receives the bearer key verbatim on the first
    call. The key then works against the real API (billing + data under the
    victim's account). This is inherent to any base-URL override; the mitigations
    are the gap tests below, not this one.
    """
    core_via_env.auth.whoami()
    assert rogue.requests[0]["headers"]["authorization"] == f"Bearer {API_KEY}"


def test_byok_set_forwards_third_party_provider_keys_to_the_rogue_host(rogue, core_via_env):
    """THREAT PIN: blast radius is wider than the KiteFrost key.

    ``byok.set`` sends the user's own LLM provider key in the body, so a rogue
    host also harvests (e.g.) an Anthropic/OpenAI key the user never meant to
    expose to a third party.
    """
    core_via_env.byok.set({"provider": "anthropic", "api_key": "provider-secret-xyz"})
    assert b"provider-secret-xyz" in rogue.requests[0]["body"]


def test_rogue_host_sees_only_the_documented_headers(rogue, core_via_env):
    """Nothing internal rides along: no hostnames, env dumps, internal hosts or tracing ids.

    The SDK sends exactly Authorization, Content-Type, Accept, User-Agent (plus the
    transport's own Host/Accept-Encoding/Connection/Content-Length). The User-Agent
    carries only the package name + version - no OS, Python build, or machine name.
    """
    core_via_env.health.check()
    headers = rogue.requests[0]["headers"]
    allowed = {
        "host",
        "authorization",
        "content-type",
        "accept",
        "user-agent",
        "accept-encoding",
        "connection",
        "content-length",
    }
    assert set(headers) <= allowed, f"unexpected headers leak: {set(headers) - allowed}"
    assert headers["user-agent"].startswith("kitefrost-core/")
    assert " " not in headers["user-agent"], "User-Agent must not grow platform details"


def test_redirects_are_not_followed_so_the_key_does_not_hop_hosts(
    rogue, second_rogue, core_via_env
):
    """A 3xx from the configured host must not carry the key to a third host.

    httpx does not follow redirects unless asked; this pins that, so a later
    ``follow_redirects=True`` (a common "fix" for a 301) cannot silently start
    forwarding Authorization to whatever Location a server names.
    """
    rogue.status = 307
    rogue.headers = {"Location": f"{second_rogue.url}/v1/auth/whoami"}
    with pytest.raises(KiteFrostError):
        core_via_env.auth.whoami()
    assert second_rogue.requests == []


def test_rogue_401_triggers_refresh_and_receives_the_fresh_token(monkeypatch, rogue):
    """THREAT PIN: refreshable auth hands the rogue host a SECOND credential.

    A 401 from the configured host makes the SDK mint a new token via the
    caller's refresh callback and resend - to the same rogue host. A rogue
    server can therefore farm fresh tokens on demand.
    """
    monkeypatch.setenv("KITEFROST_BASE_URL", rogue.url)
    rogue.status = 401
    core = KiteFrostCore(auth=RefreshableTokenAuth("tok-1", lambda: "tok-2-fresh"))
    with pytest.raises(AuthError):
        core.auth.whoami()
    core.close()
    sent = [r["headers"]["authorization"] for r in rogue.requests]
    assert sent == ["Bearer tok-1", "Bearer tok-2-fresh"]


def test_userinfo_lookalike_really_routes_to_the_attacker_host():
    """Why userinfo URLs are refused: ``https://api.kitefrost.ai@evil.example``
    reads as our host to a human but the request goes to ``evil.example``."""
    assert httpx.URL("https://api.kitefrost.ai@evil.example").host == "evil.example"


# ------------------------------------------------- fixed gaps (2026-10-12)
# Each was an xfail(strict) gap first; the reason text stays as the record.


@pytest.fixture(autouse=True)
def _fresh_warning_memory():
    """The foreign-host warning fires once per host per process; reset between tests."""
    from kitefrost_core import transport

    transport._warned_hosts.clear()
    yield
    transport._warned_hosts.clear()


# GAP (fixed): the SDK accepted any scheme/host from KITEFROST_BASE_URL. Plain http
# to a non-loopback host sent the bearer key in cleartext; file:// reached httpx.
@pytest.mark.parametrize(
    "url",
    [
        "http://api.kitefrost.ai",
        "http://evil.example",
        "file:///etc/passwd",
        "ftp://evil.example",
        "javascript:alert(1)",
        "https://user:pw@api.kitefrost.ai",
        "https://api.kitefrost.ai@evil.example",
        "not a url",
    ],
)
def test_construction_refuses_unsafe_urls(monkeypatch, rogue, url):
    monkeypatch.setenv("KITEFROST_BASE_URL", url)
    with pytest.raises(ValueError):
        KiteFrostCore(api_key=API_KEY)


def test_explicit_base_url_argument_is_checked_too():
    with pytest.raises(ValueError):
        KiteFrostCore(api_key=API_KEY, base_url="http://evil.example")


@pytest.mark.parametrize(
    "url", ["http://localhost:8000", "http://127.0.0.1:9", "http://[::1]:8000"]
)
def test_plain_http_is_allowed_for_loopback_dev_servers(monkeypatch, recwarn, url):
    monkeypatch.setenv("KITEFROST_BASE_URL", url)
    KiteFrostCore(api_key=API_KEY).close()
    assert not [w for w in recwarn if issubclass(w.category, UserWarning)]


# GAP (fixed): a non-KiteFrost host was used silently. Now it warns once, naming
# the REAL parsed host. Warn, not block: proxies are legitimate.
@pytest.mark.parametrize(
    ("url", "real_host"),
    [
        ("https://api.kitefrost.ai.evil.example", "api.kitefrost.ai.evil.example"),
        ("https://evil.example/api.kitefrost.ai", "evil.example"),
        ("https://api-kitefrost.ai", "api-kitefrost.ai"),
        ("https://kitefrost.ai.evil.example", "kitefrost.ai.evil.example"),
        ("https://evilkitefrost.ai", "evilkitefrost.ai"),
    ],
)
def test_non_kitefrost_override_warns_with_the_real_host(monkeypatch, url, real_host):
    monkeypatch.setenv("KITEFROST_BASE_URL", url)
    with pytest.warns(UserWarning, match=real_host.replace(".", r"\.")):
        KiteFrostCore(api_key=API_KEY).close()


def test_foreign_host_warning_fires_once_per_host(monkeypatch, recwarn):
    monkeypatch.setenv("KITEFROST_BASE_URL", "https://proxy.example")
    for _ in range(3):
        KiteFrostCore(api_key=API_KEY).close()
    assert len([w for w in recwarn if issubclass(w.category, UserWarning)]) == 1


def test_genuine_kitefrost_hosts_do_not_warn(monkeypatch, recwarn):
    """The real hosts must stay silent."""
    for url in (
        "https://api.kitefrost.ai",
        "https://api-staging.kitefrost.ai",
        "https://API.KiteFrost.ai.",
    ):
        monkeypatch.setenv("KITEFROST_BASE_URL", url)
        KiteFrostCore(api_key=API_KEY).close()
    monkeypatch.delenv("KITEFROST_BASE_URL")
    KiteFrostCore(api_key=API_KEY).close()  # the default
    assert not [w for w in recwarn if issubclass(w.category, UserWarning)]


# GAP (fixed): error text from the server landed verbatim in the exception message,
# so a rogue host could clear the terminal and forge log lines.
def test_server_error_text_cannot_inject_control_characters(rogue, core_via_env):
    rogue.status = 400
    rogue.body = json.dumps(
        {"detail": "bad\x1b[2J\nINFO 2026-10-12 payment ok user=admin", "feedback_id": "fbk_\r\nX"}
    ).encode()
    with pytest.raises(KiteFrostError) as exc:
        core_via_env.auth.whoami()
    message = str(exc.value)
    assert "\x1b" not in message and "\n" not in message and "\r" not in message
    assert "payment ok" in message  # escaped and visible, not dropped


def test_ordinary_error_text_is_unchanged(rogue, core_via_env):
    rogue.status = 400
    rogue.body = json.dumps({"detail": "Project 'Ünïcode \u2013 ok' not found"}).encode()
    with pytest.raises(KiteFrostError) as exc:
        core_via_env.auth.whoami()
    assert exc.value.message == "Project 'Ünïcode \u2013 ok' not found"


# ------------------------------------- second-model review findings (2026-10-12)


@pytest.mark.parametrize(
    "url",
    ["http://127.evil.example", "http://127.0.0.1.evil.example", "http://localhost.evil.example"],
)
def test_loopback_lookalike_dns_names_do_not_get_the_http_exemption(monkeypatch, url):
    """A name starting '127.' is DNS, not loopback - it can resolve to any server."""
    monkeypatch.setenv("KITEFROST_BASE_URL", url)
    with pytest.raises(ValueError):
        KiteFrostCore(api_key=API_KEY)


def test_loopback_lookalike_over_https_still_warns(monkeypatch):
    monkeypatch.setenv("KITEFROST_BASE_URL", "https://127.evil.example")
    with pytest.warns(UserWarning, match=r"127\.evil\.example"):
        KiteFrostCore(api_key=API_KEY).close()


@pytest.mark.parametrize("url", ["http://[0:0:0:0:0:0:0:1]:8000", "http://[::ffff:127.0.0.1]:8000"])
def test_ipv6_loopback_spellings_are_loopback(monkeypatch, recwarn, url):
    monkeypatch.setenv("KITEFROST_BASE_URL", url)
    KiteFrostCore(api_key=API_KEY).close()
    assert not [w for w in recwarn if issubclass(w.category, UserWarning)]


def test_warning_escalated_to_error_keeps_failing_on_retry():
    from kitefrost_core.transport import check_base_url

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        for _ in range(2):
            with pytest.raises(UserWarning):
                check_base_url("https://evil.example")


@pytest.mark.parametrize("ch", ["\u202e", "\u200b", "\u2066", "\u0085", "\u009b", "\u2028"])
def test_invisible_and_bidi_characters_are_escaped(ch):
    assert ch not in KiteFrostError(f"status: {ch}DEIFIREV").message
