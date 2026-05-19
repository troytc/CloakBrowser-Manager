# Roadmap: VendorBrowser

**Milestone:** Warm-pool / Templates / Signed-Viewer
**Created:** 2026-04-22
**Granularity:** Coarse (4 phases)
**Coverage:** 48/48 v1 requirements

---

## Phases

- [x] **Phase 1: Schema, Templates, and Security Foundations** — `vendor_templates` table, template CRUD API and admin UI, clipboard default flip, Docker UID fix, env var scaffolding (completed 2026-05-19)
- [x] **Phase 2: Sessions, Warm-Pool, and CDP Lifecycle** — `SessionManager`, dual-signal idle detection, `POST /sessions`, profile CRUD, concurrency guards, API-key auth on machine routes (completed 2026-05-19)
- [ ] **Phase 3: Signed Viewer URLs and Security Hardening** — `/viewer/*` WS route, JWT minting via PyJWT, fragment-token delivery, JTI registry, CSP, admin cookie hardening, clipboard viewer-scoping
- [ ] **Phase 4: Admin Dashboard Pivot and API Surface Cleanup** — `SessionList.tsx` + `TemplateList/Form` pivoted to ops use, old `/api/profiles/{id}/launch` removed, final API surface cleanup

---

## Phase Details

### Phase 1: Schema, Templates, and Security Foundations

**Goal**: Operators can manage vendor templates via the admin dashboard, and the foundational schema, env vars, and security defaults are in place for all subsequent phases.

**Depends on**: Nothing — this is the foundation.

**Requirements**: TMPL-01, TMPL-02, TMPL-03, TMPL-04, TMPL-05, SEC-05, SEC-06, OPS-03, OPS-04, OPS-05

**Success Criteria** (what must be TRUE):
  1. An admin can open the dashboard, navigate to Templates, and create/edit/delete a vendor template with all blueprint fields (fingerprint_seed, timezone, locale, platform, screen dims, gpu, humanize, launch_args, clipboard_sync, proxy); duplicates on `vendor_type` are rejected with a clear error.
  2. Deleting a template with existing profiles is blocked by the service with a descriptive error; deleting one with no profiles succeeds.
  3. A profile created from a template inherits all template fields as a snapshot; updating the template afterward does not change the profile row.
  4. The service refuses to start when `VIEWER_SECRET` or `MAIN_APP_API_KEY` is absent or blank (production mode); `.env.example` documents all new required vars.
  5. After a container recreate on a volume with a UID mismatch, Chromium can flush its cookie database without permission errors (Docker entrypoint `chown` runs before service start).

**Plans**: 6 plans

Plans:
- [x] 01-01-PLAN.md — Schema migration, template Pydantic models, clipboard_sync flip, PyJWT dep
- [x] 01-02-PLAN.md — Docker entrypoint chown + env var scaffolding (docker-compose.yml, .env.example)
- [x] 01-03-PLAN.md — Fail-closed startup check for MAIN_APP_API_KEY and VIEWER_SECRET
- [x] 01-04-PLAN.md — Template CRUD router (/api/templates) with two-layer delete guard
- [x] 01-05-PLAN.md — Frontend API types + useTemplates polling hook with 409 delete-blocked state
- [x] 01-06-PLAN.md — TemplateList / TemplateForm / DeleteBlockedModal components + App.tsx surface switcher

**UI hint**: yes

**Parallelization notes**:
- `viewer_tokens.py` (pure module, no Phase 1 dependencies) can be written in parallel with Phase 1 work — it has no imports from the schema or CRUD layer and is needed in Phase 3.
- React `TemplateList.tsx` and `TemplateForm.tsx` can start against mock API responses once Pydantic models are defined; backend and frontend can develop in parallel.
- `clipboard_sync` default flip and Docker entrypoint fix are small, independent tasks that can be done first in the phase.

---

### Phase 2: Sessions, Warm-Pool, and CDP Lifecycle

**Goal**: The Main App can call `POST /sessions` with `(vendor_type, vendor_connection_id)` and reliably receive a live CDP URL and session state, with profiles staying warm across automation runs and sleeping safely when idle.

