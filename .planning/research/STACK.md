# Stack Research — Additions for Warm-Pool + Signed URLs + Templates

**Domain:** Headless browser profile service (brownfield milestone additions)
**Researched:** 2026-04-22
**Confidence:** HIGH (all critical claims verified against PyPI, official docs, or Context7)

---

This file covers ONLY new additions to the existing stack. The existing stack
(FastAPI 0.115+, Python 3.12, React 19, SQLite, CloakBrowser, Playwright, KasmVNC)
is locked and documented in `.planning/codebase/STACK.md`. Nothing below is a
replacement for what already exists.

---

## New Python Backend Additions

### Core New Libraries

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `PyJWT` | `>=2.12.1` | Mint and verify signed short-lived viewer tokens | Zero new infrastructure; pure HMAC-HS256 in-process; `exp` claim enforced automatically on decode; widely audited; already compatible with Python 3.12. Latest release 2026-03-13. |
| `itsdangerous` | `>=2.2.0` | Alternative / fallback for URL-safe token signing if JWT is over-engineered for a use case | Already a Pallets project (same family as Flask/Werkzeug); `URLSafeTimedSerializer` produces compact, URL-embeddable tokens with built-in TTL. Included as option — see Alternatives below. |

### No New Infrastructure Required

The five features map entirely onto the existing async FastAPI + SQLite stack with
stdlib helpers and one small library addition:

| Feature | Addition Needed |
|---------|----------------|
| Warm-pool idle tracking | Pure in-memory counter + `asyncio.Task` (stdlib) |
| Signed viewer URLs | `PyJWT` (new dep) or stdlib `hmac` + `hashlib` (zero dep) |
| API-key auth for Main App | FastAPI `APIKeyHeader` + `Depends` (already in fastapi) |
| Vendor Template entity | New SQLite table + Pydantic schema (no new lib) |
| CDP connection signal | Application-layer counter; no reliable CDP query exists (see below) |

---

## Warm-Pool Idle State Tracking

**Pattern:** Extend the existing `RunningProfile` dataclass with two counters and
an `asyncio.Task` handle for the idle timer.

```python
@dataclass
class RunningProfile:
    # ... existing fields ...
    cdp_clients: int = 0       # incremented when Main App fetches cdp_url, decremented on explicit release or timeout
    viewer_sockets: int = 0    # incremented on VNC WebSocket connect, decremented on disconnect
    idle_task: asyncio.Task | None = None   # scheduled sleep task
```

**Idle timer implementation** — no external library needed. Use `asyncio.create_task`
with a coroutine that sleeps N seconds then calls `browser_manager.stop(profile_id)`.
Cancel and re-schedule the task whenever `cdp_clients` or `viewer_sockets` changes.

```python
async def _idle_timer(profile_id: str, delay: int):
    await asyncio.sleep(delay)
    await browser_manager.stop(profile_id)

def _reset_idle_timer(rp: RunningProfile, profile_id: str, idle_seconds: int):
    if rp.idle_task:
        rp.idle_task.cancel()
    if rp.cdp_clients == 0 and rp.viewer_sockets == 0:
        rp.idle_task = asyncio.create_task(_idle_timer(profile_id, idle_seconds))
    else:
        rp.idle_task = None
```

**Why no external state machine library:** The warm-pool has only two states
(RUNNING, SLEEPING) and two transition triggers (last connection drops, next
`/sessions` call wakes). The stdlib pattern above is 20 lines and fully async-safe
within a single-process FastAPI app. Adding a library like `transitions` or `aiomachines`
would introduce conceptual overhead with no operational benefit at this scale.

---

## Signed Short-Lived Viewer URLs

**Recommendation: PyJWT with HS256 — single new dependency, zero new services.**

Rationale over the alternatives:

- **PyJWT (recommended):** JWT is the lingua franca for scoped tokens. The `exp`,
  `sub`, and `jti` claims are standardised. FastAPI route handlers verify with a single
  `jwt.decode()` call. The Main App receives an opaque string it embeds in an iframe
  `src`; it never needs to parse the token. Version 2.12.1 (released 2026-03-13,
  verified on PyPI) is the latest stable release. HS256 with a shared secret stored
  in an env var is sufficient for a private-network service.

