# Project Research Summary

**Project:** CloakBrowser-Manager — warm-pool / templates / signed-viewer milestone
**Domain:** Single-consumer headless browser profile service (brownfield infrastructure pivot)
**Researched:** 2026-04-22
**Confidence:** HIGH

---

## Executive Summary

This milestone pivots an existing FastAPI + React + Playwright + CloakBrowser + KasmVNC admin dashboard into a private infrastructure service consumed by one trusted downstream app (the "Main App"). The entire value proposition collapses to a single call: `POST /sessions` with `(vendor_type, vendor_connection_id)` returns `{profile_id, cdp_url, vnc_viewer_url}`. Everything else — vendor templates, warm-pool lifecycle, signed viewer URLs, API-key auth — exists to make that call reliable, idempotent, and secure. Because this is brownfield, the Chromium lifecycle (CloakBrowser + Playwright), VNC pipeline (KasmVNC + noVNC + RFB filtering), SQLite persistence, and Docker deployment are all locked; only one new Python dependency is introduced (`PyJWT >= 2.12.1` for viewer token signing).

The recommended build order follows hard dependencies in the data model: schema and templates must exist before sessions can upsert profiles; sessions and warm-pool must be solid before the signed viewer route is wired up; viewer security (CSP, token delivery via fragment, JTI registry) is finished before the admin UI pivot. The warm-pool's **dual-signal idle design** — idle fires only when BOTH CDP clients AND viewer WebSockets reach zero — has no commercial analog and is the single riskiest piece of the milestone. It must be implemented with explicit asyncio locking, a per-profile task dict owned by `SessionManager`, and a startup-safe posture (no auto-wake on restart). Everything else is either well-trodden FastAPI patterns or straightforward extensions of existing code.

The three cross-cutting security rules that must be non-negotiable: (1) viewer tokens travel in the URL fragment, never the querystring, to avoid proxy/log leakage; (2) `clipboard_sync` defaults to `false` on all vendor templates and clipboard-read is scoped to the viewer auth path (signed viewer token only), not the Main App's API key; (3) the two auth surfaces (`APIKeyHeader` / `Depends` for machine routes, existing `AuthMiddleware` for admin routes) are strictly segregated by router prefix with no overlap.

---

## Key Findings

### Recommended Stack

The existing stack is locked and needs no changes beyond one new library. `PyJWT >= 2.12.1` (released 2026-03-13, actively maintained) handles viewer token minting and verification via HS256 with `exp` + `jti` claims. Warm-pool idle tracking is pure `asyncio.Task` with cancel/reschedule — no state-machine library needed at this scale. Vendor templates go in a new `vendor_templates` SQLite table with a `TEXT NOT NULL` JSON blueprint column (Pydantic handles serialization); normalizing blueprint fields into 15 columns gains nothing. API-key auth uses FastAPI's built-in `APIKeyHeader` + `Depends` pattern on a dedicated router — no second ASGI middleware, no fragile path matching.

**Core technologies (additions only — existing stack unchanged):**
- `PyJWT >= 2.12.1`: Sign and verify viewer URL tokens — only safe option; `python-jose` is abandoned with CVEs; raw `hmac` requires hand-rolling TTL/replay logic
- `asyncio.Task` (stdlib): Warm-pool idle timer per profile — 20 lines, cancel/reschedule on attach/detach events; `transitions` or `aiomachines` would add dependency with no gain at <20 profiles
- `APIKeyHeader` + `Depends` (fastapi, already present): Machine API auth — scoped to router, zero new code, OpenAPI-documented automatically
- SQLite `TEXT NOT NULL` JSON column (existing sqlite3): Vendor template blueprint storage — self-contained, transactional with profiles table, admin-editable at runtime
- Two new env vars required: `VIEWER_SECRET` (signs viewer JWTs) and `MAIN_APP_API_KEY` (authenticates machine requests); `IDLE_TIMEOUT_SECONDS` configures warm-pool sleep delay (default 600)

### Expected Features

All research dimensions agree: every feature below is required for the Main App to use the service at all. Nothing in the table-stakes list is optional for v1.