**Depends on**: Phase 1 (templates must exist before sessions can upsert profiles; schema must be in place).

**Requirements**: SESS-01, SESS-02, SESS-03, SESS-04, SESS-05, SESS-06, SESS-07, SESS-08, SESS-09, SESS-10, SESS-11, SESS-12, SESS-13, SESS-14, PROF-01, PROF-02, PROF-03, PROF-04, SEC-01

**Success Criteria** (what must be TRUE):
  1. `POST /sessions` with a valid API key and a known `vendor_type` returns `{profile_id, cdp_url, state}` (with `vnc_viewer_url` placeholder accepted as empty until Phase 3); repeated calls for the same `(vendor_type, vendor_connection_id)` return the same `profile_id` — no duplicate profile rows, even under 10 simultaneous concurrent requests.
  2. A profile that has been idle for longer than `IDLE_TIMEOUT_SECONDS` transitions to `STOPPED`; a subsequent `POST /sessions` wakes it and returns a live CDP URL — the on-disk Chromium profile directory (cookies, localStorage) is intact after the sleep/wake cycle.
  3. `GET /sessions/{profile_id}` returns `{state, cdp_attach_count, viewer_attach_count, idle_expires_at, last_launched_at}`; `DELETE /sessions/{profile_id}` tears down the browser without removing the profile row.
  4. `GET /profiles?vendor_type=X&vendor_connection_id=Y` returns the matching profile; `DELETE /profiles/{id}` stops the session and removes the on-disk directory; all machine routes return 401 to callers without a valid `MAIN_APP_API_KEY`.
  5. After a service restart, all profiles start `STOPPED` with zero attach counts; no profiles auto-wake; the first `POST /sessions` after restart successfully wakes a profile within the launch timeout.

**Plans**: 9 plans

Plans:
- [x] 02-01-PLAN.md — Wave 1: BrowserManager hardening (Semaphore(3), about:blank probe, _stop_locked refactor, RunningProfile extension)
- [x] 02-02-PLAN.md — Wave 1: APIKeyHeader auth (require_api_key) + AuthMiddleware /sessions /profiles exemption + CDP WS X-API-Key check
- [x] 02-03-PLAN.md — Wave 1: upsert_profile_by_vendor() + list_profiles_filtered() + NoTemplateError in database.py
- [x] 02-04-PLAN.md — Wave 2: SessionManager keystone (per-key locks, idle task lifecycle, get_or_wake)
- [x] 02-05-PLAN.md — Wave 2: FastAPI lifespan SessionManager wiring + CDP WS try/finally count mutations
- [x] 02-06-PLAN.md — Wave 1: Pydantic models — SessionRequest/Response/StatusResponse/ListItem, ProfilePatch, MachineProfileResponse
- [x] 02-07-PLAN.md — Wave 3: backend/routers/sessions.py — POST/GET/DELETE /sessions + integration tests including SESS-07 race regression
- [x] 02-08-PLAN.md — Wave 4: backend/routers/profiles.py — GET/PATCH/DELETE /profiles + integration tests
- [x] 02-09-PLAN.md — Wave 5: pytest slow marker + test_warm_pool_e2e.py (sleep/wake state persistence + restart safety)

**Parallelization notes**:
- `SessionList.tsx` (Phase 4 frontend) can begin development once `GET /sessions` exists — it is purely additive React work.
- Profile CRUD endpoints (PROF-01..04) and sessions endpoints can be developed on the same `sessions_router` pass; they share the same `APIKeyMiddleware` guard.
- `asyncio.Semaphore(3)` and per-key `asyncio.Lock` are small independent additions during `SessionManager` construction — add them at the same time as the upsert logic, not as a follow-up.

---

### Phase 3: Signed Viewer URLs and Security Hardening

**Goal**: `POST /sessions` returns a usable signed `vnc_viewer_url`; the iframe viewer enforces token validation, JTI single-use, and CSP; admin cookies and clipboard access are hardened against cross-surface exploitation.

**Depends on**: Phase 2 (`viewer_attach_count` on `RunningProfile` must exist before the viewer WS route can drive it; `POST /sessions` must be live to wire in token minting).

