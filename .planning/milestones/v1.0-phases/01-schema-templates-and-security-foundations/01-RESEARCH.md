# Phase 1: Schema, Templates, and Security Foundations — Research

**Researched:** 2026-04-22
**Domain:** SQLite schema migration + Pydantic v2 CRUD + Docker OPS hardening + React admin UI
**Confidence:** HIGH (CONTEXT.md locks every major decision; research fills in the HOW)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema**

- **D-01:** `vendor_templates` table shape — `id TEXT PRIMARY KEY, vendor_type TEXT UNIQUE NOT NULL, label TEXT, notes TEXT, blueprint TEXT NOT NULL (JSON), created_at TEXT, updated_at TEXT`. Blueprint is a single JSON column (research-recommended; normalizing gains nothing at ~15 fields).
- **D-02:** Blueprint JSON field list mirrors TMPL-01 exactly — `timezone`, `locale`, `platform`, `screen_width`, `screen_height`, `gpu_vendor`, `gpu_renderer`, `hardware_concurrency`, `humanize`, `human_preset`, `launch_args`, `clipboard_sync`, `proxy`, plus optional `color_scheme` and `user_agent` overrides. No `fingerprint_seed` value in the blueprint (see D-04).
- **D-03:** Profile row IS the snapshot. `profiles` extends with `vendor_type TEXT NOT NULL`, `vendor_connection_id TEXT NOT NULL`, `template_id TEXT NOT NULL REFERENCES vendor_templates(id) ON DELETE RESTRICT`. Existing normalized columns (fingerprint_seed, timezone, locale, platform, screen_*, gpu_*, humanize, human_preset, launch_args, clipboard_sync, proxy) are populated from template.blueprint at upsert time and never re-read (TMPL-05). No separate `template_snapshot` JSON column.
- **D-04:** `fingerprint_seed` is generated randomly per profile at creation (matches existing `create_profile`, random 10000–99999). Templates do NOT carry a fixed seed. Each `(vendor_type, vendor_connection_id)` gets an identity-unique fingerprint — critical anti-detection posture (Pitfall 7).
- **D-05:** `UNIQUE(vendor_type, vendor_connection_id)` constraint on `profiles` added as a DB-level guarantee from day one (Pitfall 2 hard safety net). App-layer upsert pattern is Phase 2's responsibility.
- **D-06:** Template delete (TMPL-04) is guarded in BOTH layers — app-layer 409 with blocking profile list AND `FK ON DELETE RESTRICT` on `profiles.template_id`. Belt and suspenders.

**Migration**

- **D-07:** Unconditional wipe on detection of old schema. `init_db()` checks whether `profiles.vendor_type` column exists; if not, it (a) deletes every row in `profiles` and `profile_tags`, (b) deletes corresponding `/data/profiles/{id}` directories, (c) then runs `ALTER TABLE` / new column additions. Idempotent on re-run.
- **D-08:** No safety flag. Old schema == dev/test data pre-refocus. Migration logs count of rows + directories wiped.
- **D-09:** `profile_tags` preserved as a table; its rows dropped alongside wiped profiles.

**Admin Templates UI**

- **D-10:** Functional MVP — `TemplateList.tsx` (table: vendor_type, label, created_at, edit/delete) + `TemplateForm.tsx` (section-grouped create/edit). No search, sort, inline edit, or bulk actions. Phase 4 polishes.
- **D-11:** Form sections: Identity / Fingerprint / Screen / GPU / Behavior / Proxy / Security. `clipboard_sync` toggle in Security defaults `false` with amber warning badge.
- **D-12:** Templates is a new top-level nav entry in `App.tsx` alongside Profiles. Existing profile CRUD UI survives Phase 1 intact (removed in Phase 4).
- **D-13:** 409 delete error → modal listing blocking profile IDs with copy-to-clipboard. Field-level Pydantic validation errors render inline (matches ProfileForm).

**Docker / OPS**

- **D-14:** `chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles` in `entrypoint.sh` BEFORE stale-process kill / singleton cleanup / uvicorn. Defaults to root (0). No `USER` directive added to Dockerfile.
- **D-15:** `docker-compose.yml` gains all new env var declarations. Existing `AUTH_TOKEN` stays.
- **D-16:** `.env.example` created (new file, tracked in git) documenting every env var.

**Security Foundations**

- **D-17:** Fail-closed default. Startup checks `VIEWER_SECRET` and `MAIN_APP_API_KEY`. Unset/empty → refuse to start. `DEV_MODE=1` opt-out allows missing vars with WARNING log per request.
- **D-18:** `clipboard_sync` default flipped to `false` at every touchpoint: schema `DEFAULT 0`, Pydantic `ProfileCreate.clipboard_sync: bool = False`, `ProfileResponse.clipboard_sync: bool = False`, `create_profile` fallback, blueprint JSON default.
- **D-19:** `PyJWT >= 2.12.1` added to `backend/requirements.txt` (consumed in Phase 3).

### Claude's Discretion

- `updated_at` refreshed by app code on every update (no SQLite trigger).
- `TemplateList.tsx` polling interval matches `useProfiles.ts` (3s).
- 409 delete-blocked shape: `{detail: "...", blocking_profile_ids: [...]}`.
- Modal-style editing (matches existing ProfileForm).
- Dev-mode warning copy: `"⚠ DEV_MODE=1: VIEWER_SECRET and/or MAIN_APP_API_KEY not set. Authentication is bypassed. Do not use in production."`
- Reuse existing `globals.css` palette; no new colors.

### Deferred Ideas (OUT OF SCOPE)

- `is_active` soft-disable on templates (GOV-01) — v2.
- Per-template `idle_timeout_minutes` override (SAFE-03) — v2.
- Template inheritance chains — explicit anti-feature.
- Admin UI polish (search, sort, bulk) — Phase 4.
- Navigation redesign — Phase 4.
- USER 1000 switch in Dockerfile — future hardening.
- CSRF tokens on admin mutating routes — Phase 3 handles via `SameSite=Strict`.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TMPL-01 | Admin can create vendor templates with full blueprint | `VendorTemplateCreate` Pydantic model + `TemplateBlueprint` nested model + section-grouped `TemplateForm.tsx` (see §Template Pydantic Shape, §React Template UI) |
| TMPL-02 | Templates uniquely keyed by `vendor_type`; DB rejects duplicates | `vendor_type TEXT UNIQUE NOT NULL` on `vendor_templates` + SQLite `IntegrityError` mapped to HTTP 409 (see §Schema & Migration Patterns) |
| TMPL-03 | Admin can edit templates; edits don't mutate existing profiles | `PUT /api/templates/{id}` updates `vendor_templates` row only; profiles are snapshots (see §Template Snapshot Strategy) |
| TMPL-04 | Admin can delete templates; blocked while profiles exist | Two-layer guard: app-layer 409 with `blocking_profile_ids` + FK `ON DELETE RESTRICT` (see §Delete-Guard Pattern) |
| TMPL-05 | Template fields snapshot-copied into profile row at creation | `create_profile_from_template()` helper (see §create_profile_from_template Signature) |
| SEC-05 | `clipboard_sync` defaults `false` in template schema and profile creation | 5 touchpoints flipped (see §clipboard_sync Touchpoint Matrix) |
| SEC-06 | Service refuses to start when `VIEWER_SECRET` or `MAIN_APP_API_KEY` unset in production | Fail-closed check in FastAPI lifespan (see §Fail-Closed Startup) |
| OPS-03 | Schema migration + documented env vars | `init_db()` idempotent wipe + `.env.example` + `docker-compose.yml` (see §Schema & Migration Patterns, §Env Var Scaffolding) |
| OPS-04 | Docker entrypoint `chown` fix | `chown` before stale-process kill in `entrypoint.sh` (see §Docker Entrypoint chown) |
| OPS-05 | `PyJWT >= 2.12.1` added to `requirements.txt` | Single line addition (see §PyJWT Dependency) |

</phase_requirements>

## Summary

Phase 1 is a **brownfield foundations phase** — zero new runtime behavior, but every subsequent phase hard-depends on its outputs. The work splits into five tracks that can land independently:

1. **Schema & migration** (backend/database.py) — `vendor_templates` table, `ALTER TABLE profiles` columns, idempotent detection-and-wipe for dev databases, belt-and-suspenders delete guard.
2. **Pydantic models & routes** (backend/models.py, new backend/routers/templates.py) — `VendorTemplateCreate`/`Update`/`Response` + `TemplateBlueprint` blueprint model, admin-auth-gated `/api/templates/*` CRUD. Routes live in a new `routers/` directory per CLAUDE.md's explicit direction (main.py is already 1026 lines).
3. **React Templates UI** — mirror the section-grouped `ProfileForm.tsx` pattern and the `useProfiles.ts` polling hook shape; add `"templates"` to `App.tsx`'s view union alongside existing `"empty" | "create" | "edit" | "view"`.
4. **Clipboard-sync flip** — 5 exhaustive touchpoints: schema DEFAULT, `ProfileCreate`, `ProfileResponse`, `create_profile` fallback, blueprint JSON default. All must flip; no partial landing.
5. **Docker / env var / security foundations** — `entrypoint.sh chown` step, `.env.example` as new file, `docker-compose.yml` env declarations, FastAPI lifespan fail-closed check, `PyJWT>=2.12.1` in `backend/requirements.txt`.

**Primary recommendation:** Sequence the work so that migration lands first (unblocks everything else), Pydantic models next (unblocks backend routes AND frontend types), then backend routes + frontend can proceed in parallel, with Docker/env/security as independent small tasks that can land anywhere in the phase.