**Must have (table stakes — Main App cannot function without these):**
- `POST /sessions` idempotent upsert by `(vendor_type, vendor_connection_id)` — the entire value proposition
- CDP URL in session response — Main App's automation entry point
- Profile-scoped signed viewer URL with TTL enforcement — secure iframe embedding for human 2FA
- Warm-pool sleep/wake with dual-signal idle detection (CDP + viewer WS) — preserves login state between automation runs
- Session state persistence across sleep/wake (profile directory survives; only process and VNC torn down)
- Vendor Template CRUD — no profile can be created without a template for its `vendor_type`
- Template-to-profile snapshot inheritance at upsert time — template fields frozen into profile row; template changes never retroactively affect running profiles
- API-key auth for Main App (distinct from admin cookie)
- `GET /sessions/{id}` status polling
- `GET /profiles?vendor_type=X&vendor_connection_id=Y` lookup by Main App's own IDs
- `PATCH` / `DELETE /profiles/{id}` lifecycle management
- Replace existing `/api/profiles/*` surface — clean API contract, no dual-API maintenance burden
- Admin dashboard: template CRUD screens + active session ops list

**Should have (v1.x — add after first integration cycle):**
- `POST /sessions/{id}/keepalive` heartbeat — prevents false-sleep during noVNC reconnect windows
- Read-only viewer mode (encode in token, suppress pointer events at WS layer)
- Per-template `idle_timeout_minutes` override — banking vendors need aggressive sleep, social vendors can idle longer
- Template `is_active` soft-disable
- Viewer URL navbar suppression flag

**Defer (v2+):**
- Proxy provider wiring (residential IPs) — proxy fields exist; wire when vendors actively block
- Session recording / video replay — substantial storage + pipeline; no current requester
- Second consumer / multi-tenancy — re-evaluate only when a second Main App actually exists

**Confirmed anti-features (never build):**
- Per-call fingerprint overrides from Main App — breaks template governance contract
- Multi-tenancy, billing, quotas, webhooks, OAuth for machine auth, template inheritance chains

**Unique differentiators vs. commercial analogs (Browserbase, Anchor, Steel, Hyperbrowser):**
1. Idempotent session by `(vendor_type, vendor_connection_id)` — no commercial service does this natively; all require the caller to manage ID mapping
2. Vendor template locking — enforces fingerprint/locale/timezone consistency across all profiles of the same vendor without Main App involvement
3. Implicit warm-pool lifecycle (no explicit release call) — signal-based idle detection vs. Browserbase's `REQUEST_RELEASE` or Anchor's explicit `idle_timeout` config

### Architecture Approach

The architecture is additive: a new `SessionManager` thin-orchestrator class coordinates between the unchanged `BrowserManager` (Chromium lifecycle), an extended `RunningProfile` dataclass (gains `cdp_attach_count`, `viewer_attach_count`), a new pure `viewer_tokens.py` module, and two new APIRouter instances (`sessions_router`, `admin_router`). The only changes to existing code are: (1) `RunningProfile` gets two integer fields (additive, default 0); (2) the VNC proxy route is refactored to extract a `_run_vnc_proxy()` helper so the new `/viewer/*` WS route can reuse it; (3) `database.py` gets the `vendor_templates` table and `upsert_profile_by_vendor()` function; (4) `AuthMiddleware`'s exemption list expands to include machine-API prefixes. `main.py` (currently 1,027 lines) is not rewritten — new routes go into `routers/`.