**Requirements**: VIEW-01, VIEW-02, VIEW-03, VIEW-04, VIEW-05, VIEW-06, VIEW-07, VIEW-08, VIEW-09, SEC-02, SEC-03, SEC-04, SEC-07

**Success Criteria** (what must be TRUE):
  1. `POST /sessions` returns a `vnc_viewer_url` of the form `/viewer/{profile_id}#token=<jwt>`; the JWT is signed with `VIEWER_SECRET` via HS256 and carries `{profile_id, exp, jti, iat}`; a second call returns a fresh token with a new `jti`.
  2. A valid `vnc_viewer_url` embedded in an iframe on the Main App origin loads the noVNC viewer and streams VNC frames; the same URL used a second time (token replay) is rejected with a `4401` close code.
  3. An expired token is rejected with `4401`; a token for the wrong `profile_id` is rejected; an unsigned/tampered token is rejected — in all cases without revealing which check failed.
  4. All viewer endpoint responses carry `Content-Security-Policy: frame-ancestors <MAIN_APP_ORIGIN>`; all `/admin/*` API responses carry `frame-ancestors 'none'`; the admin `auth_token` cookie is set `SameSite=Strict; HttpOnly`.
  5. `GET /profiles/{id}/clipboard` returns 403 when authenticated only by the Main App API key; it succeeds only when the request carries a valid viewer-scoped signed token.

**Plans:** 4 plans in 4 waves

Plans:
- [ ] 03-01-PLAN.md — viewer_tokens module (PyJWT mint/validate/JTI registry) [Wave 1]
- [ ] 03-02-PLAN.md — CSP hardening, clipboard viewer-scoping, SEC-03 verify [Wave 2]
- [ ] 03-03-PLAN.md — VNC core extract, viewer HTML/WS routes, WS tests [Wave 3]
- [ ] 03-04-PLAN.md — Wire vnc_viewer_url on POST /sessions + E2E checkpoint [Wave 4]

**Cross-cutting constraints:**
- Viewer tokens travel in URL fragment only (`#token=`), never in iframe `src` querystring
- JTI single-use consumed before VNC proxy starts
- Admin auth (`/api/*`) and machine auth (`/sessions`, `/profiles`) remain strictly segregated

**UI hint**: yes (`03-UI-SPEC.md` — embed viewer page)

**Parallelization notes**:
- `viewer_tokens.py` (pure module started optionally in Phase 1) is finalized and wired in here; if not started earlier, it is written at Phase 3 start.
- CSP header changes and `SameSite=Strict` cookie fix (SEC-02, SEC-03, SEC-04) are independent of the WS route work and can land on the same PR or a separate one.
- At Phase 3 start: 30-minute read of the existing noVNC client to locate the `window.location.hash` extraction hook before any implementation (as flagged in SUMMARY.md).

---

### Phase 4: Admin Dashboard Pivot and API Surface Cleanup

**Goal**: The admin dashboard is fully pivoted to ops-and-templates use; the old `/api/profiles/{id}/launch` surface is gone; the API contract is clean with no legacy endpoints surviving.

**Depends on**: Phase 3 (all machine API and viewer security must be proven before the old surface is removed; frontend pivot builds on Phase 2's sessions list endpoint and Phase 1's templates endpoint).

**Requirements**: ADM-01, ADM-02, ADM-03, ADM-04, OPS-01, OPS-02

**Success Criteria** (what must be TRUE):
  1. The admin dashboard shows a Templates page with list, create, edit, and delete; a Sessions/Profiles ops page showing `vendor_type`, `vendor_connection_id`, `state`, `cdp_attach_count`, `viewer_attach_count`, uptime, and last-launched-at for every profile.
  2. Each session row in the ops view opens a live admin-authenticated VNC viewer (using the existing `/api/profiles/{id}/vnc` admin route — not the signed-token path); the viewer is functional.
  3. The old end-user profile-creation UI (direct field entry, Launch button) is absent from the dashboard; there is no UI path to create a profile other than via template-driven `POST /sessions`.
  4. `POST /api/profiles/{id}/launch` and `POST /api/profiles/{id}/stop` return 404 or 410; the old `/api/profiles/*` CRUD surface (direct field creation) is replaced by the new machine API surface.