**The single biggest non-obvious risk:** the migration wipe (D-07) is destructive. A test run against a fresh container with no SingletonLock conflicts is mandatory before the migration code is committed — the three-step sequence (wipe DB rows → wipe `/data/profiles/*` directories → ALTER TABLE) must be verifiable as idempotent on a re-run of a migrated DB.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `vendor_templates` CRUD persistence | Database / SQLite | — | Same tier as `profiles`; no new engine (CLAUDE.md invariant) |
| Template blueprint validation | API / Backend (Pydantic) | — | Runtime-editable admin data; Pydantic is the validation boundary |
| Template CRUD endpoints | API / Backend (FastAPI router) | — | Admin-auth only; `AuthMiddleware` already covers `/api/*` |
| Migration wipe + column add | Database / SQLite (`init_db`) | — | Existing pattern; called from FastAPI lifespan startup |
| Profile snapshot from template | API / Backend (database.py helper) | — | Pure Python function over SQLite; not a cross-tier concern |
| Fail-closed env var check | API / Backend (FastAPI lifespan) | — | Must raise before uvicorn accepts traffic; lifespan is the standard seam |
| Docker entrypoint `chown` | OS / Container init | — | Host-level UID correction must happen before any Python process starts |
| `.env.example` + `docker-compose.yml` env declarations | CDN / Static (infra config) | — | Git-tracked infrastructure; no runtime tier |
| `PyJWT` dependency add | API / Backend (requirements.txt) | — | Phase 3 consumer; Phase 1 only scaffolds |
| `clipboard_sync = false` flip | API / Backend (schema + models) + Client (form default) | — | Schema default + Pydantic default + React form initial state all flip |
| Templates page UI | Browser / Client (React SPA) | Frontend Server (SSR) — N/A | Vite SPA; no SSR tier in this stack |
| Template nav entry | Browser / Client (React `App.tsx`) | — | Client-side view dispatch only |

**Why this matters:** Every Phase 1 capability except the React UI and the Docker entrypoint lives in the API/Backend tier. The planner should concentrate backend tasks in `backend/` and keep the UI work as a cleanly-parallel track. No capability crosses tiers in a non-obvious way — the clipboard default flip is the closest thing (schema + Pydantic + React form initial state all flip together), and the planner should treat it as a single atomic deliverable.

## Project Constraints (from CLAUDE.md)

**Security is non-negotiable.** Three rules apply to every change:

1. Viewer tokens travel in URL fragment (`#token=`), never querystring. (Phase 1: no viewer tokens yet — only PyJWT dep.)
2. `clipboard_sync` defaults `false` on every vendor template and every profile. (Phase 1: flip + enforcement.)
3. Two auth surfaces strictly segregated — `APIKeyHeader` guards machine routes, `AuthMiddleware` guards admin. (Phase 1: `/api/templates/*` under admin `AuthMiddleware` only; no exemption.)

**Architecture invariants to preserve:**

- `BrowserManager` owns Chromium lifecycle; don't replicate. (Phase 1 doesn't touch it.)
- SQLite + `backend/database.py` — extend via `ALTER TABLE` patterns in `init_db()`; no engine migration.
- `backend/main.py` is 1026 lines — new routes go in `backend/routers/`, NOT inline in main.py. **This is the explicit reason Phase 1 creates the `routers/` directory.**
- Single-consumer service. No multi-tenancy, no OAuth, no quotas.
- Vendor template fields snapshot-copied into profile row at creation. Live templates never re-read on warm-pool wake. Editing a template never mutates existing profiles.

**Locked tech stack additions for this milestone:** `PyJWT >= 2.12.1` only. No other new Python dependencies.

**Required env vars that the service must validate at startup:** `MAIN_APP_API_KEY`, `VIEWER_SECRET`. (Others — `MAIN_APP_ORIGIN`, `IDLE_TIMEOUT_SECONDS`, `VIEWER_TOKEN_TTL_SECS` — declared but not enforced until their consumer phases.)

## Standard Stack

### Core (already in project — no additions needed except PyJWT)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | `>=0.115.0` | HTTP framework | Existing, `APIRouter` is the idiomatic seam for the new templates router `[VERIFIED: backend/requirements.txt]` |
| `pydantic` | `>=2.0` | Request/response models + blueprint validation | Existing; `field_validator` pattern already in `models.py::coerce_clipboard_sync` `[VERIFIED: backend/models.py]` |
| `sqlite3` | stdlib | DB driver | Existing; no async wrapper (research flagged `aiosqlite` out of scope) `[VERIFIED: backend/database.py L8]` |
| `PyJWT` | `>=2.12.1` | Viewer token signing (Phase 3 consumer) | Latest stable 2.12.1 released 2026-03-13; Phase 1 adds to `requirements.txt` only `[VERIFIED: pypi.org/project/PyJWT 2026-04-22]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `react` | 19.x | Frontend framework | Existing; all UI is React function components `[VERIFIED: frontend/package.json]` |
| `typescript` | 5.7.x | Type-safe frontend | Existing; `strict: true` + `noUnusedLocals: true` in tsconfig `[VERIFIED: .planning/codebase/CONVENTIONS.md]` |
| `lucide-react` | current | Icon set | Existing; use for Templates nav icon + warning badge icon (`AlertTriangle`) `[VERIFIED: frontend/src/App.tsx L2]` |
| `tailwindcss` | 3.x | Styling | Existing; reuse `globals.css` custom palette per D-13 Discretion `[VERIFIED: frontend/src/styles/globals.css]` |

### Alternatives Considered (and why rejected)

| Instead of | Could Use | Tradeoff / Why Rejected |
|------------|-----------|-------------------------|
| SQLite TEXT JSON column for blueprint | 15 normalized columns | Research decision locked (D-01). Blueprint is a closed schema controlled by this codebase; Pydantic handles validation; normalizing gains nothing at 15 fields and makes schema evolution harder `[CITED: .planning/research/STACK.md L206-213]` |
| `aiosqlite` async DB | Existing `sqlite3` sync | Out of scope per research; event loop blocking at <20 concurrent not a concern `[CITED: .planning/research/PITFALLS.md L321-323]` |
| Alembic migrations | `init_db()` conditional `ALTER TABLE` | Existing pattern (D-01, CLAUDE.md invariant). Alembic adds ceremony with no benefit for a single-developer project at this scale `[VERIFIED: backend/database.py L69-76 existing pattern]` |
| `itsdangerous` for tokens | PyJWT | Research decision locked (D-19). JWT is standard format, widely audited; `itsdangerous` is bespoke `[CITED: .planning/research/STACK.md L85-98]` |
| Second ASGI middleware for machine routes | Router `dependencies=[Depends(...)]` | Out of scope for Phase 1 (machine auth lands Phase 2); but Phase 2 will use router-scoped dep per research `[CITED: .planning/research/STACK.md L176-179]` |

**Installation:**

```bash
# Single backend dep to add
# In backend/requirements.txt, add one line:
echo "PyJWT>=2.12.1" >> backend/requirements.txt
```

**Version verification (verified 2026-04-22):**

- `PyJWT` 2.12.1 — released 2026-03-13, verified on PyPI `[VERIFIED: pypi.org/project/PyJWT]`

**No frontend package.json changes required** in Phase 1. All new React components use existing dependencies.

## Architecture Patterns

### System Architecture Diagram (Phase 1 deliverables only)

```
                    ┌──────────────────────────────────────┐
                    │         Admin User (browser)          │
                    └───────────────┬──────────────────────┘
                                    │  auth_token cookie (admin)
                                    ▼
    ┌────────────────────────────────────────────────────────────────┐
    │  FastAPI (backend/main.py)                                      │
    │                                                                  │
    │  lifespan startup:                                               │
    │     ├─ ❶ check VIEWER_SECRET + MAIN_APP_API_KEY → fail if unset │
    │     │    (unless DEV_MODE=1, then log WARNING)                  │
    │     └─ ❷ db.init_db() — idempotent migration + wipe             │
    │                                                                  │
    │  ┌──────────────────────────────────────────────────────────┐  │
    │  │  AuthMiddleware (existing)                                 │  │
    │  │  — guards /api/*  (including /api/templates/*)             │  │
    │  └────────────────┬─────────────────────────────────────────┘  │
    │                    │                                             │
    │  ┌────────────────▼─────────────────────────────────────────┐  │
    │  │  templates_router (NEW — backend/routers/templates.py)    │  │
    │  │    GET    /api/templates         list                     │  │
    │  │    POST   /api/templates         create (409 on dup)      │  │
    │  │    GET    /api/templates/{id}    detail                   │  │
    │  │    PUT    /api/templates/{id}    update                   │  │
    │  │    DELETE /api/templates/{id}    delete (409 if in use)   │  │
    │  └────────────────┬─────────────────────────────────────────┘  │
    └───────────────────┼────────────────────────────────────────────┘
                        │  function calls
                        ▼
    ┌────────────────────────────────────────────────────────────────┐
    │  backend/database.py  (extended)                                │
    │                                                                  │
    │  init_db() with migration logic:                                │
    │    1. CREATE TABLE IF NOT EXISTS vendor_templates (…)           │
    │    2. PRAGMA table_info(profiles) → detect vendor_type column  │
    │    3. If absent → WIPE: DELETE profile_tags; DELETE profiles;   │
    │                   rmtree(/data/profiles/*); log counts          │
    │    4. ALTER TABLE profiles ADD COLUMN vendor_type …             │
    │       ALTER TABLE profiles ADD COLUMN vendor_connection_id …    │
    │       ALTER TABLE profiles ADD COLUMN template_id …             │
    │    5. CREATE UNIQUE INDEX idx_profiles_vendor_pair              │
    │       ON profiles(vendor_type, vendor_connection_id)            │
    │                                                                  │
    │  New functions:                                                  │
    │    list_templates()      get_template(id)                       │
    │    get_template_by_vendor_type(vt)                              │
    │    create_template(**)   update_template(id, **)                │
    │    delete_template(id)  count_profiles_by_template(template_id) │
    │    list_profiles_by_template(template_id)                       │
    │    create_profile_from_template(template, vendor_connection_id) │
    └────────────────┬───────────────────────────────────────────────┘
                     │  reads/writes
                     ▼
    ┌────────────────────────────────────────────────────────────────┐
    │  SQLite (/data/profiles.db)                                      │
    │    profiles (+ vendor_type, vendor_connection_id, template_id)  │
    │    profile_tags                                                  │
    │    vendor_templates (NEW)                                        │
    └────────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────────┐
   │  React SPA (frontend/src/)                                       │
   │                                                                   │
   │  App.tsx  — view: "empty"|"create"|"edit"|"view"|"templates"    │
   │     │                                                             │
   │     ├─▶ existing ProfileList / ProfileForm / ProfileViewer        │
   │     │   (survive Phase 1 unchanged; flip default in form)         │
   │     │                                                             │
   │     └─▶ TemplateList.tsx  (NEW)                                   │
   │            └─▶ TemplateForm.tsx  (NEW, section-grouped)           │
   │                                                                   │
   │  hooks/useTemplates.ts  (NEW — 3s polling, mirrors useProfiles)   │
   │  lib/api.ts  — extended with api.templates.* functions           │
   └─────────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────────┐
   │  entrypoint.sh (updated)                                         │
   │    ❶ mkdir -p /data/profiles                                    │
   │    ❷ chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles   │ ◀─ NEW
   │    ❸ pkill stale Xvnc/cloakbrowser/chromium/xclip                │
   │    ❹ find /data/profiles -name SingletonLock/Cookie/Socket -del  │
   │    ❺ rm /tmp/.X1*-lock                                          │
   │    ❻ exec uvicorn                                                │
   └─────────────────────────────────────────────────────────────────┘
```

**Trace a primary use case — "admin creates a Shopify vendor template":**

1. Admin navigates to Templates tab → `App.tsx` sets `view = "templates"` → `TemplateList.tsx` mounts
2. `useTemplates` hook polls `GET /api/templates` every 3s → empty list
3. Admin clicks "New Template" → `TemplateForm.tsx` mounts in create mode with `clipboard_sync: false` as initial state + amber warning badge in Security section
4. Admin fills `vendor_type="shopify"`, `label="Shopify Admin"`, blueprint fields in Fingerprint/Screen/GPU/Behavior/Proxy sections
5. Submit → `api.templates.create(data)` → `POST /api/templates`
6. FastAPI: `AuthMiddleware` passes (admin cookie) → `templates_router.create_template` → `VendorTemplateCreate` Pydantic validates → `db.create_template(...)` serializes blueprint dict to JSON → SQLite `INSERT` with `UNIQUE(vendor_type)` → returns `VendorTemplateResponse`
7. React updates `templates` list → row appears in `TemplateList.tsx`

**Trace the failure case — "admin tries to delete a template with 3 profiles":**

1. Admin clicks Delete on `TemplateList.tsx` row → `api.templates.remove(id)` → `DELETE /api/templates/{id}`
2. `templates_router.delete_template`:
   - `blocking_ids = db.list_profiles_by_template(id)` → `["p1", "p2", "p3"]`
   - `if blocking_ids: raise HTTPException(status_code=409, detail={"detail": "...", "blocking_profile_ids": [...]})`
3. Frontend 409 handler → modal opens listing the 3 profile IDs with copy-to-clipboard button

### Recommended Project Structure (Phase 1 additions)

```
backend/
├── routers/                  # NEW directory (per CLAUDE.md)
│   ├── __init__.py
│   └── templates.py          # NEW — /api/templates/* CRUD
├── database.py               # EXTEND — add vendor_templates table + helpers
├── models.py                 # EXTEND — TemplateBlueprint + VendorTemplate{Create,Update,Response}
├── main.py                   # EXTEND — register templates_router + lifespan fail-closed check
└── requirements.txt          # EXTEND — add PyJWT>=2.12.1

frontend/src/
├── components/
│   ├── TemplateList.tsx      # NEW — list with edit/delete actions + 409 modal
│   └── TemplateForm.tsx      # NEW — section-grouped create/edit
├── hooks/
│   └── useTemplates.ts       # NEW — 3s polling CRUD hook
├── lib/
│   └── api.ts                # EXTEND — VendorTemplate types + api.templates.*
└── App.tsx                   # EXTEND — "templates" view + nav entry

.env.example                  # NEW file (tracked in git)
entrypoint.sh                 # EXTEND — chown step
docker-compose.yml            # EXTEND — new env var declarations
Dockerfile                    # NO CHANGES (D-14 keeps USER root)
```

### Pattern 1: SQLite Schema Migration via `PRAGMA table_info` + Conditional `ALTER TABLE`

**What:** Existing pattern from `init_db()` (backend/database.py L69-76) — detect columns via `PRAGMA`, conditionally `ALTER TABLE` to add. This is the only migration strategy in the codebase; follow it exactly.

**When to use:** Every schema change in this codebase. Alembic is not on the table (CLAUDE.md invariant).

**Example (extend existing pattern for Phase 1):**

```python
# backend/database.py — extended init_db()
def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        # ① Base tables (CREATE TABLE IF NOT EXISTS is idempotent)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                fingerprint_seed INTEGER NOT NULL,
                /* … existing columns … */
                clipboard_sync BOOLEAN DEFAULT 0,   /* ← D-18: flipped from DEFAULT 1 */
                /* … */
                user_data_dir TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profile_tags (...);
            CREATE TABLE IF NOT EXISTS vendor_templates (
                id TEXT PRIMARY KEY,
                vendor_type TEXT NOT NULL UNIQUE,
                label TEXT,
                notes TEXT,
                blueprint TEXT NOT NULL,     /* JSON-encoded */
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()

        # ② Detect old schema and WIPE if needed (D-07)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}

        if "vendor_type" not in cols:
            # Old schema detected — wipe dev/test data
            import shutil
            profile_ids = [r[0] for r in conn.execute("SELECT id FROM profiles").fetchall()]
            dir_count = 0
            for pid in profile_ids:
                pdir = DATA_DIR / "profiles" / pid
                if pdir.exists():
                    shutil.rmtree(pdir, ignore_errors=True)
                    dir_count += 1
            row_count = conn.execute("DELETE FROM profile_tags").rowcount
            row_count += conn.execute("DELETE FROM profiles").rowcount
            conn.commit()
            logger.warning(
                "Schema migration: wiped %d profile rows and %d profile directories "
                "(dev/test data; new schema required)", row_count, dir_count
            )

            # ③ Add new columns (NOT NULL with no DEFAULT would fail on existing rows,
            #    but we just wiped them so this is safe)
            conn.execute("ALTER TABLE profiles ADD COLUMN vendor_type TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE profiles ADD COLUMN vendor_connection_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "ALTER TABLE profiles ADD COLUMN template_id TEXT "
                "REFERENCES vendor_templates(id) ON DELETE RESTRICT"
            )
            # Note: UNIQUE index added separately (ALTER TABLE can't add UNIQUE constraint in SQLite)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_vendor_pair "
                "ON profiles(vendor_type, vendor_connection_id)"
            )
            conn.commit()

        # ④ Previously added migration steps (idempotent)
        if "clipboard_sync" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 0")
            conn.commit()
        if "launch_args" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN launch_args TEXT DEFAULT '[]'")
            conn.commit()
