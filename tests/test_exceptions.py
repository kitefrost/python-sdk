"""Unit tests for domain-specific exceptions in the kitefrost Python SDK.

Tests new exception types added in S35-T5:
- BudgetExceededError
- InvalidBYOKKeyError
- ContentPolicyViolationError
- ServiceUnavailableError
- SessionExpiredError

Also tests code-based error parsing in _transport._raise_for_response.
"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from kitefrost import Project
from kitefrost.exceptions import (
    _CODE_TO_EXCEPTION,
    AuthError,
    BudgetExceededError,
    ContentPolicyViolationError,
    EntityNotFound,
    EntitySchemaError,
    InvalidBYOKKeyError,
    KiteFrostError,
    ProjectNotFound,
    RateLimited,
    ServerError,
    ServiceUnavailableError,
    SessionExpiredError,
    ValidationError,
)

API_KEY = "sk_test_key"
BASE_URL = "http://test.kitefrost.ai"
PROJECT_NAME = "test-project"
PROJECT_RESPONSE = {"id": "prj_test", "name": PROJECT_NAME, "created_at": "2026-01-01T00:00:00Z"}


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


class TestDomainExceptionInheritance:
    def test_budget_exceeded_is_kitefrost_error(self):
        err = BudgetExceededError("over budget")
        assert isinstance(err, KiteFrostError)

    def test_invalid_byok_key_is_kitefrost_error(self):
        err = InvalidBYOKKeyError("bad key")
        assert isinstance(err, KiteFrostError)

    def test_content_policy_violation_is_kitefrost_error(self):
        err = ContentPolicyViolationError("policy violation")
        assert isinstance(err, KiteFrostError)

    def test_service_unavailable_is_kitefrost_error(self):
        err = ServiceUnavailableError("service down")
        assert isinstance(err, KiteFrostError)

    def test_session_expired_is_kitefrost_error(self):
        err = SessionExpiredError("session gone")
        assert isinstance(err, KiteFrostError)

    def test_all_new_exceptions_catchable_as_base(self):
        new_types = [
            BudgetExceededError,
            InvalidBYOKKeyError,
            ContentPolicyViolationError,
            ServiceUnavailableError,
            SessionExpiredError,
        ]
        for exc_cls in new_types:
            with pytest.raises(KiteFrostError):
                raise exc_cls("test")


# ---------------------------------------------------------------------------
# _CODE_TO_EXCEPTION mapping
# ---------------------------------------------------------------------------


class TestCodeToExceptionMapping:
    def test_mapping_contains_new_codes(self):
        assert "budget_exceeded" in _CODE_TO_EXCEPTION
        assert "invalid_byok_key" in _CODE_TO_EXCEPTION
        assert "content_policy_violation" in _CODE_TO_EXCEPTION
        assert "service_unavailable" in _CODE_TO_EXCEPTION
        assert "session_expired" in _CODE_TO_EXCEPTION

    def test_new_code_mappings(self):
        assert _CODE_TO_EXCEPTION["budget_exceeded"] is BudgetExceededError
        assert _CODE_TO_EXCEPTION["invalid_byok_key"] is InvalidBYOKKeyError
        assert _CODE_TO_EXCEPTION["content_policy_violation"] is ContentPolicyViolationError
        assert _CODE_TO_EXCEPTION["service_unavailable"] is ServiceUnavailableError
        assert _CODE_TO_EXCEPTION["session_expired"] is SessionExpiredError

    def test_all_values_are_kitefrost_subclasses(self):
        for code, cls in _CODE_TO_EXCEPTION.items():
            assert issubclass(cls, KiteFrostError), f"{code} maps to non-KiteFrostError class"


# ---------------------------------------------------------------------------
# Code-based error parsing via HTTP responses
# ---------------------------------------------------------------------------


class TestCodeBasedErrorParsing:
    """Verify _raise_for_response checks code field before status code."""

    def test_budget_exceeded_raised_via_code(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Budget exceeded", "code": "budget_exceeded"},
            status_code=402,
        )
        with pytest.raises(BudgetExceededError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_invalid_byok_key_raised_via_code(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Bad BYOK key", "code": "invalid_byok_key"},
            status_code=400,
        )
        with pytest.raises(InvalidBYOKKeyError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_content_policy_violation_raised_via_code(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Policy violated", "code": "content_policy_violation"},
            status_code=400,
        )
        with pytest.raises(ContentPolicyViolationError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_service_unavailable_raised_via_code(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Down for maintenance", "code": "service_unavailable"},
            status_code=503,
        )
        with pytest.raises(ServiceUnavailableError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_session_expired_raised_via_code(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Session expired", "code": "session_expired"},
            status_code=401,
        )
        with pytest.raises(SessionExpiredError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_code_takes_precedence_over_status(self, httpx_mock: HTTPXMock):
        """budget_exceeded code on a 400 should still raise BudgetExceededError."""
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Budget gone", "code": "budget_exceeded"},
            status_code=400,
        )
        with pytest.raises(BudgetExceededError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_status_fallback_when_code_unknown(self, httpx_mock: HTTPXMock):
        """Unknown error code falls back to HTTP-status-based mapping."""
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"detail": "Unauthorized", "code": "some_future_code"},
            status_code=401,
        )
        with pytest.raises(AuthError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_status_fallback_when_no_code(self, httpx_mock: HTTPXMock):
        """Missing code field falls back to HTTP-status-based mapping."""
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"detail": "Unauthorized"},
            status_code=401,
        )
        with pytest.raises(AuthError):
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)

    def test_rate_limited_still_includes_retry_after(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json=PROJECT_RESPONSE,
            status_code=201,
        )
        project = Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects/prj_test/generate",
            json={"detail": "Too many requests", "code": "rate_limited"},
            status_code=429,
            headers={"Retry-After": "60"},
        )
        with pytest.raises(RateLimited) as exc_info:
            project.generate(entity="x", player="alice", prompt="hi")
        assert exc_info.value.retry_after == 60

    def test_status_code_preserved_on_domain_exception(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Session expired", "code": "session_expired"},
            status_code=401,
        )
        with pytest.raises(SessionExpiredError) as exc_info:
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
        assert exc_info.value.status_code == 401

    def test_feedback_id_populated_from_response(self, httpx_mock: HTTPXMock):
        """feedback_id from JSON error body should propagate to exception."""
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={
                "error": "Budget exceeded",
                "code": "budget_exceeded",
                "feedback_id": "fbk_abc123",
            },
            status_code=402,
        )
        with pytest.raises(BudgetExceededError) as exc_info:
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
        assert exc_info.value.feedback_id == "fbk_abc123"

    def test_feedback_id_none_when_absent_in_response(self, httpx_mock: HTTPXMock):
        """Missing feedback_id in error response → None on exception."""
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/v1/projects",
            json={"error": "Budget exceeded", "code": "budget_exceeded"},
            status_code=402,
        )
        with pytest.raises(BudgetExceededError) as exc_info:
            Project(PROJECT_NAME, api_key=API_KEY, base_url=BASE_URL, report_errors=False)
        assert exc_info.value.feedback_id is None


# ---------------------------------------------------------------------------
# feedback_id on KiteFrostError and subclasses
# ---------------------------------------------------------------------------


class TestFeedbackId:
    """Verify feedback_id field, __str__, __repr__, and to_envelope."""

    def test_base_error_without_feedback_id(self):
        exc = KiteFrostError("something broke")
        assert exc.feedback_id is None
        assert str(exc) == "something broke"
        assert "feedback_id" not in str(exc)

    def test_base_error_with_feedback_id(self):
        exc = KiteFrostError("something broke", feedback_id="fbk_xyz789")
        assert exc.feedback_id == "fbk_xyz789"
        assert str(exc) == "something broke [feedback_id=fbk_xyz789]"

    def test_repr_includes_feedback_id(self):
        exc = KiteFrostError("err", status_code=500, feedback_id="fbk_r1")
        r = repr(exc)
        assert "fbk_r1" in r
        assert "KiteFrostError" in r

    def test_to_envelope_includes_feedback_id(self):
        exc = KiteFrostError("err", feedback_id="fbk_env1")
        env = exc.to_envelope()
        assert env["feedback_id"] == "fbk_env1"

    def test_to_envelope_without_feedback_id(self):
        exc = KiteFrostError("err")
        env = exc.to_envelope()
        assert env["feedback_id"] is None

    # -- Subclass propagation -----------------------------------------------

    def test_auth_error_inherits_feedback_id(self):
        exc = AuthError("no auth", status_code=401, feedback_id="fbk_a1")
        assert exc.feedback_id == "fbk_a1"
        assert "[feedback_id=fbk_a1]" in str(exc)

    def test_project_not_found_inherits_feedback_id(self):
        exc = ProjectNotFound("gone", feedback_id="fbk_w1")
        assert exc.feedback_id == "fbk_w1"

    def test_entity_not_found_inherits_feedback_id(self):
        exc = EntityNotFound("missing", feedback_id="fbk_e1")
        assert exc.feedback_id == "fbk_e1"

    def test_rate_limited_with_feedback_id(self):
        exc = RateLimited("slow down", retry_after=30, feedback_id="fbk_rl1")
        assert exc.feedback_id == "fbk_rl1"
        assert exc.retry_after == 30
        assert "[feedback_id=fbk_rl1]" in str(exc)

    def test_server_error_inherits_feedback_id(self):
        exc = ServerError("500", status_code=500, feedback_id="fbk_s1")
        assert exc.feedback_id == "fbk_s1"

    def test_validation_error_inherits_feedback_id(self):
        exc = ValidationError("bad input", status_code=422, feedback_id="fbk_v1")
        assert exc.feedback_id == "fbk_v1"

    def test_entity_schema_error_with_feedback_id(self):
        exc = EntitySchemaError(
            "schema fail",
            entity_type="Character",
            errors=["name required"],
            feedback_id="fbk_es1",
        )
        assert exc.feedback_id == "fbk_es1"
        assert exc.entity_type == "Character"
        assert "[feedback_id=fbk_es1]" in str(exc)

    def test_budget_exceeded_inherits_feedback_id(self):
        exc = BudgetExceededError("over budget", feedback_id="fbk_b1")
        assert exc.feedback_id == "fbk_b1"

    def test_invalid_byok_inherits_feedback_id(self):
        exc = InvalidBYOKKeyError("bad key", feedback_id="fbk_bk1")
        assert exc.feedback_id == "fbk_bk1"

    def test_content_policy_inherits_feedback_id(self):
        exc = ContentPolicyViolationError("policy", feedback_id="fbk_cp1")
        assert exc.feedback_id == "fbk_cp1"

    def test_service_unavailable_inherits_feedback_id(self):
        exc = ServiceUnavailableError("down", feedback_id="fbk_su1")
        assert exc.feedback_id == "fbk_su1"

    def test_session_expired_inherits_feedback_id(self):
        exc = SessionExpiredError("expired", feedback_id="fbk_se1")
        assert exc.feedback_id == "fbk_se1"

    # -- All 12 subclasses work correctly -----------------------------------

    def test_all_subclasses_accept_feedback_id(self):
        """Every SDK exception subclass must accept feedback_id via kwargs."""
        subclasses = [
            AuthError,
            ProjectNotFound,
            EntityNotFound,
            RateLimited,
            ServerError,
            ValidationError,
            EntitySchemaError,
            BudgetExceededError,
            InvalidBYOKKeyError,
            ContentPolicyViolationError,
            ServiceUnavailableError,
            SessionExpiredError,
        ]
        for cls in subclasses:
            exc = cls("test msg", feedback_id="fbk_all")
            assert exc.feedback_id == "fbk_all", f"{cls.__name__} did not accept feedback_id"
            assert "[feedback_id=fbk_all]" in str(exc), (
                f"{cls.__name__}.__str__ missing feedback_id"
            )
