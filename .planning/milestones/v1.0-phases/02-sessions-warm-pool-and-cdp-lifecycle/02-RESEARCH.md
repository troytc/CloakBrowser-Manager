# Phase 2: Sessions, Warm-Pool, and CDP Lifecycle - Research

**Researched:** 2026-05-08
**Domain:** Brownfield FastAPI + Playwright + CloakBrowser + KasmVNC — warm-pool session orchestration with concurrency-safe upsert, dual-signal idle detection, X-API-Key machine auth on machine routes, additive `RunningProfile` extension
**Confidence:** HIGH
**Phase:** 02-sessions-warm-pool-and-cdp-lifecycle

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

The full decision register lives in `02-CONTEXT.md` `<decisions>`. **Verbatim copy** — every D-XX below is non-negotiable; the planner must produce tasks that satisfy them as-written.

#### SessionManager — Implementation Shape
- **D-01:** **Lifespan singleton.** `SessionManager` is constructed inside FastAPI's `lifespan` context next to the existing `BrowserManager` and stored on `app.state.session_manager`. Routes resolve it via a `Depends(get_session_manager)` factory that reads `request.app.state`. No module-level globals; no per-request instantiation (would lose `_idle_tasks`).
- **D-02:** **Per-key `asyncio.Lock` for upsert serialization.** `SessionManager` holds `_key_locks: dict[tuple[str, str], asyncio.Lock]` keyed by `(vendor_type, vendor_connection_id)`. A class-level `_locks_mutex: asyncio.Lock` guards the `setdefault` of new key locks (prevents the dict-mutation race). The DB-level `UNIQUE(vendor_type, vendor_connection_id)` constraint (added in Phase 1, D-05) is the belt-and-suspenders fallback for the multi-worker / cross-process case (research GAP §`asyncio.Lock` under multi-worker).
- **D-03:** **No `LAUNCH_IN_PROGRESS` state.** The per-key `asyncio.Lock` (D-02) plus a `browser_mgr.running.get(profile_id)` check inside the locked region is sufficient to serialize wakes. The research note flagged `LAUNCH_IN_PROGRESS` as one option; per-key locks give the same guarantee with less surface area. The `WarmPoolState` enum stays at `STOPPED | RUNNING | IDLE`.
- **D-04:** **Count mutations only in WS proxy `try/finally` blocks.** The CDP WS proxy (`/api/profiles/{id}/cdp` in `main.py`) and — in Phase 3 — the viewer WS proxy are the only mutation seams. They mutate `RunningProfile.cdp_attach_count` / `viewer_attach_count` under `browser_mgr._lock` and call `SessionManager.on_attach()` / `on_all_detached()` to drive the idle timer. `SessionManager` does not own a separate "attach" surface.

#### Idle Detection & Activity Tracking
- **D-05:** **Pure connection-count-based idle.** `IDLE` is entered when `cdp_attach_count == 0 AND viewer_attach_count == 0`; the WebSocket stays open during automation pauses, so paused-but-connected sessions never trigger idle. No `last_activity_at` per-frame timestamp.
- **D-06:** **`IDLE_TIMEOUT_SECONDS` default = 600.** Locked at the env-var layer in Phase 1.
- **D-07:** **No `POST /sessions/{id}/keepalive` in v1.**
- **D-08:** **Idle task action.** When the idle `asyncio.Task` fires:
  1. Acquire `browser_mgr._lock`.
  2. Re-check `cdp_attach_count == 0 AND viewer_attach_count == 0`.
  3. Call `await BrowserManager.stop(profile_id)`.
  4. Remove `RunningProfile` from `browser_mgr.running` (so state == STOPPED).
  5. Pop self from `SessionManager._idle_tasks`.
  6. Log: `warm_pool sleep profile_id=… idle_seconds=…`.
- **D-09:** **Idle timer is cancelled on every attach event.** `SessionManager.on_attach(profile_id)` finds and cancels any pending `asyncio.Task` in `_idle_tasks`. `on_all_detached(profile_id)` schedules a fresh one. Only one timer per profile is ever live.

#### Routing & Auth Surface
- **D-10:** **Two new router files.** `backend/routers/sessions.py` owns `POST /sessions`, `GET /sessions`, `GET /sessions/{profile_id}`, `DELETE /sessions/{profile_id}`. `backend/routers/profiles.py` owns `GET /profiles`, `GET /profiles?vendor_type=X&vendor_connection_id=Y`, `PATCH /profiles/{id}`, `DELETE /profiles/{id}`. Mirrors the Phase 1 `routers/templates.py` shape.
- **D-11:** **API-key auth via `APIKeyHeader` + router-wide `Depends`.** New module `backend/auth_api_key.py` exports `require_api_key` (a `Depends`-compatible coroutine that reads the `X-API-Key` header, compares with `MAIN_APP_API_KEY` via `hmac.compare_digest`, raises `HTTPException(401, "Invalid or missing API key", headers={"WWW-Authenticate": "ApiKey"})` on mismatch). Both new routers are mounted with `dependencies=[Depends(require_api_key)]`. Docker production mode requires `MAIN_APP_API_KEY` to be set; `DEV_MODE=1` opts out.
- **D-12:** **`AuthMiddleware` exemption list expands** to include `/sessions` and `/profiles` (machine API). The `_AUTH_EXEMPT` frozenset in `main.py` adds `/sessions` and `/profiles` prefixes alongside the existing exemptions.
- **D-13:** **`cdp_url` returned from `POST /sessions` is the existing `/api/profiles/{profile_id}/cdp` WS path** (relative URL). The proxy already exists; Phase 2 only adds `cdp_attach_count` increment/decrement to its `try/finally`. The CDP WS proxy stays under `/api/*` for now.
- **D-14:** **`GET /sessions` (active list) lives on the machine sessions router only.** Returns active `RunningProfile`s with state and counts. Single auth surface (`X-API-Key`).

#### Lifecycle, Errors & Tests
- **D-15:** **`upsert_profile_by_vendor()` is `SELECT → INSERT OR ABORT → SELECT` inside a single transaction.** Per-key `asyncio.Lock` (D-02) serializes within a process; `INSERT OR ABORT` + `UNIQUE` constraint catches the cross-process case.
- **D-16:** **`POST /sessions` error semantics.** 200 happy path; 400 empty/whitespace input; 404 no template (`{detail: "No template for vendor_type=…", vendor_type: "…"}`); 401 missing/invalid `X-API-Key`; 503 launch failure (semaphore timeout, `about:blank` probe failed, Chromium binary missing) with `{detail: "Browser launch failed", reason: "<short>"}`.
- **D-17:** **`DELETE /sessions/{profile_id}` semantics.** Idempotent. Always returns 204 unless profile_id is unknown (404). Stops only — does NOT drop row or directory.
- **D-18:** **`GET /sessions/{profile_id}` returns** `{state, cdp_attach_count, viewer_attach_count, idle_expires_at, last_launched_at}`. `state` is `"running" | "idle" | "stopped"` (lower-case Pydantic `Literal`). `idle_expires_at` ISO-8601 UTC when idle, else null. `last_launched_at` ISO-8601 of most recent successful launch.
- **D-19:** **Three-layer test strategy.** Unit (`tests/test_session_manager.py`) with mock `BrowserManager`; integration (`tests/test_sessions_router.py`) with FastAPI `TestClient` + temp SQLite + mock `BrowserManager`; slow E2E (`tests/test_warm_pool_e2e.py`, `pytest.mark.slow`) with real Chromium.
- **D-20:** **`GET /profiles` filtering.** Empty list (not 404) for no match. 404 only on `/profiles/{id}` and `/sessions/{id}`.

### Claude's Discretion

- Pydantic models for `SessionRequest` / `SessionResponse` / `SessionStatusResponse` / `ProfilePatch` / `ProfileResponse` mirror existing `models.py` conventions (`field_validator` for defaults, `Literal` for state enum, `model_config = ConfigDict(extra="forbid")` to reject unknown fields).
- `SessionManager` log lines use `logging.getLogger("backend.session_manager")`; structured KV: `event=upsert vendor_type=… vendor_connection_id=… profile_id=… ms=…`.
- `last_launched_at` lives on `RunningProfile` (set on successful launch); idle/stopped state pulls it from the most recent value seen in memory or a small in-process LRU. No new DB column.
- `idle_expires_at` is computed on read as `idle_started_at + IDLE_TIMEOUT_SECONDS`; `idle_started_at` is set when the idle task is scheduled.
- Phase 2 test fixtures reuse Phase 1 conftest (env-var requirement enforcement); add a `mock_browser_manager` fixture.
- `GET /sessions` returns the list sorted by `last_launched_at` desc.
- The `503` reason string from `BrowserManager.launch()` failures is sanitised (no stack traces in HTTP body); full traceback to logs.
- Per-key `asyncio.Lock` cleanup on `DELETE /profiles/{id}`: remove from `_key_locks` to prevent unbounded growth.

### Deferred Ideas (OUT OF SCOPE)

- **`POST /sessions/{id}/keepalive` heartbeat (SAFE-01)** — v1.x.
- **Read-only viewer mode (SAFE-02)** — v1.x.
- **Per-template `idle_timeout_minutes` override (SAFE-03)** — v1.x.
- **Template `is_active` soft-disable (GOV-01)** — v2.
- **CDP WS path move to `/sessions/{id}/cdp`** — Phase 4 cleanup territory.
- **Persistent `last_launched_at` across restarts** — keep in-memory only.
- **`POST /sessions` returning a non-empty `vnc_viewer_url`** — Phase 3.
- **Multi-worker uvicorn deployment** — single worker only in v1.
- **Webhooks / push events to Main App on warm-pool sleep** — out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SESS-01 | `POST /sessions` idempotent upsert by `(vendor_type, vendor_connection_id)` | §`upsert_profile_by_vendor` Concrete Implementation, §SessionManager Skeleton |
| SESS-02 | Response includes `{profile_id, cdp_url, vnc_viewer_url}` + state | §SessionResponse Pydantic Shape |
| SESS-03 | Wakes from STOPPED/IDLE; returns only after browser viable | §`about:blank` Probe Implementation, §SessionManager Wake Flow |
| SESS-04 | RUNNING while `cdp_attach_count > 0 OR viewer_attach_count > 0` | §RunningProfile Extension, §State Computation |
| SESS-05 | IDLE when both counts hit zero; STOPPED after IDLE_TIMEOUT_SECONDS | §Idle Timer Cancellation Race, §SessionManager Skeleton |
| SESS-06 | Idle timer cancels immediately on reattach | §Idle Timer Cancellation Race |
| SESS-07 | Concurrent POST serializes via per-key `asyncio.Lock` | §Concurrent POST Race Test, §Per-Key Lock Pattern |
| SESS-08 | `UNIQUE(vendor_type, vendor_connection_id)` enforced at DB layer | §Phase 1 carry-over (already in place) |
| SESS-09 | Chromium launches guarded by `asyncio.Semaphore(3)` | §Concurrent-Launch Semaphore Mechanics |
| SESS-10 | After every launch, `about:blank` probe confirms liveness | §`about:blank` Probe Implementation |
| SESS-11 | Before every launch, remove SingletonLock/Cookie/Socket | §SingletonLock Cleanup |
| SESS-12 | Profile state persists across sleep/wake | §SessionManager Wake Flow (BrowserManager.stop/launch reuses user_data_dir) |
| SESS-13 | `GET /sessions/{profile_id}` returns the live state envelope | §State Computation, §SessionStatusResponse Pydantic Shape |
| SESS-14 | `DELETE /sessions/{profile_id}` stops without deleting row | §DELETE Semantics |
| PROF-01 | `GET /profiles?vendor_type=X&vendor_connection_id=Y` lookup | §Profiles Router Shape |
| PROF-02 | `GET /profiles` list with optional vendor_type filter | §Profiles Router Shape |
| PROF-03 | `PATCH /profiles/{id}` admin fields only | §Profiles Router Shape |
| PROF-04 | `DELETE /profiles/{id}` stops, drops row, removes dir | §Profiles Router Shape |
| SEC-01 | All machine routes guarded by `X-API-Key` | §APIKeyHeader Implementation, §CDP WS Auth Seam |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