```

**Key subtleties:**

- **SQLite `ALTER TABLE ADD COLUMN` restrictions** `[CITED: sqlite.org/lang_altertable.html]`: SQLite cannot add a `NOT NULL` column without a `DEFAULT` — workaround is `DEFAULT ''` (the wipe ensures no rows exist). It also cannot add a `UNIQUE` constraint via `ALTER TABLE` — must use `CREATE UNIQUE INDEX` afterwards.
- **Foreign key enforcement** requires `PRAGMA foreign_keys=ON` per connection (already in `get_db()` L23) `[VERIFIED: backend/database.py L23]`. Without this, `ON DELETE RESTRICT` is a no-op.
- **Idempotency check**: After a successful migration, `vendor_type` is in `cols` on the next run → wipe block is skipped. `CREATE TABLE IF NOT EXISTS` and `CREATE UNIQUE INDEX IF NOT EXISTS` are idempotent.
- **Wipe order matters**: Delete from `profile_tags` BEFORE `profiles` (FK `ON DELETE CASCADE` handles it, but the explicit DELETE gives us a clean `rowcount` to log). Delete directories AFTER DB writes so a partial failure leaves DB + disk consistent. Use `rmtree(ignore_errors=True)` — some profile dirs may not exist.

**Verification commands (planner should include these as test actions):**

```bash
# After first run with old schema present:
sqlite3 /data/profiles.db "SELECT COUNT(*) FROM profiles;"       # 0
sqlite3 /data/profiles.db "PRAGMA table_info(profiles);"         # includes vendor_type
ls /data/profiles/                                                # empty or only new profiles

# After second run (idempotent):
# Logs should NOT contain "Schema migration: wiped…" on startup
```

### Pattern 2: Pydantic v2 `field_validator` for Blueprint Defaults

**What:** Use Pydantic v2's `field_validator(mode="before")` to enforce defaults on nested blueprint fields. The existing `coerce_clipboard_sync` validator in `models.py` L88-91 is the reference pattern.

**When to use:** Any field that has a policy-driven default (the amber-warning `clipboard_sync: false` is the most important case).

**Example:**

```python
# backend/models.py — new models
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class TemplateBlueprint(BaseModel):
    """The JSON payload stored in vendor_templates.blueprint.

    Mirrors ProfileCreate fields EXCEPT fingerprint_seed (generated per-profile, D-04).
    """
    # Fingerprint (no seed — per D-04)
    timezone: str | None = None
    locale: str | None = None
    platform: Literal["windows", "macos", "linux"] = "windows"
    user_agent: str | None = None  # optional override per D-02

    # Screen
    screen_width: int = 1920
    screen_height: int = 1080
    color_scheme: Literal["light", "dark", "no-preference"] | None = None  # optional per D-02

    # GPU
    gpu_vendor: str | None = None
    gpu_renderer: str | None = None
    hardware_concurrency: int | None = None

    # Behavior
    humanize: bool = False
    human_preset: Literal["default", "careful"] = "default"
    launch_args: list[str] = Field(default_factory=list)

    # Security — D-18: default FALSE
    clipboard_sync: bool = False

    # Proxy
    proxy: str | None = None

    @field_validator("clipboard_sync", mode="before")
    @classmethod
    def enforce_clipboard_default(cls, v: object) -> bool:
        """Policy: clipboard_sync MUST default False (SEC-05). Null/missing → False."""
        return bool(v) if v is not None else False


class VendorTemplateCreate(BaseModel):
    vendor_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    label: str | None = None
    notes: str | None = None
    blueprint: TemplateBlueprint


class VendorTemplateUpdate(BaseModel):
    label: str | None = None
    notes: str | None = None
    blueprint: TemplateBlueprint | None = None
    # vendor_type is the lookup key; not editable. Changing vendor_type → delete and recreate.


class VendorTemplateResponse(BaseModel):
    id: str
    vendor_type: str
    label: str | None = None
    notes: str | None = None
    blueprint: TemplateBlueprint
    created_at: str
    updated_at: str


class TemplateDeleteBlockedResponse(BaseModel):
    """409 response shape when template is in use."""
    detail: str
    blocking_profile_ids: list[str]
```

**Why `mode="before"`:** Runs before Pydantic's type coercion; lets us intercept `None`/missing values. Existing `coerce_clipboard_sync` on `ProfileResponse` uses this pattern (`models.py` L88-91).

**Round-tripping to/from SQLite:**

```python
# Serialize for INSERT/UPDATE:
import json
blueprint_json = template_create.blueprint.model_dump_json()  # Pydantic v2 native

