# Phase 1: Schema, Templates, and Security Foundations - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Foundational layer that unblocks every subsequent phase. Delivers: (1) `vendor_templates` SQLite table + `vendor_type`/`vendor_connection_id`/`template_id` columns on `profiles` with a `UNIQUE(vendor_type, vendor_connection_id)` constraint; (2) template CRUD API (admin-auth) and a functional admin Templates UI; (3) `clipboard_sync` default flipped to `false`; (4) Docker entrypoint `chown` fix (OPS-04); (5) env var scaffolding (`MAIN_APP_API_KEY`, `VIEWER_SECRET`, `MAIN_APP_ORIGIN`, `IDLE_TIMEOUT_SECONDS`, `VIEWER_TOKEN_TTL_SECS`) with production fail-closed; (6) `PyJWT >= 2.12.1` added to `requirements.txt` (consumed in Phase 3).

Out of scope for this phase: `SessionManager`, `POST /sessions`, warm-pool lifecycle, `/viewer/*`, API-key auth middleware wiring, signed token minting — all move to Phase 2 / 3. Phase 4 pivots the broader admin nav; Phase 1 just adds a Templates entry alongside existing Profiles.

</domain>

<decisions>
## Implementation Decisions

### Schema

- **D-01:** `vendor_templates` table shape — `id TEXT PRIMARY KEY, vendor_type TEXT UNIQUE NOT NULL, label TEXT, notes TEXT, blueprint TEXT NOT NULL (JSON), created_at TEXT, updated_at TEXT`. Blueprint is a single JSON column (research-recommended; normalizing gains nothing at ~15 fields).
- **D-02:** Blueprint JSON field list mirrors TMPL-01 exactly — `timezone`, `locale`, `platform`, `screen_width`, `screen_height`, `gpu_vendor`, `gpu_renderer`, `hardware_concurrency`, `humanize`, `human_preset`, `launch_args`, `clipboard_sync`, `proxy`, plus optional `color_scheme` and `user_agent` overrides. No `fingerprint_seed` value in the blueprint (see D-04).
- **D-03:** Profile row IS the snapshot. `profiles` extends with `vendor_type TEXT NOT NULL`, `vendor_connection_id TEXT NOT NULL`, `template_id TEXT NOT NULL REFERENCES vendor_templates(id) ON DELETE RESTRICT`. Existing normalized columns (fingerprint_seed, timezone, locale, platform, screen_*, gpu_*, humanize, human_preset, launch_args, clipboard_sync, proxy) are populated from template.blueprint at upsert time and never re-read (TMPL-05). No separate `template_snapshot` JSON column.
- **D-04:** `fingerprint_seed` is generated randomly per profile at creation (matches existing `create_profile` behavior, random 10000–99999). Templates do **not** carry a fixed seed. Each `(vendor_type, vendor_connection_id)` gets an identity-unique fingerprint — critical anti-detection posture (Pitfall 7).
- **D-05:** `UNIQUE(vendor_type, vendor_connection_id)` constraint on `profiles` added as a DB-level guarantee from day one (Pitfall 2 hard safety net). App-layer upsert pattern (`INSERT OR IGNORE` + `SELECT`) is Phase 2's responsibility.
- **D-06:** Template delete (TMPL-04) is guarded in **both** layers: app-layer check returns `HTTP 409` with a clear message enumerating blocking profiles; `FK ON DELETE RESTRICT` on `profiles.template_id` is the DB-level safety net. Both must pass — belt and suspenders.

### Migration

- **D-07:** Unconditional wipe on detection of old schema. `init_db()` checks whether `profiles.vendor_type` column exists; if not, it (a) deletes every row in `profiles` and `profile_tags`, (b) deletes corresponding `/data/profiles/{id}` directories on disk, (c) then runs `ALTER TABLE` / new column additions. Idempotent: a re-run against the already-migrated DB is a no-op.
- **D-08:** No safety flag required. Old schema == dev/test data pre-refocus (no production deployment with the new shape exists yet). Migration logs the count of rows and directories wiped.
- **D-09:** `profile_tags` is preserved as a table (schema-wise) but its rows are dropped alongside wiped profiles. Tags are not part of the vendor_template model; they stay a profile-level admin convenience.