**Major components:**
1. `SessionManager` (`backend/session_manager.py`, new) — upserts profile by `(vendor_type, vendor_connection_id)`; calls `BrowserManager.launch/stop`; owns `_idle_tasks` dict of `asyncio.Task` objects; cancels/reschedules timers via `on_attach()` / `on_all_detached()` callbacks
2. `viewer_tokens.py` (`backend/viewer_tokens.py`, new) — pure module, no FastAPI/BrowserManager imports; `mint(profile_id, ttl)` returns JWT string; `validate(token, claimed_profile_id)` raises `ViewerTokenError` on failure
3. `sessions_router` + `admin_router` (`backend/routers/`, new) — machine API (`/sessions/*`, `/profiles/*`) protected by `APIKeyHeader`; admin API (`/admin/*`) protected by existing `AuthMiddleware`
4. `RunningProfile` extension — `cdp_attach_count` and `viewer_attach_count` fields; mutations guarded by `browser_mgr._lock`; counts drive `SessionManager.on_attach/on_all_detached` callbacks
5. `vendor_templates` table + `upsert_profile_by_vendor()` — `INSERT OR IGNORE` + `SELECT` in a single transaction; `UNIQUE(vendor_type, vendor_connection_id)` constraint as hard DB guarantee
6. `/viewer/{profile_id}/ws` WS route — validates token (fragment-delivered, not querystring) before WebSocket accept; proxies to KasmVNC; increments/decrements `viewer_attach_count`; CSWSH origin check reused
7. React admin pivot — `TemplateList.tsx`, `TemplateForm.tsx`, `SessionList.tsx`; existing `ProfileViewer.tsx` survives for admin VNC access

**Warm-pool state machine (4 states):**
- `STOPPED` — no process, no `RunningProfile`
- `RUNNING` — at least one attach count > 0; idle timer cancelled
- `IDLE` — both counts == 0; `asyncio.Task` ticking toward `IDLE_TIMEOUT_SECONDS`
- back to `STOPPED` when idle timer fires (`BrowserManager.stop()` called)

On restart, all profiles enter `STOPPED`; wake happens lazily on the next `POST /sessions` call. No auto-wake on startup.

### Critical Pitfalls

Full detail in `.planning/research/PITFALLS.md`. The 5 highest-priority items by risk x frequency:

1. **Dual-signal idle false-positive kills live sessions (Pitfall 3)** — Automation pauses between CDP commands look like "zero connected clients" to a naive boolean-connected check. Prevention: use a `last_activity_at` timestamp reset on every WS frame/connect event, not just on disconnect. Set `IDLE_TIMEOUT_SECONDS` default to 600+ to survive 2FA page loads. Add `POST /sessions/{id}/keepalive` as a v1.x safety valve.

2. **Concurrent `POST /sessions` race creates duplicate profiles (Pitfall 2)** — Two simultaneous requests for the same `(vendor_type, vendor_connection_id)` pass the existence check before either commits. Prevention: `UNIQUE(vendor_type, vendor_connection_id)` DB constraint + `INSERT OR IGNORE` / `SELECT` in one transaction + per-key `asyncio.Lock` in `SessionManager` to serialize concurrent requests for the same pair.

3. **Viewer token in querystring logged by every proxy (Pitfall 5)** — An `<iframe src="/viewer?token=eyJ...">` token appears in nginx, CDN, and application logs. Prevention: deliver token via URL fragment (`#token=...`); noVNC JS reads `window.location.hash` and presents it in the WS upgrade request. Fragment never reaches the server log.

4. **Thundering-herd wake on service restart (Pitfall 4)** — Post-restart, 20 simultaneous `POST /sessions` calls launch 20 Chrome + 20 KasmVNC processes concurrently; 6-16 GB memory spike causes OOM. Prevention: `asyncio.Semaphore(3)` on `BrowserManager.launch()`; no auto-wake on startup; `LAUNCH_IN_PROGRESS` as a third profile state so concurrent wake attempts serialize.

5. **Clipboard sync leaks OTP codes to Main App API key (Pitfall 11)** — Existing `clipboard_sync` default may be `true`; the Main App's API key can poll `/api/profiles/{id}/clipboard` and read OTPs or session tokens copied inside the vendor portal. Prevention: flip `clipboard_sync` default to `false` everywhere; scope clipboard-read access to the viewer auth path (signed viewer token only), not the machine API key.

**Additional pitfalls that must be addressed per phase (see Pitfall-to-Phase mapping in PITFALLS.md):**
- SingletonLock files from SIGKILL: clean up before every warm-pool wake (Phase 2)
- Silent wake failure (Playwright returns success but Chrome is stale): probe `about:blank` immediately after `launchPersistentContext` (Phase 2)
- Token replay: server-side JTI registry, mark token consumed on first WS upgrade (Phase 3)
- Admin CSRF via viewer iframe: `SameSite=Strict` on admin cookie, `frame-ancestors <Main App origin>` on viewer responses (Phase 3)
- Docker UID mismatch: `chown -R ${CHROME_UID}` in entrypoint before service start (Phase 1)
- Zombie Xvnc processes on partial launch failure: process-group kill, persist display allocations in SQLite (Phase 2)

