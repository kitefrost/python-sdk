"""kitefrost-core - shared runtime for every per-pack KiteFrost SDK.

Owns HTTP transport, auth (incl. one-shot 401 refresh), error types, and the
SHARED_TAGS resource clients. Per-pack SDKs depend on this package and add only
their pack-specific resources on top (PPI-3, D-PPI-SDK-BUNDLING Option A).
"""

from __future__ import annotations

from .auth import ApiKeyAuth, AuthProvider, RefreshableTokenAuth
from .core import KiteFrostCore
from .exceptions import (
    AuthError,
    KiteFrostError,
    NotFoundError,
    RateLimited,
    ServerError,
    ValidationError,
)
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
from .transport import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, Transport
from .version import CORE_VERSION, assert_core_version_compatible

__version__ = CORE_VERSION

__all__ = [
    "KiteFrostCore",
    "Transport",
    "AuthProvider",
    "ApiKeyAuth",
    "RefreshableTokenAuth",
    "KiteFrostError",
    "AuthError",
    "NotFoundError",
    "ValidationError",
    "RateLimited",
    "ServerError",
    "AuthResource",
    "KeysResource",
    "BillingResource",
    "ProjectsResource",
    "EventsResource",
    "ContextResource",
    "ByokResource",
    "WebhooksResource",
    "HealthResource",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "CORE_VERSION",
    "assert_core_version_compatible",
    "__version__",
]