The planner MUST honor these without re-deriving them:

1. **Viewer tokens travel in URL fragment (`#token=`), never querystring.** (Phase 3 concern, but applies to any token surface added in Phase 2.)
2. **`clipboard_sync` defaults to `false` everywhere.** Phase 2 `PATCH /profiles/{id}` MUST NOT allow clipboard_sync to be flipped without explicit per-template opt-in (see Phase 1 D-18 / SEC-06).
3. **Two auth surfaces are strictly segregated** by router prefix. Phase 2 `_AUTH_EXEMPT` additions are limited to `/sessions` and `/profiles` — no overlap with `/admin/*`.
4. **`BrowserManager` owns Chromium lifecycle** — `SessionManager` is a thin orchestrator. SessionManager calls `await browser_mgr.launch(profile)` and `await browser_mgr.stop(profile_id)` only.
5. **`RunningProfile` extension is additive** — `cdp_attach_count: int = 0`, `viewer_attach_count: int = 0`, `last_launched_at: datetime | None = None`, `idle_started_at: datetime | None = None`. Existing fields untouched.
6. **Warm-pool state lives in-process.** On restart, all profiles begin STOPPED with zero counts. No auto-wake.
7. **Vendor template fields are snapshot-copied at creation.** Live templates never re-read at wake (snapshot already in `profiles` row).
8. **Chromium launches guarded by `asyncio.Semaphore(3)`.** Lives on `BrowserManager`, allocated in `__init__`.
9. **Before every launch:** delete `SingletonLock`, `SingletonCookie`, `SingletonSocket` from the profile dir. **Already implemented** (`browser_manager.py:188-190`) — Phase 2 only verifies it covers warm-pool wake (it does — `launch()` runs the cleanup unconditionally).
10. **After every launch:** `about:blank` probe to detect silent wake failure.
11. **`backend/main.py` is 1,066 lines** (re-checked 2026-05-08) — new routes go in `backend/routers/`, not inline.
12. **No new external services** — no Redis, no Postgres, no queue.

## Summary

Phase 2 is the keystone of the milestone: it delivers `POST /sessions` and the warm-pool state machine. The architectural decisions are fully locked in CONTEXT.md (D-01..D-20); this research focuses exclusively on **the implementation specifics not yet decided in CONTEXT.md** (the 15-question focus list from the orchestrator).

The primary findings:

1. **CDP WS auth (L-03) — ADD X-API-Key validation to the existing handler in `main.py`.** Move is rejected (too invasive); add a small async helper that validates the upgrade header before `accept()` and closes with `4401` on failure. The existing `_AUTH_EXEMPT` change (D-12) bypasses `AuthMiddleware` for `/sessions`/`/profiles` only — `/api/profiles/{id}/cdp` keeps flowing through `AuthMiddleware`, but Phase 2 ALSO adds `X-API-Key` validation at the handler level so the Main App (which never has the admin cookie) can authenticate.
2. **`asyncio.Semaphore(3)` lives on `BrowserManager` (allocated in `__init__`); acquired OUTSIDE the existing `_lock`.** The semaphore wraps the entire launch body (including VNC start, Chromium launch, `about:blank` probe). Use `asyncio.wait_for(sem.acquire(), timeout=30)` so backed-up wake requests fail cleanly as 503 instead of hanging.
3. **Idle timer cancellation: `task.cancel()` BEFORE incrementing the count, under `browser_mgr._lock`.** This avoids the lost-cancel race where the timer fires the very moment `on_attach` runs.
4. **`upsert_profile_by_vendor()` builds on the existing `create_profile_from_template()` helper from Phase 1.** Three-step SELECT → INSERT-OR-ABORT → SELECT in a `with conn:` block; on `IntegrityError`, swallow and re-SELECT.
5. **`about:blank` probe is `await page.goto("about:blank", timeout=5000)` on a fresh page from `context.new_page()`.** Failures are wrapped in `BrowserLaunchError` and surface as 503.
6. **Lifespan shutdown cancels all idle tasks; does NOT stop running profiles** (BrowserManager already handles its own shutdown via `cleanup_all`).
7. **Restart safety (success criterion 5) requires NOTHING new in lifespan startup** — existing `cleanup_stale()` already kills orphan Xvnc; profiles begin STOPPED naturally because `BrowserManager.running` is empty.

**Primary recommendation:** Mirror the Phase 1 `routers/templates.py` shape exactly; lean on `BrowserManager` for all Chromium logic; keep `SessionManager` to <250 lines; use `pytest.mark.slow` (declared in `pyproject.toml`) for the E2E layer with default `-m "not slow"` in CI.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `POST /sessions` request handling | API / Backend (FastAPI router) | — | Single-host service; no frontend involvement in v1 |
| Per-key concurrency control | API / Backend (`SessionManager._key_locks`) | DB layer (`UNIQUE` constraint) | In-process lock is the fast path; DB is the cross-process safety net |
| Profile creation snapshot | API / Backend (`database.create_profile_from_template`) | DB layer (transaction) | Already implemented in Phase 1; Phase 2 wraps with upsert logic |
| Chromium lifecycle (launch/stop) | API / Backend (`BrowserManager`) | OS process tree | Owned by BrowserManager; SessionManager never spawns Chromium |
| Idle timer | API / Backend (`SessionManager._idle_tasks`) | — | In-process `asyncio.Task` per profile; in-memory only |
| Connection counting | API / Backend (WS proxy `try/finally`) | `RunningProfile` dataclass | Counts mutate on `RunningProfile` under `browser_mgr._lock` |
| API-key auth | API / Backend (`Depends(require_api_key)`) | — | Router-level `dependencies=[...]`; OpenAPI-documented |
| State persistence (cookies, etc.) | Database / Storage (Chromium profile dir on disk) | Volume mount | Survives sleep/wake by reusing `user_data_dir` path |
| Profile metadata | Database / Storage (SQLite `profiles` row) | — | UNIQUE constraint enforces identity |

## Standard Stack

### Core (already in place — no additions for Phase 2)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.115.0 | Web framework, routers, `Depends` | Already pinned; `APIKeyHeader` + `Depends` is the documented machine-auth pattern `[CITED: fastapi.tiangolo.com/reference/security]` |
| Pydantic | >=2.0 | Request/response validation | Phase 1 already uses; `Literal` enums, `field_validator`, `model_config = ConfigDict(extra="forbid")` |
| Python `asyncio` | stdlib (3.12) | `Lock`, `Semaphore`, `Task`, `wait_for`, `create_task` | `[VERIFIED: docs.python.org/3/library/asyncio-task]` |
| Python `sqlite3` | stdlib | DB transactions; `with conn:` block | Already used; raw sqlite (no async wrapper) — research note GAP §"SQLite under asyncio" — acceptable at <20 concurrent |
| Python `hmac` | stdlib | `compare_digest` constant-time API key comparison | `[CITED: docs.python.org/3/library/hmac.html#hmac.compare_digest]` — already used at `main.py:103, 114` |
| `cloakbrowser` | >=0.3.14 | `launch_persistent_context_async` | Locked dependency; do not change |
| `playwright` (transitively) | via cloakbrowser | `BrowserContext`, `page.goto`, `context.new_page` | `[CITED: playwright.dev/python/docs/api/class-page#page-goto]` |

### Supporting (Phase 2 testing)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `starlette.testclient.TestClient` | bundled with FastAPI | Sync HTTP test fixture | Already used in Phase 1 (`backend/tests/test_api.py`); use for integration layer (D-19) |
| `httpx.AsyncClient(transport=ASGITransport(app=...))` | from `httpx` >=0.27 | Async HTTP test fixture | Use for the concurrent-race test in `test_sessions_router.py` (`asyncio.gather(*[client.post...])`) |
| `pytest-asyncio` | implicit via `asyncio_mode = "auto"` (`pyproject.toml`) | Async test discovery | Already configured; new tests just declare `async def test_...` |
| `unittest.mock.AsyncMock` / `MagicMock` | stdlib | Mock `BrowserManager` for unit + integration | Already used in Phase 1 conftest |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `APIKeyHeader` + `Depends` | Inline `Header(alias="X-API-Key")` parameter | `APIKeyHeader` auto-generates OpenAPI security scheme — chosen by D-11 |
| `asyncio.Semaphore` | `asyncio.Queue` with worker pool | Semaphore is simpler; queue gives FIFO guarantees we don't need (D-09 already cancels on attach) |
| Per-key `asyncio.Lock` | Single global lock | Per-key allows concurrent wakes for DIFFERENT vendor pairs; D-02 chose per-key explicitly |
| `aiosqlite` | stdlib `sqlite3` blocking | `aiosqlite` adds a dependency; raw sqlite blocks the event loop briefly (~ms) — acceptable at <20 concurrent. **Documented constraint** — do NOT migrate without scaling discussion. |
| `pytest.mark.skipif(slow)` | `pytest.mark.slow` + `-m "not slow"` | The mark approach is pytest-idiomatic; CI runs `-m "not slow"`, dev runs `-m slow` separately. |

### Installation

No new packages required for Phase 2. `PyJWT >= 2.12.1` is already pinned (Phase 1) but is a Phase 3 concern.

**Version verification (`[VERIFIED: backend/requirements.txt as of 2026-05-08]`):**
- fastapi>=0.115.0
- pydantic>=2.0
- cloakbrowser[geoip]>=0.3.14 — **L-02 NOTE: this is a floor pin (`>=`), not exact.** Reproducible-build property is "version on `pip install` build day." Acceptable for v1; revisit if vendor portals start fingerprint-detecting CloakBrowser version drift (Pitfall 7).

## Architecture Patterns

### System Architecture Diagram

