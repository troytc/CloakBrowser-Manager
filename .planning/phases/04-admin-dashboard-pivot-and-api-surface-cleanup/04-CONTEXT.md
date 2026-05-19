# Phase 4: Admin Dashboard Pivot and API Surface Cleanup - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning
**Mode:** Auto-generated (ROADMAP + REQUIREMENTS + Phase 2/3 handoff)

<domain>
## Phase Boundary

After Phase 4:

- Admin dashboard is **ops + templates only**: Templates CRUD (Phase 1) remains; Profiles end-user UI is gone.
- **Sessions** ops page lists **every** profile row in SQLite with `vendor_type`, `vendor_connection_id`, warm-pool `state`, attach counts, `last_launched_at`, and computed uptime — not only currently running browsers.
- Clicking a **running** session row opens the existing admin VNC viewer (`ProfileViewer` → `/api/profiles/{id}/vnc` WebSocket, cookie auth). Stopped rows show state but do not offer launch-from-dashboard (profiles are created only via Main App `POST /sessions`).
- `POST /api/profiles/{id}/launch` and `POST /api/profiles/{id}/stop` are removed (404 or 410).
- Legacy admin profile CRUD that duplicates machine API is removed or narrowed: no `POST /api/profiles` create, no full-fingerprint `PUT`; admin keeps only what ops still needs (VNC WS, clipboard, optional `DELETE` for cleanup).

Out of scope: Changing machine `/sessions` or `/profiles` contracts; signed `/viewer/*` path (Phase 3); template schema changes; multi-tenant admin.

</domain>

<handoff>
## Phase 2 / 3 Handoff (executor prerequisites)

**Phase 2 (complete):**

- `GET /sessions` (machine, `X-API-Key`) returns active rows from `browser_mgr.running` only — **not** sufficient alone for ADM-02 “all profiles”.
- `SessionManager.status_envelope(profile_id)` is the source of truth for `state`, attach counts, `idle_expires_at`, `last_launched_at`.
- Admin auth remains `AuthMiddleware` on `/api/*`; machine routes exempt.

**Phase 3 (implemented locally, uncommitted per parent agent):**

- `POST /sessions` returns `vnc_viewer_url` with fragment token; `/viewer/*` for Main App embed.
- CSP, clipboard viewer-scoping, `viewer_tokens.py`, `security_csp.py`, viewer router — do **not** regress when editing `main.py` in Phase 4.
- **275 tests pass** before Phase 4 execution; re-run full suite after each plan.

**Phase 1 (complete):**

- Templates surface: `TemplateList`, `TemplateForm`, `DeleteBlockedModal`, `useTemplates`, `api.templates.*` — satisfies ADM-01 when Sessions pivot lands.

</handoff>

<decisions>
## Implementation Decisions

### Admin sessions list (ADM-02)

- **D-01:** Add **`GET /api/admin/sessions`** (admin cookie/Bearer only) in `backend/routers/admin_sessions.py`, mounted from `main.py`. Returns **all** DB profiles merged with `SessionManager.status_envelope()` — stopped profiles get `state: "stopped"`, zero counts, `last_launched_at: null` unless historical field added later.
- **D-02:** Response model `AdminSessionListItem` extends session fields with `name`, `clipboard_sync` (for `ProfileViewer`), and `uptime_seconds: int | null` (server-computed: `now - last_launched_at` when `state` is `running` or `idle`, else `null`).
- **D-03:** Do **not** expose `MAIN_APP_API_KEY` to the browser. Admin UI never calls machine `/sessions` directly.

### Sessions UI (ADM-02, ADM-03, ADM-04)

- **D-04:** New `SessionList.tsx` + `useSessions` hook (3s poll, mirror `useTemplates`). Replace sidebar `ProfileList` on the ops surface.
- **D-05:** Reuse **`ProfileViewer.tsx` unchanged** for admin VNC (`ws://host/api/profiles/{id}/vnc`). Row action “Open viewer” only enabled when `state === "running"`.
- **D-06:** App surface switcher labels: **`Sessions` | `Templates`** (remove “Profiles”). Default surface **`sessions`**. Delete `ProfileForm`, `LaunchButton`, `ProfileList` usage from `App.tsx`; keep files until Plan 04-04 confirms no imports, then delete dead components in same plan or follow-up cleanup task.
- **D-07:** No “New Profile” button, no launch/stop controls (ADM-04).

### API cleanup (OPS-01, OPS-02)

- **D-08:** Remove **`POST /api/profiles/{id}/launch`** and **`POST /api/profiles/{id}/stop`** from `main.py`; return **410 Gone** with stable JSON body if tests expect deprecation period, else **404** — planner chooses 410 for clearer ops signal.
- **D-09:** Remove **`POST /api/profiles`** (create) and **`PUT /api/profiles/{id}`** (full blueprint update). Remove **`GET /api/profiles`** list once admin sessions list exists. **Keep:** `GET /api/profiles/{id}` only if still needed for viewer metadata — prefer passing `clipboard_sync` via `AdminSessionListItem` and drop single-profile GET if unused.
- **D-10:** **Keep** admin infrastructure routes: `/api/profiles/{id}/vnc` WS, CDP proxy paths, clipboard POST/GET (admin cookie), `DELETE /api/profiles/{id}` for ops cleanup (optional in UI but keep API).
- **D-11:** Legacy removal is **last plan (04-04)** after new Sessions UI is wired and smoke-tested.

### Templates (ADM-01)

- **D-12:** No new template features in Phase 4. Plan 04-03 includes a verification checklist that Phase 1 template UI still works after App pivot.

### Claude's Discretion

- Table vs card layout for `SessionList` — follow `TemplateList` table pattern for density.
- Whether to expose profile `DELETE` in Sessions UI — optional; API may remain without UI button.
- Sort order: default `last_launched_at` desc, then `vendor_type` asc.

</decisions>

<code_context>
## Existing Code Insights

| Area | Location | Notes |
|------|----------|-------|
| Legacy launch | `backend/main.py` ~628–658 | `launch_profile`, `stop_profile` — remove in 04-04 |
| Legacy admin CRUD | `backend/main.py` ~541–622 | list/create/put/delete — narrow in 04-04 |
| Admin VNC | `backend/main.py` ~939, `ProfileViewer.tsx` ~36 | `wsUrl` uses `/api/profiles/{id}/vnc` |
| Machine sessions list | `backend/routers/sessions.py` `list_sessions` | Running-only; pattern for envelope merge |
| Templates UI | `frontend/src/components/Template*.tsx`, `App.tsx` surface switcher | ADM-01 done |
| Profiles UI (remove) | `ProfileList`, `ProfileForm`, `LaunchButton`, `useProfiles` launch/create | ADM-04 |

</code_context>

<requirements>
## Requirements This Phase Closes

| ID | Summary |
|----|---------|
| ADM-01 | Templates page — already shipped Phase 1; verify after pivot |
| ADM-02 | Sessions ops list with vendor identity + warm-pool telemetry |
| ADM-03 | Row opens admin VNC viewer |
| ADM-04 | Remove end-user profile creation / Launch UI |
| OPS-01 | Remove launch/stop REST endpoints |
| OPS-02 | Replace legacy `/api/profiles/*` CRUD with machine API + admin ops shim |

</requirements>

<success_criteria>
## Phase Success Criteria (from ROADMAP)

1. Templates + Sessions ops pages live; sessions show vendor pair, state, attach counts, uptime, last-launched-at.
2. Running session → admin VNC viewer works.
3. No profile create form, no Launch button.
4. Launch/stop endpoints gone; legacy admin profile CRUD removed per D-09/D-10.

</success_criteria>
