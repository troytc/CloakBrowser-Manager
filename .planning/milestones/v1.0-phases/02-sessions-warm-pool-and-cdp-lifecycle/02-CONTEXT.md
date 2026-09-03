# Phase 2: Sessions, Warm-Pool, and CDP Lifecycle - Context

**Gathered:** 2026-05-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Delivers the milestone's core value proposition. After Phase 2:

- `POST /sessions` with `(vendor_type, vendor_connection_id)` returns `{profile_id, cdp_url, state}` — idempotent, race-safe, wakes from warm-pool sleep transparently. (`vnc_viewer_url` is allowed to come back empty/placeholder; the signed URL is wired in Phase 3.)
- `GET /sessions/{profile_id}` returns the live state envelope `{state, cdp_attach_count, viewer_attach_count, idle_expires_at, last_launched_at}`.
- `DELETE /sessions/{profile_id}` tears down Chromium + KasmVNC for that profile but leaves the row and the on-disk profile directory intact (idempotent).
- `GET /profiles`, `GET /profiles?vendor_type=X&vendor_connection_id=Y`, `PATCH /profiles/{id}`, `DELETE /profiles/{id}` cover the profile-management surface.
- All machine routes (`/sessions/*`, `/profiles/*`) are guarded by an `X-API-Key` header check against `MAIN_APP_API_KEY`. Existing `AuthMiddleware` continues to guard `/admin/*` and the dashboard — strictly segregated.
- Warm-pool state machine works: `STOPPED → RUNNING → IDLE → STOPPED` driven by attach counts; Chromium launches are guarded by `asyncio.Semaphore(3)`; per-key `asyncio.Lock` serialises concurrent upserts; `SingletonLock`/`SingletonCookie`/`SingletonSocket` are removed before every launch; an `about:blank` probe fires after every launch to catch silent wake failure.

Out of scope for this phase: signed viewer URLs (Phase 3), `/viewer/*` WS route (Phase 3), JTI registry (Phase 3), `frame-ancestors` CSP on viewer responses (Phase 3), admin dashboard pivot (Phase 4), removal of legacy `/api/profiles/{id}/launch` (Phase 4), `POST /sessions/{id}/keepalive` heartbeat (deferred to v1.x), `is_active` on templates (v2).

</domain>

<decisions>
## Implementation Decisions

### SessionManager — Implementation Shape

- **D-01:** **Lifespan singleton.** `SessionManager` is constructed inside FastAPI's `lifespan` context next to the existing `BrowserManager` and stored on `app.state.session_manager`. Routes resolve it via a `Depends(get_session_manager)` factory that reads `request.app.state`. No module-level globals; no per-request instantiation (would lose `_idle_tasks`).
- **D-02:** **Per-key `asyncio.Lock` for upsert serialization.** `SessionManager` holds `_key_locks: dict[tuple[str, str], asyncio.Lock]` keyed by `(vendor_type, vendor_connection_id)`. A class-level `_locks_mutex: asyncio.Lock` guards the `setdefault` of new key locks (prevents the dict-mutation race). The DB-level `UNIQUE(vendor_type, vendor_connection_id)` constraint (added in Phase 1, D-05) is the belt-and-suspenders fallback for the multi-worker / cross-process case (research GAP §`asyncio.Lock` under multi-worker).
- **D-03:** **No `LAUNCH_IN_PROGRESS` state.** The per-key `asyncio.Lock` (D-02) plus a `browser_mgr.running.get(profile_id)` check inside the locked region is sufficient to serialize wakes. The research note flagged `LAUNCH_IN_PROGRESS` as one option; per-key locks give the same guarantee with less surface area. The `WarmPoolState` enum stays at `STOPPED | RUNNING | IDLE`.
- **D-04:** **Count mutations only in WS proxy `try/finally` blocks.** The CDP WS proxy (`/api/profiles/{id}/cdp` in `main.py`) and — in Phase 3 — the viewer WS proxy are the only mutation seams. They mutate `RunningProfile.cdp_attach_count` / `viewer_attach_count` under `browser_mgr._lock` and call `SessionManager.on_attach()` / `on_all_detached()` to drive the idle timer. `SessionManager` does not own a separate "attach" surface.

