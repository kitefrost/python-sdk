# kitefrost - Python SDK

Thin Python wrapper for the [KiteFrost API](https://kitefrost.ai).
Four lines to hello project. Fully typed. Both sync and async.

## Install

```bash
pip install kitefrost
```

Requires Python 3.10+ and [`httpx`](https://www.python-httpx.org/) (installed automatically).

## Hello Project

```python
import kitefrost

# 1. Open a project (creates it if it doesn't exist)
project = kitefrost.Project("medieval-rpg", api_key="sk_...")

# 2. Add an entity
project.entity("blacksmith", type="npc", name="Gideon", personality="gruff but kind")

# 3. Record what happens
project.event("player.bought_sword", entity="blacksmith", player="alice",
            details="haggled to 35 gold")

# 4. Generate context-aware dialogue
response = project.generate(
    entity="blacksmith",
    player="alice",
    prompt="Player returns after slaying dragon",
)
print(response.text)
# "Ah, the Dragon Slayer returns! Still got that sword I sold ye?"
```

## Async

```python
import asyncio
import kitefrost

async def main():
    project = kitefrost.AsyncProject("medieval-rpg", api_key="sk_...")
    await project.init()  # async project creation

    blacksmith = await project.entity(
        "blacksmith-gideon",
        type="npc",
        name="Gideon the Blacksmith",
        personality="gruff but kind, retired adventurer",
    )

    await project.event(
        "player.bought_sword",
        entity=blacksmith,
        player="alice",
        details="haggled from 50 to 35 gold",
    )

    response = await project.generate(
        entity=blacksmith,
        player="alice",
        prompt="Player returns after slaying the dragon",
    )
    print(response.text)

asyncio.run(main())
```

## API Reference

> **Not in the SDK: pack discovery.** This SDK is for building on the pack you
> already chose. Enumerating packs or picking one at runtime (the `GET /v1/packs`
> catalogue and the agent selector-prompt) is an AI-agent concern served by the
> REST + MCP API directly, not by the SDK - so there is intentionally no
> `list_packs` / selector-prompt method. Choose your pack at signup; the SDK
> covers everything under it.

### `kitefrost.Project(project_name, *, api_key, base_url?, timeout?, auto_create?)`

Synchronous client bound to a single project.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_name` | `str` | required | Project slug (e.g. `"medieval-rpg"`) |
| `api_key` | `str` | required | Bearer token (`sk_...` or `pk_...`) |
| `base_url` | `str` | `https://api.kitefrost.ai` | Override for self-hosted |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `auto_create` | `bool` | `True` | POST `/v1/projects` on init |

Supports use as a context manager (`with kitefrost.Project(...) as project:`).

---

### `project.entity(entity_id, *, type, name, **properties) -> Entity`

Upsert an entity (NPC, location, faction, item, or player).

```python
blacksmith = project.entity(
    "blacksmith-gideon",
    type="npc",
    name="Gideon the Blacksmith",
    personality="gruff but kind",
    location="village-square",
)
print(blacksmith.id)          # server-assigned ID (e.g. "ent_xyz789")
print(blacksmith.properties)  # {"personality": "gruff but kind", ...}
```

You can pass the returned `Entity` object directly to `event()` and `generate()`.

---

### `project.event(event_type, *, entity?, player?, **data) -> Event`

Record an immutable event in the project timeline.

```python
ev = project.event(
    "player.bought_sword",
    entity=blacksmith,       # Entity object or string external_id
    player="alice",
    details="haggled from 50 to 35 gold",
    session_number=12,
)
print(ev.id)
```

---

### `project.context(*, query?, entity_id?, player_id?) -> ContextResult`

Query assembled project context. Returns `.entity`, `.relevant_events`,
`.facts`, and `.summary`.

```python
ctx = project.context(
    query="blacksmith knowledge about player-alice",
    entity_id="ent_xyz789",
)
print(ctx.summary)
print(ctx.relevant_events)
```

---

### `project.generate(*, entity, player, prompt, type?) -> GenerateResponse`

Generate context-aware content for an entity/player interaction.

```python
response = project.generate(
    entity=blacksmith,       # Entity object or string external_id
    player="alice",
    prompt="Player approaches the forge",
    type="dialogue",         # "dialogue" | "narration" | "summary"
)
print(response.text)
print(response.tokens_used)  # {"input": 2340, "output": 89}
```

---

### `project.tell(statement) -> TellResponse`

Ingest a natural-language statement into project memory.  The engine parses
the statement, extracts entities and relationships, and persists them as
structured events and facts.

```python
result = project.tell("Alice bought a sword from Gideon for 35 gold.")
print(result.understood)           # True
print(result.actions)              # [{"type": "event.recorded", ...}]
print(result.entities_referenced)  # ["alice", "gideon"]
print(result.tokens_used)          # {"input": 120, "output": 45}
```

---

### `project.ask(question, *, respond_as?) -> AskResponse`

Ask a natural-language question about project memory.  Returns a factual
answer and, optionally, an in-character response voiced by a specific entity.

```python
response = project.ask(
    "What does Gideon know about Alice?",
    respond_as="gideon",        # optional - entity external_id
)
print(response.answer)       # Factual summary from project memory
print(response.in_character) # In-character response voiced as Gideon
print(response.context_used) # {"events_referenced": 3, "facts_referenced": 2}
print(response.tokens_used)  # {"input": 980, "output": 120}
```

---

## Convenience Methods

High-level helpers that wrap core API methods for common patterns.

---

### `project.remember(entity_id, event_text, metadata?) -> Event`

Record a free-text memory for an entity.  Wraps `event()` with `type="memory"`.

```python
project.remember("blacksmith", "Sold a legendary sword to Alice")
project.remember("blacksmith", "Was insulted by a thief", metadata={"severity": "minor"})
```

---

### `project.recall(entity_id, *, limit?) -> ContextResult`

Retrieve memories for a single entity.  Wraps `context()` filtered to one entity.

```python
ctx = project.recall("blacksmith", limit=5)
print(ctx.summary)
print(ctx.relevant_events)
```

---

### `project.create_npc(name, properties?) -> Entity`

Create an NPC entity with `type="npc"` and an auto-generated `entity_id`
derived from the name (lowercased, spaces replaced with hyphens).

```python
npc = project.create_npc("Gideon the Blacksmith", properties={"personality": "gruff but kind"})
# entity_id = "gideon-the-blacksmith"
print(npc.id)
```

---

### `project.npc_respond(entity_id, player_action, *, model?) -> GenerateResponse`

Generate an NPC response to a player action.  Wraps `generate()` with an
NPC-focused prompt format.

```python
response = project.npc_respond("blacksmith", "Player asks about rare weapons")
print(response.text)

# Override generation type
response = project.npc_respond("blacksmith", "Player draws sword", model="narration")
```

---

### `kitefrost.AsyncProject`

Identical API to `Project` but every method is a coroutine (including all
convenience methods above). Call `await project.init()` once before using
other methods, or use as an async context manager.

## Error Handling

All exceptions inherit from `kitefrost.KiteFrostError` and expose:
- `.status_code` - HTTP status code
- `.message` - human-readable error description
- `.doc_url` - link to resolution guidance in the KiteFrost docs

### Exception reference

| Exception | HTTP status | When raised |
|-----------|-------------|-------------|
| `AuthenticationError` | 401 | Missing or invalid API key |
| `ForbiddenError` | 403 | Key exists but lacks permission for the operation |
| `NotFoundError` | 404 | Project, entity, or resource does not exist |
| `ValidationError` | 422 | Malformed request payload |
| `RateLimitError` | 429 | Too many requests; check `.retry_after` |
| `ConflictError` | 409 | Conflicting state (e.g. duplicate entity ID) |
| `BudgetExceededError` | 402 | API spend limit reached for the account |
| `InvalidBYOKKeyError` | 401 | BYOK key was rejected by the upstream provider |
| `ContentPolicyViolationError` | 422 | Prompt or content failed moderation |
| `ServiceUnavailableError` | 503 | Server temporarily unavailable |
| `SessionExpiredError` | 410 | Session has expired and cannot be resumed |
| `ServerError` | 5xx | Unexpected server error |

### Basic example

```python
import kitefrost

try:
    project = kitefrost.Project("my-project", api_key="sk_invalid")
    project.entity("hero", type="player", name="Alice")
except kitefrost.AuthenticationError as e:
    print(f"Bad API key: {e.message}")
    print(f"Help: {e.doc_url}")
except kitefrost.NotFoundError as e:
    print(f"Not found: {e.message}")
except kitefrost.RateLimitError as e:
    print(f"Rate limited - retry after {e.retry_after}s")
except kitefrost.KiteFrostError as e:
    print(f"API error {e.status_code}: {e.message}")
```

### BYOK error handling

When using a Bring Your Own Key (BYOK) configuration, the upstream provider may
reject the key independently of your KiteFrost credentials. Handle both cases:

```python
import kitefrost

project = kitefrost.Project("my-project", api_key="sk_...", byok_key="sk-openai-...")

try:
    response = project.generate(entity="npc", player="alice", prompt="Hello")
except kitefrost.InvalidBYOKKeyError as e:
    # The BYOK key was rejected by the upstream provider (e.g. OpenAI).
    # Check the key in your KiteFrost dashboard, then retry.
    print(f"BYOK key rejected: {e.message}")
    print(f"Resolution: {e.doc_url}")
except kitefrost.AuthenticationError as e:
    # KiteFrost API key itself is invalid.
    print(f"KiteFrost auth failed: {e.message}")
except kitefrost.BudgetExceededError as e:
    print(f"Spend limit reached: {e.message}")
except kitefrost.ContentPolicyViolationError as e:
    print(f"Content moderation blocked request: {e.message}")
```

## Development

```bash
cd sdk/python
pip install -e ".[dev]"
pytest
```

## License

MIT - see [LICENSE](LICENSE).