---

## Implications for Roadmap

All four research dimensions converge on the same build order driven by hard data-model and functional dependencies. This is not a preference — templates must exist before sessions can create profiles; sessions must be solid before viewer URL security matters; viewer security must be complete before the admin UI pivot is the right focus.

### Phase 1: Schema, Templates, and Security Foundations

**Rationale:** Nothing else can be built without the data schema. Vendor template CRUD unblocks every subsequent phase. Security foundations (clipboard default flip, Docker UID fix, env vars) are cheapest to get right here and most expensive to retrofit later.

**Delivers:**
- `vendor_templates` table + migration; `UNIQUE(vendor_type, vendor_connection_id)` + `vendor_type` / `vendor_connection_id` / `template_id` columns on `profiles`
- `VendorTemplate` Pydantic model + CRUD API (`admin_router`)
- Admin UI: `TemplateList.tsx` + `TemplateForm.tsx`
- `clipboard_sync` default flipped to `false` in DB schema and all seed/default paths
- Docker entrypoint `chown` fix for volume UID mismatch
- `VIEWER_SECRET` and `MAIN_APP_API_KEY` env vars scaffolded in `docker-compose.yml` and `.env.example`

**Addresses from FEATURES.md:** Vendor Template CRUD, Template to Profile inheritance design, Admin UI template screens

**Avoids from PITFALLS.md:** Clipboard credential leak (Pitfall 11), Docker UID mismatch (Pitfall 10), fingerprint inconsistency from live template reads (Pitfall 7 — snapshot strategy decided here)

**Research flag:** Standard patterns — no additional research needed. Schema migrations follow existing `ALTER TABLE` pattern in `init_db()`.

---

### Phase 2: Sessions, Warm-Pool, and CDP Lifecycle

**Rationale:** The core value proposition. Depends on Phase 1 (templates must exist to upsert profiles). The dual-signal idle design is the novel and riskiest piece; it must be built and hardened before any downstream surface depends on it.

**Delivers:**
- `viewer_tokens.py` pure module (can be built in parallel with Phase 1, unblocks Phase 3)
- `SessionManager` with `get_or_wake_session()`, `on_attach()`, `on_all_detached()`, `_idle_tasks` dict
- `RunningProfile` extended with `cdp_attach_count`, `viewer_attach_count`
- Per-key `asyncio.Lock` in `SessionManager` to serialize concurrent `POST /sessions` for the same profile pair
- `asyncio.Semaphore(3)` on `BrowserManager.launch()` for thundering-herd prevention
- `LAUNCH_IN_PROGRESS` state to prevent double-launch on concurrent wakes
- SingletonLock cleanup before every `launchPersistentContext` call
- `about:blank` probe after every launch to catch silent wake failures
- `sessions_router`: `POST /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}`
- `APIKeyHeader` + `Depends` guard on sessions router
- CDP proxy route gains `cdp_attach_count` increment/decrement in `try/finally`
- `GET /sessions` active list endpoint (admin + API)
- `IDLE_TIMEOUT_SECONDS` env var wired to warm-pool

**Addresses from FEATURES.md:** `POST /sessions` idempotent upsert, warm-pool sleep/wake, dual-signal idle detection, session state persistence, session status polling, profile CRUD by `(vendor_type, vendor_connection_id)`, API-key auth

**Avoids from PITFALLS.md:** Concurrent duplicate profiles (Pitfall 2), idle false-positives (Pitfall 3), thundering herd on restart (Pitfall 4), SingletonLock corruption (Pitfall 1), silent wake failure (Pitfall 13), zombie Xvnc processes (Pitfall 12)

**Research flag:** Needs careful implementation review for the dual-signal idle design — no commercial analog, no reference implementation. The asyncio.Lock + per-key serialization pattern should be validated against FastAPI's async request model (concurrent requests share one event loop, not threads).

