---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 03
current_plan: 0
status: ready_to_plan
last_updated: "2026-05-19T12:00:00Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 17
  completed_plans: 17
  percent: 100
---

# Project State: VendorBrowser

**Milestone:** Warm-pool / Templates / Signed-Viewer
**Initialized:** 2026-04-22
**Last updated:** 2026-05-19

---

## Project Reference

**Core Value:** One idempotent API call gives the Main App a live CDP URL + a scoped iframe viewer URL for a vendor-specific browser profile, with session state preserved across automation runs via a warm pool.

**Codebase baseline:** v0.0.7 (2026-04-22) — brownfield refocus. Chromium lifecycle, VNC pipeline, SQLite, Docker, admin auth, React shell all validated and intact. Building on top.

**One sentence:** `POST /sessions` with `(vendor_type, vendor_connection_id)` → `{profile_id, cdp_url, vnc_viewer_url}`.

---

## Current Position

Phase: 03 (signed-viewer-urls-and-security-hardening) — Ready to plan
Plan: 0 of TBD
**Status:** Phase 2 complete; ready for Phase 3 planning

**Progress:**

```
[Phase 1] [Phase 2] [Phase 3] [Phase 4]
  [█]       [█]       [ ]       [ ]
 100%      100%        -         -
```

---

## Phase Summary

| # | Name | Requirements | Status |
|---|------|-------------|--------|
| 1 | Schema, Templates, and Security Foundations | 10 | Complete (2026-05-19) |
| 2 | Sessions, Warm-Pool, and CDP Lifecycle | 19 | Complete (2026-05-19) |
| 3 | Signed Viewer URLs and Security Hardening | 13 | Not started |
| 4 | Admin Dashboard Pivot and API Surface Cleanup | 6 | Not started |

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases total | 4 |
| Phases complete | 2 |
| Requirements total | 48 |
| Plans complete (milestone) | 17 / 17 planned so far |
| Phase 2 verification | passed (02-VERIFICATION.md) |

---

## Accumulated Context

### Key Decisions (locked)

| Decision | Rationale |
|----------|-----------|
| Templates are full blueprints keyed by `vendor_type` | Consistency across all vendor accounts; snapshot into profile at creation |
| Profile identity = `(vendor_type, vendor_connection_id)` | Main App already has `vendor_connection_id`; service stays stateless re: human identity |
| Warm-pool idle = both CDP AND viewer counts reach zero | Preserves login state; human 2FA keeps session alive; no explicit release call needed |
| `POST /sessions` as the canonical happy path | Minimizes Main App complexity; hides warm-pool and upsert mechanics |
| Service mints signed viewer URLs (not Main App) | No signing keys shared; service controls TTL and revocation |
| API-key / shared-secret for Main App | Single trusted consumer; OAuth over-engineered |
| Replace existing `/api/profiles/*` entirely | Clean surface area; no dual-API maintenance burden |
| Admin dashboard pivots to template management + ops | Reuses React shell; humans add vendors there; API consumers never touch template CRUD |
| PyJWT >= 2.12.1 only | `python-jose` abandoned+CVEs; raw `hmac` requires hand-rolling TTL/replay logic |
| Token delivered via URL fragment, not querystring | Fragments not logged by proxies; prevents token leakage in access logs |
| SessionManager on `app.state` as lifespan singleton | Thin orchestrator over BrowserManager; per-key locks + idle tasks |
| CDP attach counts via WS proxy try/finally | Idle detection uses proxy counts, not Playwright events |
| `vnc_viewer_url` empty until Phase 3 | Viewer JWT + WS route deferred; CDP machine API complete |

### Critical Implementation Constraints

- `asyncio.Lock` per `(vendor_type, vendor_connection_id)` + `UNIQUE` DB constraint together prevent duplicate profiles under concurrent load
- `asyncio.Semaphore(3)` on `BrowserManager.launch()` prevents thundering-herd OOM on restart
- Idle detection uses WS proxy connection counts, NOT Playwright connection events (CloakBrowser event surface not guaranteed)
- `clipboard_sync` defaults `false` everywhere; clipboard-read endpoint is viewer-token-only (not API-key)
- Admin `auth_token` cookie must be `SameSite=Strict; HttpOnly`
- `VIEWER_SECRET` and `MAIN_APP_API_KEY` must be set or service refuses to start (production mode)

### Phase 2 Execution Notes

- Pre-lookups confirmed: KasmVNC websockify binds `127.0.0.1`; cloakbrowser pinned in requirements.txt
- Commit split: `main.py` auth/CDP wiring landed in 02-05 commit (`cda70c2`), not 02-02
- Slow E2E tests (`pytest -m slow`) require real CloakBrowser; skipped in default CI run

### Pending Lookups (address at phase start)

- **Phase 3 start:** Read existing noVNC 1.4.0 client to locate `window.location.hash` extraction hook (~30 min) before writing `/viewer/*` route

### Todos

- [ ] Start Phase 3 planning: `/gsd-plan-phase 3`

### Blockers

None.

---

## Session Continuity

**Last session:** 2026-05-19 — Completed Phase 2 execute-phase (9 plans, verification passed)
**Stopped at:** Phase 2 complete; ready for Phase 3
**Resume file:** None

**What "done" looks like for this milestone:**

- `POST /sessions` with `(vendor_type, vendor_connection_id)` returns `{profile_id, cdp_url, vnc_viewer_url}` from a live warm-pooled browser
- Profiles persist login state across sleep/wake cycles
- Signed iframe viewer loads noVNC, validates token, streams VNC
- Admin dashboard shows templates + session ops list with no legacy launch UI
- Old `/api/profiles/{id}/launch` is gone

---
*State updated: 2026-05-19*
