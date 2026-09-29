"""Typed exceptions for the KiteFrost SDK."""

from __future__ import annotations


class KiteFrostError(Exception):
    """Base exception for all KiteFrost SDK errors.

    ``feedback_id`` (C-FB1) is a server-issued ULID (prefix ``fbk_``) that
    uniquely identifies this error instance. Pass it back via
    ``POST /v1/feedback`` to annotate or bug-report this specific failure.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        feedback_id: str | None = None,
        request_id: str | None = None,
        request_body: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.feedback_id = feedback_id
        self.request_id = request_id
        self.request_body = request_body

    def to_envelope(self) -> dict:
        """Serialise this error to a ``KiteFrostErrorEvent`` dict.

        Used by the SDK auto-telemetry sender (C-FB3).
        """
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "status_code": self.status_code,
            "feedback_id": self.feedback_id,
            "request_id": self.request_id,
        }

    def __str__(self) -> str:
        """Return a human-readable string including feedback_id when present.

        Examples::

            >>> str(KiteFrostError("oops"))
            'oops'
            >>> str(KiteFrostError("oops", feedback_id="fbk_abc123"))
            'oops [feedback_id=fbk_abc123]'

        To surface ``feedback_id`` in structured logs, attach it as an extra::

            import logging
            logger = logging.getLogger("kitefrost")
            try:
                project.generate(...)
            except KiteFrostError as exc:
                logger.error(str(exc), extra={"feedback_id": exc.feedback_id})
        """
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
    """Raised when the API key is missing, invalid, or lacks permission.

    HTTP 401 or 403.
    """


class ProjectNotFound(KiteFrostError):
    """Raised when the requested project does not exist.

    HTTP 404 on a project resource.
    """


class EntityNotFound(KiteFrostError):
    """Raised when the requested entity does not exist.

    HTTP 404 on an entity resource.
    """


class RateLimited(KiteFrostError):
    """Raised when the API rate limit is exceeded.

    HTTP 429. Inspect ``retry_after`` for the suggested back-off (seconds).
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


class ValidationError(KiteFrostError):
    """Raised when the API rejects the request payload (HTTP 422)."""


class EntitySchemaError(KiteFrostError):
    """Raised when an entity upsert fails schema validation (HTTP 422).

    Provides structured access to per-field validation errors.

    Attributes:
        entity_type: The entity type whose schema was violated.
        errors: List of human-readable per-field error strings.
    """

    def __init__(
        self,
        message: str,
        entity_type: str = "",
        errors: list[str] | None = None,
        feedback_id: str | None = None,
    ) -> None:
        super().__init__(message, status_code=422, feedback_id=feedback_id)
        self.entity_type = entity_type
        self.errors: list[str] = errors or []

    def __repr__(self) -> str:
        return (
            f"EntitySchemaError(entity_type={self.entity_type!r}, "
            f"errors={self.errors!r}, feedback_id={self.feedback_id!r})"
        )


class BudgetExceededError(KiteFrostError):
    """Raised when the request would exceed the account or project budget."""


class InvalidBYOKKeyError(KiteFrostError):
    """Raised when the provided BYOK (Bring Your Own Key) API key is invalid or rejected."""


class ContentPolicyViolationError(KiteFrostError):
    """Raised when generated or submitted content violates the content policy."""


class ServiceUnavailableError(KiteFrostError):
    """Raised when a downstream service or the API itself is temporarily unavailable."""


class SessionExpiredError(KiteFrostError):
    """Raised when the session token has expired and re-authentication is required."""


# Map machine-readable error code strings to exception classes.
# Used by _transport to check code field before falling back to HTTP status.
_CODE_TO_EXCEPTION: dict[str, type[KiteFrostError]] = {
    "budget_exceeded": BudgetExceededError,
    "invalid_byok_key": InvalidBYOKKeyError,
    "content_policy_violation": ContentPolicyViolationError,
    "service_unavailable": ServiceUnavailableError,
    "session_expired": SessionExpiredError,
    "rate_limited": RateLimited,
}