---

### Phase 3: Signed Viewer URLs and Security Hardening

**Rationale:** Depends on Phase 2 (`viewer_attach_count` must exist before the viewer WS route can drive it). The security properties here (token-in-fragment, JTI registry, CSP, admin CSRF) are non-negotiable before the Main App embeds the viewer in production.

**Delivers:**
- `/viewer/{profile_id}/ws` WS route with token validation (fragment-delivered JWT, not querystring)
- `viewer_tokens.mint()` wired into `POST /sessions` response
- Server-side JTI registry (in-memory dict with TTL eviction, or `used_tokens` SQLite table); token marked consumed on first WS upgrade
- Viewer WS `viewer_attach_count` increment/decrement + `SessionManager.on_attach/on_all_detached` callbacks
- `Content-Security-Policy: frame-ancestors <MAIN_APP_ORIGIN>` on all viewer endpoint responses
- `SameSite=Strict` on admin `auth_token` cookie
- `frame-ancestors 'none'` on all `/admin/*` API responses
- Clipboard-read endpoint scoped to viewer auth (signed token), blocked for machine API key
- `VIEWER_TOKEN_TTL_SECS` env var (default 300)
- Refactor existing `vnc_proxy` route to extract `_run_vnc_proxy()` helper; both admin `/api/profiles/{id}/vnc` and new `/viewer/*` route call it; both routes drive `viewer_attach_count`

**Addresses from FEATURES.md:** Profile-scoped signed viewer URL, viewer URL TTL enforcement, viewer URL revocation on profile stop, secure iframe embedding

**Avoids from PITFALLS.md:** Viewer token in querystring (Pitfall 5), token replay (Pitfall 6), admin CSRF via viewer iframe (Pitfall 9), CDP URL without expiry/scope (Pitfall 8)

**Research flag:** The fragment-delivery mechanism for noVNC requires inspecting where to inject the `window.location.hash` extraction hook in the existing noVNC 1.4.0 client. Likely the `RFB` constructor options or a pre-connect callback. 30-minute code read at Phase 3 start before any implementation.

---

### Phase 4: Admin Dashboard Pivot and API Surface Cleanup

**Rationale:** Frontend work can begin once Phase 1's admin_router returns data, but the full pivot (removing old routes, final ops UI) is last so nothing regresses before the machine API is proven in phases 2-3.

**Delivers:**
- `SessionList.tsx` — ops view: running sessions, vendor_type, vendor_connection_id, uptime, CDP status, link to admin VNC viewer
- `ProfileList.tsx` / `ProfileForm.tsx` pivoted to read-heavy ops use (no direct launch button)
- Old `/api/profiles/{id}/launch` route removed
- Old profile-creation flow (direct field entry) replaced by template-driven upsert via admin UI
- `PATCH /profiles/{id}` / `DELETE /profiles/{id}` exposed on machine API surface
- OpenAPI spec clean-up; deprecation notices removed; machine API surface finalized

**Addresses from FEATURES.md:** Replace existing `/api/profiles/*` surface, admin dashboard ops pivot, active session list with debug link

**Avoids from PITFALLS.md:** No new pitfalls specific to this phase; this is the cleanup pass that removes the last surfaces that could create dual-API confusion.

**Research flag:** Standard patterns — React component work with established patterns. No additional research needed.

---

### Phase Ordering Rationale

The dependency graph, confirmed independently by FEATURES.md, ARCHITECTURE.md, and PITFALLS.md, enforces this exact sequence:

```
Phase 1: vendor_templates schema + snapshot strategy + clipboard default + Docker UID
    |
    └──unblocks──> Phase 2: SessionManager + warm-pool + POST /sessions
                       |
                       └──unblocks──> Phase 3: /viewer/* WS + signed tokens + CSP
                                          |
                                          └──unblocks──> Phase 4: Admin pivot + old surface removal
```

