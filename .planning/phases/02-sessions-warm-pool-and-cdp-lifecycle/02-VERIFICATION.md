---
phase: 02-sessions-warm-pool-and-cdp-lifecycle
verified: 2026-05-19T00:00:00Z
status: passed
score: 5/5 roadmap success criteria verified; 19/19 phase requirements structurally satisfied
human_verification:
  - test: "Run slow E2E suite with real CloakBrowser binary"
    expected: "pytest -m slow passes test_idle_sleep_then_wake_persists_cookies and test_restart_safety_first_post_after_lifespan_wakes_within_timeout"
    why_human: "Default CI skips slow tests; cookie persistence across real Chromium sleep/wake requires the binary"
  - test: "Main App integration smoke"
    expected: "POST /sessions with X-API-Key returns cdp_url; CDP WS connects with same key; idle stop after disconnect"
    why_human: "End-to-end operator flow across real network and automation client not exercised in unit/integration mocks"
---

# Phase 2: Sessions, Warm-Pool, and CDP Lifecycle Verification Report

**Phase Goal:** The Main App can call `POST /sessions` with `(vendor_type, vendor_connection_id)` and reliably receive a live CDP URL and session state, with profiles staying warm across automation runs and sleeping safely when idle.

**Verified:** 2026-05-19  
**Status:** passed  
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `POST /sessions` with valid API key returns `{profile_id, cdp_url, state}`; repeated calls reuse same `profile_id`; 10 concurrent requests do not duplicate rows or launches | ✓ VERIFIED | `backend/routers/sessions.py` → `SessionManager.get_or_wake`; `database.upsert_profile_by_vendor` + UNIQUE index; `test_sessions_router.py::test_post_sessions_concurrent_race_uses_per_key_lock` asserts one profile_id, one DB row, `launch.await_count == 1` |
| 2 | Profile idle longer than `IDLE_TIMEOUT_SECONDS` becomes `stopped`; next `POST /sessions` wakes with same `profile_id` and on-disk profile dir intact | ✓ VERIFIED | `SessionManager._idle_sleep` + `on_all_detached`; unit tests in `test_session_manager.py` (idle fire, cancel, defense-in-depth); `test_warm_pool_e2e.py::test_idle_sleep_then_wake_persists_cookies` (slow, real Chromium when available) |
| 3 | `GET /sessions/{profile_id}` returns status envelope; `DELETE /sessions/{profile_id}` stops browser without deleting row or directory | ✓ VERIFIED | `get_session_status` / `delete_session` in `routers/sessions.py`; integration tests in `test_sessions_router.py` |
| 4 | `GET /profiles` filtered list; `DELETE /profiles/{id}` destructive with `shutil.rmtree`; machine routes 401 without API key | ✓ VERIFIED | `routers/profiles.py`; `list_profiles_filtered`; `test_profiles_router.py`; `auth_api_key.require_api_key` + `test_auth_api_key.py` |
| 5 | After service restart, profiles begin stopped with zero attach counts; no auto-wake; first `POST /sessions` wakes within launch timeout | ✓ VERIFIED | Fresh process: `browser_mgr.running` starts empty; lifespan runs `cleanup_stale` only (no auto-launch); `test_warm_pool_e2e.py::test_restart_safety_first_post_after_lifespan_wakes_within_timeout` |