```
                                ┌────────────────────────────────────┐
                                │  Main App (external consumer)      │
                                │  X-API-Key: <MAIN_APP_API_KEY>     │
                                └─────────────┬──────────────────────┘
                                              │  HTTP + WS
                                              │  /sessions/*  /profiles/*
                                              │  /api/profiles/{id}/cdp  (WS)
                                              ▼
            ┌─────────────────────────────────────────────────────────────┐
            │  FastAPI app (backend/main.py + routers/)                    │
            │                                                              │
            │  AuthMiddleware (existing — admin only after D-12 update)    │
            │   exempts: /api/auth/*, /api/status, /sessions, /profiles    │
            │                                                              │
            │  ┌─────────────────────────────┐  ┌──────────────────────┐  │
            │  │ routers/sessions.py         │  │ routers/profiles.py  │  │
            │  │ (NEW — D-10)                │  │ (NEW — D-10)         │  │
            │  │ POST /sessions              │  │ GET    /profiles     │  │
            │  │ GET  /sessions              │  │ GET    /profiles/{id}│  │
            │  │ GET  /sessions/{id}         │  │ PATCH  /profiles/{id}│  │
            │  │ DELETE /sessions/{id}       │  │ DELETE /profiles/{id}│  │
            │  │ deps=[Depends(require_api_key)]                       │  │
            │  └──────┬──────────────────────┘  └──────┬───────────────┘  │
            │         │                                 │                  │
            │         ▼                                 ▼                  │
            │  ┌──────────────────────────────────────────────────┐       │
            │  │  SessionManager  (NEW — backend/session_manager.py│       │
            │  │  Lifespan singleton on app.state.session_manager  │       │
            │  │  - get_or_wake(vendor_type, vendor_connection_id) │       │
            │  │  - on_attach(profile_id)                          │       │
            │  │  - on_all_detached(profile_id)                    │       │
            │  │  - _key_locks: dict[(str,str), asyncio.Lock]      │       │
            │  │  - _idle_tasks: dict[str, asyncio.Task]           │       │
            │  └────┬──────────────┬──────────────────────┬────────┘       │
            │       │              │                      │                │
            │       ▼              ▼                      ▼                │
            │  ┌─────────┐   ┌───────────────┐   ┌──────────────────┐     │
            │  │ database│   │BrowserManager │   │  CDP WS proxy    │     │
            │  │ upsert_ │   │ + Semaphore(3)│   │  (existing       │     │
            │  │ profile │   │ + about:blank │   │   handler in     │     │
            │  │ _by_    │   │   probe       │   │   main.py — gets │     │
            │  │ vendor  │   │ - launch      │   │   X-API-Key check│     │
            │  │ ()      │   │ - stop        │   │   + try/finally  │     │
            │  └────┬────┘   │ + RunningProf │   │   count mutation)│     │
            │       │        │   extension   │   └──────┬───────────┘     │
            │       │        └───┬───────────┘          │                  │
            │       ▼            ▼                       │                  │
            │  ┌─────────────────────────────────────────▼──┐               │
            │  │  SQLite profiles + vendor_templates         │               │
            │  │  UNIQUE(vendor_type, vendor_connection_id)  │               │
            │  └─────────────────────────────────────────────┘               │
            └────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                         ┌──────────────────────┐
                         │  Per-profile          │
                         │  Chromium + Xvnc      │
                         │  (BrowserManager      │
                         │   owns lifecycle)     │
                         └──────────────────────┘
```

### Recommended Project Structure

```
backend/
├── main.py                      # MODIFIED — _AUTH_EXEMPT additions, lifespan
│                                #   constructs SessionManager, CDP WS handler
│                                #   gains X-API-Key check + count mutations
├── browser_manager.py           # MODIFIED — RunningProfile extended (4 fields),
│                                #   __init__ allocates Semaphore(3),
│                                #   launch() wraps in semaphore + about:blank probe
├── session_manager.py           # NEW
├── auth_api_key.py              # NEW
├── database.py                  # MODIFIED — adds upsert_profile_by_vendor()
├── models.py                    # MODIFIED — adds SessionRequest/Response/StatusResponse,
│                                #   ProfilePatch
├── routers/
│   ├── templates.py             # UNCHANGED (Phase 1)
│   ├── sessions.py              # NEW
│   └── profiles.py              # NEW
└── tests/
    ├── conftest.py              # MODIFIED — adds mock_browser_manager fixture
    ├── test_session_manager.py  # NEW (unit)
    ├── test_sessions_router.py  # NEW (integration)
    ├── test_profiles_router.py  # NEW (integration)
    ├── test_auth_api_key.py     # NEW (unit)
    └── test_warm_pool_e2e.py    # NEW (slow, marked)
```

`pyproject.toml` gets a `markers` section:

```toml
[tool.pytest.ini_options]
testpaths = ["backend/tests"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow (real Chromium, real VNC). Run with -m slow.",
]
addopts = "-m 'not slow'"  # default: skip slow tests; CI overrides for nightly run
```

### Pattern 1: Lifespan-Scoped SessionManager Singleton (D-01)

**What:** SessionManager is constructed once in `lifespan` and stored on `app.state`. Routes resolve via `Depends(get_session_manager)`.

**When to use:** Required by D-01.

**Example:**
```python
# backend/main.py — modify the existing lifespan
from .session_manager import SessionManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_required_env()
    db.init_db()
    await browser_mgr.cleanup_stale()
    # NEW (D-01):
    app.state.session_manager = SessionManager(browser_mgr=browser_mgr)
    logger.info("VendorBrowser started")
    yield
    # NEW (D-01): cancel all idle tasks before BrowserManager.cleanup_all
    await app.state.session_manager.shutdown()
    logger.info("Shutting down — stopping all browsers...")
    await browser_mgr.cleanup_all()
```

```python
# backend/routers/sessions.py
from fastapi import APIRouter, Depends, Request
from ..session_manager import SessionManager
from ..auth_api_key import require_api_key

def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_api_key)],
)

@router.post("", response_model=SessionResponse)
async def post_session(
    payload: SessionRequest,
    sm: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    ...
```

### Pattern 2: Per-Key `asyncio.Lock` with Mutex on Dict (D-02)

**What:** A `dict[tuple[str,str], asyncio.Lock]` plus a class-level `asyncio.Lock` that guards the dict-mutation race.

**When to use:** Required by D-02.

**Example:**
```python
class SessionManager:
    def __init__(self, browser_mgr: BrowserManager) -> None:
        self._browser = browser_mgr
        self._key_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._locks_mutex = asyncio.Lock()
        self._idle_tasks: dict[str, asyncio.Task] = {}

    async def _get_key_lock(self, key: tuple[str, str]) -> asyncio.Lock:
        async with self._locks_mutex:
            return self._key_locks.setdefault(key, asyncio.Lock())

    async def get_or_wake(self, vendor_type: str, vendor_connection_id: str) -> SessionResult:
        key = (vendor_type, vendor_connection_id)
        lock = await self._get_key_lock(key)
        async with lock:
            # ─── CRITICAL SECTION ───
            profile = db.upsert_profile_by_vendor(vendor_type, vendor_connection_id)
            running = self._browser.running.get(profile["id"])
            if running is None:
                running = await self._browser.launch(profile)  # Semaphore + probe inside
            self._cancel_idle(profile["id"])
            return SessionResult(profile_id=profile["id"], cdp_url=..., state=...)
```

### Pattern 3: WS Proxy `try/finally` for Count Mutation (D-04)

**What:** The CDP WS proxy increments `cdp_attach_count` on accept, decrements on disconnect, both under `browser_mgr._lock`. On zero across both signals, schedules an idle task.

**When to use:** Required by D-04. Phase 2 modifies the existing `cdp_proxy` handler at `main.py:1007`.

**Example:**
```python
# backend/main.py — modify existing handler
@app.websocket("/api/profiles/{profile_id}/cdp")
async def cdp_proxy(websocket: WebSocket, profile_id: str):
    if not await _check_websocket_origin(websocket):
        return

    # ── NEW (L-03 resolution): X-API-Key validation BEFORE accept ──
    if not _ws_api_key_valid(websocket):
        await websocket.close(code=4401, reason="Invalid or missing API key")
        return

    running = browser_mgr.running.get(profile_id)
    if not running:
        await websocket.close(code=4004, reason="Profile not running")
        return

    await websocket.accept()

    # ── NEW: increment under lock, notify SessionManager ──
    async with browser_mgr._lock:
        running.cdp_attach_count += 1
    sm: SessionManager = app.state.session_manager
    sm.on_attach(profile_id)

    try:
        # … existing code: get ws_url from /json/version, call _proxy_cdp_websocket
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:{running.cdp_port}/json/version", timeout=5)
            ws_url = resp.json()["webSocketDebuggerUrl"]
        await _proxy_cdp_websocket(websocket, ws_url, f"CDP proxy [{profile_id}]")
    finally:
        # ── NEW: decrement under lock, notify on zero ──
        async with browser_mgr._lock:
            running.cdp_attach_count = max(0, running.cdp_attach_count - 1)
            both_zero = running.cdp_attach_count == 0 and running.viewer_attach_count == 0
        if both_zero:
            sm.on_all_detached(profile_id)
```

The same try/finally pattern applies to `/api/profiles/{profile_id}/cdp/devtools/{path:path}` at `main.py:1035`.

### Anti-Patterns to Avoid

- **Don't put `await semaphore.acquire()` INSIDE `browser_mgr._lock`.** That serializes ALL launches behind `_lock` and makes the semaphore redundant. Acquire the semaphore FIRST, then enter `_lock` only for the small `running` dict mutations.
- **Don't have `SessionManager` call `VNCManager.allocate()` directly.** It calls only `BrowserManager.launch/stop`.
- **Don't read live template fields at wake time.** The profile row is the snapshot (Phase 1 D-03 / TMPL-05).
- **Don't put idle timers in a module-global dict or DB table.** They live in `SessionManager._idle_tasks`.
- **Don't merge machine API and admin API into one router.** Two routers, two auth surfaces (D-10, D-12).
- **Don't `await context.new_page()` inside `browser_mgr._lock`** for the `about:blank` probe — Playwright I/O can block the lock for seconds. Probe AFTER releasing `_lock` and BEFORE inserting into `running` dict; if probe fails, run cleanup before raising.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Constant-time API key comparison | `if api_key == MAIN_APP_API_KEY:` | `hmac.compare_digest(api_key.encode(), MAIN_APP_API_KEY.encode())` | Timing-attack resistant; already the project pattern at `main.py:103, 114` `[CITED: docs.python.org/3/library/hmac.html]` |
| API key header extraction | `request.headers.get("X-API-Key")` | `from fastapi.security import APIKeyHeader; api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)` | Auto-generates OpenAPI security scheme; D-11 mandates this `[CITED: fastapi.tiangolo.com/reference/security/#apikeyheader]` |
| Concurrent launch cap | hand-rolled queue + bool flags | `asyncio.Semaphore(3)` + `asyncio.wait_for` | Stdlib, race-tested, well-documented `[CITED: docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore]` |
| Per-profile idle timer | thread + condition variable | `asyncio.create_task(asyncio.sleep(...))` + `task.cancel()` | Single event loop; no thread synchronization needed |
| WebSocket auth | inline `if` chain reading scope headers | small helper that reads headers from `websocket.scope` and `compare_digest`s | Match existing `_check_websocket_origin` pattern at `main.py:127` |
| Idempotent upsert | application-level check-then-insert | DB `UNIQUE` + `INSERT OR ABORT` + per-key `asyncio.Lock` | Pitfall 2 — race-tested by every production system that has had it; D-15 |
| State enum | string literals scattered through code | Pydantic `Literal["running", "idle", "stopped"]` | Type-checked at API boundary; D-18 |
| Datetime formatting | `str(dt)` | `dt.isoformat()` (UTC) | Consistent with existing `database.py::_now()` |