Parallel work within phases:
- `viewer_tokens.py` (Phase 3 component) is a pure module with no Phase 2 dependencies and can be written during Phase 1
- React admin template UI (Phase 1 frontend) can start against mock API responses once the Pydantic models are defined
- `SessionList.tsx` (Phase 4) can start once Phase 2's `GET /sessions` endpoint exists

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All claims verified: PyJWT 2.12.1 confirmed on PyPI (2026-03-13); FastAPI `APIKeyHeader` pattern verified against official docs; CDP connection-count absence confirmed against official DevTools Protocol reference |
| Features | HIGH | Verified against four commercial analogs (Browserbase, Anchor, Steel, Hyperbrowser) with full doc access; confirmed against PROJECT.md constraints and existing codebase map |
| Architecture | HIGH | All findings from direct codebase analysis (`backend/main.py`, `browser_manager.py`, `database.py`, `vnc_manager.py`); no speculative external sources required |
| Pitfalls | HIGH | All 13 pitfalls sourced from Playwright GitHub issues, Browserless production post-mortems, JWT security best practices, SQLite concurrency docs, Docker volume UID docs — not theoretical |

**Overall confidence:** HIGH

### Gaps to Address

- **noVNC fragment-token hook location:** The mechanism for extracting the viewer token from `window.location.hash` and presenting it in the WS upgrade needs a specific JS integration point. The existing noVNC 1.4.0 client must be inspected at Phase 3 start to identify the correct hook (likely the `RFB` constructor options or a pre-connect event). Low-risk but requires a 30-minute code read before implementation.

- **KasmVNC WebSocket port binding:** The existing `VNCManager.allocate()` assigns per-profile WebSocket ports (`:6100 + offset`). Confirm KasmVNC's websockify binds to `127.0.0.1` (not `0.0.0.0`) so the raw VNC WebSocket is never directly reachable from outside the container. Verify in `VNCManager` at Phase 3 start.

- **`asyncio.Lock` per `(vendor_type, vendor_connection_id)` under multi-worker deployment:** FastAPI runs in a single asyncio event loop with the default single uvicorn worker. Per-key `asyncio.Lock` objects work correctly in this model. If the deployment ever adds `--workers N > 1`, per-process locks stop providing the race guarantee and the DB `UNIQUE` constraint becomes the only protection. Document this constraint explicitly in `session_manager.py`.

- **CloakBrowser binary version pinning:** Pitfall 7 (fingerprint inconsistency on sleep/wake) requires pinning the CloakBrowser binary SHA in the Docker image. Confirm the current `Dockerfile` version pinning strategy at Phase 2 start; if using a floating tag, lock it before any warm-pool sleep/wake testing.

---

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK.md` — PyJWT, APIKeyHeader, asyncio timer, SQLite JSON column, CDP no-connection-count confirmation
- `.planning/research/FEATURES.md` — table stakes, differentiators, anti-features, feature dependency graph, competitive analysis
- `.planning/research/ARCHITECTURE.md` — component boundaries, warm-pool state machine, build order, data flow diagrams, integration seams
- `.planning/research/PITFALLS.md` — 13 pitfalls with phase mapping and recovery strategies
- `.planning/PROJECT.md` — scope, constraints, locked decisions, out-of-scope list
- `.planning/codebase/ARCHITECTURE.md` — existing system structure (ground truth)
- PyPI PyJWT 2.12.1 (verified 2026-03-13)
- FastAPI Security reference (fastapi.tiangolo.com/reference/security/)
- Chrome DevTools Protocol reference (chromedevtools.github.io/devtools-protocol/)
- Playwright GitHub issues #35466, #31849 (SingletonLock, context close behavior)

### Secondary (MEDIUM confidence)
- Browserbase, Anchor Browser, Steel.dev, Hyperbrowser docs — competitive feature comparison
- Browserless.io production observations (5M sessions/week) — thundering herd and zombie process patterns
- JWT security best practices (curity.io) — token-in-querystring logging risk
- SQLite concurrent writes post (tenthousandmeters.com) — WAL mode and upsert patterns

### Tertiary (LOW confidence)
- Kernel vs. Hyperbrowser comparison — page 404'd at research time; findings sourced from Hyperbrowser docs directly instead

---
*Research completed: 2026-04-22*
*Ready for roadmap: yes*