**Plans**: TBD

**UI hint**: yes

**Parallelization notes**:
- `SessionList.tsx` can be completed in parallel with the backend OPS-01/OPS-02 removal work once Phase 2 sessions endpoints are live — it has no Phase 3 dependencies.
- `TemplateList.tsx` and `TemplateForm.tsx` (started in Phase 1) should be finalized here if not already complete.
- Old route removal (OPS-01, OPS-02) is the last step within Phase 4 — complete and smoke-test the new surface first, then remove the old endpoints.

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema, Templates, and Security Foundations | 8/8 | Complete    | 2026-05-19 |
| 2. Sessions, Warm-Pool, and CDP Lifecycle | 0/9 | Not started | - |
| 3. Signed Viewer URLs and Security Hardening | 0/? | Not started | - |
| 4. Admin Dashboard Pivot and API Surface Cleanup | 0/? | Not started | - |

---

## Coverage Map

| Phase | Requirements |
|-------|-------------|
| Phase 1 | TMPL-01, TMPL-02, TMPL-03, TMPL-04, TMPL-05, SEC-05, SEC-06, OPS-03, OPS-04, OPS-05 |
| Phase 2 | SESS-01, SESS-02, SESS-03, SESS-04, SESS-05, SESS-06, SESS-07, SESS-08, SESS-09, SESS-10, SESS-11, SESS-12, SESS-13, SESS-14, PROF-01, PROF-02, PROF-03, PROF-04, SEC-01 |
| Phase 3 | VIEW-01, VIEW-02, VIEW-03, VIEW-04, VIEW-05, VIEW-06, VIEW-07, VIEW-08, VIEW-09, SEC-02, SEC-03, SEC-04, SEC-07 |
| Phase 4 | ADM-01, ADM-02, ADM-03, ADM-04, OPS-01, OPS-02 |

**Total: 48/48 requirements mapped. No orphans.**

---

## Dependency Graph

```
Phase 1: vendor_templates schema + template CRUD + clipboard default + Docker UID + env vars
    |
    +--parallel--> viewer_tokens.py (pure module, no Phase 1 deps — optional early start)
    |
    └──unblocks──> Phase 2: SessionManager + warm-pool + POST /sessions + profile CRUD + API-key auth
                       |
                       +--parallel--> SessionList.tsx (React, starts once GET /sessions exists)
                       |
                       └──unblocks──> Phase 3: /viewer/* WS + signed tokens + JTI registry + CSP hardening
                                          |
                                          └──unblocks──> Phase 4: Admin pivot + old surface removal
```

---

## Key Implementation Notes

**Riskiest piece:** Dual-signal idle detection (`SESS-04` through `SESS-06`) — no commercial analog. Idle fires only when BOTH `cdp_attach_count == 0` AND `viewer_attach_count == 0`. Use `asyncio.Task` per profile in `SessionManager._idle_tasks`; cancel on any attach event. Do NOT use Playwright connection events — count at the WS proxy layer only.

**Hard dependency order within Phase 2:** `vendor_templates` schema (Phase 1) → `upsert_profile_by_vendor()` → `SessionManager` → sessions router. Do not wire up the router until the upsert logic has DB-level `UNIQUE(vendor_type, vendor_connection_id)` enforcement.

**noVNC fragment hook:** At Phase 3 start, read the existing noVNC 1.4.0 client to locate where `window.location.hash` extraction should be injected before writing any `/viewer/*` route code (estimated 30 minutes; flagged in research as a required first step).

**One new dependency only:** `PyJWT >= 2.12.1` for viewer token signing. Do not use `python-jose` (abandoned, CVEs) or raw `hmac` (requires hand-rolling TTL/replay logic). Add to `requirements.txt` in Phase 1 alongside env var scaffolding.

---
*Roadmap created: 2026-04-22*
*Next: `/gsd-plan-phase 1`*