- **Why not itsdangerous URLSafeTimedSerializer:** Produces equivalent security but
  the token format is bespoke. If the Main App ever needs to inspect claims, or if
  a second service needs to verify tokens, JWT is a better surface. Use `itsdangerous`
  only if you need URL-safe serialisation of arbitrary Python dicts without JWT
  overhead — not needed here since the payload is just `{sub: profile_id, exp: ...,
  jti: ...}`.

- **Why not raw `hmac` + `hashlib`:** Zero-dependency is attractive but requires
  hand-rolling claim encoding, TTL comparison, and replay detection. The risk of a
  subtle implementation bug exceeds the cost of adding PyJWT.

**Token schema:**

```python
import jwt
from datetime import datetime, timezone, timedelta
import secrets

VIEWER_SECRET = os.environ["VIEWER_SECRET"]   # new env var, separate from AUTH_TOKEN

def mint_viewer_token(profile_id: str, ttl_seconds: int = 300) -> str:
    return jwt.encode(
        {
            "sub": profile_id,
            "jti": secrets.token_urlsafe(16),   # prevents replay within TTL window
            "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds),
            "iat": datetime.now(tz=timezone.utc),
        },
        VIEWER_SECRET,
        algorithm="HS256",
    )

def verify_viewer_token(token: str) -> str:
    """Returns profile_id or raises jwt.InvalidTokenError."""
    payload = jwt.decode(token, VIEWER_SECRET, algorithms=["HS256"])
    return payload["sub"]
```

**Viewer URL shape:** `https://<host>/viewer/<token>` — a React route that mounts
the existing noVNC component, but with the VNC WebSocket authenticated by the
embedded token rather than the admin cookie.

**TTL guidance:** 5 minutes (300 s) default. The Main App re-calls `POST /sessions`
to get a fresh URL whenever it needs to embed the viewer. Short TTL limits blast
radius of a leaked URL.

**New environment variable required:** `VIEWER_SECRET` — minimum 32 random bytes,
generated at deploy time via `python -c "import secrets; print(secrets.token_hex(32))"`.

---

## API-Key Auth for the Main App

**Pattern: FastAPI `APIKeyHeader` + `Depends` — zero new dependencies.**

FastAPI's built-in `fastapi.security.APIKeyHeader` is the correct primitive. It
integrates with OpenAPI docs automatically and keeps the validation logic in a
reusable dependency function, consistent with the existing `AuthMiddleware` pattern.

```python
from fastapi.security import APIKeyHeader
from fastapi import Security, HTTPException

MAIN_APP_API_KEY = os.environ.get("MAIN_APP_API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def require_main_app_auth(key: str = Security(api_key_header)) -> None:
    if not MAIN_APP_API_KEY or not hmac.compare_digest(key, MAIN_APP_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key")
```

Apply via `dependencies=[Depends(require_main_app_auth)]` on the router that serves
`/sessions`, `/templates` (read-only), and `/profiles` (Main App surface).

**Separation from admin auth:** The existing `AuthMiddleware` stays for admin routes
(`/api/profiles/*` during transition, admin dashboard). Main App routes live under
a distinct router prefix (e.g., `/api/v1/`) and use only `require_main_app_auth`.
This means both auth systems coexist with no interference.

**New environment variable required:** `MAIN_APP_API_KEY` — 32+ random bytes,
separate from `AUTH_TOKEN`.

**Why not middleware for this:** The existing `AuthMiddleware` is global with exempt
paths. Adding a second middleware that carves out `/api/v1/*` would create fragile
path-matching logic. A `Depends`-based approach scopes auth to exactly the router
it protects and is the FastAPI-idiomatic pattern (verified against official
FastAPI security docs 2026-04-22).

---

## Vendor Template Storage

**Recommendation: New SQLite table — stay in SQLite, use a TEXT/JSON column for
the blueprint blob.**

No new database, no new library.

**Schema:**