### Admin Templates UI

- **D-10:** Functional MVP scope in Phase 1: `TemplateList.tsx` (table with `vendor_type`, `label`, `created_at`, edit/delete actions) + `TemplateForm.tsx` (section-grouped create/edit form). No search, no sort, no inline edit, no bulk actions. Phase 4 polishes.
- **D-11:** Form is grouped into sections mirroring the existing `ProfileForm` layout: Identity (`vendor_type`, `label`, `notes`) / Fingerprint (`timezone`, `locale`, `platform`) / Screen (`screen_width`, `screen_height`, `color_scheme`) / GPU (`gpu_vendor`, `gpu_renderer`, `hardware_concurrency`) / Behavior (`humanize`, `human_preset`, `launch_args`) / Proxy (`proxy`) / Security (`clipboard_sync` toggle defaulting `false` with an amber warning badge explaining the credential-leak risk).
- **D-12:** Templates is a new top-level nav entry in `App.tsx` alongside the existing Profiles surface. Existing profile CRUD UI survives Phase 1 intact (it's removed in Phase 4). No navigation redesign here.
- **D-13:** Error surfacing: 409 on delete-blocked returns a list of offending profile IDs; UI shows a modal listing them with a "copy to clipboard" helper. Inline field-level Pydantic validation errors render beside the field (matches existing ProfileForm pattern).

### Docker / OPS

- **D-14:** `chown -R ${CHROME_UID}:${CHROME_UID} /data/profiles` added to `entrypoint.sh` **before** stale-process kill / singleton cleanup / uvicorn exec. `CHROME_UID` defaults to `0` (root) via `CHROME_UID=${CHROME_UID:-0}`. No `USER` directive in `Dockerfile`; service continues to run as root (acceptable for a single-host private-network service). Future switch to USER 1000 only requires flipping the env default.
- **D-15:** `docker-compose.yml` gains all new env var declarations (`MAIN_APP_API_KEY`, `VIEWER_SECRET`, `MAIN_APP_ORIGIN`, `IDLE_TIMEOUT_SECONDS`, `VIEWER_TOKEN_TTL_SECS`) with explicit unset defaults so missing-vars behavior triggers correctly. Existing `AUTH_TOKEN` declaration stays.
- **D-16:** `.env.example` is created (does not currently exist) documenting every env var with a one-line description and a sample value. This is a new file tracked in git.

### Security Foundations

- **D-17:** Production-mode enforcement: fail-closed default. Startup checks `VIEWER_SECRET` and `MAIN_APP_API_KEY`. If either is unset or empty, service refuses to start with a clear error naming the missing vars. `DEV_MODE=1` opt-out allows missing vars and logs a WARNING on every request that an unauthenticated fallback is active. No `ENV=production` flag — enforcement is the default, not a posture toggle.
- **D-18:** `clipboard_sync` default flipped to `false`: schema `BOOLEAN DEFAULT 0`, Pydantic `ProfileCreate.clipboard_sync: bool = False`, `ProfileResponse.clipboard_sync: bool = False`, `create_profile` fallback `fields.get("clipboard_sync", False)`. Blueprint JSON default is also `false`. Every touchpoint must flip; no partial change.
- **D-19:** `PyJWT >= 2.12.1` added to `backend/requirements.txt` in Phase 1 even though it is consumed in Phase 3. Lets the viewer-token module be written in parallel (Parallelization note in ROADMAP).

### Claude's Discretion

- `updated_at` column on `vendor_templates` is refreshed by app code on every update (no SQLite trigger).
- `TemplateList.tsx` polling interval matches the existing `useProfiles.ts` (3s) to share muscle memory, unless it would cause UI jank.
- 409 `delete blocked` response shape: `{detail: "...", blocking_profile_ids: [...]}` — standard FastAPI pattern.
- Inline-vs-modal editing is modal for now (matches existing ProfileForm), but optional Phase 4 refinement.
- Dev-mode warning copy: `"⚠ DEV_MODE=1: VIEWER_SECRET and/or MAIN_APP_API_KEY not set. Authentication is bypassed. Do not use in production."` logged once at startup + per-request debug log.
- Tailwind design tokens: reuse existing `globals.css` palette; no new colors.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope & requirements

- `.planning/PROJECT.md` — Milestone scope, constraints, Key Decisions table (locked).
- `.planning/REQUIREMENTS.md` — Phase 1 requirement set: TMPL-01..05, SEC-05, SEC-06, OPS-03, OPS-04, OPS-05.
- `.planning/ROADMAP.md` §"Phase 1: Schema, Templates, and Security Foundations" — Goal, success criteria, parallelization notes.
- `.planning/STATE.md` — Locked decisions and critical implementation constraints carried into planning.

### Research (prescriptive)

- `.planning/research/SUMMARY.md` §"Recommended Stack" + §"Phase 1" — build order, stack recommendations, security rules.
- `.planning/research/STACK.md` — PyJWT version, `APIKeyHeader` pattern, SQLite JSON column rationale.
- `.planning/research/PITFALLS.md` — Pitfall 2 (concurrent upsert race → `UNIQUE` constraint), Pitfall 7 (fingerprint inconsistency → snapshot-at-creation + binary pinning), Pitfall 10 (Docker UID mismatch → entrypoint chown), Pitfall 11 (clipboard credential leak → default `false`, viewer-scoped read).
- `.planning/research/FEATURES.md` §"Vendor Template CRUD" + §"Must have" — Template-to-Profile inheritance, anti-features.
- `.planning/research/ARCHITECTURE.md` §"Major components" — where `SessionManager` / `viewer_tokens.py` sit (referenced only; not built here).

### Codebase (existing patterns)

- `.planning/codebase/STRUCTURE.md` — directory layout, naming conventions, "Where to add new code" recipes.
- `.planning/codebase/CONVENTIONS.md` — Python/TypeScript style, FastAPI route patterns.
- `.planning/codebase/ARCHITECTURE.md` — `backend/main.py` middleware stack, `AuthMiddleware` exemption list pattern.
- `.planning/codebase/INTEGRATIONS.md` — CloakBrowser / Playwright / KasmVNC integration seams.
- `backend/database.py` — existing `init_db()` migration pattern (ALTER TABLE for column adds), `create_profile` helper to extend.
- `backend/models.py` — existing Pydantic patterns to mirror for `VendorTemplateCreate` / `VendorTemplateUpdate` / `VendorTemplateResponse`.
- `frontend/src/components/ProfileForm.tsx` — section-grouped form layout to mirror in `TemplateForm.tsx`.
- `frontend/src/hooks/useProfiles.ts` — polling hook pattern to mirror in `useTemplates.ts`.
- `entrypoint.sh` — existing startup sequence; chown insertion point is before stale-process kill.

### Top-level config

- `Dockerfile` — multi-stage build; `entrypoint.sh` invocation; no current USER directive.
- `docker-compose.yml` — existing env var declaration shape (only `AUTH_TOKEN` today).
- `CLAUDE.md` (repo root) — security rules, architecture invariants, brownfield reality; re-read before edits.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`backend/database.py::init_db()`** — Add `vendor_templates` `CREATE TABLE` + `ALTER TABLE profiles ADD COLUMN` migrations inline. Extend existing `cols` detection pattern. The wipe logic for D-07 slots in as a pre-migration step when `vendor_type` column is absent.
- **`backend/database.py::create_profile()`** — Extend to accept `vendor_type`, `vendor_connection_id`, `template_id` + pull field defaults from a template blueprint dict rather than `**fields`. Keep existing signature for any residual test usage; add a new `create_profile_from_template()` helper.
- **`backend/models.py`** — Add `VendorTemplateCreate`, `VendorTemplateUpdate`, `VendorTemplateResponse`, `TemplateBlueprint` Pydantic models. Mirror existing `ProfileCreate`/`ProfileUpdate` patterns (`field_validator` for defaults, `Literal` for enums).
- **`backend/main.py` AuthMiddleware** — Existing exemption list pattern. Template admin CRUD routes stay behind `AuthMiddleware` (admin auth). **Do not** add exemptions for `/api/templates/*`.
- **`frontend/src/components/ProfileForm.tsx`** — Section-grouped form layout, Tailwind patterns, validation UX. Copy the shape for `TemplateForm.tsx`.
- **`frontend/src/hooks/useProfiles.ts`** — Polling hook (3s interval), CRUD action surface. Copy shape for `useTemplates.ts`.
- **`frontend/src/lib/api.ts`** — Typed fetch client. Add `api.templates.*` functions matching the existing `api.profiles.*` shape.
- **`entrypoint.sh`** — Existing singleton lock cleanup and stale-process kill. Add `chown` step at the top; existing cleanup already handles SingletonLock/SingletonCookie/SingletonSocket.

### Established Patterns

- **SQLite migrations** live in `init_db()` via `PRAGMA table_info` + conditional `ALTER TABLE`. Follow this pattern, not Alembic.
- **No async DB layer** — raw `sqlite3` in a contextmanager. Keep it that way (research flagged `aiosqlite` as out of scope).
- **Pydantic v2** — use `field_validator` for defaults on optional bool fields (see existing `coerce_clipboard_sync`).
- **Route handlers in `main.py`** are large. The plan should put new template routes in `backend/routers/templates.py` (new directory) to avoid bloating `main.py` further. CLAUDE.md explicitly directs this.
- **React nav** — `App.tsx` dispatches on a `view` state; add a `"templates"` view alongside existing `"empty" | "create" | "edit" | "view"`.
- **Tailwind tokens** — `frontend/src/styles/globals.css` holds custom color vars; reuse.

### Integration Points

- `backend/main.py` — register new `templates_router` under `/api/templates` behind existing `AuthMiddleware` (no exemption). Mount point near existing profile routes.
- `backend/database.py::init_db()` — single entry point for schema migrations; all changes land here.
- `frontend/src/App.tsx` — add `"templates"` to the `view` union and a nav entry alongside Profiles.
- `entrypoint.sh` — single file for startup sequence; add chown + env var validation (fail-closed startup check) here or delegate to a Python startup hook in `backend/main.py`'s lifespan.
- `docker-compose.yml` — single file for env var declarations; `.env.example` is a new sibling.

</code_context>

<specifics>
## Specific Ideas

- Blueprint form's security section surfaces a visible amber warning next to the `clipboard_sync` toggle — operators should see *why* flipping it on is risky (Pitfall 11 summary in one sentence).
- Template delete error lists the *specific* blocking profile IDs in the 409 response body and in the UI modal — operators should know exactly what they have to clean up before a delete can succeed.
- Migration logs the count of wiped rows + wiped directories on service startup so the one-time wipe is visible in ops logs, not silent.
- Nav ordering: "Profiles" (existing) first, "Templates" (new) second during Phase 1. Phase 4 reorders.
- Dev-mode warning is loud (startup log + per-request debug line) — operators running locally should never wonder "is auth on right now?".

</specifics>

<deferred>
## Deferred Ideas

- **`is_active` soft-disable on templates (GOV-01)** — v2. Phase 1 enforces hard delete-block only.
- **Per-template `idle_timeout_minutes` override (SAFE-03)** — v2. Phase 1 has no warm-pool, and global `IDLE_TIMEOUT_SECONDS` env var covers v1.
- **Template inheritance chains** — explicitly anti-feature (out of scope, per PROJECT.md).
- **Admin UI polish (search, sort, bulk actions)** — Phase 4.
- **Navigation redesign** — Phase 4 pivots the dashboard; Phase 1 only adds a nav entry.
- **USER 1000 switch in Dockerfile** — future hardening; Phase 1 keeps root with chown. Flip `CHROME_UID` env default + add USER directive when needed.
- **CSRF tokens on admin mutating routes** — Phase 3 handles admin cookie hardening (`SameSite=Strict`, `frame-ancestors`); explicit CSRF tokens not in v1 (research considers `SameSite=Strict` sufficient).

</deferred>

---

*Phase: 01-schema-templates-and-security-foundations*
*Context gathered: 2026-04-22*
