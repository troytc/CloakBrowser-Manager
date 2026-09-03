# Phase 4: Admin Dashboard Pivot and API Surface Cleanup — Research

**Researched:** 2026-05-19  
**Phase:** 04-admin-dashboard-pivot-and-api-surface-cleanup  
**Confidence:** HIGH (brownfield; patterns from Phase 1 templates UI + Phase 2 session envelope)

---

## Summary

Phase 4 is primarily a **frontend pivot** plus a **thin admin read API** and **legacy endpoint removal**. The machine API (`/sessions`, `/profiles` with `X-API-Key`) is already correct from Phase 2; the admin dashboard still uses pre-refocus `/api/profiles` CRUD and launch/stop. Executors add `GET /api/admin/sessions` to merge DB rows with `SessionManager.status_envelope`, build `SessionList.tsx`, rewire `App.tsx`, then delete launch/stop and redundant admin CRUD from `main.py`.

**Order constraint (ROADMAP):** Ship and smoke-test the new Sessions UI **before** removing old endpoints (Plan 04-04 last).

---

## Codebase Anchors

### Legacy launch / stop (OPS-01 targets)

```628:658:backend/main.py
@app.post("/api/profiles/{profile_id}/launch", response_model=LaunchResponse)
async def launch_profile(profile_id: str):
    ...
@app.post("/api/profiles/{profile_id}/stop")
async def stop_profile(profile_id: str):
    ...
```

**Tests referencing launch:** `backend/tests/test_api.py` (`test_launch_*`, `test_launch_args_*` on create path), `frontend/src/lib/api.test.ts` (`api.launchProfile`), `frontend/src/hooks/useProfiles.test.ts`.

### Legacy admin profile CRUD (OPS-02 targets)

```541:622:backend/main.py
@app.get("/api/profiles", response_model=list[ProfileResponse])
@app.post("/api/profiles", ...)
@app.get("/api/profiles/{profile_id}", ...)
@app.put("/api/profiles/{profile_id}", ...)
@app.delete("/api/profiles/{profile_id}")
```

**Keep after cleanup:** `DELETE` (ops), VNC WS ~939, clipboard ~693–724, CDP routes ~958+.

### Machine sessions list (pattern, not admin consumer)

```87:120:backend/routers/sessions.py
@router.get("", response_model=list[SessionListItem])
async def list_sessions(...):
    # Only browser_mgr.running keys — NOT all profiles
```

Phase 4 admin list must iterate **`db.list_profiles()`** (or `list_profiles_filtered` with no filters) and call `sm.status_envelope(pid)` per row.

### Session envelope source

```206:248:backend/session_manager.py
def status_envelope(self, profile_id: str) -> SessionStatusEnvelope:
    # state: running | idle | stopped; counts; idle_expires_at; last_launched_at
```

### Frontend entry + surfaces

```18:19:frontend/src/App.tsx
type View = "empty" | "create" | "edit" | "view";
type Surface = "profiles" | "templates";
```

**Pivot:** `Surface` → `"sessions" | "templates"`; remove `create` view and `handleNew` / `handleLaunch` / `handleStop`.

### Admin VNC (ADM-03 — do not change WS path)

```35:40:frontend/src/components/ProfileViewer.tsx
const wsUrl = `${protocol}//${window.location.host}/api/profiles/${profileId}/vnc`;
rfb = new RFB(containerRef.current!, wsUrl, {
  wsProtocols: ["binary"],
});
```

### API client legacy methods

```166:189:frontend/src/lib/api.ts
listProfiles, createProfile, updateProfile, deleteProfile,
launchProfile, stopProfile,
```

Remove or gate unused methods in Plan 04-04; add `listAdminSessions` → `GET /api/admin/sessions`.

### Templates (ADM-01 — already landed)

| File | Role |
|------|------|
| `frontend/src/components/TemplateList.tsx` | Table + delete |
| `frontend/src/components/TemplateForm.tsx` | Blueprint form |
| `frontend/src/hooks/useTemplates.ts` | 3s polling |
| `frontend/src/App.tsx` | `surface === "templates"` branch |

### Auth segregation (must preserve)

```101:105:backend/main.py
_AUTH_EXEMPT_PREFIXES: tuple[str, ...] = ("/sessions", "/profiles", "/viewer")
```

`/api/admin/sessions` is **not** exempt — requires admin cookie/Bearer.

---

## Gap: ADM-02 vs GET /sessions

| Endpoint | Auth | Rows returned |
|----------|------|----------------|
| `GET /sessions` | X-API-Key | Running profiles only |
| `GET /api/profiles` (legacy) | Admin | All profiles, old shape (name/tags, no vendor counts) |
| **`GET /api/admin/sessions` (new)** | Admin | All profiles + envelope fields |

---

## Recommended Admin Response Shape

```python
class AdminSessionListItem(BaseModel):
    profile_id: str
    name: str
    vendor_type: str
    vendor_connection_id: str
    state: Literal["running", "idle", "stopped"]
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
    idle_expires_at: str | None = None
    last_launched_at: str | None = None
    uptime_seconds: int | None = None  # computed when running/idle
    clipboard_sync: bool = False
```

---

## Frontend Component Plan

| New / changed | Based on |
|---------------|----------|
| `SessionList.tsx` | `TemplateList.tsx` + `ProfileList.tsx` search header |
| `useSessions.ts` | `useTemplates.ts` polling pattern |
| `App.tsx` | Replace profiles branch with sessions + viewer |

**Uptime display:** format `uptime_seconds` client-side (`formatUptime(secs)` → `2h 14m`).

---

## Test Impact Checklist

| Suite | Action |
|-------|--------|
| `backend/tests/test_api.py` | Remove/adapt launch/stop/create tests; add `test_admin_sessions_list` |
| `backend/tests/test_auth.py` | Assert `/api/admin/sessions` requires auth |
| `frontend/src/lib/api.test.ts` | Drop `launchProfile` tests; add admin sessions fetch |
| `frontend/src/hooks/useProfiles.test.ts` | Delete or replace with `useSessions.test.ts` |
| Full pytest | Must stay green (275+ baseline after Phase 3) |

---

## Pitfalls

1. **Calling machine `/sessions` from React** — leaks API key requirement; use admin route only (D-03).
2. **Removing `GET /api/profiles` before Sessions UI ships** — breaks dashboard during 04-03; order plans 04-01→04-03 before 04-04.
3. **Breaking Phase 3 viewer routes** — avoid broad `main.py` refactors; mount `admin_sessions` router additively.
4. **Launch for stopped rows in admin** — out of scope; show disabled viewer action + copy “Wake via Main App POST /sessions”.

---

## Plan Split (executor reference)

| Plan | Focus |
|------|-------|
| 04-01 | `GET /api/admin/sessions` + model + tests |
| 04-02 | `api.ts`, `useSessions`, `SessionList.tsx` |
| 04-03 | `App.tsx` pivot, ADM-01 verify, viewer wiring |
| 04-04 | Remove launch/stop/legacy CRUD, test + frontend cleanup |

---

## Confidence

| Area | Level | Notes |
|------|-------|-------|
| Backend admin list | HIGH | Straight merge of existing DB + envelope |
| Frontend pivot | HIGH | Mirrors Phase 1 templates pattern |
| Endpoint removal | MEDIUM | Large `test_api.py` diff — run full suite |
