# Architecture Research

**Domain:** Headless browser profile service — warm-pool sessions, signed viewer URLs, vendor templates
**Researched:** 2026-04-22
**Confidence:** HIGH (based on direct codebase analysis, no external sources needed)

---

## System Overview

### Current Architecture (Existing — Do Not Rewrite)

```
┌──────────────────────────────────────────────────────────────────────┐
│  React SPA (admin dashboard)                                          │
│  App.tsx → ProfileList / ProfileForm / ProfileViewer / LaunchButton   │
└─────────────────────────┬────────────────────────────────────────────┘
                           │  HTTP + WebSocket  /api/*
┌──────────────────────────▼────────────────────────────────────────────┐
│  FastAPI  (backend/main.py)                                            │
│  AuthMiddleware → routes → BrowserManager → VNCManager                │
│                                                                        │
│  Existing routes:                                                      │
│    POST /api/profiles/{id}/launch                                      │
│    GET/POST /api/profiles  (CRUD)                                      │
│    WS  /api/profiles/{id}/vnc   ← RFB filter + relay                  │
│    WS  /api/profiles/{id}/cdp   ← CDP bidirectional proxy             │
└──────────┬─────────────────┬─────────────────────────────────────────┘
           │                 │
  ┌────────▼──────┐  ┌───────▼────────┐
  │ BrowserManager│  │  VNCManager    │
  │ running: dict │  │ _allocated:dict│
  │ launch/stop   │  │ allocate/start │
  │ _lock asyncio │  │ stop_vnc       │
  └───────────────┘  └────────────────┘
           │
  ┌────────▼──────────────────────────────┐
  │  Per-profile process tree              │
  │  Xvnc (:100) → KasmVNC WS :6100       │
  │  Chromium (cdp :5100) → DISPLAY=:100   │
  └───────────────────────────────────────┘
           │
  ┌────────▼──────┐
  │  SQLite        │
  │  profiles      │
  │  profile_tags  │
  └───────────────┘
```

### Target Architecture (After This Milestone)

```
┌───────────────────────────────────────────────────────────────────────┐
│  Main App (external consumer)           React Admin Dashboard          │
│  API key auth                           Admin cookie auth              │
└──────────────┬──────────────────────────────┬─────────────────────────┘
               │  /sessions  /profiles         │  /admin/templates
               │  /viewer/*  (API key)         │  /admin/sessions (admin token)
┌──────────────▼──────────────────────────────▼─────────────────────────┐
│  FastAPI (backend/main.py)                                              │
│                                                                         │
│  ┌─────────────────┐   ┌──────────────────────────────────────────┐    │
│  │  APIKeyMiddleware│   │  AuthMiddleware (existing, admin routes)  │    │
│  └────────┬────────┘   └─────────────────────┬────────────────────┘    │
│           │                                  │                          │
│  ┌────────▼────────────────────────────────────────────────────────┐   │
│  │  sessions_router  (new)      │  admin_router (new)               │   │
│  │  POST /sessions              │  GET/POST/PUT/DELETE /admin/...   │   │
│  │  GET  /sessions/{id}         │  Templates CRUD                   │   │
│  │  DELETE /sessions/{id}       │  Sessions list (ops view)         │   │
│  └────────┬─────────────────────┴───────────────────────────────────┘  │
│           │                                                              │
│  ┌────────▼────────────────────────────────────────────────────────┐   │
│  │  SessionManager  (new — backend/session_manager.py)              │   │
│  │  upsert_profile()        — find-or-create by (vendor, conn_id)   │   │
│  │  get_or_wake_session()   — checks warm pool, launches if needed  │   │
│  │  create_viewer_token()   — mints signed viewer URL               │   │
│  └────────┬─────────────────────────────────────────────────────────┘  │
│           │                                                              │
└───────────┼──────────────────────────────────────────────────────────┘
            │  calls into existing lifecycle (unchanged)
  ┌─────────▼──────────────────────────────────────────────────────────┐
  │  BrowserManager (existing — unchanged externally)                   │
  │  + RunningProfile gains: cdp_attach_count, viewer_attach_count,     │
  │    idle_since, _idle_timer (asyncio.Task)                           │
  └──────────┬─────────────────────────────────────────────────────────┘
             │
  ┌──────────▼──────┐   ┌──────────────────────────┐
  │  VNCManager      │   │  SQLite                   │
  │  (unchanged)     │   │  profiles (+ vendor_type, │
  └──────────────────┘   │    vendor_connection_id,  │
                         │    template_id FK)         │
                         │  vendor_templates (new)    │
                         └──────────────────────────┘
```