```sql
CREATE TABLE vendor_templates (
    id          TEXT PRIMARY KEY,          -- UUID
    vendor_type TEXT NOT NULL UNIQUE,      -- e.g. "facebook", "amazon"
    blueprint   TEXT NOT NULL,             -- JSON blob: full profile config
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

The `blueprint` column stores the full profile blueprint (fingerprint_seed rules,
timezone, locale, platform, screen dims, launch_args, humanize flags, clipboard_sync)
as a JSON-serialised string. SQLite 3.38+ (the version available in Python 3.12's
bundled sqlite3) supports `json_extract()` for querying specific fields if needed,
but the primary access pattern is a full read-then-deserialise in Python.

**Why TEXT/JSON over separate normalised columns:** The blueprint is a closed schema
controlled entirely by this codebase (it mirrors the existing `ProfileCreate` fields).
Normalising it into 15 columns gains nothing and makes schema evolution harder.
A Pydantic model (`VendorTemplateBlueprint`) handles serialisation/deserialisation in
Python, giving full validation without DB schema coupling.

**Why not SQLite JSONB (3.45+/3.51+):** The `JSONB` binary type in SQLite 3.45+
offers marginally faster JSON function calls on large documents. The blueprint
payloads here are ~1 KB. The performance difference is immeasurable. Use `TEXT NOT NULL`
for maximum compatibility with the sqlite3 stdlib module and existing tooling.

**Why not a separate config file / YAML / structured JSON file on disk:** The
templates are admin-managed at runtime via the dashboard UI. Storing them in SQLite
keeps them in the same transaction scope as profiles (e.g., "delete template only
if no profiles reference it"), survives container restarts on the existing `/data`
volume, and requires zero new read/write infrastructure.

---

## CDP Connection Signal (Warm-Pool Idle Detection)

**Verdict: No reliable external CDP query exists. Use application-layer tracking.**

**What was investigated:**
- The Chromium CDP HTTP API exposes `/json/version`, `/json/list`, `/json/new`,
  `/json/activate`, `/json/close`. None of these endpoints expose a client connection
  count or whether a WebSocket is currently attached to a target. This was confirmed
  against the official CDP protocol reference (chromedevtools.github.io/devtools-protocol,
  verified 2026-04-22).
- The `webSocketDebuggerUrl` field in `/json/list` responses may disappear or be
  null when a devtools client is attached, but this behaviour is target-type-dependent
  and not documented as a reliable signal. Multiple community reports show inconsistent
  results (Chromium issue tracker, cyrus-and/chrome-remote-interface#402).
- Playwright's `browser.is_connected` property reflects whether Playwright's own
  internal connection to the browser subprocess is alive — it does NOT reflect
  whether an *external* CDP client has connected via the debugging port.

**Practical approach:**

The service controls the CDP URL it returns to the Main App. Track connectivity
at the application layer:

1. When `POST /sessions` returns a `cdp_url`, record a "CDP slot leased" timestamp
   in `RunningProfile`.
2. The Main App calls `POST /sessions` with a configurable heartbeat interval (or
   again on each automation job). Each call resets the idle timer.
3. Optionally, expose `DELETE /sessions/{id}` for explicit release; the warm-pool
   idle timer is the safety net regardless.

This is simpler and more reliable than polling a browser HTTP endpoint that doesn't
expose the signal you need.

**If a tighter signal is ever required:** The only viable approach is to run a small
CDP proxy (e.g., a WebSocket proxy the service controls) between the Main App's
automation client and Chromium's debugging port. The proxy can count open WebSocket
connections precisely. This is additional infrastructure and not warranted for v1.

---

## Supporting Libraries (Existing — Confirm Already Present)

These are already in `requirements.txt` and need no changes, but are exercised by
the new features:

| Library | Existing Version | Used By New Features |
|---------|-----------------|---------------------|
| `pydantic` | `>=2.0` | VendorTemplate schema, blueprint validation |
| `httpx` | `>=0.27` | Internal async HTTP (e.g., polling CDP `/json` if needed) |
| `uvicorn[standard]` | `>=0.34` | Serves the new routes; no changes |
| `websockets` | `>=14.0` | VNC WebSocket — viewer token verification plugs in here |

---

## Installation Delta

```bash
# Single new backend dependency
pip install "PyJWT>=2.12.1"
```

No new frontend npm dependencies are needed. The viewer URL page reuses the
existing noVNC component (`@novnc/novnc 1.4.0`) with the token passed as a URL
parameter. The template admin UI is new React pages using existing Tailwind + Lucide
components.

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| `PyJWT` (HS256) | `itsdangerous URLSafeTimedSerializer` | Both work; PyJWT chosen because JWT is a standard format the Main App could inspect if needed; `itsdangerous` is bespoke. Either is a legitimate choice. |
| `PyJWT` (HS256) | Raw `hmac` + `hashlib` + `secrets` | Zero deps is appealing but requires hand-rolling TTL, claim encoding, and replay logic. Too much security-sensitive DIY. |
| `PyJWT` (HS256) | RSA / ES256 asymmetric signing | Asymmetric only needed if the Main App must verify tokens without calling back to this service. That's not the architecture — the Main App never verifies tokens, only embeds them in iframes. Symmetric HS256 is correct. |
| `APIKeyHeader` + `Depends` | Second `AuthMiddleware` for Main App routes | Middleware requires fragile URL-prefix matching; `Depends` scopes auth to exactly the router, is idiomatic FastAPI, and is zero new code. |
| SQLite `TEXT` JSON column | Separate `vendor_template_fields` normalised table | A 15-column normalised table for a config blob that's always read-and-written atomically is over-engineered; Pydantic handles validation. |
| asyncio stdlib timer | `transitions` or `aiomachines` state machine lib | Two-state warm-pool logic is 20 lines of stdlib asyncio; a state machine library adds a dependency and learning curve for no operational gain at <20 profiles. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `python-jose` | Unmaintained since 2022; CVEs in older versions; project effectively abandoned | `PyJWT 2.12.x` — actively maintained, released 2026-03-13 |
| Redis | No distributed state needed; single-box; would add operational overhead | In-memory dict in `BrowserManager` (already the pattern) |
| Celery / task queue | Async wake-on-demand is a simple `asyncio.create_task`; Celery is appropriate for distributed job queues, not in-process timers | `asyncio.Task` with cancel/reschedule |
| A CDP proxy library | No v1 requirement for precise external CDP connection counting; adds infrastructure | Application-layer "last session call" heartbeat |

---

## New Environment Variables Required

| Variable | Purpose | Generation |
|----------|---------|-----------|
| `VIEWER_SECRET` | Signs viewer JWT tokens | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `MAIN_APP_API_KEY` | Authenticates Main App requests | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `IDLE_TIMEOUT_SECONDS` | Warm-pool sleep delay (default: 600) | Integer, configured at deploy time |

---

## Version Compatibility

| Package | Version Constraint | Python 3.12 Compatible | Notes |
|---------|-------------------|------------------------|-------|
| `PyJWT` | `>=2.12.1` | Yes | Verified PyPI 2026-03-13 |
| `itsdangerous` | `>=2.2.0` | Yes | Pallets 2.2.x stable branch |
| `fastapi` | `>=0.115` | Yes | `APIKeyHeader` + `Security` available since 0.95 |
| `pydantic` | `>=2.0` | Yes | Already in use; no version change |

---

## Sources

- `/jpadilla/pyjwt` (Context7) — encode/decode with `exp`, `jti`, `iat`; `ExpiredSignatureError` handling
- PyPI PyJWT project page — version 2.12.1, released 2026-03-13 (verified directly)
- `/pallets/itsdangerous` (Context7) — `URLSafeTimedSerializer`, `TimestampSigner` TTL patterns
- PyPI itsdangerous — version 2.2.0 stable (verified directly)
- FastAPI Security reference (fastapi.tiangolo.com/reference/security/) — `APIKeyHeader` + `Depends` pattern
- Chrome DevTools Protocol reference (chromedevtools.github.io/devtools-protocol/) — confirmed no connection-count endpoint exists
- SQLite JSON docs (sqlite.org/json1.html) — `TEXT` column + json functions; JSONB availability
- PyPI `python-jose` advisory — last meaningful release 2022, not recommended
- Playwright Python docs (Context7 /microsoft/playwright-python) — `browser.is_connected` scope confirmed

---
*Stack research for: CloakBrowser-Manager warm-pool + signed-URL + template additions*
*Researched: 2026-04-22*