### Idle Detection & Activity Tracking

- **D-05:** **Pure connection-count-based idle.** `IDLE` is entered when `cdp_attach_count == 0 AND viewer_attach_count == 0`; the WebSocket stays open during automation pauses, so paused-but-connected sessions never trigger idle. No `last_activity_at` per-frame timestamp (Pitfall 3's mitigation was about avoiding naive boolean checks, not about timestamps; counting handles it).
- **D-06:** **`IDLE_TIMEOUT_SECONDS` default = 600.** Locked at the env-var layer in Phase 1. Survives multi-step 2FA flows.
- **D-07:** **No `POST /sessions/{id}/keepalive` in v1.** Research labelled it v1.x (SAFE-01). Connection-count idle does not produce false-sleeps in the current design; revisit only if the Main App reports them.
- **D-08:** **Idle task action.** When the idle `asyncio.Task` fires:
  1. Acquire `browser_mgr._lock`.
  2. Re-check `cdp_attach_count == 0 AND viewer_attach_count == 0` (concurrent attach during the sleep cancels the sleep — but defence-in-depth re-check).
  3. Call `await BrowserManager.stop(profile_id)`.
  4. Remove `RunningProfile` from `browser_mgr.running` (so state == STOPPED).
  5. Pop self from `SessionManager._idle_tasks`.
  6. Log: `warm_pool sleep profile_id=… idle_seconds=…`.
- **D-09:** **Idle timer is cancelled on every attach event.** `SessionManager.on_attach(profile_id)` finds and cancels any pending `asyncio.Task` in `_idle_tasks`. `on_all_detached(profile_id)` schedules a fresh one. Only one timer per profile is ever live.

### Routing & Auth Surface

- **D-10:** **Two new router files.** `backend/routers/sessions.py` owns `POST /sessions`, `GET /sessions`, `GET /sessions/{profile_id}`, `DELETE /sessions/{profile_id}`. `backend/routers/profiles.py` owns `GET /profiles`, `GET /profiles?vendor_type=X&vendor_connection_id=Y`, `PATCH /profiles/{id}`, `DELETE /profiles/{id}`. Mirrors the Phase 1 `routers/templates.py` shape. CLAUDE.md mandates new routes go in `backend/routers/`, not `main.py` (1,027 lines).
- **D-11:** **API-key auth via `APIKeyHeader` + router-wide `Depends`.** New module `backend/auth_api_key.py` exports `require_api_key` (a `Depends`-compatible coroutine that reads the `X-API-Key` header, compares with `MAIN_APP_API_KEY` via `hmac.compare_digest`, raises `HTTPException(401, "Invalid or missing API key", headers={"WWW-Authenticate": "ApiKey"})` on mismatch). Both new routers are mounted with `dependencies=[Depends(require_api_key)]`. Docker production mode requires `MAIN_APP_API_KEY` to be set (Phase 1 D-17 fail-closed); `DEV_MODE=1` opts out.
- **D-12:** **`AuthMiddleware` exemption list expands** to include `/sessions` and `/profiles` (machine API). The `_AUTH_EXEMPT` frozenset in `main.py` adds `/sessions` and `/profiles` prefixes alongside the existing exemptions. Strictly segregated: machine API never receives admin cookies; admin routes never receive `X-API-Key` checks.
- **D-13:** **`cdp_url` returned from `POST /sessions` is the existing `/api/profiles/{profile_id}/cdp` WS path** (relative URL). The proxy already exists; Phase 2 only adds `cdp_attach_count` increment/decrement to its `try/finally`. The CDP WS proxy stays under `/api/*` for now — Phase 4 cleans up the legacy `/api/profiles/{id}/launch` REST endpoint, but the CDP WS itself stays as-is.
- **D-14:** **`GET /sessions` (active list) lives on the machine sessions router.** Returns `[{profile_id, vendor_type, vendor_connection_id, state, cdp_attach_count, viewer_attach_count, idle_expires_at, last_launched_at, ...}]` for every profile currently in `browser_mgr.running`. Single auth surface (`X-API-Key`). The Phase 4 admin dashboard reaches it via the existing admin proxy or a thin admin shim — Phase 2 does not add a parallel `admin_router` for sessions.

### Lifecycle, Errors & Tests

- **D-15:** **`upsert_profile_by_vendor()` is `SELECT → INSERT OR ABORT → SELECT` inside a single transaction.** Pseudocode:
  ```python
  with conn:  # BEGIN..COMMIT
      row = SELECT * FROM profiles WHERE vendor_type=? AND vendor_connection_id=?
      if row: return row
      template = SELECT * FROM vendor_templates WHERE vendor_type=?
      if not template: raise NoTemplateError(vendor_type)
      try:
          INSERT INTO profiles (... fields snapshot from template ...)
      except sqlite3.IntegrityError:  # multi-worker race
          pass  # the other worker won; fall through
      row = SELECT * FROM profiles WHERE vendor_type=? AND vendor_connection_id=?
  return row
  ```
  Per-key `asyncio.Lock` (D-02) serializes within a process; `INSERT OR ABORT` + `UNIQUE` constraint catches the cross-process case. Returned dict is the freshly-snapshotted profile.
- **D-16:** **`POST /sessions` error semantics.**
  - 200 — happy path; `state` reflects whether the profile was already RUNNING, just woken, or freshly created.
  - 400 — `vendor_type` or `vendor_connection_id` is empty/whitespace (Pydantic `min_length=1`).
  - 404 — no `vendor_template` exists for the given `vendor_type` (`NoTemplateError`); body: `{detail: "No template for vendor_type=…", vendor_type: "…"}`.
  - 401 — missing/invalid `X-API-Key`; body: `{detail: "Invalid or missing API key"}`.
  - 503 — `BrowserManager.launch()` raised (Semaphore wait timed out, `about:blank` probe failed, Chromium binary missing); body: `{detail: "Browser launch failed", reason: "<short>"}`.
- **D-17:** **`DELETE /sessions/{profile_id}` semantics.** Idempotent. Always returns 204:
  1. If `profile_id` is unknown → 404 (separate concern from "not currently running").
  2. If `profile_id` is in `browser_mgr.running` → call `BrowserManager.stop()`, cancel any idle timer, remove from `running` dict.
  3. If not running → no-op, still 204.
  Profile row stays. On-disk profile directory stays. `DELETE /profiles/{id}` is the destructive endpoint (stops + drops row + removes dir).
- **D-18:** **`GET /sessions/{profile_id}` returns** `{state, cdp_attach_count, viewer_attach_count, idle_expires_at, last_launched_at}`. `state` is one of `"running" | "idle" | "stopped"` (lower-case enum; Pydantic `Literal`). `idle_expires_at` is ISO-8601 in UTC when state is `idle`, else `null`. `last_launched_at` is ISO-8601 of the most recent successful launch, else `null` for never-launched.
- **D-19:** **Three-layer test strategy.**
  - **Unit (`tests/test_session_manager.py`)** — `SessionManager.on_attach`/`on_all_detached`/idle-timer cancellation/`_key_locks` lifecycle with a mock `BrowserManager`. Fast, deterministic.
  - **Integration with real SQLite (`tests/test_sessions_router.py`)** — uses FastAPI `TestClient`, a temp SQLite DB, and a mock `BrowserManager` (no real Chromium). Covers: idempotent upsert, 401 on bad API key, 404 on no-template, 404 on unknown `profile_id`, 204 idempotent `DELETE`, race test (`asyncio.gather(10x POST /sessions)` for the same `(vendor_type, vendor_connection_id)` → all return same `profile_id`, only one INSERT happened).
  - **Slow E2E (`tests/test_warm_pool_e2e.py`, `pytest.mark.slow`)** — real Chromium via `BrowserManager`. One happy-path: `POST /sessions` → assert state=running → close CDP WS → with `IDLE_TIMEOUT_SECONDS=2` env override, `await asyncio.sleep(3)` → assert state=stopped → `POST /sessions` again → assert wake succeeded + cookies dir from before still on disk.
- **D-20:** **`GET /profiles` filtering** — query params `vendor_type` (optional) and `vendor_connection_id` (optional). Both present → return at most one row. `vendor_type` only → list filtered by vendor. Neither → return all (admin debug). Always 200 with a (possibly empty) list. The `(vendor_type, vendor_connection_id)`-specific 404 lives on `GET /sessions/{id}` and `GET /profiles/{id}` only — list endpoints return empty lists, not 404.

### Pre-Phase Lookups (must verify before coding starts)

- **L-01:** Confirm KasmVNC websockify binds to `127.0.0.1` not `0.0.0.0` in `VNCManager` (STATE.md "Phase 2 start" carry-over).
- **L-02:** Confirm `Dockerfile` CloakBrowser version is pinned (not floating tag) before warm-pool sleep/wake testing (STATE.md "Phase 2 start" carry-over). Pitfall 7 (fingerprint inconsistency on sleep/wake).
- **L-03:** Verify the existing CDP proxy at `/api/profiles/{id}/cdp` survives the `AuthMiddleware` exemption change (it currently flows through admin auth; once `/sessions`/`/profiles` are exempt, the CDP WS path still needs to authenticate via `X-API-Key`). Decide: add `X-API-Key` validation to the CDP WS handler in `main.py` (preferred) OR move the CDP WS into the new sessions router (more invasive).

### Claude's Discretion

- Pydantic models for `SessionRequest` / `SessionResponse` / `SessionStatusResponse` / `ProfilePatch` / `ProfileResponse` mirror existing `models.py` conventions (`field_validator` for defaults, `Literal` for state enum, `model_config = ConfigDict(extra="forbid")` to reject unknown fields).
- `SessionManager` log lines use the existing `logging.getLogger("backend.session_manager")` pattern; structured KV style: `event=upsert vendor_type=… vendor_connection_id=… profile_id=… ms=…`.
- `last_launched_at` lives on `RunningProfile` (set on successful launch); idle/stopped state pulls it from the most recent value seen in memory or a small in-process LRU. No new DB column unless tests prove we need persistence across restarts (we don't — restart resets to STOPPED + zero counts per design).
- `idle_expires_at` is computed on read as `idle_started_at + IDLE_TIMEOUT_SECONDS`; `idle_started_at` is set when the idle task is scheduled.
- Phase 2 test fixtures reuse the Phase 1 conftest (env-var requirement enforcement); add a `mock_browser_manager` fixture that stubs `launch`/`stop`/`running` for the integration tests.
- `GET /sessions` (list) returns the list in deterministic order (sort by `last_launched_at` desc) — easier debugging.
- The `503` reason string from `BrowserManager.launch()` failures is sanitised (no stack traces in HTTP body); full traceback goes to logs.
- Per-key `asyncio.Lock` cleanup: when a profile is `DELETE /profiles/{id}`'d, the corresponding lock is removed from `_key_locks` to prevent unbounded growth. Otherwise locks live for process lifetime — fine at ≤20 concurrent profiles.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope & requirements

- `.planning/PROJECT.md` — Milestone scope, constraints, Key Decisions table.
- `.planning/REQUIREMENTS.md` — Phase 2 requirement set: SESS-01..14, PROF-01..04, SEC-01.
- `.planning/ROADMAP.md` §"Phase 2: Sessions, Warm-Pool, and CDP Lifecycle" — Goal, success criteria, parallelization notes.
- `.planning/STATE.md` — Locked decisions and Phase 2 pre-start lookups.

### Research (prescriptive)

- `.planning/research/SUMMARY.md` §"Phase 2" + §"Critical Pitfalls" — build order, dual-signal idle design, top 5 pitfalls.
- `.planning/research/ARCHITECTURE.md` §"Component Boundaries", §"Data Flow", §"Warm-Pool State Machine", §"Architectural Patterns" — `SessionManager` shape, attach-counting design, anti-patterns.
- `.planning/research/PITFALLS.md` — Pitfall 2 (concurrent upsert race), Pitfall 3 (idle false-positive), Pitfall 4 (thundering herd on restart), Pitfall 1 (SingletonLock cleanup), Pitfall 13 (silent wake failure / `about:blank` probe), Pitfall 12 (zombie Xvnc).
- `.planning/research/STACK.md` — `APIKeyHeader` + `Depends` pattern, `asyncio.Task` idle timer rationale, FastAPI single-worker assumption.

### Codebase (existing patterns)

- `.planning/codebase/ARCHITECTURE.md` — `backend/main.py` middleware stack, `_AUTH_EXEMPT` exemption list pattern, existing `/api/profiles/{id}/cdp` WS proxy.
- `.planning/codebase/STRUCTURE.md` — directory layout, "Where to add new code" recipes.
- `.planning/codebase/CONVENTIONS.md` — Python/TypeScript style, FastAPI route patterns, logging conventions.
- `backend/browser_manager.py::RunningProfile` — dataclass to extend (`cdp_attach_count`, `viewer_attach_count` are additive integer fields, default 0).
- `backend/browser_manager.py::BrowserManager.launch()` / `stop()` / `_lock` — used unchanged by `SessionManager`. Add `asyncio.Semaphore(3)` guard inside `launch()`.
- `backend/database.py::init_db()` / `create_profile()` — extend with `upsert_profile_by_vendor()`; reuse the existing `ALTER TABLE` migration shape if any column tweaks are needed (mostly already in place from Phase 1).
- `backend/main.py` — CDP WS proxy `try/finally` is the seam for `cdp_attach_count` mutations; `_AUTH_EXEMPT` frozenset is the seam for path-prefix exemptions.
- `backend/routers/templates.py` (Phase 1) — shape to mirror for `routers/sessions.py` and `routers/profiles.py`.
- `backend/models.py` — Pydantic v2 patterns; mirror existing `VendorTemplate*` models.
- `entrypoint.sh` — pre-launch SingletonLock cleanup already present (Phase 1 chown step lives next to it). `about:blank` probe is a `BrowserManager.launch()` change, not entrypoint.

### Top-level config

- `Dockerfile` — confirm CloakBrowser binary is pinned (L-02).
- `docker-compose.yml` — `MAIN_APP_API_KEY`, `IDLE_TIMEOUT_SECONDS` declarations land here (Phase 1 already added them; verify).
- `CLAUDE.md` — security rules, architecture invariants, brownfield reality; re-read before edits.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`backend/browser_manager.py::RunningProfile` (line 149)** — dataclass to extend. Add `cdp_attach_count: int = 0` and `viewer_attach_count: int = 0` additively; existing fields untouched.
- **`backend/browser_manager.py::BrowserManager._lock` (line 162)** — `asyncio.Lock()` already present; reused to guard count mutations and idle-task fire-time stop.
- **`backend/browser_manager.py::BrowserManager.launch()` (line 164)** — wrap inner launch body with `asyncio.Semaphore(3)` (allocated in `__init__`); add `SingletonLock` / `SingletonCookie` / `SingletonSocket` removal at the top; add `about:blank` probe at the end (open a CDP page, navigate, assert success, close).
- **`backend/main.py` `_AUTH_EXEMPT` frozenset** — add `/sessions` and `/profiles` path prefixes to skip the existing `AuthMiddleware`.
- **`backend/main.py` CDP WS proxy** — locate existing `/api/profiles/{id}/cdp` WS handler. Wrap its body in `try/finally`: `try: increment cdp_attach_count + on_attach; ... finally: decrement + (if zero) on_all_detached`. Add `X-API-Key` validation at the top of the handler (the WS upgrade path skips ASGI middleware in this codebase's pattern).
- **`backend/database.py::create_profile()`** — already extended in Phase 1 to accept `vendor_type`, `vendor_connection_id`, `template_id`, and `create_profile_from_template()` helper exists. `upsert_profile_by_vendor()` builds on top.
- **`backend/routers/templates.py`** — shape, file-naming, mounting pattern, Pydantic body parsing, `Depends`-based auth — copy idiom for `routers/sessions.py` and `routers/profiles.py`.
- **`backend/models.py`** — `field_validator`, `model_config = ConfigDict(extra="forbid")`, `Literal` enums, `Annotated[str, StringConstraints(min_length=1)]` patterns — reuse for `SessionRequest` / `SessionResponse` / `SessionStatusResponse` / `ProfilePatch`.
- **`backend/main.py` `lifespan` context manager** — construct `SessionManager` here next to `BrowserManager` and attach to `app.state.session_manager`. Cancel any in-flight `_idle_tasks` on shutdown (loop over the dict and `task.cancel()`).
- **`backend/tests/conftest.py`** — already enforces `MAIN_APP_API_KEY` / `VIEWER_SECRET` env requirements; Phase 2 tests inherit. Add `mock_browser_manager` fixture for the integration layer.

### Established Patterns

- **Routers in `backend/routers/`** — Phase 1 set the precedent with `templates.py`. Each new router gets one file.
- **Pydantic v2** — `field_validator` for defaults; `Literal` for state enums; `ConfigDict(extra="forbid")` to reject unknown body keys.
- **Raw `sqlite3` (no async DB layer)** — `with conn:` block for transactions. Phase 2 stays on this pattern.
- **`AuthMiddleware` exemption list** — single frozenset in `main.py`; add the new prefixes there.
- **`Depends`-based auth** — Phase 1's templates router uses admin auth via the existing pattern; Phase 2's machine routers use `Depends(require_api_key)` from a new `auth_api_key.py` module.
- **Logging** — `logging.getLogger(__name__)` per module; structured KV strings (`event=… profile_id=… ms=…`).
- **WebSocket auth** — middleware does not see WS upgrades reliably in this codebase; auth is enforced inside the WS handler before `accept()` (matches existing CSWSH origin check pattern).

### Integration Points

- `backend/main.py::lifespan` — single seam to instantiate `SessionManager` and attach to `app.state`.
- `backend/main.py` middleware stack — only the `_AUTH_EXEMPT` frozenset changes.
- `backend/main.py` CDP WS proxy handler — adds `X-API-Key` validation, count mutations, `on_attach` / `on_all_detached` calls.
- `backend/main.py` route includes — register `sessions_router` under `/sessions`, `profiles_router` under `/profiles`. Phase 1's `templates_router` mounting is the template.
- `backend/database.py` — `upsert_profile_by_vendor()` lives next to existing `create_profile_from_template()`.
- `backend/browser_manager.py` — `launch()` body wrapping (semaphore, singleton cleanup, probe); `RunningProfile` dataclass extension; `stop()` left as-is (just called from `SessionManager`'s idle task).
- `backend/auth_api_key.py` — new file. Single async function `require_api_key(x_api_key: str = Header(...))` raising `HTTPException(401)`.
- `backend/session_manager.py` — new file. `SessionManager` class as specified above.

### Anti-patterns (do NOT do these — research §"Anti-Patterns to Avoid")

- Don't have `SessionManager` call `VNCManager.allocate()` directly. It calls only `BrowserManager.launch/stop`.
- Don't use Playwright `context.on("close")` or CDP `/json/list` polling for connection state. Count WS connections at the proxy.
- Don't read live template fields at wake time. Profile row is the snapshot (Phase 1 D-03).
- Don't put idle timers in a module-global dict or DB table. They live in `SessionManager._idle_tasks`.
- Don't merge machine API and admin API into one router. Two routers, two auth surfaces.

</code_context>

<specifics>
## Specific Ideas

- **Race-test concretely.** The integration test `asyncio.gather(*[client.post('/sessions', ...) for _ in range(10)])` for the same `(vendor_type, vendor_connection_id)` must assert: all 10 responses have the same `profile_id`; the DB has exactly one row with that pair; `BrowserManager.launch` was called exactly once. This is the explicit Pitfall-2 regression guard.
- **Silent-wake test concretely.** The `about:blank` probe must fire after every `launch()`. Add a unit test that monkey-patches the Playwright context to return a "successful" launch but a stale page; the probe must raise and surface as 503.
- **Idle log line is a debugging gold mine.** When the timer fires, log: `event=warm_pool_sleep profile_id=… vendor_type=… vendor_connection_id=… idle_seconds=… launched_at=… reason=idle_timeout`. Operators must be able to grep this when a session disappears unexpectedly.
- **`GET /sessions/{id}` field shapes** are the exact wire contract the Main App polls; do not add or rename fields in this phase. The `state` enum is `"running" | "idle" | "stopped"` lowercase.
- **Idempotent DELETE is not optional.** `DELETE /sessions/{id}` returning 204 even when not running is what lets the Main App use it as a force-stop without first checking state.
- **The 503 path is real.** When 20 simultaneous wakes happen post-restart, `Semaphore(3)` makes some calls wait; if their wait exceeds the route's effective timeout, they need a clean 503 (not a hung connection or a 500). Add an explicit wait-timeout (e.g., 30s) on the semaphore acquire.
- **The CDP WS proxy authentication is the `_AUTH_EXEMPT` gotcha.** Once `/sessions`/`/profiles` are exempt, the existing `/api/profiles/{id}/cdp` WS path must still authenticate. Add `X-API-Key` validation at the top of the WS handler (before `accept()`); reject with `close(4401)` on missing/invalid key.

</specifics>

<deferred>
## Deferred Ideas

- **`POST /sessions/{id}/keepalive` heartbeat (SAFE-01)** — v1.x.
- **Read-only viewer mode (SAFE-02)** — v1.x.
- **Per-template `idle_timeout_minutes` override (SAFE-03)** — v1.x; Phase 2 uses the global `IDLE_TIMEOUT_SECONDS` env var.
- **Template `is_active` soft-disable (GOV-01)** — v2.
- **CDP WS path move to `/sessions/{id}/cdp`** — Phase 4 cleanup territory; if it happens at all, it's after the legacy `/api/profiles/{id}/launch` REST endpoint is removed.
- **Persistent `last_launched_at` across restarts** — keep in-memory only for now; add a DB column only if the Main App needs cross-restart visibility (it doesn't today).
- **`POST /sessions` returning a non-empty `vnc_viewer_url`** — Phase 3 wires the signed URL. Phase 2 returns an empty string or `null` for the field.
- **Multi-worker uvicorn deployment** — single worker only in v1; per-key `asyncio.Lock` correctness depends on it. Documented as a constraint in `session_manager.py` module docstring.
- **Webhooks / push events to Main App on warm-pool sleep** — out of scope (PROJECT.md). Main App polls `GET /sessions/{id}`.

</deferred>

---

*Phase: 02-sessions-warm-pool-and-cdp-lifecycle*
*Context gathered: 2026-05-08*
