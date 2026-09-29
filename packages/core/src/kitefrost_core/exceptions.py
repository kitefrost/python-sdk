"""Typed exceptions for the KiteFrost shared core.

Mirrors the hand-written ``kitefrost`` SDK exception surface so per-pack SDKs
built on the core keep the same DX (KiteFrostError base + AuthError /
ProjectNotFound / ValidationError / RateLimited / ServerError, plus the
``feedback_id`` field from C-FB1).
"""

from __future__ import annotations


class KiteFrostError(Exception):
    """Base exception for all KiteFrost core errors.

    ``feedback_id`` (C-FB1) is a server-issued ULID (prefix ``fbk_``) that
    uniquely identifies this error instance. Pass it back via
    ``POST /v1/feedback`` to annotate or bug-report this specific failure.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        feedback_id: str | None = None,
    ) -> None:
        # The API's error envelope is structured: `detail` is often a dict such as
        # {"message": ..., "code": ...}, not a string. Stored raw, it made __str__
        # return a dict, so `str(exc)` raised and tracebacks showed
        # "<exception str() failed>" - a customer could not read the error at all
        # (FND-20260923-7A0). Keep the raw payload, but always hold a string.
        self.detail = message
        if not isinstance(message, str):
            if isinstance(message, dict) and isinstance(message.get("message"), str):
                message = message["message"]
            else:
                message = repr(message)
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.feedback_id = feedback_id

    def __str__(self) -> str:
        base = self.message
        if self.feedback_id:
            base = f"{base} [feedback_id={self.feedback_id}]"
        return base

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        return (
            f"{cls}(message={self.message!r}, status_code={self.status_code}, "
            f"feedback_id={self.feedback_id!r})"
        )


class AuthError(KiteFrostError):
    """Raised when credentials are missing, invalid, or lack permission (401/403)."""


class NotFoundError(KiteFrostError):
    """Raised when the requested resource does not exist (404)."""


class ValidationError(KiteFrostError):
    """Raised when the API rejects the request payload (422)."""


class RateLimited(KiteFrostError):
    """Raised when the API rate limit is exceeded (429).

    Inspect ``retry_after`` for the suggested back-off (seconds).
    """

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        feedback_id: str | None = None,
    ) -> None:
        super().__init__(message, status_code=429, feedback_id=feedback_id)
        self.retry_after = retry_after

    def __repr__(self) -> str:
        return (
            f"RateLimited(message={self.message!r}, retry_after={self.retry_after}, "
            f"feedback_id={self.feedback_id!r})"
        )


class ServerError(KiteFrostError):
    """Raised on unexpected 5xx responses from the KiteFrost API."""