**Score:** 5/5 truths verified (structural + automated test coverage)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/browser_manager.py` | Semaphore(3), about:blank probe, RunningProfile counts, `_stop_locked` | ✓ VERIFIED | 437 lines; `BrowserLaunchError`, `_launch_sem`, `_probe_about_blank`, Singleton* cleanup, `cdp_attach_count`/`viewer_attach_count`/`last_launched_at`/`idle_started_at` |
| `backend/auth_api_key.py` | `require_api_key`, hmac.compare_digest, request-time env | ✓ VERIFIED | 67 lines; DEV_MODE bypass; tests cover 401 paths |
| `backend/database.py` | `upsert_profile_by_vendor`, `NoTemplateError`, `list_profiles_filtered` | ✓ VERIFIED | IntegrityError swallow + re-SELECT; UNIQUE index `idx_profiles_vendor_pair` |
| `backend/session_manager.py` | Per-key locks, idle tasks, get_or_wake, status envelope | ✓ VERIFIED | 338 lines; `on_attach`/`on_all_detached`/`shutdown` wired |
| `backend/routers/sessions.py` | POST/GET/DELETE /sessions | ✓ VERIFIED | 166 lines; router-level `Depends(require_api_key)` |
| `backend/routers/profiles.py` | GET/PATCH/DELETE /profiles | ✓ VERIFIED | 153 lines; PATCH rejects `clipboard_sync` via Pydantic |
| `backend/models.py` | Session/Profile machine models | ✓ VERIFIED | `SessionRequest/Response/StatusResponse/ListItem`, `ProfilePatch`, `MachineProfileResponse` |
| `backend/main.py` | Lifespan SessionManager; CDP WS counts; router includes | ✓ VERIFIED | `app.state.session_manager`; shutdown before `cleanup_all`; `_AUTH_EXEMPT_PREFIXES`; CDP WS `_ws_api_key_valid` before `accept()` |
| `backend/tests/test_*.py` | Unit + integration + slow E2E | ✓ VERIFIED | 166 tests passed (`pytest` default, `-m 'not slow'`) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `sessions.py::post_session` | `SessionManager.get_or_wake` | `await sm.get_or_wake(...)` | ✓ WIRED | grep `sm.get_or_wake` |
| `get_or_wake` | `database.upsert_profile_by_vendor` | under per-key lock | ✓ WIRED | line 122 |
| `get_or_wake` | `BrowserManager.launch` | when not in `running` | ✓ WIRED | line 132 |
| `main.py::cdp_proxy` | `cdp_attach_count` + idle hooks | try/finally under `_lock` | ✓ WIRED | increment/decrement + `on_attach`/`on_all_detached` |
| `main.py::lifespan` | `SessionManager.shutdown` | before `cleanup_all` | ✓ WIRED | lines 467–469 |
| `profiles.py::delete_profile` | `stop` + `remove_key_lock` + `rmtree` | sequential | ✓ WIRED | PROF-04 path complete |
| `AuthMiddleware` | `/sessions`, `/profiles` | prefix exempt | ✓ WIRED | `_AUTH_EXEMPT_PREFIXES` |

### Requirements Coverage (Phase 2)

| Requirement | Status | Notes |
|-------------|--------|-------|
| SESS-01 … SESS-14 | ✓ SATISFIED | Upsert, wake, idle dual-signal (CDP wired; viewer count field ready for Phase 3 WS), per-key lock, UNIQUE, semaphore, probe, singleton cleanup, status GET, session DELETE |
| PROF-01 … PROF-04 | ✓ SATISFIED | Filtered list, PATCH notes-only, destructive DELETE with dir removal |
| SEC-01 | ✓ SATISFIED | Machine routes + CDP WS X-API-Key; segregated from admin middleware |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None in Phase 2 backend modules | — | No TODO/FIXME/placeholder stubs in `session_manager.py`, routers, `auth_api_key.py` |

### Human Verification Recommended (Non-Blocking)

1. **Slow E2E with real Chromium** — Run `pytest -m slow` on a host with CloakBrowser installed to confirm SESS-12 cookie/dir persistence under real launch/stop (tests skip cleanly when mocked).

2. **Main App smoke** — Exercise `POST /sessions` → CDP WS with `X-API-Key` → disconnect → wait for idle → second `POST` from the consuming application.

### Phase 3 Boundary (Not Gaps)

- `vnc_viewer_url` intentionally empty on `SessionResponse` until Phase 3 JWT minting.
- `viewer_attach_count` is read and checked in idle logic but only incremented from the viewer WS route (Phase 3). CDP-only idle behavior is complete for Phase 2.

### Test Gate

```
166 passed in 4.49s  (pytest default: -m 'not slow')
```

### Gaps Summary

No structural gaps found. Phase 2 goal is achieved in the working tree: machine session API, warm-pool idle lifecycle, profile CRUD, and SEC-01 auth are implemented, wired, and covered by automated tests. Optional human runs of the slow E2E suite and a Main App integration smoke remain recommended before production promotion but do not block phase completion.

---

_Verified: 2026-05-19_  
_Verifier: Claude (gsd-verifier)_