# Deserialize from SELECT row:
blueprint_dict = json.loads(row["blueprint"])
blueprint = TemplateBlueprint.model_validate(blueprint_dict)
```

### Pattern 3: FastAPI APIRouter for Modular Routes

**What:** New routes live in `backend/routers/templates.py` as an `APIRouter` instance; `main.py` just does `app.include_router(templates_router)`. This is the explicit CLAUDE.md direction for all new routes (main.py is 1026 lines already).

**When to use:** Any new route file going forward in this project.

**Example:**

```python
# backend/routers/templates.py  (NEW FILE)
from __future__ import annotations
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlite3 import IntegrityError

from .. import database as db
from ..models import (
    VendorTemplateCreate,
    VendorTemplateUpdate,
    VendorTemplateResponse,
    TemplateBlueprint,
)

logger = logging.getLogger("cloakbrowser.manager.templates")
router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[VendorTemplateResponse])
async def list_templates():
    rows = db.list_templates()
    return [_row_to_response(r) for r in rows]


@router.post("", response_model=VendorTemplateResponse, status_code=201)
async def create_template(payload: VendorTemplateCreate):
    try:
        row = db.create_template(
            vendor_type=payload.vendor_type,
            label=payload.label,
            notes=payload.notes,
            blueprint_json=payload.blueprint.model_dump_json(),
        )
    except IntegrityError as exc:
        # UNIQUE(vendor_type) violation — surface as 409
        raise HTTPException(
            status_code=409,
            detail=f"Template with vendor_type={payload.vendor_type!r} already exists",
        ) from exc
    return _row_to_response(row)


@router.get("/{template_id}", response_model=VendorTemplateResponse)
async def get_template(template_id: str):
    row = db.get_template(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return _row_to_response(row)


@router.put("/{template_id}", response_model=VendorTemplateResponse)
async def update_template(template_id: str, payload: VendorTemplateUpdate):
    fields: dict[str, Any] = {}
    if payload.label is not None:
        fields["label"] = payload.label
    if payload.notes is not None:
        fields["notes"] = payload.notes
    if payload.blueprint is not None:
        fields["blueprint_json"] = payload.blueprint.model_dump_json()

    row = db.update_template(template_id, **fields)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return _row_to_response(row)


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    # ① App-layer check (D-06 belt)
    blocking = db.list_profiles_by_template(template_id)
    if blocking:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": f"Template is in use by {len(blocking)} profile(s); "
                          f"delete those profiles first.",
                "blocking_profile_ids": blocking,
            },
        )
    # ② DB-layer safety net (D-06 suspenders) — FK ON DELETE RESTRICT
    try:
        deleted = db.delete_template(template_id)
    except IntegrityError as exc:
        # Race: profile created between the SELECT above and DELETE below
        raise HTTPException(
            status_code=409,
            detail="Template acquired a profile reference during deletion; retry",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}


def _row_to_response(row: dict[str, Any]) -> VendorTemplateResponse:
    blueprint = TemplateBlueprint.model_validate(json.loads(row["blueprint"]))
    return VendorTemplateResponse(
        id=row["id"],
        vendor_type=row["vendor_type"],
        label=row["label"],
        notes=row["notes"],
        blueprint=blueprint,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

**Wire-up in main.py (one-line addition):**

```python
# backend/main.py — after existing app setup (around L384)
from .routers import templates as templates_router
app.include_router(templates_router.router)
```

`AuthMiddleware` automatically gates `/api/*` paths (existing behavior, main.py L158). The router does NOT need to be added to `_AUTH_EXEMPT`.

### Pattern 4: `create_profile_from_template` Helper

**What:** A new helper in `backend/database.py` that takes a template row + a `vendor_connection_id` and creates a profile by snapshot-copying blueprint fields into the profile row. The existing `create_profile(name, fingerprint_seed, **fields)` is preserved for any residual use; the new helper wraps/extends it with template-specific logic.

**When to use:** Phase 2's `POST /sessions` handler calls this. Phase 1 writes the helper but exercises it only through tests (no route calls it yet in Phase 1).

**Signature and implementation:**

```python
# backend/database.py — new helper

import random, uuid, json
from typing import Any

def create_profile_from_template(
    template: dict[str, Any],  # row dict including 'blueprint' as JSON string OR already-parsed dict
    vendor_connection_id: str,
    name: str | None = None,  # optional display name; defaults to "{vendor_type}/{vendor_connection_id}"
) -> dict[str, Any]:
    """Create a profile by snapshotting template.blueprint into profile columns.

    - fingerprint_seed is generated here (D-04) — NOT read from template.
    - All blueprint fields are copied into the profile row. Template is never re-read after this.
    - template_id is stored for auditability; FK ON DELETE RESTRICT protects deletion.

    Called by Phase 2's POST /sessions handler (not called in Phase 1 routes).
    """
    # Normalize blueprint (template may carry JSON string or pre-parsed dict)
    bp = template["blueprint"]
    if isinstance(bp, str):
        bp = json.loads(bp)

    profile_id = str(uuid.uuid4())
    seed = random.randint(10000, 99999)  # D-04: always random per profile
    display_name = name or f"{template['vendor_type']}/{vendor_connection_id}"
    user_data_dir = str(DATA_DIR / "profiles" / profile_id)
    now = _now()

    with get_db() as conn:
        conn.execute(
            """INSERT INTO profiles (
                id, name, fingerprint_seed,
                vendor_type, vendor_connection_id, template_id,
                proxy, timezone, locale, platform, user_agent,
                screen_width, screen_height, gpu_vendor, gpu_renderer,
                hardware_concurrency, humanize, human_preset,
                headless, geoip, clipboard_sync, color_scheme, launch_args, notes,
                user_data_dir, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id, display_name, seed,
                template["vendor_type"], vendor_connection_id, template["id"],
                bp.get("proxy"),
                bp.get("timezone"),
                bp.get("locale"),
                bp.get("platform", "windows"),
                bp.get("user_agent"),
                bp.get("screen_width", 1920),
                bp.get("screen_height", 1080),
                bp.get("gpu_vendor"),
                bp.get("gpu_renderer"),
                bp.get("hardware_concurrency"),
                bool(bp.get("humanize", False)),
                bp.get("human_preset", "default"),
                False,  # headless — existing default
                False,  # geoip — existing default
                bool(bp.get("clipboard_sync", False)),  # D-18: default False
                bp.get("color_scheme"),
                json.dumps(bp.get("launch_args") or []),
                None,  # notes (profile-level, not template)
                user_data_dir, now, now,
            ),
        )
        conn.commit()

    return get_profile(profile_id)  # type: ignore[return-value]
```

**Why keep `create_profile()` alongside this:**

- The existing `create_profile(name, fingerprint_seed, **fields)` is used by `backend/main.py` L445-453 (`POST /api/profiles`). Phase 1 must NOT break the existing profile-creation surface — it is removed in Phase 4, not Phase 1 (per ROADMAP Phase 4 OPS-01, OPS-02).
- The existing path creates profiles with `vendor_type=""` and `vendor_connection_id=""` (defaults from the `ALTER TABLE` step). That is acceptable in Phase 1 because the UNIQUE constraint only fires when a second row has the same pair — and a second `""`/`""` pair would collide. **Decision required:** either (a) exempt the old CRUD path from the UNIQUE constraint (not possible in SQLite without a partial index), (b) remove the old profile-create UI in Phase 1 (contradicts D-10 "existing profile CRUD UI survives Phase 1 intact"), or (c) generate a placeholder `vendor_type="legacy"` + `vendor_connection_id=<uuid>` for profiles created via the old path.

  **Recommendation:** Option (c). In the old `create_profile()`, default `fields["vendor_type"] = fields.get("vendor_type") or "__legacy__"` and `fields["vendor_connection_id"] = fields.get("vendor_connection_id") or str(uuid.uuid4())`. This keeps the existing UI working, respects the UNIQUE constraint, and the `__legacy__` marker makes old profiles easy to identify and purge in Phase 4. **Flagged for discuss-phase confirmation:** [ASSUMED] — CONTEXT.md does not explicitly address how the existing `POST /api/profiles` route coexists with the new NOT NULL `vendor_type` column.

### Pattern 5: FastAPI Lifespan Fail-Closed Startup

**What:** The existing `lifespan` context in `main.py` L372-379 is the correct seam for the `VIEWER_SECRET` / `MAIN_APP_API_KEY` check. Raising in `lifespan` prevents uvicorn from accepting traffic.

**When to use:** Any startup validation that must fail the process if unsatisfied.

**Example:**

```python
# backend/main.py — extended lifespan

VIEWER_SECRET: str | None = os.environ.get("VIEWER_SECRET")
MAIN_APP_API_KEY: str | None = os.environ.get("MAIN_APP_API_KEY")
DEV_MODE: bool = os.environ.get("DEV_MODE", "").strip() in ("1", "true", "yes")

_DEV_MODE_WARNING = (
    "⚠ DEV_MODE=1: VIEWER_SECRET and/or MAIN_APP_API_KEY not set. "
    "Authentication is bypassed. Do not use in production."
)


def _check_required_env() -> None:
    """Fail-closed check for production secrets (SEC-06 / D-17).

    Raises RuntimeError in production mode if either secret is missing/blank.
    Logs a loud warning in DEV_MODE=1 and continues.
    """
    missing = []
    if not VIEWER_SECRET or not VIEWER_SECRET.strip():
        missing.append("VIEWER_SECRET")
    if not MAIN_APP_API_KEY or not MAIN_APP_API_KEY.strip():
        missing.append("MAIN_APP_API_KEY")

    if not missing:
        return  # All good

    if DEV_MODE:
        logger.warning(_DEV_MODE_WARNING)
        logger.warning("Missing in dev mode: %s", ", ".join(missing))
        return

    raise RuntimeError(
        f"Refusing to start: required env vars not set: {', '.join(missing)}. "
        f"Set them in your environment, or set DEV_MODE=1 for local development."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_required_env()          # ← NEW: fail-closed before any DB init or browser setup
    db.init_db()                   # existing (extended with migration)
    await browser_mgr.cleanup_stale()  # existing
    logger.info("CloakBrowser Manager started")
    yield
    logger.info("Shutting down — stopping all browsers...")
    await browser_mgr.cleanup_all()
```

**Per-request DEV_MODE warning log** (lightweight, triggered from `AuthMiddleware`):

```python
# backend/main.py — inside AuthMiddleware.__call__, right after path match logic
# Add before the existing _check_auth call:
if DEV_MODE and scope["type"] == "http" and scope["path"].startswith("/api/"):
    # One DEBUG log per request; a startup-level WARNING already warned loudly
    logger.debug("DEV_MODE active on %s %s", scope.get("method"), scope["path"])
```

**Why `lifespan` not `entrypoint.sh`:** The check needs access to the Python environment (os.environ), needs to emit structured logs via the `logging` module, and must prevent uvicorn from binding — raising inside `lifespan` is exactly this contract per FastAPI docs. `entrypoint.sh` is too early (no Python logging yet) and would require shell-level env checks that duplicate Python logic `[CITED: fastapi.tiangolo.com/advanced/events/]`.

### Pattern 6: React Admin UI — Mirror Existing ProfileForm / useProfiles / api.ts Shapes

**What:** Three new React files that follow the existing code precisely. No new dependencies; no new patterns; reuse the existing Tailwind palette.

#### `frontend/src/lib/api.ts` — extend with template types + functions

```typescript
// frontend/src/lib/api.ts — additions

export interface TemplateBlueprint {
  timezone: string | null;
  locale: string | null;
  platform: "windows" | "macos" | "linux";
  user_agent: string | null;
  screen_width: number;
  screen_height: number;
  color_scheme: "light" | "dark" | "no-preference" | null;
  gpu_vendor: string | null;
  gpu_renderer: string | null;
  hardware_concurrency: number | null;
  humanize: boolean;
  human_preset: "default" | "careful";
  launch_args: string[];
  clipboard_sync: boolean;  // default false — amber warning in UI
  proxy: string | null;
}

export interface VendorTemplate {
  id: string;
  vendor_type: string;
  label: string | null;
  notes: string | null;
  blueprint: TemplateBlueprint;
  created_at: string;
  updated_at: string;
}

export interface VendorTemplateCreateData {
  vendor_type: string;
  label?: string | null;
  notes?: string | null;
  blueprint: TemplateBlueprint;
}

export interface VendorTemplateUpdateData {
  label?: string | null;
  notes?: string | null;
  blueprint?: TemplateBlueprint;
}

export interface TemplateDeleteBlockedError {
  detail: string;
  blocking_profile_ids: string[];
}

// Add to the existing `api` object:
export const api = {
  // ... existing ...

  listTemplates: () => request<VendorTemplate[]>("/api/templates"),

  getTemplate: (id: string) => request<VendorTemplate>(`/api/templates/${id}`),

  createTemplate: (data: VendorTemplateCreateData) =>
    request<VendorTemplate>("/api/templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateTemplate: (id: string, data: VendorTemplateUpdateData) =>
    request<VendorTemplate>(`/api/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteTemplate: (id: string) =>
    request<{ ok: boolean }>(`/api/templates/${id}`, { method: "DELETE" }),
};
```

#### `frontend/src/hooks/useTemplates.ts` — mirror `useProfiles.ts` exactly

```typescript
// frontend/src/hooks/useTemplates.ts (NEW)
// Mirrors useProfiles.ts — same 3s polling, same loading/error shape

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type VendorTemplate,
  type VendorTemplateCreateData,
  type VendorTemplateUpdateData,
  type TemplateDeleteBlockedError,
} from "../lib/api";