---

## Component Boundaries

| Component | File | Responsibility | Communicates With |
|-----------|------|----------------|-------------------|
| SessionManager | `backend/session_manager.py` (new) | Upsert profile by (vendor, conn_id); wake from warm pool; mint viewer tokens; coordinate idle timer | BrowserManager (lifecycle), database (upsert), token module |
| WarmPoolTracker | Embedded in `RunningProfile` dataclass (extend existing) | Track cdp_attach_count + viewer_attach_count; fire idle callback when both reach 0 | SessionManager (idle callback), BrowserManager (owns RunningProfile) |
| ViewerTokens | `backend/viewer_tokens.py` (new) | Mint/validate HMAC-signed tokens scoped to (profile_id, exp); pure module, no state | SessionManager (minting), main.py VNC proxy (validation) |
| APIKeyMiddleware | Inline in `backend/main.py` or `backend/auth.py` (new) | Check `X-API-Key` header on `/sessions/*` and `/profiles/*` Machine App routes; distinct from admin AuthMiddleware | main.py (middleware chain) |
| sessions_router | `backend/routers/sessions.py` (new) | POST /sessions, GET /sessions/{id}, DELETE /sessions/{id} | SessionManager |
| admin_router | `backend/routers/admin.py` (new) | Templates CRUD, ops-oriented session list; protected by admin auth | database (templates CRUD), BrowserManager (status) |
| vendor_templates | `backend/database.py` (extend existing) | SQLite vendor_templates table; CRUD functions | sessions_router, admin_router |
| VNC WS proxy | `backend/main.py` (existing, extend) | Count viewer_attach_count when WS connects/disconnects; validate viewer token on /viewer/* WS route | WarmPoolTracker (count mutations), ViewerTokens (validation) |
| React Admin | `frontend/src/` (extend existing) | Template management screens; session ops list; removes old ProfileForm complexity | admin_router |

---

## Data Flow

### POST /sessions (Happy Path)

```
Main App
  POST /sessions
  {vendor_type, vendor_connection_id}
        │
        ▼
  APIKeyMiddleware — validate X-API-Key header
        │
        ▼
  sessions_router.post_session()
        │
        ▼
  SessionManager.get_or_wake_session(vendor_type, vendor_connection_id)
        │
        ├─ db.upsert_profile_by_vendor(vendor_type, vendor_connection_id)
        │    — SELECT ... WHERE vendor_type=? AND vendor_connection_id=?
        │    — if missing: look up vendor_templates, snapshot fields into new profile row
        │    — returns profile dict (id, all config fields)
        │
        ├─ BrowserManager.running.get(profile_id)
        │    ├─ if running: (warm pool hit) → skip launch, reset idle timer
        │    └─ if not running: BrowserManager.launch(profile)  ← existing code, unchanged
        │
        ├─ ViewerTokens.mint(profile_id, ttl=3600)
        │    — HMAC-SHA256(secret, f"{profile_id}:{exp}") → base64url token
        │    — returns signed_token string
        │
        └─ return SessionResponse
             {profile_id, cdp_url, vnc_viewer_url: "/viewer/{profile_id}?token={signed_token}"}

Main App receives response
  — cdp_url: connect Playwright for automation
  — vnc_viewer_url: embed as iframe for end-user 2FA
```

### Warm-Pool State Machine

```
States:
  STOPPED   — no process, no RunningProfile in dict
  RUNNING   — RunningProfile exists; cdp_attach_count > 0 OR viewer_attach_count > 0
  IDLE      — RunningProfile exists; both counts == 0; idle_timer ticking
  SLEEPING  — idle_timer expired; BrowserManager.stop() called; back to STOPPED

Transitions:
  STOPPED  →  RUNNING    : /sessions called, BrowserManager.launch() succeeds
  RUNNING  →  IDLE       : last CDP client disconnects AND last viewer WS disconnects
                           (both counts drop to 0)
  IDLE     →  RUNNING    : /sessions called again OR any attach event increments a count
  IDLE     →  SLEEPING   : asyncio idle_timer fires (N minutes; configurable via env IDLE_TIMEOUT_SECS)
                           → calls BrowserManager.stop(profile_id)
                           → removes RunningProfile → back to STOPPED
  SLEEPING →  RUNNING    : /sessions called → BrowserManager.launch() again
                           (Chromium profile dir preserved on disk — session state intact)

Timer model:
  idle_timer lives as asyncio.Task on RunningProfile (or tracked by SessionManager).
  On RUNNING→IDLE: asyncio.create_task(_idle_sleep(profile_id, IDLE_TIMEOUT_SECS))
  On IDLE→RUNNING (re-attach): cancel idle_timer Task before it fires.
  On timer fire: await BrowserManager.stop(profile_id) → state back to STOPPED.

  Implementation sketch:
    async def _idle_sleep(profile_id: str, delay: int):
        await asyncio.sleep(delay)
        await browser_mgr.stop(profile_id)
        logger.info("Warm pool: profile %s slept after %ds idle", profile_id, delay)
```

### CDP-Attach Counting

```
Approach: count WebSocket connections to /api/profiles/{id}/cdp proxy.

When a CDP WS client connects to the cdp_proxy route:
  running.cdp_attach_count += 1
  SessionManager.on_attach(profile_id)  ← cancels idle timer if any

When the CDP WS client disconnects (either side closes):
  running.cdp_attach_count -= 1
  if running.cdp_attach_count == 0 and running.viewer_attach_count == 0:
      SessionManager.on_all_detached(profile_id)  ← starts idle timer

Note: The existing cdp_proxy route in main.py already has try/finally around
the WebSocket lifetime — the count mutations fit cleanly there without touching
BrowserManager internals or Playwright internals.

Do NOT use Playwright BrowserContext connection events — CloakBrowser wraps
the context and the event surface is not guaranteed. The WS proxy already owns
the connection lifecycle, so counting there is the only correct seam.
```

### Viewer-Attach Counting

```
Approach: count WebSocket connections to the VNC proxy route.

Existing: /api/profiles/{id}/vnc — admin dashboard VNC viewer.
New:      /viewer/{profile_id}/vnc?token={signed_token} — Main App iframe viewer.

Both routes use the same underlying VNC proxy logic (_proxy_vnc_websocket).
Both need to increment/decrement viewer_attach_count on connect/disconnect.

For the /viewer/* route:
  1. Validate signed token BEFORE accepting WebSocket.
  2. Verify token.profile_id == profile_id path param.
  3. Verify token not expired (check exp claim).
  4. On validation pass: accept WS → increment viewer_attach_count.
  5. On WS close: decrement viewer_attach_count.
  6. If 401/403: close WS with appropriate code (reuse 4401 pattern).

The existing /api/profiles/{id}/vnc (admin) also increments viewer_attach_count
so admin viewers keep the session alive. This is the correct behavior — admin
has an open viewer, profile stays warm.
```

### Signed Viewer Token Flow

```
Minting (POST /sessions):
  secret = os.environ["VIEWER_TOKEN_SECRET"]  # required env var
  exp = int(time.time()) + TTL_SECS
  payload = f"{profile_id}:{exp}"
  sig = hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()[:16]
  token = base64url_encode(f"{payload}:{sig}")

Validation (/viewer/{profile_id}/vnc?token=...):
  decoded = base64url_decode(token)
  parts = decoded.split(":")  → [profile_id, exp, sig]
  if time.time() > int(exp): reject (expired)
  if path profile_id != parts[0]: reject (wrong profile)
  expected_sig = hmac.new(secret.encode(), f"{parts[0]}:{parts[1]}".encode(), sha256).hexdigest()[:16]
  if not hmac.compare_digest(sig, expected_sig): reject (invalid)

Token TTL: 3600s default (1 hour). Configurable via VIEWER_TOKEN_TTL_SECS env var.
Token is single-use in spirit — the Main App re-calls /sessions to get a fresh URL
when embedding. No server-side revocation needed for v1 (TTL is the control).

Location: backend/viewer_tokens.py
  mint(profile_id: str, ttl: int) → str
  validate(token: str, claimed_profile_id: str) → bool | raises ViewerTokenError

Keep it a pure module with no imports from FastAPI or BrowserManager.
```

### Template Snapshot on Profile Creation

```
vendor_templates table:
  id TEXT PK
  vendor_type TEXT UNIQUE NOT NULL  ← the lookup key
  fingerprint_seed INTEGER
  timezone TEXT
  locale TEXT
  platform TEXT
  screen_width INTEGER
  screen_height INTEGER
  gpu_vendor TEXT
  gpu_renderer TEXT
  hardware_concurrency INTEGER
  humanize BOOLEAN
  human_preset TEXT
  launch_args TEXT  (JSON array, same as profiles.launch_args)
  clipboard_sync BOOLEAN
  color_scheme TEXT
  notes TEXT
  created_at TEXT
  updated_at TEXT

profiles table additions:
  vendor_type TEXT NOT NULL
  vendor_connection_id TEXT NOT NULL
  template_id TEXT  (FK vendor_templates.id — nullable for profiles created before templates exist)
  UNIQUE(vendor_type, vendor_connection_id)

Snapshot strategy:
  On upsert_profile_by_vendor():
    1. Look up template by vendor_type.
    2. If profile row doesn't exist yet: copy all template fields into new profile row.
       Store template_id FK for auditability.
    3. If profile row already exists: return it unchanged.
       (Template changes do NOT retroactively alter live profiles — intentional.)

This means profiles are independent after creation. The template_id column is
informational only (shows which template was used). Admins who want to re-apply
a template to an existing profile do so explicitly via admin UI (future feature).
```

---

## Recommended Project Structure (New Files Only)

```
backend/
├── routers/                     # NEW — split large main.py into routers
│   ├── __init__.py
│   ├── sessions.py              # POST /sessions, GET/DELETE /sessions/{id}
│   └── admin.py                 # /admin/templates CRUD, /admin/sessions ops list
├── session_manager.py           # NEW — SessionManager class
├── viewer_tokens.py             # NEW — mint/validate signed viewer URLs
├── auth.py                      # NEW (optional) — APIKeyMiddleware extracted here
└── main.py                      # EXISTING — add router includes, add /viewer/* WS route
```

The `routers/` split is recommended because `main.py` is already 1,027 lines and adding templates, sessions, admin, and viewer endpoints inline would make it unmanageable. The existing RFB code stays in `main.py` unchanged — only new routes go into routers.

Frontend:
```
frontend/src/
├── components/
│   ├── TemplateList.tsx         # NEW — admin list of vendor templates
│   ├── TemplateForm.tsx         # NEW — create/edit template form
│   └── SessionList.tsx          # NEW — ops view: running sessions + status
├── hooks/
│   └── useTemplates.ts          # NEW — CRUD hook for templates
└── lib/
    └── api.ts                   # EXTEND — add template + session endpoint types
```

The existing `ProfileList.tsx`, `ProfileForm.tsx`, and `LaunchButton.tsx` become ops-oriented (read-heavy, no launch button for direct use). `ProfileViewer.tsx` remains for admin VNC access.

---

## Architectural Patterns

### Pattern 1: SessionManager as Thin Orchestrator

SessionManager does not own lifecycle; it orchestrates between existing components.

```python
class SessionManager:
    def __init__(self, browser_mgr: BrowserManager):
        self._browser = browser_mgr
        self._idle_tasks: dict[str, asyncio.Task] = {}

    async def get_or_wake_session(
        self, vendor_type: str, vendor_connection_id: str
    ) -> SessionResult:
        profile = db.upsert_profile_by_vendor(vendor_type, vendor_connection_id)
        profile_id = profile["id"]

        running = self._browser.running.get(profile_id)
        if running is None:
            running = await self._browser.launch(profile)

        # Cancel any pending idle timer (we have a new consumer)
        self._cancel_idle(profile_id)

        token = viewer_tokens.mint(profile_id)
        return SessionResult(
            profile_id=profile_id,
            cdp_url=f"/api/profiles/{profile_id}/cdp",
            vnc_viewer_url=f"/viewer/{profile_id}/vnc?token={token}",
        )

    def on_attach(self, profile_id: str):
        self._cancel_idle(profile_id)

    def on_all_detached(self, profile_id: str):
        delay = int(os.environ.get("IDLE_TIMEOUT_SECS", "300"))
        task = asyncio.create_task(self._idle_sleep(profile_id, delay))
        self._idle_tasks[profile_id] = task

    async def _idle_sleep(self, profile_id: str, delay: int):
        await asyncio.sleep(delay)
        self._idle_tasks.pop(profile_id, None)
        await self._browser.stop(profile_id)

    def _cancel_idle(self, profile_id: str):
        task = self._idle_tasks.pop(profile_id, None)
        if task and not task.done():
            task.cancel()
```

### Pattern 2: Extend RunningProfile for Connection Counts

Avoid a separate tracking dict — keep counts co-located with the running instance.

```python
@dataclass
class RunningProfile:
    profile_id: str
    context: Any  # Playwright BrowserContext
    display: int
    ws_port: int
    cdp_port: int
    # NEW fields:
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
```

Counts are mutated under `browser_mgr._lock` to prevent races with `stop()` and `launch()`. The VNC proxy and CDP proxy routes call `SessionManager.on_attach()` / `on_all_detached()` which check the counts on `RunningProfile`.

### Pattern 3: Two Auth Middlewares in Sequence

The existing `AuthMiddleware` checks admin cookie/bearer for `/api/*`. A new `APIKeyMiddleware` checks `X-API-Key` for the Main App routes. Both are raw ASGI middleware (same pattern as existing — avoids BaseHTTPMiddleware WebSocket breakage).

Route segregation:
- `/sessions/*`, `/profiles/*` (machine API) → APIKeyMiddleware
- `/admin/*` (admin UI backing) → AuthMiddleware (existing)
- `/viewer/*` (WS viewer) → no middleware, token validated inside WS handler
- `/api/auth/*`, `/api/status` → exempt (existing exemption list)

The `_AUTH_EXEMPT` frozenset expands to include `/sessions/*` prefix (or the APIKeyMiddleware runs first and handles them before AuthMiddleware sees them).

### Pattern 4: Idempotent Upsert for Profile Identity

```python
def upsert_profile_by_vendor(
    vendor_type: str, vendor_connection_id: str
) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
            (vendor_type, vendor_connection_id)
        ).fetchone()
        if row:
            profile = dict(row)
            profile["launch_args"] = json.loads(profile.get("launch_args") or "[]")
            return profile

        # First time: snapshot from template
        template = conn.execute(
            "SELECT * FROM vendor_templates WHERE vendor_type=?",
            (vendor_type,)
        ).fetchone()
        if not template:
            raise ValueError(f"No template configured for vendor_type={vendor_type!r}")

        # create_profile() handles uuid, user_data_dir, timestamps
        return create_profile(
            name=f"{vendor_type}/{vendor_connection_id}",
            vendor_type=vendor_type,
            vendor_connection_id=vendor_connection_id,
            template_id=template["id"],
            **_template_to_profile_fields(dict(template))
        )
```

---

## Data Flow: /viewer/* WebSocket Route (New)

```
Main App iframe src="/viewer/{profile_id}/vnc?token={signed_token}"
    ↓
noVNC JS inside iframe loads, connects WS to:
    ws://<host>/viewer/{profile_id}/ws?token={signed_token}
    ↓
FastAPI WS handler: viewer_vnc_proxy()
    1. _check_websocket_origin() — CSWSH protection (existing helper, reuse)
    2. viewer_tokens.validate(token, profile_id)
       — expired? close(4401)
       — wrong profile? close(4403)
       — bad sig? close(4401)
    3. running = browser_mgr.running.get(profile_id)
       — not running? close(4004, "Profile not running")
    4. running.viewer_attach_count += 1
       session_mgr.on_attach(profile_id)
    5. await websocket.accept()
    6. Connect to KasmVNC at ws://127.0.0.1:{running.ws_port}/websockify
       — same logic as existing vnc_proxy() — extract into _run_vnc_proxy() helper
    7. finally:
         running.viewer_attach_count -= 1
         if running.cdp_attach_count == 0 and running.viewer_attach_count == 0:
             session_mgr.on_all_detached(profile_id)
```

The existing `/api/profiles/{id}/vnc` admin route gets the same count mutations added to it so admin viewers keep profiles warm too.

---

## Integration Seams with Existing Code

| Existing Thing | How New Code Hooks In | Change to Existing Code |
|----------------|----------------------|------------------------|
| `BrowserManager.launch()` | SessionManager calls it unchanged | None — add fields to RunningProfile dataclass only |
| `BrowserManager.stop()` | SessionManager calls it unchanged | None |
| `BrowserManager.running` dict | SessionManager reads it; WS handlers mutate `cdp_attach_count`/`viewer_attach_count` on the RunningProfile | Extend RunningProfile dataclass with two int fields (default 0) — additive |
| `VNCManager` | No changes | None |
| `database.py` | Add `vendor_templates` table + schema, add columns to `profiles`, add `upsert_profile_by_vendor()` | Additive — schema migrations follow existing `ALTER TABLE` pattern already in `init_db()` |
| `main.py` VNC proxy | Extract `_run_vnc_proxy()` helper; existing admin route calls it; new `/viewer/*` route also calls it | Refactor to helper (no behavior change); add count mutations in both callers |
| `AuthMiddleware` | No change to admin auth | Add `APIKeyMiddleware` for machine routes; add `/sessions` and `/profiles` (machine) to exemption list for `AuthMiddleware` |
| `_AUTH_EXEMPT` frozenset | Expand to include machine API prefixes | Minimal — add entries |
| `models.py` | Add `SessionRequest`, `SessionResponse`, `VendorTemplateCreate`, `VendorTemplateResponse` | Additive only |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: SessionManager Owning the Process Tree

If SessionManager tries to call `VNCManager.allocate()` or manage displays directly, it duplicates BrowserManager logic and creates split ownership.

Do this instead: SessionManager calls only `BrowserManager.launch(profile)` and `BrowserManager.stop(profile_id)`. All VNC/process lifecycle stays in BrowserManager.

### Anti-Pattern 2: Polling CDP or Playwright for Connection State

Using Playwright's `context.on("close")` or checking CDP `/json/list` to detect disconnections introduces race conditions and dependency on internal Playwright/CloakBrowser event behavior.

Do this instead: count WebSocket connections at the proxy layer. The proxy already owns the connection lifetime. This is the only reliable seam.

### Anti-Pattern 3: Live Template Inheritance (Template Changes Affect Running Profiles)

If profile rows store only a `template_id` FK and read template fields at launch time, a template change mid-session causes profile behavior to change unexpectedly.

Do this instead: snapshot all template fields into the profile row at creation. Profile row is self-contained after that. Template changes only affect newly created profiles.

### Anti-Pattern 4: Global idle_timer State Outside BrowserManager

If idle timers are tracked in a module-level dict or inside database rows, they become stale across restarts and hard to cancel cleanly.

Do this instead: idle timers live in `SessionManager._idle_tasks` dict (asyncio.Task objects). On startup, all running profiles start with zero counts (just launched or recovered) so no timers need to be restored. Profiles that were running before a restart will re-enter RUNNING state on the next `/sessions` call.

### Anti-Pattern 5: Merging Machine API and Admin API Into One Router

If sessions and admin templates share a router, you can't apply different auth middleware to them. Adding auth exceptions inline scales poorly.

Do this instead: two separate APIRouter instances with clear path prefixes. `APIKeyMiddleware` intercepts `/sessions/*` and `/profiles/*` (machine), `AuthMiddleware` intercepts `/admin/*`. Each middleware checks only its own prefix.

---

## Build Order (Phase Dependencies)

The milestone has hard dependencies that constrain sequencing:

```
1. Database schema (vendor_templates table, profile columns)
   Unblocks everything. No new component can work without this.

2. ViewerTokens module (backend/viewer_tokens.py)
   Pure module, no dependencies on step 1 or BrowserManager.
   Can be written and tested in isolation immediately.
   Unblocks: /viewer/* WS route, /sessions response.

3. Template CRUD (database functions + admin_router + admin UI)
   Depends on: step 1.
   Can be built before SessionManager — gives operators a way to
   create templates so /sessions has data to work with.
   Unblocks: upsert_profile_by_vendor (needs a template to exist).

4. Profile identity migration (vendor_type + vendor_connection_id columns)
   Depends on: step 1 (same migration batch).
   Existing profiles get NULL vendor_type/vendor_connection_id — that's fine,
   they won't be touched by /sessions.

5. SessionManager + upsert_profile_by_vendor
   Depends on: steps 1, 2, 3.
   Core of the milestone — POST /sessions calls this.

6. Warm-pool state machine (RunningProfile count fields + idle timer)
   Depends on: step 5 (SessionManager exists before timers make sense).
   Extend RunningProfile with count fields.
   Add on_attach/on_all_detached calls to CDP proxy and VNC proxy routes.

7. /viewer/* WS route + token validation
   Depends on: step 2 (ViewerTokens), step 6 (viewer_attach_count).
   Refactor existing vnc_proxy into _run_vnc_proxy() helper at this step.

8. sessions_router (POST /sessions, GET /sessions/{id}, DELETE /sessions/{id})
   Depends on: steps 5, 6, 7 (all pieces exist).
   Wire up APIKeyMiddleware here too.

9. Remove old /api/profiles/{id}/launch
   Depends on: step 8 (/sessions is live and tested).
   Final cleanup — do last so nothing regresses before /sessions is solid.

10. Admin dashboard pivot (React — TemplateList, TemplateForm, SessionList)
    Depends on: step 3 (admin_router), step 8 (sessions list endpoint).
    Frontend can be developed in parallel with backend steps 3-8 if mock
    API responses are used.
```

Parallel work possible:
- ViewerTokens (step 2) and Template CRUD backend (step 3) can be built simultaneously.
- React admin UI (step 10) can start once step 3 admin_router returns data.

---

## Scaling Considerations

This service is explicitly scoped to single-host, <20 concurrent profiles. The warm-pool design is optimized for this constraint.

| Concern | At <20 profiles (target) | Notes |
|---------|--------------------------|-------|
| In-memory running dict | Works perfectly | No external state needed |
| asyncio idle timers | Trivial at 20 concurrent | asyncio.Task per profile is lightweight |
| SQLite under concurrent requests | WAL mode already enabled | Fine for <20 concurrent writes |
| CDP WS proxy fan-out | One WS per /sessions call | Main App typically has 1 CDP client per profile |
| Viewer WS fan-out | One WS per iframe | Multiple admin viewers could attach; counts handle it |

If concurrency grows to >50 profiles, the first bottleneck is X display numbers (BASE_DISPLAY + N approach) and port allocations, not the architecture. The warm-pool and token design scales fine to hundreds with no changes.

---

## Sources

- Direct codebase analysis: `backend/browser_manager.py`, `backend/main.py`, `backend/database.py`, `backend/vnc_manager.py`, `backend/models.py`
- Project requirements: `.planning/PROJECT.md`
- Existing architecture map: `.planning/codebase/ARCHITECTURE.md`
- Confidence: HIGH — all findings from direct code inspection, no external sources required

---
*Architecture research for: CloakBrowser-Manager warm-pool session service refocus*
*Researched: 2026-04-22*