**Key insight:** Every "Don't Hand-Roll" entry above already has a stdlib or framework-provided answer. The Phase 2 surface area is small (~600 LoC across `session_manager.py`, `auth_api_key.py`, `routers/sessions.py`, `routers/profiles.py`); custom solutions to any of these would dwarf the actual orchestration logic.

## Pre-Phase Lookups (Resolved)

### L-01: KasmVNC websockify binds to 127.0.0.1

**Status:** ✅ RESOLVED — already correct.

`[VERIFIED: backend/vnc_manager.py:62]`:
```python
"-interface", "127.0.0.1",  # internal only, proxied by FastAPI
```
Plus `-publicIP 127.0.0.1` (line 68) skips STUN. The Xvnc websocket port is reachable only from inside the container; the FastAPI WS proxy is the only externally-reachable surface. No Phase 2 work required.

### L-02: CloakBrowser binary version pinning

**Status:** ⚠️ PARTIAL — `requirements.txt` uses floor pin only.

`[VERIFIED: backend/requirements.txt as of 2026-05-08]`:
```
cloakbrowser[geoip]>=0.3.14
```

The Dockerfile pulls whatever version `pip install` resolves on build day, then `ensure_binary()` downloads the matching Chromium binary into the image. The image IS reproducible byte-for-byte once built (because the binary is baked in), but two `docker build` runs on different days may produce different versions.

**Phase 2 action:** Out of scope to flip to exact pin (`==0.3.22` or whatever current is) — that's a Dockerfile change with deploy implications. **Recommend the planner add a non-blocking task** that pins `cloakbrowser` to an exact version in `requirements.txt` and documents the upgrade procedure. Pitfall 7 (fingerprint inconsistency on sleep/wake) is the rationale; risk is LOW for v1 as long as we don't unpin between sleeps in production.

**Confidence:** HIGH — verified by direct file read.

### L-03: CDP WS auth seam — DECISION

**Status:** ✅ RESOLVED — **add X-API-Key validation at the top of the existing handler**, do NOT move the route.

**Reasoning:**

1. The existing `/api/profiles/{id}/cdp` handler is at `main.py:1007-1032` plus the page-specific variant at `:1035-1049`. Moving them is invasive: the path moves, the URL on `/json/version` rewriting (`main.py:912, 942`) breaks, and any downstream system caching the old path breaks.
2. The `_AUTH_EXEMPT` change in D-12 only adds `/sessions` and `/profiles` prefixes. `/api/profiles/{id}/cdp` is NOT exempted, so `AuthMiddleware` continues to gate it on the admin cookie/Bearer token. **But** the Main App does not have those credentials.
3. **Solution:** Add `X-API-Key` validation INSIDE the WS handler, BEFORE `accept()`. If `AuthMiddleware` already accepted on the admin token, the X-API-Key check passes through (admin can still connect for debugging via the dashboard). If `AuthMiddleware` rejected, the handler never runs — but then the Main App needs to authenticate.

**Wait — there's a subtler issue.** If `AuthMiddleware` rejects the upgrade before the handler sees it, the Main App (no cookie, no bearer) can never connect. **Two options:**

**Option A (CHOSEN):** Add `/api/profiles/{id}/cdp` AND `/api/profiles/{id}/cdp/devtools/{path}` to `_AUTH_EXEMPT` (or skip those paths in `AuthMiddleware`), and validate `X-API-Key` inside the handler. This is the smallest viable change.

**Option B:** Move the route into `routers/sessions.py` under `dependencies=[Depends(require_api_key)]`. Rejected — too invasive, breaks `/json/version` URL rewriting, and Phase 4 owns CDP path cleanup.

**Implementation sketch (Option A):**

```python
# backend/main.py — extend _AUTH_EXEMPT and add CDP-specific bypass
_AUTH_EXEMPT = frozenset({
    "/api/auth/status",
    "/api/auth/login",
    "/api/status",
})
# CDP WS paths use prefix matching; AuthMiddleware learns to skip them
_AUTH_EXEMPT_PREFIXES = ("/sessions", "/profiles")  # NEW (D-12)
_CDP_WS_PREFIX = "/api/profiles/"  # path matches /api/profiles/{id}/cdp...

# In AuthMiddleware.__call__:
if (path in _AUTH_EXEMPT
    or any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES)
    or (scope["type"] == "websocket"
        and path.startswith(_CDP_WS_PREFIX)
        and "/cdp" in path)
    or not path.startswith("/api/")):
    await self.app(scope, receive, send)
    return
```

```python
# backend/main.py — small helper added near _check_websocket_origin
def _ws_api_key_valid(websocket: WebSocket) -> bool:
    """Validate X-API-Key on the WS upgrade scope before accept()."""
    if DEV_MODE and not MAIN_APP_API_KEY:
        return True
    if not MAIN_APP_API_KEY:
        return False  # fail-closed in production (already enforced by lifespan)
    for key, val in websocket.scope.get("headers", []):
        if key == b"x-api-key":
            return hmac.compare_digest(val.decode("latin-1"), MAIN_APP_API_KEY)
    return False

# In cdp_proxy and cdp_page_proxy, BEFORE accept():
if not _ws_api_key_valid(websocket):
    await websocket.close(code=4401, reason="Invalid or missing API key")
    return
```

**Browser caveat:** The browser-side WebSocket API does not support custom request headers `[CITED: peterbraden.co.uk/article/websocket-auth-fastapi]`. **The Main App is a server-side Playwright client**, which CAN send custom headers via `websockets.connect(..., extra_headers=[("X-API-Key", "…")])` — so this works for Phase 2's actual client. Phase 3's noVNC viewer uses a token-in-fragment scheme (URL-only auth), so the WS-headers limitation doesn't apply there.

**Confidence:** HIGH — verified the handler shape at `main.py:1007-1049` and the AuthMiddleware exemption pattern at `main.py:196`.

## Implementation Specifics (the 15-question focus list)

### 1. CDP WS Auth Seam (L-03)

Resolved above. Smallest viable change:
- Add `_AUTH_EXEMPT_PREFIXES` to bypass `AuthMiddleware` for CDP WS paths AND machine-API paths.
- Add `_ws_api_key_valid(websocket)` helper that reads `X-API-Key` from `websocket.scope.get("headers", [])` and compares with `hmac.compare_digest`.
- Call the helper before `await websocket.accept()` in `cdp_proxy` and `cdp_page_proxy`. Reject with `await websocket.close(code=4401, reason="Invalid or missing API key")`.

`[VERIFIED: backend/main.py:1007-1049]`

### 2. Concurrent-Launch Semaphore Mechanics (SESS-09)

The `Semaphore(3)` lives on `BrowserManager`, allocated in `__init__`. The acquire goes around the entire launch body (VNC start + Chromium launch + `about:blank` probe + post-conditions), but OUTSIDE the existing `self._lock` so concurrent launches for DIFFERENT profiles can proceed in parallel up to the cap.

```python
# backend/browser_manager.py — modify __init__ and launch
class BrowserManager:
    LAUNCH_TIMEOUT_SECS = 30  # how long to wait for a launch slot

    def __init__(self) -> None:
        self.running: dict[str, RunningProfile] = {}
        self._launching: set[str] = set()
        self.vnc = VNCManager()
        self._lock = asyncio.Lock()
        # NEW (SESS-09):
        self._launch_sem = asyncio.Semaphore(3)

    async def launch(self, profile: dict[str, Any]) -> RunningProfile:
        profile_id = profile["id"]

        # Quick guard against double-launch BEFORE acquiring the semaphore — cheap.
        async with self._lock:
            if profile_id in self.running or profile_id in self._launching:
                raise RuntimeError(f"Profile {profile_id} is already running")
            self._launching.add(profile_id)

        try:
            # NEW (SESS-09): cap concurrent launches; 503 on timeout
            try:
                await asyncio.wait_for(
                    self._launch_sem.acquire(),
                    timeout=self.LAUNCH_TIMEOUT_SECS,
                )
            except asyncio.TimeoutError:
                async with self._lock:
                    self._launching.discard(profile_id)
                raise BrowserLaunchError(
                    f"timed out waiting for launch slot after {self.LAUNCH_TIMEOUT_SECS}s"
                )

            try:
                # ... existing body: VNC allocate + start, port check,
                #     SingletonLock cleanup (already done at lines 187-190),
                #     launch_persistent_context_async, init_script, RunningProfile() ...

                # NEW (SESS-10): about:blank probe BEFORE registering in `running`
                await self._probe_about_blank(context, profile_id)

                async with self._lock:
                    self.running[profile_id] = running
                    self._launching.discard(profile_id)
                return running

            except Exception:
                async with self._lock:
                    self._launching.discard(profile_id)
                # NOTE: VNC cleanup already happens in existing except block
                raise
            finally:
                self._launch_sem.release()

        except BrowserLaunchError:
            raise
```

Failure paths:
- Semaphore acquire timeout → `BrowserLaunchError("timed out waiting for launch slot...")` → caught by `routers/sessions.py` → 503 with `{detail: "Browser launch failed", reason: "timed out waiting for launch slot"}`.
- `about:blank` probe failure → `BrowserLaunchError(...)` → same 503 path.
- Existing failures (CDP port in use, Xvnc fail, CloakBrowser exception) → propagate unchanged.

`[VERIFIED: docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore]` — `Semaphore.acquire` is awaitable; `release` is sync. `asyncio.wait_for` cancels the inner coroutine on timeout (Python 3.8+).

### 3. Idle Timer Cancellation Race (SESS-05, SESS-06, D-08, D-09)

The timer logic lives entirely in `SessionManager`. Two callbacks: `on_attach(profile_id)` (cancels any pending timer) and `on_all_detached(profile_id)` (schedules a new one).

**The cancel-vs-fire ordering:**

Inside `cdp_proxy`'s `try/finally`, the count mutation happens UNDER `browser_mgr._lock`. The cancel call (`sm.on_attach`) is **after** the increment, but the increment is still under the lock. Meanwhile, the idle task — when it fires — re-acquires `browser_mgr._lock` BEFORE checking the counts (D-08 step 1). So the sequence is naturally serialised by `_lock`:

| Thread A (`on_attach`) | Thread B (`_idle_sleep` firing) |
|---|---|
| Acquires `_lock` | Awaiting `asyncio.sleep(...)` |
| `cdp_attach_count += 1` | (sleep done, awaits `_lock`) |
| Releases `_lock` | Acquires `_lock` |
| Calls `sm.on_attach()` → `task.cancel()` | Re-checks counts: `cdp_attach_count == 1` → no stop |
| | Releases `_lock` |
| | (CancelledError already raised between steps but doesn't matter; even if the cancel arrives AFTER the re-check passes, the re-check would say "don't stop" and the task exits) |

**The lost-cancel scenario** (cancel arrives AFTER `await asyncio.sleep` returns but BEFORE the task acquires `_lock`):

```python
async def _idle_sleep(self, profile_id: str, delay: int) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    # cancel arrives in this window? It still works because:
    async with self._browser._lock:
        running = self._browser.running.get(profile_id)
        if not running:
            return
        if running.cdp_attach_count > 0 or running.viewer_attach_count > 0:
            return  # ← defence-in-depth re-check (D-08 step 2)
        await self._browser.stop_locked(profile_id)  # see note below
```

The D-08 re-check INSIDE the lock is what saves us. Even if `task.cancel()` arrives between `await asyncio.sleep` returning and the lock acquisition, the count re-check rejects the stop. **`on_attach` mutates the count BEFORE calling `task.cancel()`**, so by the time the timer wins the lock, the count is already >0.

**Important:** `BrowserManager.stop()` itself takes `_lock` at line 302 — calling `stop()` from inside `_idle_sleep` while already holding `_lock` would deadlock. **Two options:**

- **Option 1 (CHOSEN):** Refactor `BrowserManager.stop()` into a `_stop_locked()` helper that assumes the lock is held, and a wrapper `stop()` that takes the lock and calls `_stop_locked()`. The idle task uses `_stop_locked()`.
- **Option 2:** Idle task doesn't hold the lock when calling `stop()`. But then the cancel race is back. Rejected.

```python
class BrowserManager:
    async def stop(self, profile_id: str) -> None:
        async with self._lock:
            await self._stop_locked(profile_id)

    async def _stop_locked(self, profile_id: str) -> None:
        """Caller must hold self._lock."""
        running = self.running.pop(profile_id, None)
        if not running:
            return
        # ... existing context.close() + vnc.stop_vnc(running.display)
```

**Cancel-then-await pattern** (recommended by `[CITED: docs.python.org/3/library/asyncio-task.html#asyncio.Task.cancel]`):

```python
def _cancel_idle(self, profile_id: str) -> None:
    task = self._idle_tasks.pop(profile_id, None)
    if task is not None and not task.done():
        task.cancel()
        # Note: we don't await — the cancellation is fire-and-forget; the task's
        # finally block (D-08) handles cleanup. Awaiting would force on_attach
        # callers to be async, which is fine, but unnecessary for correctness.
```

Per the asyncio docs, `task.cancel()` schedules `CancelledError` on the next await point — it does not wait for the task to finish. This is fine because the idle task's only post-sleep action is to acquire `_lock`, re-check counts, and stop OR exit. Either path is harmless.

### 4. `upsert_profile_by_vendor` — Concrete SQL + Python (D-15)

**New function in `backend/database.py`** (lives next to existing `create_profile_from_template` at line 392):

```python
class NoTemplateError(Exception):
    def __init__(self, vendor_type: str) -> None:
        self.vendor_type = vendor_type
        super().__init__(f"No template configured for vendor_type={vendor_type!r}")


def upsert_profile_by_vendor(
    vendor_type: str,
    vendor_connection_id: str,
) -> dict[str, Any]:
    """SELECT → INSERT OR ABORT → SELECT in a single transaction (D-15).

    Returns the profile dict (with launch_args JSON-deserialized).
    Raises NoTemplateError if no vendor_template exists for the given type.

    Per-key asyncio.Lock at the SessionManager layer (D-02) is the in-process
    serialization; the UNIQUE(vendor_type, vendor_connection_id) constraint
    + IntegrityError swallow here is the cross-process safety net.
    """
    with get_db() as conn:
        # Step 1: SELECT existing.
        row = conn.execute(
            "SELECT * FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
            (vendor_type, vendor_connection_id),
        ).fetchone()
        if row:
            profile = dict(row)
            profile["launch_args"] = json.loads(profile.get("launch_args") or "[]")
            tags = conn.execute(
                "SELECT tag, color FROM profile_tags WHERE profile_id = ?",
                (profile["id"],),
            ).fetchall()
            profile["tags"] = [dict(t) for t in tags]
            return profile

        # Step 2: lookup template (raise if missing — D-16 404 path).
        template_row = conn.execute(
            "SELECT id, vendor_type, label, notes, blueprint, created_at, updated_at "
            "FROM vendor_templates WHERE vendor_type=?",
            (vendor_type,),
        ).fetchone()
        if not template_row:
            raise NoTemplateError(vendor_type)
        template = dict(template_row)

    # Step 3: snapshot via existing helper. Wraps its own with-conn transaction.
    # IntegrityError on the INSERT (cross-process race) is caught and re-SELECT
    # returns the winner's row.
    try:
        return create_profile_from_template(
            template=template,
            vendor_connection_id=vendor_connection_id,
            name=None,  # default: f"{vendor_type}/{vendor_connection_id}"
        )
    except sqlite3.IntegrityError:
        # Another worker won — re-SELECT.
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
                (vendor_type, vendor_connection_id),
            ).fetchone()
            if not row:
                # Should never happen — UNIQUE constraint guarantees the row exists.
                raise
            profile = dict(row)
            profile["launch_args"] = json.loads(profile.get("launch_args") or "[]")
            return profile
```

**Note on `INSERT OR ABORT` vs `INSERT OR IGNORE`:** The existing `create_profile_from_template` uses a plain `INSERT INTO profiles ...` — which behaves as `INSERT OR ABORT` by default (raises `IntegrityError` on UNIQUE violation). D-15 reads "INSERT OR ABORT"; this is satisfied by leaving the existing INSERT alone and catching `IntegrityError` upstream. **Do NOT switch the INSERT to `INSERT OR IGNORE`** — that would silently drop the conflict and the second SELECT would see a stale row.

### 5. `about:blank` Probe Implementation (SESS-10, Pitfall 13)

**Lives on `BrowserManager`. Called from `launch()` AFTER `add_init_script` and BEFORE registering in `running`.**

```python
class BrowserManager:
    PROBE_TIMEOUT_MS = 5000

    async def _probe_about_blank(self, context, profile_id: str) -> None:
        """Verify Chromium is alive after launch (Pitfall 13).

        Raises BrowserLaunchError on probe failure; caller cleans up.
        """
        try:
            page = await context.new_page()
            try:
                await page.goto("about:blank", timeout=self.PROBE_TIMEOUT_MS)
            finally:
                await page.close()
        except Exception as exc:  # PlaywrightError, TimeoutError, asyncio.TimeoutError, ConnectionError
            logger.warning(
                "about:blank probe failed for profile %s: %s: %s",
                profile_id, type(exc).__name__, exc,
            )
            # Clean up the half-launched context before raising
            try:
                await context.close()
            except Exception as inner_exc:
                logger.debug("post-probe context.close() failed: %s", inner_exc)
            raise BrowserLaunchError(f"about:blank probe failed: {type(exc).__name__}: {exc}")
```

**Exception types caught:** Playwright wraps all driver-side errors as `playwright._impl._errors.Error` subclasses. Defensively use a broad `except Exception` here — any failure (timeout, target closed, connection refused, browser crashed) means the launch is bad. The actual exception class name is logged for debugging.

**Error class:**
```python
# backend/browser_manager.py — module-level
class BrowserLaunchError(RuntimeError):
    """Raised when launch fails after the semaphore acquire (probe fail, timeout, etc.)."""
```

**Failure → 503 in routes:**
```python
# backend/routers/sessions.py
@router.post("", response_model=SessionResponse)
async def post_session(payload: SessionRequest, sm: ...):
    try:
        result = await sm.get_or_wake(payload.vendor_type, payload.vendor_connection_id)
    except NoTemplateError as exc:
        raise HTTPException(404, {"detail": str(exc), "vendor_type": exc.vendor_type})
    except BrowserLaunchError as exc:
        # Sanitize: no stack trace in body
        raise HTTPException(503, {"detail": "Browser launch failed", "reason": str(exc)})
    return result
```

`[CITED: playwright.dev/python/docs/api/class-page#page-goto]` — `page.goto(url, timeout=ms)`. Default timeout is 30s; we explicitly set 5s.

### 6. SingletonLock Cleanup (SESS-11, Pitfall 1)

**Status:** ✅ ALREADY IMPLEMENTED in Phase 1 (carried forward from pre-refocus codebase).

`[VERIFIED: backend/browser_manager.py:187-190]`:
```python
# Clean stale Chromium lock files (left by previous container crashes)
user_data_dir = Path(profile["user_data_dir"])
for lock_file in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
    lock_path = user_data_dir / lock_file
    lock_path.unlink(missing_ok=True)
```

This block runs UNCONDITIONALLY at the top of `launch()`, BEFORE `launchPersistentContext`, so it covers both fresh starts and warm-pool wakes after SIGKILL. No Phase 2 work required for SESS-11; **the planner should add a verification test that asserts the cleanup runs on every launch** (via mock filesystem with stale files pre-created).

### 7. `RunningProfile` Extension Shape (D-04, SESS-04)

```python
# backend/browser_manager.py — extend dataclass at line 148
import datetime

@dataclass
class RunningProfile:
    profile_id: str
    context: Any
    display: int
    ws_port: int
    cdp_port: int
    # ── NEW Phase 2 (additive) ──
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
    last_launched_at: datetime.datetime | None = None
    idle_started_at: datetime.datetime | None = None
```

**Mutation rules:**

| Field | Mutated By | Lock Required |
|-------|-----------|---------------|
| `cdp_attach_count` | CDP WS proxy try/finally | `browser_mgr._lock` |
| `viewer_attach_count` | (Phase 3) viewer WS proxy + admin VNC proxy | `browser_mgr._lock` |
| `last_launched_at` | `BrowserManager.launch()` | `browser_mgr._lock` (set when registering in `running` dict) |
| `idle_started_at` | `SessionManager.on_all_detached()` | `browser_mgr._lock` (set under same lock that observed both counts hit zero) |

`last_launched_at = datetime.datetime.now(datetime.timezone.utc)` set just before `self.running[profile_id] = running` inside the lock. `idle_started_at = datetime.datetime.now(datetime.timezone.utc)` set inside `on_all_detached` when the timer is scheduled; cleared (`None`) on `on_attach` cancel.

### 8. FastAPI Lifespan + Shutdown (D-01)

```python
# backend/main.py — modify existing lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_required_env()
    db.init_db()
    await browser_mgr.cleanup_stale()
    # NEW
    app.state.session_manager = SessionManager(browser_mgr=browser_mgr)
    logger.info("VendorBrowser started")
    yield
    logger.info("Shutting down — stopping all browsers...")
    # NEW: cancel idle timers FIRST so they don't try to run during cleanup_all
    await app.state.session_manager.shutdown()
    await browser_mgr.cleanup_all()
```

**`SessionManager.shutdown()`:**

```python
async def shutdown(self) -> None:
    """Cancel all pending idle tasks. Does NOT stop running profiles —
    BrowserManager.cleanup_all() handles that."""
    tasks = list(self._idle_tasks.values())
    self._idle_tasks.clear()
    for t in tasks:
        if not t.done():
            t.cancel()
    # Optional: gather with return_exceptions to drain CancelledError
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

`SessionManager` does NOT call `BrowserManager.cleanup_all()` — that's the existing behavior on shutdown and stays unchanged. `SessionManager` only owns the timer dict.

### 9. APIKeyHeader Implementation (SEC-01, D-11)

```python
# backend/auth_api_key.py — new file
"""Machine-API authentication via X-API-Key header (D-11, SEC-01).

Mounted on routers/sessions.py and routers/profiles.py via:
    router = APIRouter(prefix="/sessions", dependencies=[Depends(require_api_key)])
"""
from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger("vendorbrowser.auth_api_key")

# auto_error=False so we raise our own 401 with a sanitized body and the
# WWW-Authenticate header (RFC 7235 §4.1).
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _expected_key() -> str | None:
    """Read MAIN_APP_API_KEY at request time (NOT module import time) so tests
    that monkeypatch os.environ via the conftest behave correctly."""
    return (os.environ.get("MAIN_APP_API_KEY") or "").strip() or None


def _dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").strip().lower() in ("1", "true", "yes")


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """Validate X-API-Key against MAIN_APP_API_KEY (constant-time compare).

    Raises 401 on missing/invalid. In DEV_MODE with no MAIN_APP_API_KEY set,
    bypasses (matches Phase 1 D-17 fail-closed-in-prod / open-in-dev convention).
    """
    expected = _expected_key()
    if expected is None:
        if _dev_mode():
            logger.debug("DEV_MODE bypass for X-API-Key check")
            return "dev-mode"
        # Production-mode missing key — should never happen because lifespan
        # _check_required_env() refuses to start. Fail-closed anyway.
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not hmac.compare_digest(api_key.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
```

**Why `APIKeyHeader` over `Header(alias="X-API-Key")`:**

| Aspect | `APIKeyHeader` | `Header(alias="X-API-Key")` |
|---|---|---|
| OpenAPI docs | Auto-generates `securitySchemes: {ApiKeyAuth: {type: apiKey, in: header, name: X-API-Key}}` | No security scheme; just a header parameter |
| Swagger UI "Authorize" button | Yes | No |
| Reusability | One-line `dependencies=[Depends(require_api_key)]` | Same |
| Validation | Identical (you implement) | Identical (you implement) |

D-11 mandated `APIKeyHeader`. `[CITED: fastapi.tiangolo.com/reference/security/#apikeyheader]`.

**Why `hmac.compare_digest` not `==`:** `==` short-circuits on first mismatched byte; an attacker can measure response time to learn each byte. `compare_digest` always compares the full string. The existing codebase already uses this at `main.py:103, 114`. `[CITED: docs.python.org/3/library/hmac.html#hmac.compare_digest]`.

### 10. Concurrent `POST /sessions` Race Test (SESS-07)

**Use `httpx.AsyncClient` with `ASGITransport(app=...)` — NOT `TestClient`.** `TestClient` is sync (uses `anyio.from_thread`); driving it with `asyncio.gather` doesn't actually achieve concurrency at the asyncio layer. `httpx.AsyncClient` over ASGI runs in the same event loop as the app and gives a real concurrent test.

```python
# backend/tests/test_sessions_router.py
import asyncio
import pytest
from httpx import ASGITransport, AsyncClient

@pytest.mark.asyncio
async def test_concurrent_post_sessions_idempotent(
    app_async_client: AsyncClient,  # fixture below
    seeded_template,                 # fixture creates a vendor_template with vendor_type="acme"
    auth_headers,                    # fixture returns {"X-API-Key": "test-key"}
    mock_browser_manager,            # fixture stubs launch/stop and tracks call count
    tmp_db,
):
    # SESS-07 regression guard for Pitfall 2.
    payload = {"vendor_type": "acme", "vendor_connection_id": "user-1"}

    responses = await asyncio.gather(*[
        app_async_client.post("/sessions", json=payload, headers=auth_headers)
        for _ in range(10)
    ])

    # All 10 succeed
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]

    # All 10 share the same profile_id
    profile_ids = {r.json()["profile_id"] for r in responses}
    assert len(profile_ids) == 1, f"Got multiple profile_ids: {profile_ids}"

    # DB has exactly one row for the pair
    import sqlite3
    from backend import database as db
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
            ("acme", "user-1"),
        ).fetchall()
    assert len(rows) == 1

    # BrowserManager.launch was called exactly once
    assert mock_browser_manager.launch.call_count == 1


# Fixture (lives in conftest.py)
@pytest.fixture
async def app_async_client(tmp_db, monkeypatch, mock_browser_manager):
    from backend import main
    # Wire the mock into app.state where the route looks for it
    monkeypatch.setattr(main, "browser_mgr", mock_browser_manager)
    # ... TestClient handles lifespan; AsyncClient needs an ASGITransport
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # TestClient(main.app) ensures lifespan ran; replicate manually:
        async with main.app.router.lifespan_context(main.app):
            yield client
```

**Why this works:** `mock_browser_manager.launch` is an `AsyncMock` that returns a fake `RunningProfile` with `cdp_attach_count=0`. Per-key `asyncio.Lock` (D-02) serialises the 10 calls; the second-through-tenth see `running.get(profile_id) is not None` after the first one wakes. Without the lock, they would all rush past `db.upsert_profile_by_vendor` (one would succeed, nine would `IntegrityError` and re-SELECT — still correct via D-15, but `launch.call_count` would be the giveaway).

**Note on fixtures vs `app_client`:** Phase 1 already has a sync `app_client` fixture (`backend/tests/conftest.py:62-72`). Phase 2 adds an `async` variant for race tests. Both can coexist.

### 11. Slow E2E Test Gating (D-19)

**`pyproject.toml`:**
```toml
[tool.pytest.ini_options]
testpaths = ["backend/tests"]
asyncio_mode = "auto"
markers = [
    "slow: real Chromium + real KasmVNC (warm-pool e2e). Run with -m slow.",
]
addopts = "-m 'not slow'"
```

**Test file:**
```python
# backend/tests/test_warm_pool_e2e.py
import asyncio
import os
import pytest

pytestmark = pytest.mark.slow

# This file does NOT import the cloakbrowser mock from conftest;
# instead it uses the real binary. Override fixtures as needed.

@pytest.mark.asyncio
async def test_idle_sleep_then_wake_persists_cookies(monkeypatch, real_browser_app):
    # Force a 2-second idle timeout for this test
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "2")

    # POST /sessions → live profile
    r = await real_browser_app.post("/sessions", json={...}, headers=...)
    assert r.json()["state"] in ("running", "running")  # may say "running"

    # Close CDP WS
    # ... open ws to /api/profiles/{id}/cdp, close, ...

    # Wait > IDLE_TIMEOUT_SECONDS
    await asyncio.sleep(3)

    # GET /sessions/{id} should now report stopped
    r = await real_browser_app.get(f"/sessions/{profile_id}", headers=...)
    assert r.json()["state"] == "stopped"

    # POST /sessions again → wakes from STOPPED
    r2 = await real_browser_app.post("/sessions", json={...}, headers=...)
    assert r2.json()["profile_id"] == profile_id
    assert r2.json()["state"] == "running"

    # Cookies dir on disk still present (proves session state persisted)
    profile_dir = ...  # from r.json()["profile_id"] → profiles/{id}
    assert (profile_dir / "Default" / "Cookies").exists() or \
           (profile_dir / "Default").exists()
```

CI runs `pytest` (default → skips `slow`). Nightly / pre-release runs `pytest -m slow` separately.

### 12. `GET /sessions/{id}` State Computation (D-18, SESS-13)

```python
# backend/session_manager.py — derive state envelope on demand

def status_envelope(self, profile_id: str) -> SessionStatusResponse | None:
    """Return state envelope for /sessions/{id}, or None if unknown.

    Caller (router) uses None as the 404 trigger.
    """
    # Note: profile must EXIST in DB even if not running. The router
    # SHOULD check db.get_profile(profile_id) first; if profile row missing,
    # return 404. If profile row exists but not running, state="stopped".
    running = self._browser.running.get(profile_id)
    idle_task = self._idle_tasks.get(profile_id)

    if running is None:
        return SessionStatusResponse(
            state="stopped",
            cdp_attach_count=0,
            viewer_attach_count=0,
            idle_expires_at=None,
            last_launched_at=None,  # in-memory only; lost on restart
        )

    has_attach = (running.cdp_attach_count > 0 or running.viewer_attach_count > 0)

    if has_attach:
        state = "running"
        idle_expires_at = None
    elif idle_task is not None and not idle_task.done():
        state = "idle"
        idle_started = running.idle_started_at
        if idle_started is not None:
            idle_timeout = int(os.environ.get("IDLE_TIMEOUT_SECONDS", "600"))
            idle_expires_at = idle_started + datetime.timedelta(seconds=idle_timeout)
        else:
            idle_expires_at = None
    else:
        # Edge: counts are zero but no idle task scheduled yet (just-launched window).
        # Treat as "running" — the WS hasn't connected yet but the process is alive.
        state = "running"
        idle_expires_at = None

    return SessionStatusResponse(
        state=state,
        cdp_attach_count=running.cdp_attach_count,
        viewer_attach_count=running.viewer_attach_count,
        idle_expires_at=idle_expires_at.isoformat() if idle_expires_at else None,
        last_launched_at=running.last_launched_at.isoformat() if running.last_launched_at else None,
    )
```

**Router:**
```python
@router.get("/{profile_id}", response_model=SessionStatusResponse)
async def get_session_status(
    profile_id: str,
    sm: SessionManager = Depends(get_session_manager),
) -> SessionStatusResponse:
    if db.get_profile(profile_id) is None:
        raise HTTPException(404, {"detail": "Profile not found", "profile_id": profile_id})
    envelope = sm.status_envelope(profile_id)
    if envelope is None:
        raise HTTPException(404, {"detail": "Profile not found", "profile_id": profile_id})
    return envelope
```

### 13. Restart Safety (Success Criterion 5)

**No new lifespan startup work required.**

`[VERIFIED: backend/main.py:411-418]` — existing lifespan calls `browser_mgr.cleanup_stale()` which (via `vnc_manager.cleanup_stale`) kills any orphan Xvnc processes from a prior container. After that, `browser_mgr.running` is empty. First `POST /sessions` after restart hits `running.get(profile_id) is None` → calls `launch()` → semaphore acquires → Xvnc allocates a fresh display → Chromium relaunches with the same `user_data_dir`.

**Pitfall 12 (zombie Xvnc) is already covered** by the existing `cleanup_stale` logic. The Phase 2 success criterion 5 just requires:

1. ✅ Lifespan startup does not auto-wake (it doesn't — `running` is built lazily)
2. ✅ `cleanup_stale` removes any zombie processes
3. ✅ `SingletonLock` cleanup runs on the first launch (already in `launch()` line 187-190)
4. ✅ Wake within launch timeout — the `LAUNCH_TIMEOUT_SECS=30` semaphore timeout

**Recommend the planner add a unit test** that:
- Constructs `BrowserManager` fresh (mocked Chromium / VNC)
- Asserts `running == {}`
- Calls `POST /sessions` for a known `(vendor_type, vendor_connection_id)` whose template exists
- Asserts the response says `state=running` and `last_launched_at` is set
- Asserts `running` now contains exactly one entry

### 14. `GET /profiles`, `PATCH /profiles`, `DELETE /profiles` (PROF-01..04, D-20)

Mirror `routers/templates.py`. Thin wrappers over `database.py` helpers. `DELETE` calls `BrowserManager.stop` first (existing pattern at `main.py:533-552`).

```python
# backend/routers/profiles.py
from fastapi import APIRouter, Depends, HTTPException, Path, Query

router = APIRouter(
    prefix="/profiles",
    tags=["profiles"],
    dependencies=[Depends(require_api_key)],
)

@router.get("", response_model=list[ProfileResponse])
async def list_profiles(
    vendor_type: str | None = Query(default=None),
    vendor_connection_id: str | None = Query(default=None),
) -> list[ProfileResponse]:
    rows = db.list_profiles_filtered(  # NEW DB helper, see below
        vendor_type=vendor_type,
        vendor_connection_id=vendor_connection_id,
    )
    return [ProfileResponse(**r) for r in rows]


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str) -> ProfileResponse:
    row = db.get_profile(profile_id)
    if row is None:
        raise HTTPException(404, {"detail": "Profile not found", "profile_id": profile_id})
    return ProfileResponse(**row)


@router.patch("/{profile_id}", response_model=ProfileResponse)
async def patch_profile(profile_id: str, payload: ProfilePatch) -> ProfileResponse:
    # PROF-03: only admin-owned fields. Identity keys (vendor_type, vendor_connection_id,
    # template_id) are not patchable. Phase 2 v1: notes only. clipboard_sync NOT patchable
    # (CLAUDE.md security rule 2).
    fields = payload.model_dump(exclude_unset=True)
    row = db.update_profile(profile_id, **fields)
    if row is None:
        raise HTTPException(404, {"detail": "Profile not found", "profile_id": profile_id})
    return ProfileResponse(**row)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    request: Request,
):
    profile = db.get_profile(profile_id)
    if profile is None:
        raise HTTPException(404, {"detail": "Profile not found", "profile_id": profile_id})

    # 1. Stop running session (idempotent)
    if profile_id in browser_mgr.running:
        await browser_mgr.stop(profile_id)

    # 2. Cancel any idle task for this profile
    sm: SessionManager = request.app.state.session_manager
    sm._cancel_idle(profile_id)

    # 3. Remove the per-key lock entry (Claude's discretion — prevent unbounded growth)
    key = (profile["vendor_type"], profile["vendor_connection_id"])
    sm._key_locks.pop(key, None)

    # 4. Drop DB row
    db.delete_profile(profile_id)

    # 5. Remove on-disk profile dir
    user_data_dir = Path(profile["user_data_dir"])
    if user_data_dir.exists():
        shutil.rmtree(user_data_dir, ignore_errors=True)

    # 204 → no body
```

**`db.list_profiles_filtered` (NEW helper):**
```python
def list_profiles_filtered(
    vendor_type: str | None = None,
    vendor_connection_id: str | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM profiles"
    where: list[str] = []
    params: list[Any] = []
    if vendor_type is not None:
        where.append("vendor_type = ?")
        params.append(vendor_type)
    if vendor_connection_id is not None:
        where.append("vendor_connection_id = ?")
        params.append(vendor_connection_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    with get_db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        result = []
        for row in rows:
            p = dict(row)
            p["launch_args"] = json.loads(p.get("launch_args") or "[]")
            tags = conn.execute(
                "SELECT tag, color FROM profile_tags WHERE profile_id = ?",
                (p["id"],),
            ).fetchall()
            p["tags"] = [dict(t) for t in tags]
            result.append(p)
        return result
```

### 15. Project Skills (.claude/skills/)

`[VERIFIED: 2026-05-08]` — only the user-level `~/.claude` skill paths exist; no project-local `.claude/skills/` directory. The `find /Users/troy/Code/_kickback/CloakBrowser-Manager -name "SKILL.md"` returns three results, all inside `backend/.venv/` (vendored Playwright + FastAPI agent skills). **None apply to Phase 2.** No project-skill constraints.

## Pydantic Model Shapes

```python
# backend/models.py — additions

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated, Literal

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_type: NonEmptyStr
    vendor_connection_id: NonEmptyStr


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    cdp_url: str                           # /api/profiles/{id}/cdp (D-13)
    vnc_viewer_url: str = ""               # Phase 3 wires; empty string for now
    state: Literal["running", "idle", "stopped"]


class SessionStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["running", "idle", "stopped"]
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
    idle_expires_at: str | None = None     # ISO-8601 UTC or null
    last_launched_at: str | None = None    # ISO-8601 UTC or null


class SessionListItem(BaseModel):
    """One entry in GET /sessions response (D-14)."""
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    vendor_type: str
    vendor_connection_id: str
    state: Literal["running", "idle", "stopped"]
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
    idle_expires_at: str | None = None
    last_launched_at: str | None = None


class ProfilePatch(BaseModel):
    """Admin-owned fields only (PROF-03). Identity keys NOT patchable;
    clipboard_sync NOT patchable (CLAUDE.md security rule 2)."""
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None)
    # Phase 2 v1: notes-only patch surface; PATCH expand happens in v1.x.


class SessionDeleteResponse(BaseModel):
    """Empty body — 204 No Content."""
    pass
```

## Common Pitfalls

### Pitfall A: Acquiring `Semaphore` inside `_lock`

**What goes wrong:** Wrapping `await self._launch_sem.acquire()` inside `async with self._lock:` serialises ALL launches behind the lock. The cap of 3 means nothing — only one launch runs at a time.

**Why it happens:** Misreading the existing pattern at `browser_mgr.launch:168-171` where `_lock` guards the `running` dict mutation.

**How to avoid:** Acquire the semaphore OUTSIDE `_lock`. Only mutate `running` / `_launching` under `_lock`. See §2 implementation sketch.

**Warning signs:** Race test fails (`launch.call_count > 1`); restart wake takes 30s instead of ~3s.

### Pitfall B: Missed-cancel race on idle timer

**What goes wrong:** `task.cancel()` arrives AFTER the task's `await asyncio.sleep` returns but BEFORE it acquires `_lock`. The task proceeds to call `BrowserManager.stop()` despite the attach event.

**Why it happens:** Cancel and resume are independent events; without a re-check, the cancel can lose.

**How to avoid:** Defence-in-depth: the timer task re-checks `cdp_attach_count > 0 OR viewer_attach_count > 0` INSIDE `_lock` before calling `stop()` (D-08 step 2). And `on_attach` MUST mutate the count BEFORE calling `task.cancel()` so the re-check sees the truth.

**Warning signs:** "Connection refused" from the Main App after warm-pool wake; `event=warm_pool_sleep` log lines paired with non-zero counts in the same second.

### Pitfall C: `BrowserManager.stop()` deadlock

**What goes wrong:** Idle timer holds `_lock` and calls `await self._browser.stop(profile_id)`, which itself does `async with self._lock` — deadlock (`asyncio.Lock` is not re-entrant).

**Why it happens:** Reusing the public `stop()` API from inside the lock.

**How to avoid:** Refactor `stop()` into `_stop_locked()` (lock-held) + public `stop()` (lock-acquiring wrapper). See §3.

**Warning signs:** Idle timer task hangs forever; `asyncio.all_tasks()` shows pending `_idle_sleep`.

### Pitfall D: Tests using `TestClient` for concurrency

**What goes wrong:** `asyncio.gather(*[client.post(...)])` against `starlette.testclient.TestClient` does NOT achieve real concurrency — `TestClient` runs the app in a separate thread via `anyio.from_thread`, so all 10 calls serialize.

**Why it happens:** `TestClient` looks like an async client (you call it from `async` test code), but it bridges to sync internally.

**How to avoid:** Use `httpx.AsyncClient(transport=ASGITransport(app=app))` for concurrency tests. See §10.

**Warning signs:** Race test passes even when `_key_locks` is removed; `launch.call_count` always equals 1 even without serialization.

### Pitfall E: Reading `MAIN_APP_API_KEY` at module import

**What goes wrong:** `MAIN_APP_API_KEY = os.environ.get(...)` at module top of `auth_api_key.py` captures the env var at import time. Tests that set the env var via `monkeypatch.setenv("MAIN_APP_API_KEY", "test-key")` don't take effect.

**Why it happens:** Module import order vs. fixture activation.

**How to avoid:** Read at request time inside `require_api_key`. See §9 `_expected_key()` helper.

**Warning signs:** Tests with monkeypatched API keys see 401s on routes that should accept the test key.

### Pitfall F: `INSERT OR IGNORE` swallowing the conflict silently

**What goes wrong:** If the upsert helper uses `INSERT OR IGNORE INTO profiles ...` and a parallel worker won the race, the IGNORE returns success but does NOT report which row exists. The follow-up SELECT works, but the codebase loses the "I just created this" signal — and any callers relying on `row.lastrowid` get garbage.

**Why it happens:** `INSERT OR IGNORE` is intuitive but loses information.

**How to avoid:** Use plain `INSERT` (default `OR ABORT`), catch `sqlite3.IntegrityError`, and re-SELECT. See §4.

**Warning signs:** Phantom "row exists but seems different" debugging sessions; flaky tests where the second worker thinks it inserted.

## Code Examples

### Verified Pattern: FastAPI Lifespan with `app.state`

```python
# backend/main.py — pattern from FastAPI docs
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session_manager = SessionManager(...)
    yield
    await app.state.session_manager.shutdown()

# In a route:
def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager
```

`[CITED: fastapi.tiangolo.com/advanced/events/#lifespan]` — `app.state` survives between requests within a single ASGI app instance. Lifespan runs once per process.

### Verified Pattern: `asyncio.wait_for` with `Semaphore.acquire`

```python
try:
    await asyncio.wait_for(sem.acquire(), timeout=30)
except asyncio.TimeoutError:
    raise BrowserLaunchError("timed out waiting for launch slot")
try:
    # ... do work ...
finally:
    sem.release()
```

`[CITED: docs.python.org/3/library/asyncio-task.html#asyncio.wait_for]` — `wait_for` cancels the wrapped coroutine on timeout. `Semaphore.acquire` is a coroutine; on cancel, it does NOT acquire (so no `release()` mismatch).

### Verified Pattern: `hmac.compare_digest` for API keys

```python
import hmac
if hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
    ...
```

`[CITED: docs.python.org/3/library/hmac.html#hmac.compare_digest]` — constant-time comparison. Already used at `backend/main.py:103, 114`.

### Verified Pattern: `pytest.mark.slow`

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = ["slow: marks tests as slow"]
addopts = "-m 'not slow'"
```

`[CITED: docs.pytest.org/en/stable/how-to/mark.html]` — registered markers + `addopts` filter is the canonical pattern for opt-in slow tests.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `python-jose` for JWT | `PyJWT >= 2.12.1` | python-jose abandoned 2024-2025 with CVEs | Phase 1 already pinned PyJWT; not a Phase 2 concern |
| Inline header parsing for API keys | `fastapi.security.APIKeyHeader` | Always preferred | D-11 chose APIKeyHeader for OpenAPI docs |
| Polling Playwright `browser.connected` for state | Count WS connections at proxy | Pitfall 13 (silent wake failure) — Playwright connected-ness is not a live health probe | Phase 2 uses count-based + `about:blank` probe |
| `requests` / sync HTTP test | `httpx.AsyncClient` for concurrency | httpx 0.27+ is the de-facto async test client | Phase 2 race test uses httpx |

**Deprecated/outdated:**
- `BaseHTTPMiddleware` for auth on WS routes — wraps request body, breaks WS upgrade. The codebase already avoided this (`AuthMiddleware` is raw ASGI). Phase 2 follows the same pattern: no new middleware.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | `httpx.AsyncClient(ASGITransport(app=...))` runs the test in the SAME event loop as the app, providing real concurrency for `asyncio.gather(*[client.post(...)])` | §10 Concurrent POST Race Test | If wrong, the race test would pass even without `_key_locks`. Mitigation: in addition to checking `launch.call_count`, the test asserts the DB has exactly one row. |
| A2 | `BrowserManager.stop()`'s existing implementation acquires `_lock` (line 302) and is therefore non-reentrant — calling it from inside `_lock` deadlocks | §3 Idle Timer / Pitfall C | If stop() is already non-locking (just pop + close), no refactor needed. **Verified** — `[VERIFIED: backend/browser_manager.py:299-315]` does take the lock. Refactor required. |
| A3 | The `about:blank` probe via `await page.goto("about:blank", timeout=5000)` is sufficient to detect silent Chromium crashes between launch and registration | §5 about:blank Probe | Pitfall 13 explicitly recommended this approach; if probe is insufficient (e.g., page renders but JS crashes), tests would catch it. Acceptable risk. |
| A4 | The Main App connects via server-side `websockets.connect(extra_headers=...)`, not browser JS, so X-API-Key in upgrade headers works | §1 CDP WS Auth (L-03) | If Main App ever uses browser JS for CDP, headers are not supported by browser WebSocket API. Phase 2 assumes server-side only — documented in `cdp_proxy` docstring. |
| A5 | `IDLE_TIMEOUT_SECONDS` is read at idle-task-schedule time, not at task-fire time | §12 State Computation | If env var changes mid-process, behavior is "frozen at schedule." Acceptable — env vars don't change at runtime. |

## Open Questions (RESOLVED)

1. **Phase 1 didn't add `last_launched_at` columns to `profiles`. Should `GET /sessions/{id}` return null for `last_launched_at` after a service restart?**
   - What we know: D-18 says ISO-8601 of most recent successful launch, else `null`. Claude's discretion section says "in-memory only; lost on restart."
   - What's unclear: After restart, the very first `POST /sessions` wakes a profile. From that point forward, `last_launched_at` is set. Restart-then-`GET-without-`POST` returns `null` — by design.
   - Recommendation: Lock this behavior in the planner with an explicit unit test ("after restart, GET /sessions/{id} returns last_launched_at=null until first POST").

2. **`asyncio.Lock` cleanup on `DELETE /profiles/{id}` — what about race with a concurrent `POST /sessions`?**
   - What we know: Claude's discretion says clean up the per-key lock on delete.
   - What's unclear: A concurrent `POST /sessions` for the same key can have just acquired the lock; deleting the dict entry mid-call is harmless (the live `Lock` object is held by reference) but the next `POST` will create a fresh `Lock`, which means the in-flight `POST` and the new `POST` won't serialise.
   - Recommendation: Document that `DELETE /profiles/{id}` is "destructive — concurrent `POST /sessions` for the same key may race." This is acceptable because the destructive operation is a Main-App-initiated decision; the Main App should not concurrently DELETE and POST the same vendor pair.

3. **Should the slow E2E test reset `IDLE_TIMEOUT_SECONDS` cleanly between runs?**
   - What we know: `monkeypatch.setenv` reverts at test teardown.
   - What's unclear: If `IDLE_TIMEOUT_SECONDS` is captured at `SessionManager.__init__` time (e.g., cached), monkeypatch won't affect it.
   - Recommendation: Read the env var at scheduling time inside `on_all_detached`, not at `SessionManager.__init__`. Already reflected in §12 (calls `os.environ.get` per scheduling).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All backend | ✓ (verified `pyproject.toml` + Dockerfile) | 3.12-slim | — |
| FastAPI | API layer | ✓ | >=0.115.0 | — |
| Pydantic | Validation | ✓ | >=2.0 | — |
| `cloakbrowser` | Chromium | ✓ | >=0.3.14 (floor pin — see L-02) | — |
| KasmVNC `Xvnc` | VNC | ✓ (Dockerfile installs `kasmvncserver_bookworm_1.3.3`) | 1.3.3 | — |
| `pytest`, `pytest-asyncio` | Tests | ✓ (asyncio_mode=auto) | implicit | — |
| `httpx >=0.27` | Race tests | ✓ (already in requirements) | >=0.27.0 | — |
| `httpx.ASGITransport` | Race tests | ✓ (httpx 0.26+) | bundled | — |
| `unittest.mock.AsyncMock` | Unit tests | ✓ stdlib (Python 3.8+) | stdlib | — |
| Real Chromium for E2E | `pytest -m slow` | ✓ on dev machines via Dockerfile build, ✓ on CI runners with `cloakbrowser` installed | — | Skip with `addopts = "-m 'not slow'"` if unavailable |

**No missing dependencies.** Phase 2 introduces zero new third-party packages.

## Validation Architecture

Project config: `workflow.nyquist_validation: false` in `.planning/config.json`. **Per the gsd-phase-researcher contract, this section is omitted when nyquist_validation is explicitly false.**

(Stub retained for compliance with the standard schema:)

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (asyncio_mode=auto) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest -m "not slow"` |
| Full suite command | `pytest && pytest -m slow` |

### Sampling Rate

- **Per task commit:** `pytest backend/tests/test_session_manager.py backend/tests/test_sessions_router.py backend/tests/test_profiles_router.py backend/tests/test_auth_api_key.py -x`
- **Per wave merge:** `pytest -m "not slow"`
- **Phase gate:** `pytest -m "not slow"` clean + `pytest -m slow` clean before `/gsd-verify-work`

## Security Domain

`security_enforcement` not explicitly set in config — treat as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `APIKeyHeader` + `hmac.compare_digest` (D-11, SEC-01) |
| V3 Session Management | yes (Phase 3 owns full surface) | Phase 2: machine-API key only; admin cookie is Phase 3's `SameSite=Strict` hardening |
| V4 Access Control | yes | Strict path-prefix segregation (`/sessions`, `/profiles` → API key; `/admin/*` → cookie) — D-12 |
| V5 Input Validation | yes | Pydantic `min_length=1` on `vendor_type` / `vendor_connection_id`; `model_config = ConfigDict(extra="forbid")` rejects unknown fields |
| V6 Cryptography | yes (light — Phase 3 owns JWT signing) | Phase 2: `hmac.compare_digest` only; NEVER manual HMAC computation in Phase 2 |
| V7 Error Handling | yes | 503 body sanitised — no stack traces; full traceback to logs (Claude's discretion) |
| V14 Configuration | yes | `MAIN_APP_API_KEY` fail-closed via existing Phase 1 `_check_required_env` |

### Known Threat Patterns for FastAPI + Playwright + WebSocket Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Timing attack on API key compare | Information Disclosure | `hmac.compare_digest` (mandated D-11) |
| Token in querystring logged by proxies | Information Disclosure | (Phase 3 concern; Phase 2's `vnc_viewer_url` is empty/placeholder, no token surface) |
| Concurrent upsert creates duplicate profiles | Tampering | UNIQUE constraint + per-key `asyncio.Lock` (Pitfall 2, D-15) |
| Thundering herd on restart | Denial of Service | `asyncio.Semaphore(3)` + `wait_for` timeout → 503 (Pitfall 4, SESS-09) |
| Silent wake failure (Chromium crashes after launch) | Denial of Service | `about:blank` probe (Pitfall 13, SESS-10) |
| Stale SingletonLock blocks login state | Tampering / Spoofing | `unlink(missing_ok=True)` before launch (Pitfall 1, SESS-11) — already implemented |
| Missing X-API-Key reaches CDP WS via admin path bypass | Elevation of Privilege | L-03 resolution: validate X-API-Key INSIDE the WS handler regardless of upstream middleware result |
| `clipboard_sync` flipped to true via `PATCH /profiles/{id}` | Information Disclosure (OTPs leak) | `ProfilePatch` excludes `clipboard_sync` from patchable fields (CLAUDE.md security rule 2) |
| WS auth bypass via accept-then-validate | Elevation of Privilege | Validate BEFORE `await websocket.accept()`; close with `4401` on failure |

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: backend/main.py]` — full file read for `_AUTH_EXEMPT`, `AuthMiddleware`, `lifespan`, `cdp_proxy`, `cdp_page_proxy`, `_check_websocket_origin`
- `[VERIFIED: backend/browser_manager.py]` — full file read for `RunningProfile`, `BrowserManager.launch/stop/_lock`, SingletonLock cleanup at lines 187-190
- `[VERIFIED: backend/database.py]` — full file read for schema, `create_profile_from_template`, UNIQUE index
- `[VERIFIED: backend/routers/templates.py]` — Phase 1 router shape to mirror
- `[VERIFIED: backend/models.py]` — Pydantic v2 patterns
- `[VERIFIED: backend/vnc_manager.py:62, :68]` — L-01 confirmation
- `[VERIFIED: backend/requirements.txt]` — L-02 status (floor pin only)
- `[VERIFIED: backend/tests/conftest.py]` — Phase 1 fixture patterns to extend
- `[VERIFIED: .planning/phases/02-sessions-warm-pool-and-cdp-lifecycle/02-CONTEXT.md]` — D-01..D-20
- `[VERIFIED: .planning/research/PITFALLS.md]` — Pitfall 1, 2, 3, 4, 12, 13
- `[CITED: docs.python.org/3/library/hmac.html#hmac.compare_digest]`
- `[CITED: docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore]`
- `[CITED: docs.python.org/3/library/asyncio-task.html#asyncio.Task.cancel, asyncio.wait_for]`
- `[CITED: fastapi.tiangolo.com/reference/security/#apikeyheader]`
- `[CITED: fastapi.tiangolo.com/advanced/events/#lifespan]`
- `[CITED: playwright.dev/python/docs/api/class-page#page-goto]`
- `[CITED: docs.pytest.org/en/stable/how-to/mark.html]`

### Secondary (MEDIUM confidence)
- WebSearch (2026-05-08) — FastAPI WebSocket auth before-accept patterns; Hex Shift, Peter Braden, FastAPI docs concurrence on "validate before `accept()`"
- WebSearch (2026-05-08) — `APIKeyHeader` vs `Header` comparison; FastAPI GitHub issues #142, #2835
- WebSearch (2026-05-08) — `asyncio.Task.cancel` race patterns; Python issues #112202

### Tertiary (LOW confidence)
- (none — all critical claims are HIGH or MEDIUM)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version verified against `requirements.txt`
- Architecture: HIGH — every code seam verified against current `main.py` / `browser_manager.py` line numbers
- Pitfalls: HIGH — all from Pitfall-to-Phase mapping in PITFALLS.md (already-done research)
- L-01: HIGH — direct file read confirmed binding
- L-02: MEDIUM — current state is "floor pin" not "exact pin"; recommended action documented
- L-03: HIGH — design choice + implementation sketch verified against existing handler shape
- Test strategy: HIGH — fixture pattern verified by reading existing `backend/tests/conftest.py` and `test_api.py`

**Research date:** 2026-05-08
**Valid until:** 2026-06-07 (30 days for stable backend stack; this milestone has no fast-moving frontier)

---

*Phase: 02-sessions-warm-pool-and-cdp-lifecycle*
*Researched: 2026-05-08*
*Ready for planning: yes*
