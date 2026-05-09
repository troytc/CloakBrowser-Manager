---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 01
current_plan: 1
status: executing
last_updated: "2026-05-09T02:47:45.536Z"
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 8
  completed_plans: 6
  percent: 75
---

# Project State: CloakBrowser-Manager

**Milestone:** Warm-pool / Templates / Signed-Viewer
**Initialized:** 2026-04-22
**Last updated:** 2026-04-22

---

## Project Reference

**Core Value:** One idempotent API call gives the Main App a live CDP URL + a scoped iframe viewer URL for a vendor-specific browser profile, with session state preserved across automation runs via a warm pool.

**Codebase baseline:** v0.0.7 (2026-04-22) — brownfield refocus. Chromium lifecycle, VNC pipeline, SQLite, Docker, admin auth, React shell all validated and intact. Building on top.

**One sentence:** `POST /sessions` with `(vendor_type, vendor_connection_id)` → `{profile_id, cdp_url, vnc_viewer_url}`.

---

## Current Position

Phase: 01 (schema-templates-and-security-foundations) — EXECUTING
Plan: 1 of 6
**Current phase:** 01
**Current plan:** 1
**Status:** Ready to execute

**Progress:**

```
[Phase 1] [Phase 2] [Phase 3] [Phase 4]
  [ ]        [ ]       [ ]       [ ]
  0%         -         -         -
```

---

## Phase Summary

| # | Name | Requirements | Status |
|---|------|-------------|--------|
| 1 | Schema, Templates, and Security Foundations | 10 | Not started |
| 2 | Sessions, Warm-Pool, and CDP Lifecycle | 19 | Not started |
| 3 | Signed Viewer URLs and Security Hardening | 13 | Not started |
| 4 | Admin Dashboard Pivot and API Surface Cleanup | 6 | Not started |

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases total | 4 |
| Requirements total | 48 |
| Requirements complete | 0 |
| Plans created | 0 |
| Plans complete | 0 |

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

### Critical Implementation Constraints

- `asyncio.Lock` per `(vendor_type, vendor_connection_id)` + `UNIQUE` DB constraint together prevent duplicate profiles under concurrent load
- `asyncio.Semaphore(3)` on `BrowserManager.launch()` prevents thundering-herd OOM on restart
- Idle detection uses WS proxy connection counts, NOT Playwright connection events (CloakBrowser event surface not guaranteed)
- `clipboard_sync` defaults `false` everywhere; clipboard-read endpoint is viewer-token-only (not API-key)
- Admin `auth_token` cookie must be `SameSite=Strict; HttpOnly`
- `VIEWER_SECRET` and `MAIN_APP_API_KEY` must be set or service refuses to start (production mode)

### Parallelization Opportunities

- `viewer_tokens.py` (pure module) can start during Phase 1 — no schema dependencies
- React `TemplateList.tsx` / `TemplateForm.tsx` can start against mock API once Pydantic models are defined (Phase 1)
- `SessionList.tsx` can start once `GET /sessions` exists (Phase 2)

### Pending Lookups (address at phase start)

- **Phase 3 start:** Read existing noVNC 1.4.0 client to locate `window.location.hash` extraction hook (~30 min) before writing `/viewer/*` route
- **Phase 2 start:** Confirm KasmVNC websockify binds to `127.0.0.1` not `0.0.0.0` in `VNCManager`
- **Phase 2 start:** Confirm `Dockerfile` CloakBrowser version is pinned (not floating tag) — lock before warm-pool sleep/wake testing

### Todos

- [ ] Start Phase 1 planning: `/gsd-plan-phase 1`

### Blockers

None.

---

## Session Continuity

**How to resume:** Read this file, then `ROADMAP.md` for phase details, then `REQUIREMENTS.md` for the full requirement list with traceability.

**What "done" looks like for this milestone:**

- `POST /sessions` with `(vendor_type, vendor_connection_id)` returns `{profile_id, cdp_url, vnc_viewer_url}` from a live warm-pooled browser
- Profiles persist login state across sleep/wake cycles
- Signed iframe viewer loads noVNC, validates token, streams VNC
- Admin dashboard shows templates + session ops list with no legacy launch UI
- Old `/api/profiles/{id}/launch` is gone

---
*State initialized: 2026-04-22*
