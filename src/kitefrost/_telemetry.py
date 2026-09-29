"""SDK auto-telemetry for error reporting (C-FB3).

Fire-and-forget error telemetry sender. Never raises, never retries,
never blocks the caller beyond 100ms.

Design reference:
  docs/design/concepts/feedback-channels/design.md section 1
"""

from __future__ import annotations

import logging
import os
import platform
import sys
from typing import Any

import httpx

from ._transport import _SDK_VERSION
from .exceptions import KiteFrostError

logger = logging.getLogger("kitefrost")

# In-memory dedup: set of API key prefixes that have already seen the banner.
_telemetry_banner_shown: set[str] = set()

_TELEMETRY_TIMEOUT = 0.1  # 100ms - per CDS design


def _banner_key(api_key: str) -> str:
    """Derive the dedup key for the telemetry banner.

    Uses the full key string so that different keys within the same
    process each show the banner once.
    """
    return api_key


def _resolve_report_errors(code_level: bool) -> bool:
    """Resolve the effective report_errors flag.

    ``KITEFROST_REPORT_ERRORS=false`` overrides a code-level ``True``.
    """
    env_val = os.environ.get("KITEFROST_REPORT_ERRORS", "").lower()
    if env_val == "false":
        return False
    return code_level


def warn_telemetry_enabled_once(api_key: str) -> None:
    """Log the first-run telemetry banner once per API key per process."""
    key = _banner_key(api_key)
    if key in _telemetry_banner_shown:
        return
    _telemetry_banner_shown.add(key)
    msg = (
        "[kitefrost] Error telemetry enabled. "
        "We collect crash info (not conversation content) to fix bugs. "
        "Opt out: KiteFrost(..., report_errors=False) "
        "or set KITEFROST_REPORT_ERRORS=false. "
        "Docs: https://docs.kitefrost.ai/telemetry"
    )
    logger.info(msg)


def _build_telemetry_payload(
    exc: KiteFrostError,
    report_context: bool,
) -> dict[str, Any]:
    """Build the ``FeedbackSubmission`` payload for an error."""
    payload: dict[str, Any] = {
        "schema_version": "1",
        "signal": "error_telemetry",
        "ref": getattr(exc, "request_id", None),
        "payload": {
            "error": exc.to_envelope(),
            "client": {
                "sdk": "kitefrost-python",
                "sdk_version": _SDK_VERSION,
                "runtime": f"python/{sys.version_info.major}.{sys.version_info.minor}",
                "os": platform.system().lower(),
            },
            "attempt": getattr(exc, "attempt", 1),
            "latency_ms": getattr(exc, "latency_ms", None),
        },
    }
    if report_context and getattr(exc, "request_body", None) is not None:
        payload["context"] = {"request_body": exc.request_body}
    return payload


def _auth_headers(api_key: str | None) -> dict[str, str]:
    """Build Authorization header if API key available."""
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


def send_telemetry_sync(
    exc: KiteFrostError,
    base_url: str,
    report_context: bool,
    api_key: str | None = None,
) -> None:
    """Fire-and-forget synchronous telemetry. Never raises."""
    try:
        payload = _build_telemetry_payload(exc, report_context)
        headers = _auth_headers(api_key)
        with httpx.Client(timeout=_TELEMETRY_TIMEOUT) as client:
            client.post(f"{base_url}/v1/feedback", json=payload, headers=headers)
    except Exception:
        pass  # fire-and-forget - telemetry must never break caller


async def send_telemetry_async(
    exc: KiteFrostError,
    base_url: str,
    report_context: bool,
    api_key: str | None = None,
) -> None:
    """Fire-and-forget async telemetry. Never raises."""
    try:
        payload = _build_telemetry_payload(exc, report_context)
        headers = _auth_headers(api_key)
        async with httpx.AsyncClient(timeout=_TELEMETRY_TIMEOUT) as client:
            await client.post(f"{base_url}/v1/feedback", json=payload, headers=headers)
    except Exception:
        pass  # fire-and-forget - telemetry must never break caller


def reset_banner_state() -> None:
    """Clear the banner dedup set. For testing only."""
    _telemetry_banner_shown.clear()
