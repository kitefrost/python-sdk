"""Lockstep version stamp for the shared core (D-PPI-SDK-BUNDLING / D-PPI-SDK-GENERATED).

Every per-pack SDK pins this exact value in lockstep with the backend contract
release. The per-pack codegen (STREAM-003 TASK-003) reads ``CORE_VERSION`` to
emit a compatible dependency range and to assert that the installed core matches
the contract version it was generated against.
"""

from __future__ import annotations

CORE_VERSION = "1.2.0a3"


def assert_core_version_compatible(required_major: int) -> None:
    """Assert the installed core satisfies the major a per-pack SDK was built for.

    Lockstep versioning forbids cross-major mixing (a fatal venv skew when two
    packs pin incompatible cores); same-major is compatible.
    """
    installed_major = int(CORE_VERSION.split(".")[0])
    if installed_major != required_major:
        raise RuntimeError(
            f"kitefrost-core version skew: installed {CORE_VERSION} "
            f"(major {installed_major}) but a pack SDK requires core major {required_major}. "
            "Per-pack SDKs and the core publish in lockstep; align their versions."
        )
