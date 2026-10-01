# kitefrost-core

Shared runtime core for the KiteFrost per-pack SDKs (PPI-3, D-PPI-SDK-BUNDLING
Option A). Importable as `kitefrost_core`.

It owns the cross-pack infrastructure surface so each per-pack SDK does not
duplicate it:

- HTTP transport (single httpx connection pool)
- Auth provider with one-shot 401 refresh
- Typed error hierarchy (`KiteFrostError` and subclasses)
- The SHARED_TAGS resource clients (auth, keys, billing, projects, events,
  context, byok, webhooks, health)
- A lockstep version stamp (`CORE_VERSION`) the per-pack SDKs pin

```python
from kitefrost_core import KiteFrostCore

core = KiteFrostCore(api_key="sk_live_...")
print(core.health.check())
```

When a customer installs more than one per-pack SDK, the packs share a single
`KiteFrostCore` instance, so they share one auth provider and one connection
pool (the Option-A DX win).

## Pre-release (alpha) builds

Alpha and beta builds are published as PyPI pre-releases (`1.2.0a3`, `1.2.0b1`,
`1.2.0rc1`). pip skips them unless you ask:

```bash
pip install kitefrost-core==1.2.0a3 kitefrost-<pack>==1.2.0a3   # pin the alpha; do NOT use --pre (see below)
```

Pin the exact alpha version rather than using `pip install --pre`: `--pre` lets pip pick
pre-releases of **every** dependency too, and it currently installs an `httpx` 1.0
development build that this SDK does not support.


To point the client at a non-default API (for example the address in an early-access
invite), set `KITEFROST_BASE_URL`, or pass `base_url=` to the client. The explicit
argument wins over the environment variable, which wins over the default.