export interface DeleteBlockedState {
  templateId: string;
  vendorType: string;
  blockingIds: string[];
}

export function useTemplates() {
  const [templates, setTemplates] = useState<VendorTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteBlocked, setDeleteBlocked] = useState<DeleteBlockedState | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listTemplates();
      setTemplates(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch templates");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);  // match useProfiles
    return () => clearInterval(interval);
  }, [refresh]);

  const create = useCallback(async (data: VendorTemplateCreateData) => {
    try {
      const t = await api.createTemplate(data);
      setTemplates((prev) => [t, ...prev]);
      return t;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create template");
    }
  }, []);

  const update = useCallback(async (id: string, data: VendorTemplateUpdateData) => {
    try {
      const t = await api.updateTemplate(id, data);
      setTemplates((prev) => prev.map((x) => (x.id === id ? t : x)));
      return t;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update template");
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    const existing = templates.find((t) => t.id === id);
    try {
      await api.deleteTemplate(id);
      setTemplates((prev) => prev.filter((x) => x.id !== id));
    } catch (err) {
      // Detect 409 delete-blocked and surface structured state
      // ApiError message is the stringified detail; need to re-parse for blocking_profile_ids.
      // Recommendation: extend request() in api.ts to attach body.detail/blocking_profile_ids on ApiError.
      if (err && typeof err === "object" && "status" in err && (err as { status: number }).status === 409) {
        const body = (err as { body?: TemplateDeleteBlockedError }).body;
        if (body && body.blocking_profile_ids) {
          setDeleteBlocked({
            templateId: id,
            vendorType: existing?.vendor_type ?? "?",
            blockingIds: body.blocking_profile_ids,
          });
          return;
        }
      }
      setError(err instanceof Error ? err.message : "Failed to delete template");
    }
  }, [templates]);

  const dismissDeleteBlocked = useCallback(() => setDeleteBlocked(null), []);

  return {
    templates, loading, error,
    refresh, create, update, remove,
    deleteBlocked, dismissDeleteBlocked,
  };
}
```

**Small extension needed to `api.ts`:** the existing `ApiError` class (L74-81) doesn't capture the response body. For the 409 modal to show blocking profile IDs, extend it:

```typescript
class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,   // ← NEW — structured detail
  ) {
    super(message);
  }
}

// In request(), when the body has structured detail:
if (!res.ok) {
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  if (res.status === 401 && _onUnauthorized) {
    _onUnauthorized();
    throw new ApiError(401, "Unauthorized", body);
  }
  throw new ApiError(res.status, body.detail || res.statusText, body);
}
```

#### `frontend/src/components/TemplateForm.tsx` — section-grouped form

Mirror `ProfileForm.tsx` sectioning exactly (D-11). Sections: Identity / Fingerprint / Screen / GPU / Behavior / Proxy / Security. Initial state sets `clipboard_sync: false`. The Security section renders an amber badge with copy:

> `<AlertTriangle className="h-3.5 w-3.5"/> Enabling clipboard sync gives the viewer session read access to anything copied inside the vendor portal — including OTP codes and session tokens. Leave OFF unless you specifically need paste-from-host.`

Reuse existing Tailwind classes: `btn-primary`, `btn-secondary`, `btn-danger`, `input`, `label`, `text-xs font-semibold text-gray-400 uppercase tracking-wider` (ProfileForm L205). Amber palette: `bg-amber-600/15 border-amber-600/30 text-amber-400` — matches the existing red error-banner pattern `[VERIFIED: App.tsx L210]`.

#### `frontend/src/components/TemplateList.tsx` — list + 409 modal

Table columns: `vendor_type`, `label`, `created_at` (relative), Edit, Delete. When `deleteBlocked` state is non-null, render a modal with the blocking profile IDs and a "Copy to clipboard" button. Modal styling: reuse the existing `bg-surface-1 border border-border` conventions from App.tsx L158.

**Copy-to-clipboard helper:**

```typescript
async function copyIds(ids: string[]) {
  try {
    await navigator.clipboard.writeText(ids.join("\n"));
  } catch {
    // Fallback: create a textarea, select, execCommand('copy')
  }
}
```

#### `frontend/src/App.tsx` — nav entry + view dispatch

Extend the `View` union:

```typescript
type View = "empty" | "create" | "edit" | "view" | "templates";
```

Add a nav item in the sidebar area (App.tsx L157-166). Nav ordering: Profiles first (existing), Templates second (per CONTEXT.md specific "Nav ordering" guidance).

```tsx
// Around App.tsx L75 (top-level layout), add a top-nav or segmented switcher:
<div className="flex gap-2 border-b border-border px-4 py-2">
  <button
    onClick={() => setView("empty")}
    className={view !== "templates" ? "font-semibold" : ""}
  >
    Profiles
  </button>
  <button
    onClick={() => { setSelectedId(null); setView("templates"); }}
    className={view === "templates" ? "font-semibold" : ""}
  >
    Templates
  </button>
</div>
```

Then dispatch:

```tsx
{view === "templates" && <TemplateList />}
```

**Design note:** Phase 4 pivots the navigation completely. Phase 1 is adding a minimal switcher, not a navigation redesign (D-12). Use the simplest mechanism that gets operators to the Templates screen.

### Anti-Patterns to Avoid

- **Re-reading template at warm-pool wake.** (CLAUDE.md invariant, TMPL-05.) Every profile field that comes from a template is snapshotted into the profile row at creation. On wake, the profile row is the source of truth — never look up the template.
- **Partial `clipboard_sync` flip.** All 5 touchpoints must change together. A partial flip leaves a path where default-true leaks in (e.g., if schema flips but Pydantic still defaults `True`, `POST /api/profiles` with no value inserts True).
- **Adding a second middleware for `/api/templates/*`.** The existing `AuthMiddleware` already gates `/api/*`. Adding a second auth layer for admin routes creates fragile prefix matching. `/api/templates/*` under admin auth is achieved by simply routing under `/api/` and NOT exempting it `[CITED: .planning/research/STACK.md L176-179]`.
- **Using Pydantic v1 `validator` syntax.** Project is Pydantic v2; use `field_validator` + `@classmethod` (existing pattern in `models.py` L88-91).
- **Inline route handlers in `main.py`.** CLAUDE.md explicit direction: new routes go in `backend/routers/`. main.py is 1026 lines; don't extend it.
- **`try: os.makedirs` before `chown` in entrypoint.** The current `mkdir -p /data/profiles` is correct as-is; don't reorder. chown goes AFTER mkdir but BEFORE stale-process kill.
- **Setting `USER 1000` in Dockerfile.** Out of scope per D-14. `CHROME_UID=${CHROME_UID:-0}` and `chown -R` to that UID; service continues to run as root. Future hardening flips both pieces together.
- **Forgetting `PRAGMA foreign_keys=ON`.** Already enabled in `get_db()` L23 `[VERIFIED]`, but on fresh connections elsewhere it's easy to forget. The FK ON DELETE RESTRICT guard ONLY works with FKs enabled.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization of blueprint | Manual `str()` / custom encoder | `pydantic.BaseModel.model_dump_json()` / `model_validate()` | Pydantic v2 handles all edge cases (Literal unions, None, nested models) `[CITED: pydantic.dev v2 docs]` |
| Template upsert idempotency | Python `try INSERT except SELECT` | `UNIQUE(vendor_type)` + `IntegrityError` catch → 409 | SQLite enforces atomicity; app-layer check-then-insert is racy `[CITED: .planning/research/PITFALLS.md Pitfall 2]` |
| Schema migration tracking | Custom version_table + numbered scripts | `PRAGMA table_info` + conditional `ALTER TABLE` in `init_db()` | Existing pattern; Alembic is not on the table per CLAUDE.md invariant `[VERIFIED: backend/database.py L69-76]` |
| UUID generation | Hand-rolled counter / timestamp concatenation | `uuid.uuid4()` stdlib | Existing pattern in `create_profile` L89 `[VERIFIED]` |
| Token signing (Phase 3 consumer) | Raw `hmac.new(...)` + base64url | `PyJWT` HS256 | Hand-rolled requires claim encoding, TTL parsing, replay logic; PyJWT handles all three `[CITED: .planning/research/STACK.md L102-103]` |
| Copy-to-clipboard in React | `document.execCommand('copy')` | `navigator.clipboard.writeText()` | Modern API; execCommand is deprecated; only fall back for old browser support `[CITED: developer.mozilla.org/Clipboard_API]` |
| Delete-blocked guard | Check on UI only | Server-side 409 + FK RESTRICT | UI-only checks get bypassed via curl; belt-and-suspenders is D-06 lock |

**Key insight:** In this codebase, every "should I build this or use a library?" question has already been answered by the codebase map and the research docs. The Phase 1 work is entirely applied patterns from existing code — no new paradigms.

## Runtime State Inventory

Phase 1 is **not a pure rename/refactor phase**, but it does perform a destructive migration (D-07 wipes old dev data). This inventory documents what state must be considered:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | SQLite `profiles.db` rows pre-refocus (dev/test data only — per D-08 no production deployment exists with the new shape) | Unconditional wipe in `init_db()` when `vendor_type` column absent (D-07). |
| Stored data | `/data/profiles/{id}/` Chromium profile directories for old profile rows | `shutil.rmtree(ignore_errors=True)` for each pre-wipe row (D-07 step b). |
| Live service config | None — no external services keyed by strings renamed in this phase | None — verified by CONTEXT.md scope (no rebrand/rename; only additive). |
| OS-registered state | None — no Task Scheduler / launchd / systemd entries; service is Docker-only | None. |
| Secrets / env vars | `VIEWER_SECRET`, `MAIN_APP_API_KEY`, `MAIN_APP_ORIGIN`, `IDLE_TIMEOUT_SECONDS`, `VIEWER_TOKEN_TTL_SECS` are NEW — no existing values to migrate | Declare in `.env.example` + `docker-compose.yml`; enforce `VIEWER_SECRET` and `MAIN_APP_API_KEY` at startup (D-15, D-17). Existing `AUTH_TOKEN` stays untouched. |
| Build artifacts | None — no compiled binaries or egg-info tied to the schema; Docker image built fresh each deploy | None. |

**Nothing found in "OS-registered state" or "Build artifacts" categories:** State explicitly — verified by reading the CLAUDE.md architecture invariants (Docker single-host, no external process registration) and by running `ls -la .planning/` (no Dockerfile stanza installs agents or services outside the container).

**The canonical question answered:** After every file in the repo is updated for Phase 1, what runtime systems still have "old-style" profile state?

**Answer:** Only SQLite + `/data/profiles/` on disk. Both are wiped by `init_db()` migration step (D-07). No caches, no registries, no external services hold derivative state. The destruction is complete and intentional.

## Common Pitfalls

### Pitfall 1: Migration Partial Failure Leaves Inconsistent State

**What goes wrong:** `init_db()` deletes `/data/profiles/{id}/` directories first, crashes on a permission error, then on retry the DB still has rows but the disks are gone. Warm-pool launches fail because `user_data_dir` doesn't exist.

**Why it happens:** The wipe has two destructive steps (DB rows, disk directories) but no transactional boundary between them. A disk-level permission error (Docker volume UID mismatch before chown lands) can happen.

**How to avoid:**

- Order the wipe: **DB writes first, commit, THEN disk cleanup.** If disk cleanup partially fails, the DB is consistent (no rows) and the orphan directories are harmless — they'll be re-created with fresh UUIDs for new profiles.
- Use `shutil.rmtree(path, ignore_errors=True)` — don't let one permission error abort the whole sweep.
- Log each directory that fails to delete: `logger.warning("Could not remove %s: %s", pdir, exc)`.

**Warning signs:**

- Fresh container startup logs "Schema migration: wiped N rows" but `/data/profiles/` still contains UUID-named directories.
- FK `ON DELETE RESTRICT` errors if the wipe is interrupted mid-`DELETE`.

**Phase to address:** Phase 1 — this is THE migration step.

### Pitfall 2: `UNIQUE` Constraint Collision with Legacy Profile Path

**What goes wrong:** The old `POST /api/profiles` path calls `create_profile(name, **fields)` without `vendor_type` / `vendor_connection_id`. Column defaults are `''` (empty string). Second invocation → UNIQUE constraint violation → 500.

**Why it happens:** `ALTER TABLE ADD COLUMN vendor_type TEXT NOT NULL DEFAULT ''` produces rows where every column is `''` — the UNIQUE index collapses them into one allowed row.

**How to avoid:** Patch `create_profile()` (old helper) to inject a placeholder pair:

```python
def create_profile(name, fingerprint_seed=None, **fields):
    fields["vendor_type"] = fields.get("vendor_type") or "__legacy__"
    fields["vendor_connection_id"] = fields.get("vendor_connection_id") or str(uuid.uuid4())
    # template_id may be NULL for legacy profiles
    # ... rest of existing function ...
```

**Warning signs:**

- Second POST to `/api/profiles` returns 500 "UNIQUE constraint failed".
- Phase 4 cleanup script struggles to distinguish "legitimately created" vs "legacy" profiles.

**Phase to address:** Phase 1 — this is the specific coexistence mechanism for Phase 1 preserving the old UI (D-10).

[ASSUMED] CONTEXT.md does not explicitly spell out this legacy-profile collision handling. The planner should surface this to the user for confirmation; the cheap fix above is the recommended path.

### Pitfall 3: Blueprint JSON Round-Trip Loses Field Defaults

**What goes wrong:** `TemplateBlueprint.model_dump_json()` emits only non-default fields (if `exclude_defaults=True` is used). On round-trip, `model_validate()` sees a sparse dict and re-applies defaults — but if the Pydantic default changed between write and read (e.g., `clipboard_sync: True` → `False` after D-18 lands), the in-flight templates get silently upgraded.

**Why it happens:** Pydantic v2 `model_dump_json` options affect emission; defaults are re-computed on read.

**How to avoid:**

- Use `model_dump_json()` with DEFAULT params (no `exclude_defaults`) — emits all fields including defaults. This is stable across code changes.
- On read, use `model_validate(json.loads(row["blueprint"]))` and rely on Pydantic v2 strict validation.
- Migration note: if Phase 1 is landed against a DB that already has pre-existing templates (it shouldn't — D-08 says dev data only), no backfill is needed. But Phase 4 or v2 changes to the blueprint schema will need this answer.

**Warning signs:**

- Existing template loads with surprising field values after a schema change.
- Round-trip test: `model_validate(json.loads(template.model_dump_json()))` produces different output than `template`.

**Phase to address:** Phase 1 (set the pattern correctly from the start).

### Pitfall 4: Docker `chown` Runs as Wrong User

**What goes wrong:** `chown -R ${CHROME_UID}:${CHROME_UID} /data/profiles` runs inside the container at entrypoint. The container is running as root (no `USER` directive), so chown succeeds. But if someone later flips `USER 1000` in Dockerfile without updating entrypoint, chown fails silently (non-root cannot chown files owned by root) and the fix regresses.

**Why it happens:** chown is non-privileged for non-root; there's no error exit.

**How to avoid:**

- Use `chown -R ... || true` → NO. This masks the error.
- Use `chown -R ... 2>&1 | head -5` → NO. Still loses the exit code.
- **Recommended:** Leave the chown as a simple `chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles` with no error redirect. If it fails, the container entrypoint exits non-zero and the container fails to start loudly. That's the right failure mode.
- Document in `Dockerfile` comments: "chown in entrypoint requires container to run as root (current default). When switching to `USER 1000`, move chown to a setuid helper or pre-build step."

**Warning signs:**

- Chrome logs `Permission denied` for `Default/Cookies-journal` after a profile stop.
- Cookie database does not update across sessions (Pitfall 10 from the main PITFALLS.md).

**Phase to address:** Phase 1.

### Pitfall 5: Fail-Closed Check Runs Too Late

**What goes wrong:** `_check_required_env()` is called inside `lifespan`, which FastAPI invokes when uvicorn starts up — but uvicorn has ALREADY bound the port by the time `lifespan` runs. A brief window exists where port :8080 is open but no routes are mounted.

**Why it happens:** ASGI startup sequence: bind → create app → enter `lifespan` → mount routes. `lifespan` raises after bind.

**How to avoid:**

- Good enough: raising in `lifespan` causes uvicorn to log the error and exit within ~100ms. Port binding without routes returns 502/503 briefly, which is acceptable for a private-network service with no load balancer in front.
- Better: duplicate the check at the top of `main.py` module (outside `lifespan`), so importing `main.py` raises immediately. This catches the problem in unit tests too.

```python
# backend/main.py — at module top level, after os.environ reads:
if not DEV_MODE:
    _missing = [n for n in ("VIEWER_SECRET", "MAIN_APP_API_KEY") if not os.environ.get(n, "").strip()]
    if _missing:
        raise RuntimeError(
            f"Refusing to import: required env vars not set: {', '.join(_missing)}. "
            f"Set them, or set DEV_MODE=1 for local development."
        )
```

This runs at `import backend.main` time — before FastAPI app construction, before port binding.

**Warning signs:**

- Startup log shows "Uvicorn running on http://0.0.0.0:8080" followed by a crash message, with ports briefly accepting connections.
- Unit tests that `from backend.main import app` succeed in environments where they shouldn't.

**Phase to address:** Phase 1.

### Pitfall 6: `vendor_type` Slug Validation Too Permissive

**What goes wrong:** A template is created with `vendor_type="My Vendor Co."` (spaces + punctuation). Phase 2's `POST /sessions` URL becomes `/sessions?vendor_type=My%20Vendor%20Co.` — works, but path-style routing (if ever added) breaks.

**Why it happens:** No validator on `vendor_type` at the Pydantic layer.

**How to avoid:** Add a regex `pattern=r"^[a-z0-9_-]+$"` to `VendorTemplateCreate.vendor_type`:

```python
vendor_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
```

This enforces: lowercase letters, digits, `_`, `-`. Forbids spaces, uppercase, Unicode. Documented in API contract → admins see a clear Pydantic 422 on attempt.

**Warning signs:**

- URL encoding in Main App's `POST /sessions` request bodies.
- Case-sensitivity bugs downstream (`"Shopify"` vs `"shopify"`).

**Phase to address:** Phase 1 (set it right from schema creation).

## Code Examples

Verified patterns from existing codebase and research:

### Schema migration pattern (existing, extended)

Already shown under Pattern 1 above. Key callouts:

- `PRAGMA table_info(profiles)` returns a list of `(cid, name, type, notnull, dflt_value, pk)` rows `[CITED: sqlite.org/pragma.html#pragma_table_info]`
- `ALTER TABLE ADD COLUMN` supports `NOT NULL DEFAULT ''` but cannot add `UNIQUE` — use `CREATE UNIQUE INDEX` `[CITED: sqlite.org/lang_altertable.html]`
- Wipe order: commit DB writes before disk removal.

### Pydantic v2 `field_validator` pattern (existing)

```python
# Existing in backend/models.py L88-91:
@field_validator("clipboard_sync", mode="before")
@classmethod
def coerce_clipboard_sync(cls, v: object) -> bool:
    return v if v is not None else True   # ← D-18: change to False for Phase 1
```

The pattern is `@field_validator(fieldname, mode="before") @classmethod def name(cls, v): ...`. Must be `classmethod`. `mode="before"` runs before type coercion so we can handle None.

### FastAPI 409 with structured detail

```python
# backend/routers/templates.py — delete endpoint:
raise HTTPException(
    status_code=409,
    detail={
        "detail": "Template is in use by 3 profile(s); delete those profiles first.",
        "blocking_profile_ids": ["p1", "p2", "p3"],
    },
)
# FastAPI serializes dict detail as JSON. Frontend reads response.body.detail / body.blocking_profile_ids.
```

**Source:** FastAPI HTTPException accepts any JSON-serializable `detail` `[CITED: fastapi.tiangolo.com/advanced/custom-response]`.

### React polling hook (existing pattern in useProfiles.ts)

```typescript
useEffect(() => {
  refresh();
  const interval = setInterval(refresh, 3000);
  return () => clearInterval(interval);
}, [refresh]);
```

3 seconds matches admin UX expectations; verified against useProfiles.ts L22-26 `[VERIFIED]`.

### Entrypoint chown insertion point

```bash
#!/bin/bash
set -e

# ① Initialize data directories (existing)
mkdir -p /data/profiles

# ② NEW — Fix UID mismatch on mounted volume (OPS-04 / D-14 / Pitfall 10)
#    Runs as root (no USER directive); sets UID on all profile dirs for Chrome's cookie flush.
chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles

# ③ Kill stale processes from previous container runs (existing)
pkill -f 'Xvnc :[0-9]' 2>/dev/null || true
pkill -f 'cloakbrowser.*chrome' 2>/dev/null || true
pkill -f 'chromium.*fingerprint' 2>/dev/null || true
pkill -f xclip 2>/dev/null || true

# ④ Clean Chrome lock files (existing)
find /data/profiles -maxdepth 2 -name 'SingletonLock' -delete 2>/dev/null || true
find /data/profiles -maxdepth 2 -name 'SingletonCookie' -delete 2>/dev/null || true
find /data/profiles -maxdepth 2 -name 'SingletonSocket' -delete 2>/dev/null || true

# ⑤ Remove X11 lock files (existing)
rm -f /tmp/.X1*-lock 2>/dev/null || true

# ⑥ Start FastAPI (existing)
cd /app
echo ""
echo "  CloakBrowser Manager running at http://localhost:8080"
echo ""
exec uvicorn backend.main:app --host 0.0.0.0 --port 8080 --log-level warning
```

Position rationale: chown must happen BEFORE Chrome tries to write (it doesn't in entrypoint, but the later `pkill` + singleton cleanup DO touch files — chown first ensures those operations succeed as non-root shouldn't get that far, but root here can clean files of any owner). Chown AFTER `mkdir -p /data/profiles` because the mkdir creates the directory as root; chown then correctly propagates. `[VERIFIED: .planning/research/PITFALLS.md Pitfall 10]`

### `.env.example` (new file)

```dotenv
# .env.example — CloakBrowser-Manager environment variables
# Copy to .env and fill values for local dev. Keep .env out of git.

# ─ Admin dashboard ──────────────────────────────────────────
# Bearer token / cookie value for admin dashboard authentication.
# If unset, admin routes are open (local dev). Set a strong value in production.
AUTH_TOKEN=

# ─ Main App machine authentication (Phase 2 consumer) ───────
# Shared secret the Main App presents in the X-API-Key header on /sessions/* and /profiles/*.
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
# REQUIRED unless DEV_MODE=1.
MAIN_APP_API_KEY=

# ─ Viewer token signing (Phase 3 consumer) ──────────────────
# HMAC-SHA256 secret for signing short-lived viewer JWTs.
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
# REQUIRED unless DEV_MODE=1.
VIEWER_SECRET=

# Origin allowed in Content-Security-Policy: frame-ancestors on /viewer/* responses.
# Example: https://main-app.example.com
MAIN_APP_ORIGIN=

# Viewer JWT TTL in seconds (default 300). Short TTL limits blast radius of a leaked URL.
VIEWER_TOKEN_TTL_SECS=300

# ─ Warm-pool (Phase 2 consumer) ─────────────────────────────
# Idle timeout in seconds before a warm profile is torn down (default 600).
IDLE_TIMEOUT_SECONDS=600

# ─ Docker runtime ───────────────────────────────────────────
# UID for Chrome profile file ownership. Matches entrypoint.sh chown target.
# Leave 0 (root) unless you flip to USER 1000 in Dockerfile.
CHROME_UID=0

# ─ Development mode ─────────────────────────────────────────
# Set to 1 to bypass fail-closed startup check for MAIN_APP_API_KEY / VIEWER_SECRET.
# LOUD WARNING logged at startup + DEBUG log per request. DO NOT USE IN PRODUCTION.
DEV_MODE=0
```

### `docker-compose.yml` extension

```yaml
services:
  manager:
    build: .
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ~/.cloakbrowser-manager:/data
    environment:
      # Existing
      - AUTH_TOKEN=${AUTH_TOKEN:-}
      # New (Phase 1 scaffolding; consumed in Phases 2-3)
      - MAIN_APP_API_KEY=${MAIN_APP_API_KEY:-}
      - VIEWER_SECRET=${VIEWER_SECRET:-}
      - MAIN_APP_ORIGIN=${MAIN_APP_ORIGIN:-}
      - VIEWER_TOKEN_TTL_SECS=${VIEWER_TOKEN_TTL_SECS:-300}
      - IDLE_TIMEOUT_SECONDS=${IDLE_TIMEOUT_SECONDS:-600}
      - CHROME_UID=${CHROME_UID:-0}
      - DEV_MODE=${DEV_MODE:-0}
```

The `${VAR:-}` vs `${VAR:-default}` distinction matters: required secrets use `${VAR:-}` (empty-string fallback → fail-closed startup check fires); optional config uses `${VAR:-default}` so container boots with sensible defaults.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `python-jose` for JWT | `PyJWT >=2.12.1` | python-jose abandoned 2022; PyJWT 2.12.x actively maintained, 2026-03-13 latest release | Phase 1 dep add; Phase 3 consumer `[VERIFIED: pypi.org 2026-04-22]` |
| Global middleware for per-route auth | Router `dependencies=[Depends(...)]` (Phase 2 machine routes) | FastAPI 0.95+ made `Security` / `APIKeyHeader` first-class | Phase 1 doesn't add; Phase 2 will `[CITED: .planning/research/STACK.md L176-179]` |
| Pydantic v1 `@validator` decorator | Pydantic v2 `@field_validator` + `@classmethod` | Pydantic 2.0 released 2023-06-30 | Already used; extend the pattern `[VERIFIED: backend/models.py L88]` |
| SQLite `TEXT` column + app-layer JSON parse | SQLite 3.45+ `JSONB` binary type | JSONB added 2024-01; Python 3.12 bundles SQLite 3.43 (no JSONB) | Research explicitly recommends stay on `TEXT` — perf difference immeasurable at ~1KB payloads `[CITED: .planning/research/STACK.md L214-217]` |

**Deprecated / outdated:**

- `clipboard_sync: True` default — kept for legacy profiles until Phase 4 cleanup, but new schema and all new profiles use `False`.
- Direct `POST /api/profiles` profile creation — removed entirely in Phase 4 (OPS-01/OPS-02). Phase 1 keeps it working.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Existing `POST /api/profiles` handler will coexist with the new `NOT NULL vendor_type` column by injecting a `__legacy__` placeholder | §create_profile_from_template Signature; §Pitfall 2 | If wrong, the old profile-create UI (which CONTEXT.md D-10 requires to survive Phase 1) starts returning 500 on its second invocation due to UNIQUE collision |
| A2 | The `updated_at` refresh "by app code on every update (no SQLite trigger)" in CONTEXT.md Discretion means Python-level `_now()` call in each UPDATE — not a TRIGGER | §Pattern 5 (implicit in update_template fields dict) | Low; implementation is trivial either way |
| A3 | The Phase 1 UI switcher between Profiles and Templates can be a minimal two-button top-bar and NOT a full navigation redesign | §React Admin UI — nav entry | If wrong, scope creeps into Phase 4's navigation redesign work |
| A4 | `ApiError` class extension to capture response body is allowed (small refactor to existing code) | §api.ts extension | If wrong, the 409 delete-blocked modal can't show blocking profile IDs cleanly; workaround is parsing error message strings |
| A5 | `CHROME_UID` env var is a NEW environment variable that docker-compose.yml and .env.example should declare (it's referenced in entrypoint.sh but not yet declared anywhere) | §docker-compose.yml extension; §.env.example | If wrong, minor (declaring it doesn't hurt); if CONTEXT.md wants it set somewhere else, small config change |
| A6 | The secondary module-level fail-closed check (import-time raise) is desired in addition to the lifespan check | §Pattern 5; §Pitfall 5 | If wrong, one of the two paths is redundant; no harm, only code duplication |
| A7 | Blueprint JSON should be emitted with all fields (not `exclude_defaults`) for stable round-trips across code changes | §Pitfall 3 | If wrong, a future change to a Pydantic default silently rewrites all existing templates on read |

**These items should be confirmed by discuss-phase or flagged for user sign-off before the planner locks them into tasks.** Items A1 and A3 are the highest-risk — they make architectural choices beyond what CONTEXT.md explicitly decided.

## Open Questions

1. **Does the legacy profile path (existing `POST /api/profiles`) need to be disabled in Phase 1, or left working with a `__legacy__` placeholder vendor_type?**
   - What we know: CONTEXT.md D-10 says "Existing profile CRUD UI survives Phase 1 intact". D-08 says migration wipe is acceptable. CLAUDE.md architecture invariant says `(vendor_type, vendor_connection_id)` uniqueness.
   - What's unclear: Whether "UI survives" also means "backend route must succeed" or just "the UI doesn't 404". If only UI, the backend route can be disabled in Phase 1 with the UI showing errors.
   - Recommendation: Keep the backend route working with the `__legacy__` placeholder (Pitfall 2 fix). Cheapest path; minimally invasive; lets Phase 4 cleanup find and purge legacy rows by a clean marker.

2. **Is a single UNIQUE index on `(vendor_type, vendor_connection_id)` sufficient, or should we add separate indexes for common query patterns?**
   - What we know: D-05 locks the UNIQUE constraint; Phase 2 will add `upsert_profile_by_vendor()` which does `WHERE vendor_type=? AND vendor_connection_id=?` (research ARCHITECTURE.md L132-134).
   - What's unclear: Whether `list_profiles_by_template(template_id)` needs its own index for the delete-guard check. At <20 profiles, full table scan is ~nothing.
   - Recommendation: Single UNIQUE index now. Add `idx_profiles_template_id` if Phase 4 ops UI shows measurable latency on template listing.

3. **Should `TemplateForm.tsx` include Template-level fields (label, notes) separately from the blueprint sub-form, or inline everything?**
   - What we know: D-01 has `label` and `notes` as template-level columns (sibling of `blueprint`). D-11 lists sections starting with "Identity (vendor_type, label, notes)" — so the Identity section contains both template-level fields AND the vendor_type key.
   - What's unclear: Pedagogically whether `blueprint.` fields are presented as a nested group vs flat form. CONTEXT.md specifies section-grouped mirroring ProfileForm; ProfileForm is flat on the data model even though visually sectioned.
   - Recommendation: Flat form state (`{vendor_type, label, notes, ...blueprint}`), submit mapped into nested shape (`{vendor_type, label, notes, blueprint: {...}}`). Mirrors the existing ProfileForm internal shape; zero UX friction.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Backend runtime | ✓ | 3.12 (locked per PROJECT.md) | — |
| SQLite (bundled with Python 3.12) | Schema migration + all CRUD | ✓ | 3.43.x (Python 3.12 stdlib) | — |
| `sqlite3` supports `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` | Migration pattern | ✓ | SQLite 3.3+ for PRAGMA, 3.2+ for ALTER | — |
| `sqlite3` supports `PRAGMA foreign_keys=ON` + `ON DELETE RESTRICT` | FK enforcement | ✓ | SQLite 3.6.19+ (all modern versions) | — |
| `pydantic >=2.0` `field_validator` + `model_dump_json` | Blueprint models | ✓ | `>=2.0` in `backend/requirements.txt` | — |
| FastAPI `APIRouter` + `app.include_router` | New templates router | ✓ | FastAPI 0.115+ | — |
| Node 20 + Vite 6 (frontend build) | React UI | ✓ | Locked per Dockerfile stage 1 | — |
| `lucide-react` `AlertTriangle` icon | Amber warning badge | ✓ | Already installed (App.tsx uses `Lock`, `PanelLeftClose`, `PanelLeft`) | — |
| PyJWT 2.12.1 on PyPI | Phase 1 dep add (Phase 3 consumer) | ✓ | 2.12.1 (2026-03-13) | — |
| Docker `chown` (root privilege) | entrypoint.sh fix | ✓ | Container runs as root (no `USER` directive) | — |

**All Phase 1 dependencies are available on the target environment.** No blockers, no fallback paths required.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing `AuthMiddleware` (bearer/cookie) guards `/api/templates/*`; admin-only. Phase 2 adds `APIKeyHeader` for machine routes (out of scope for Phase 1). |
| V3 Session Management | partial | Admin `auth_token` cookie already set `HttpOnly; SameSite=Strict; Secure` on HTTPS `[VERIFIED: backend/main.py L408-415]`. No new session mechanism in Phase 1. |
| V4 Access Control | yes | Template delete guard (two-layer: 409 + FK ON DELETE RESTRICT). Strict router segregation — `/api/templates/*` admin-only; no `_AUTH_EXEMPT` entry. |
| V5 Input Validation | yes | Pydantic v2 `field_validator` + `pattern` regex on `vendor_type`. `TemplateBlueprint` enforces typed shape for all blueprint fields. |
| V6 Cryptography | yes (prep) | PyJWT >= 2.12.1 added to requirements.txt (not used in Phase 1 runtime; Phase 3 consumer). `VIEWER_SECRET` env var declared + fail-closed startup. |
| V9 Communications | N/A | HTTPS termination handled by reverse proxy (not in scope). |
| V14 Configuration | yes | `.env.example` documents every required env var; `docker-compose.yml` declares them; fail-closed startup refuses insecure defaults. |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JSON injection in blueprint field values | Tampering | Pydantic v2 type coercion + Literal unions for enums (e.g., `platform`, `human_preset`) reject unexpected values before SQLite sees them. |
| SQL injection via `vendor_type` or `template_id` in admin inputs | Tampering | All DB access uses parameterized queries (`?` placeholders) — existing pattern `[VERIFIED: backend/database.py L102-125]`. Never string-concatenate user input into SQL. |
| Missing secret in production (credential exposure) | Information Disclosure | Fail-closed startup (SEC-06 / D-17) — service refuses to start without `VIEWER_SECRET` + `MAIN_APP_API_KEY`. |
| Clipboard credential leak to Main App | Information Disclosure | `clipboard_sync=false` default (SEC-05 / D-18). Clipboard-read scope restriction lands in Phase 3; Phase 1 only flips defaults. |
| Schema migration destroys production data | Denial of Service | D-08 explicitly acknowledges old schema is dev/test only. Log row+dir counts loudly. No safety flag needed (deliberate). |
| Template delete cascades into live profiles | Denial of Service | FK `ON DELETE RESTRICT` + app-layer 409 with blocking_profile_ids — two layers must both pass. |
| Unbounded `blueprint` JSON size causes DB bloat | Denial of Service | Pydantic field types bound each field; `launch_args: list[str]` is unbounded in count — consider adding `Field(max_length=32)` for belt-and-suspenders. [ASSUMED] |
| Unauthenticated template enumeration | Information Disclosure | `GET /api/templates` sits behind `AuthMiddleware` — admin-auth required. No public exposure. |

## Sources

### Primary (HIGH confidence)

- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/.planning/phases/01-schema-templates-and-security-foundations/01-CONTEXT.md` — 19 locked decisions
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/.planning/research/STACK.md` — PyJWT, SQLite JSON rationale, APIKeyHeader pattern
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/.planning/research/PITFALLS.md` — Pitfalls 2, 7, 10, 11
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/.planning/research/ARCHITECTURE.md` — Template snapshot strategy, data flow
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/.planning/research/FEATURES.md` — Vendor Template CRUD table stakes
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/.planning/research/SUMMARY.md` — Phase 1 build order
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/backend/database.py` — existing migration + CRUD patterns
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/backend/models.py` — existing Pydantic patterns
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/backend/main.py` — AuthMiddleware, lifespan, existing routes
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/frontend/src/components/ProfileForm.tsx` — section-grouped form pattern
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/frontend/src/hooks/useProfiles.ts` — polling hook pattern
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/frontend/src/lib/api.ts` — typed fetch client + ApiError
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/frontend/src/App.tsx` — view dispatcher
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/entrypoint.sh` — existing startup sequence
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/Dockerfile` — multi-stage build
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/docker-compose.yml` — existing env var declarations
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/CLAUDE.md` — project invariants and security rules
- `[VERIFIED]` `/Users/troy/Code/_kickback/CloakBrowser-Manager/.planning/config.json` — nyquist_validation=false (skip Validation section)
- `[VERIFIED]` PyPI PyJWT 2.12.1 (released 2026-03-13; verified via WebSearch 2026-04-22)

### Secondary (MEDIUM confidence)

- `[CITED]` sqlite.org/lang_altertable.html — ALTER TABLE restrictions (NOT NULL DEFAULT workaround, UNIQUE not addable)
- `[CITED]` sqlite.org/pragma.html#pragma_table_info — PRAGMA return shape
- `[CITED]` fastapi.tiangolo.com/advanced/events/ — lifespan context contract
- `[CITED]` fastapi.tiangolo.com/advanced/custom-response — HTTPException with dict detail
- `[CITED]` developer.mozilla.org/Clipboard_API — navigator.clipboard.writeText availability

### Tertiary (LOW confidence)

None — every claim is verified against existing code or cited to an official source.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — every library is already in the codebase except PyJWT, which is verified current on PyPI.
- Architecture: **HIGH** — all patterns are extensions of existing code (init_db migration, Pydantic models, APIRouter, React hook shape).
- Pitfalls: **HIGH** — all six pitfalls documented here either (a) have direct code-level prevention steps, or (b) are explicitly acknowledged in CONTEXT.md.
- UI patterns: **HIGH** — mirroring ProfileForm / useProfiles / api.ts shapes verified against actual files.
- [ASSUMED] items: 7 assumptions logged; 2 (A1 legacy profile coexistence, A3 nav switcher scope) are architectural and should be confirmed before the planner locks tasks.

**Research date:** 2026-04-22

**Valid until:** 30 days (2026-05-22) for stable patterns; PyJWT version should be re-verified if Phase 3 is delayed past 2026-06-01.
