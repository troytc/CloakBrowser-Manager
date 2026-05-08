---
phase: 01-schema-templates-and-security-foundations
verified: 2026-05-08T09:40:00Z
status: gaps_found
score: 4/5 success criteria verified
overrides_applied: 0
gaps:
  - truth: "An admin can open the dashboard, navigate to Templates, and create/edit/delete a vendor template with all blueprint fields; duplicates on vendor_type are rejected with a clear error."
    status: partial
    reason: "Backend CRUD + AuthMiddleware + duplicate-409 all verified end-to-end. Frontend components and wiring are present and structurally correct, but BL-02 (stale-closure in handleDeleteTemplateFromForm) breaks the planned 'form stays open while modal blocks the delete' UX. Modal still surfaces the 409, so the failure mode is form-unmount-then-modal-overlay rather than total breakage. UI flow has not been tested in a live browser."
    artifacts:
      - path: "frontend/src/App.tsx"
        issue: "Line 142-149: handleDeleteTemplateFromForm awaits removeTemplate then reads deleteBlocked from the render-time closure. removeTemplate resolves (does not throw on 409) and synchronously calls setDeleteBlocked, but the closure still sees the prior render's deleteBlocked=null, so setSelectedTemplateId(null) + setTemplateView('empty') fire and the form unmounts before the modal mounts. Modal still appears (state did update), but the locked UX of 'form stays open' is broken."
    missing:
      - "Refactor useTemplates.remove to return a discriminated result (e.g. {blocked: boolean}) so the caller can branch reliably without reading stale closure state, then update App.tsx handleDeleteTemplateFromForm to gate the form unmount on the returned result."
      - "Add a live-browser smoke test (or Vitest + Testing Library) that delete-from-form against a template with attached profiles keeps the form mounted while the modal is open."

  - truth: "Deleting a template with existing profiles is blocked by the service with a descriptive error; deleting one with no profiles succeeds."
    status: failed
    reason: "Service-side blocking IS verified (TestClient run: 409 with structured detail + blocking_profile_ids; 200 {ok:true} after profiles removed; FK ON DELETE RESTRICT also catches the race). However, BL-01 leaves a clipboard_sync=1 default on the legacy ALTER TABLE migration in backend/database.py:86, which directly contradicts CLAUDE.md security rule 2 ('clipboard_sync defaults to false on every vendor template and every profile') and Plan 01-01's own acceptance criterion (`grep -c 'clipboard_sync BOOLEAN DEFAULT 1' backend/database.py == 0`). The wipe block immediately following clears any pre-D-18 row, so no live row currently leaks; but the column-level DEFAULT persists for any future INSERT path that omits the column. Listed under this success criterion because Success Criterion 2 is the closest umbrella for SEC-06 invariants in this phase."
    artifacts:
      - path: "backend/database.py"
        issue: "Line 86: `ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1` — must be DEFAULT 0 to match CREATE TABLE default and CLAUDE.md security rule 2. Plan 01-01 explicitly required `grep -c 'clipboard_sync BOOLEAN DEFAULT 1' backend/database.py` to return 0; current value is 1."
    missing:
      - "Change line 86 to `ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 0`."
      - "Optionally add a follow-on `UPDATE profiles SET clipboard_sync = 0 WHERE clipboard_sync = 1` to forcibly normalise any pre-existing rows on a database migrated under the old default before the wipe block runs."
      - "Re-run the grep guard: `grep -c 'clipboard_sync BOOLEAN DEFAULT 1' backend/database.py` must return 0."

human_verification:
  - test: "Open the admin dashboard at /, log in if AUTH_TOKEN is set, click the Templates pill in the top bar, click 'New Template', fill in vendor_type='shopify' + label='Shopify' + leave other fields default, click Create. Confirm the new template appears in the list."
    expected: "Form unmounts back to the empty/list view; new row appears in the table with vendor_type=shopify and label=Shopify; no error banner."
    why_human: "Visual confirmation of full TMPL-01 user flow including segmented switcher, form layout, and list refresh — cannot be observed via grep or TestClient."
  - test: "From the Templates list, click Edit on an existing template, change Label, click Save. Confirm the row updates."
    expected: "Form returns to list view; row label updates (within 3s polling refresh)."
    why_human: "Confirms TMPL-03 edit-without-mutating-snapshot UX end-to-end; only TestClient-level verification was run automatically."
  - test: "Create a template, then via API or another flow create a profile that references it (Phase 2 surface), then attempt to Delete the template from the row's Delete button. Click OK on the confirm. Observe the DeleteBlockedModal."
    expected: "DeleteBlockedModal appears with title 'Cannot delete template', the template's vendor_type quoted, the count of attached profiles, the list of profile IDs, a 'Copy IDs' button (toggles to 'Copied' for 2s on click), and a Close button. Escape key dismisses."
    why_human: "Visual + interactive confirmation. Note BL-02: when this modal is triggered from the Edit Template form's own Delete button, the form unmounts under the modal — confirm the failure mode is acceptable for v1 or schedule the fix from gaps[0]."
  - test: "After closing the DeleteBlockedModal, delete the blocking profile (Phase 2 surface or direct DB), return to Templates, attempt the Delete again."
    expected: "Confirm dialog → row disappears from the list; no modal."
    why_human: "Confirms TMPL-04 success path (delete with no profiles succeeds) end-to-end."
  - test: "Stop the docker container with `docker compose down`, then change the host UID owning ~/.cloakbrowser-manager (e.g., `sudo chown -R 1000:1000 ~/.cloakbrowser-manager`), then `docker compose up`. Watch the entrypoint logs and the first Chromium launch on a wake."
    expected: "Service starts cleanly (entrypoint chown -R brings ownership back to CHROME_UID before uvicorn exec). On first profile launch, Chromium can write cookies (no 'Failed to flush cookies' / EACCES errors)."
    why_human: "OPS-04 is fundamentally a Docker volume + UID interaction; can only be verified by container-recreate-with-mismatched-volume-UID test. Not reproducible in a host-Python TestClient run."
  - test: "Try to start the service WITHOUT MAIN_APP_API_KEY or VIEWER_SECRET set in the docker-compose .env, with DEV_MODE unset. Watch logs."
    expected: "Container exits with a RuntimeError naming both VIEWER_SECRET and MAIN_APP_API_KEY as missing, and pointing operator at DEV_MODE=1. Uvicorn does not bind port 8080."
    why_human: "End-to-end docker-compose lifecycle confirmation that the lifespan-level RuntimeError actually halts container startup (not just the in-process check). The in-process check is verified automatically; container-level fail-closed is verified visually."

deferred: []
---

# Phase 01 Verification Report

**Phase Goal:** Operators can manage vendor templates via the admin dashboard, and the foundational schema, env vars, and security defaults are in place for all subsequent phases.

**Verified:** 2026-05-08T09:40:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Success Criteria (from ROADMAP)

| #   | Success Criterion | Status | Evidence |
| --- | ----------------- | ------ | -------- |
| 1 | Admin creates/edits/deletes templates via dashboard with full blueprint; duplicates on vendor_type rejected with clear error. | ⚠️ PARTIAL | Backend CRUD + duplicate 409 verified end-to-end via FastAPI TestClient. Frontend components present and structurally correct (TemplateForm 471 lines / 7 sections in correct order, TemplateList 140 lines, DeleteBlockedModal 91 lines, App.tsx surface switcher wired). BL-02 in App.tsx breaks form-stays-open UX during delete-from-edit. |
| 2 | Delete blocked when profiles exist (descriptive error); succeeds when none. | ✗ FAILED (downgrade) | Two-layer guard verified: (a) app-layer 409 with `{detail, blocking_profile_ids}` ✓; (b) FK ON DELETE RESTRICT IntegrityError catch ✓; (c) 200 `{ok:true}` after profiles cleared ✓. **Failure: BL-01 — backend/database.py:86 still has `DEFAULT 1` on the legacy clipboard_sync ALTER, violating CLAUDE.md security rule 2 and Plan 01-01's own acceptance criterion.** Listed here because Success Criterion 2 is the umbrella for SEC-06 invariants in this phase. |
| 3 | Profile created from template inherits all template fields as snapshot; updating template does not change profile. | ✓ VERIFIED | TestClient run: created template with screen_width=1920, created profile from template, PUT template to screen_width=1280, profile row still shows screen_width=1920. `create_profile_from_template` snapshot-copies 13 blueprint fields and generates fresh fingerprint_seed. TMPL-05 satisfied. |
| 4 | Service refuses to start when VIEWER_SECRET or MAIN_APP_API_KEY is absent/blank in production; .env.example documents all new vars. | ✓ VERIFIED | `_check_required_env()` raises RuntimeError naming both vars when missing, returns silently when both present, logs WARNING when DEV_MODE=1. Whitespace-only is treated as missing. DEV_MODE parser accepts `1/true/yes` (case-insensitive, trimmed). Lifespan calls `_check_required_env()` before `db.init_db()`. `.env.example` exists at repo root, tracked in git, documents 8 vars (AUTH_TOKEN, MAIN_APP_API_KEY, VIEWER_SECRET, MAIN_APP_ORIGIN, VIEWER_TOKEN_TTL_SECS, IDLE_TIMEOUT_SECONDS, CHROME_UID, DEV_MODE). |
| 5 | After container recreate with UID mismatch, Chromium flushes cookies without permission errors (entrypoint chown runs before service start). | ✓ VERIFIED (static) | entrypoint.sh:9 has `chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles`. Awk line-order check confirms ordering: mkdir(line 5) < chown(line 9) < pkill(line 12). No `\|\| true` swallow on chown. `set -e` preserved on line 2. `bash -n entrypoint.sh` succeeds. **Note:** Live container-recreate-with-mismatched-UID test routed to human verification (cannot be reproduced in a host-Python harness). |

**Score:** 4/5 success criteria verified (1 PARTIAL with downgrade due to BL-01 surfacing as a SEC-06 violation; UI flow needs human spot-check)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/database.py` | vendor_templates table + 8 helpers + create_profile_from_template + UNIQUE index + FK RESTRICT + clipboard_sync default 0 | ⚠️ STUB-FREE BUT POLLUTED | All helpers present and tested. CREATE TABLE default is 0. Legacy ALTER on line 86 still has DEFAULT 1 (BL-01). |
| `backend/models.py` | TemplateBlueprint + VendorTemplateCreate (with vendor_type slug regex) + VendorTemplateUpdate + VendorTemplateResponse + TemplateDeleteBlockedResponse + clipboard_sync flipped on ProfileCreate/ProfileResponse | ✓ VERIFIED | All 5 classes exist with correct shape. Slug regex `^[a-z0-9_-]+$` enforced. clipboard_sync=False on ProfileCreate (L27), ProfileResponse (L86), TemplateBlueprint (L163). field_validator coerces null→False on both ProfileResponse (L91) and TemplateBlueprint (L172). |
| `backend/requirements.txt` | PyJWT>=2.12.1 | ✓ VERIFIED | Present at line 7; exact match. |
| `entrypoint.sh` | chown between mkdir and pkill, no swallow, set -e preserved | ✓ VERIFIED | Order verified by awk; no `\|\| true` on chown; `set -e` on line 2; uvicorn exec preserved on line 30. |
| `docker-compose.yml` | 8 env var declarations with correct fallback semantics | ✓ VERIFIED | All 8 entries present (AUTH_TOKEN, MAIN_APP_API_KEY, VIEWER_SECRET, MAIN_APP_ORIGIN, IDLE_TIMEOUT_SECONDS=600, VIEWER_TOKEN_TTL_SECS=300, CHROME_UID=0, DEV_MODE). YAML parses cleanly. |
| `.env.example` | 8 documented env vars with placeholder values, tracked in git, .env in .gitignore | ✓ VERIFIED | 8 KEY=VALUE assignments, section dividers, `change-me-...` placeholders for secrets. `.env.example` is tracked, `.env` is in .gitignore. |
| `backend/main.py` | _check_required_env + lifespan integration + templates_router registration after AuthMiddleware + _AUTH_EXEMPT unchanged | ✓ VERIFIED | _check_required_env defined at L67; lifespan calls it on L412 before db.init_db(); templates_router imported at L40 and registered on L423 immediately after `app.add_middleware(AuthMiddleware)` on L422. _AUTH_EXEMPT unchanged on L92. |
| `backend/routers/templates.py` | APIRouter with 5 endpoints + two-layer delete guard + IntegrityError → 409 | ✓ VERIFIED | All 5 endpoints, prefix=/api/templates. List, create (201 + duplicate 409), get/put/delete (404 + 409 with blocking_profile_ids + IntegrityError catch). |
| `backend/routers/__init__.py` | empty package marker | ✓ VERIFIED | Exists. |
| `frontend/src/lib/api.ts` | TemplateBlueprint, VendorTemplate, VendorTemplateCreateData, TemplateDeleteBlockedError types + ApiError.body + api.templates namespace | ✓ VERIFIED | All 4 types exported (L74–112). ApiError exported with `body?: unknown` (L114-122). request<T> forwards body on both 401 and non-401 paths. api.templates namespace with 5 typed CRUD functions (L202-217). |
| `frontend/src/hooks/useTemplates.ts` | 3s polling + CRUD + 409 delete-blocked carve-out | ✓ VERIFIED | 170 lines. Hook signature matches. setInterval(refresh, 3000) on L97. ApiError + status 409 + isDeleteBlockedBody guard on L143. Hook actually accepts BOTH flat and FastAPI-nested 409 body shapes (defensive); readBlockingIds extracts from either. |
| `frontend/src/components/TemplateForm.tsx` | 7 sections + amber clipboard warning + clipboard_sync=false default | ✓ VERIFIED | 471 lines. EMPTY_BLUEPRINT.clipboard_sync=false (L24). 7 section headings present at lines 160 (Identity), 206 (Fingerprint), 250 (Screen), 303 (Gpu), 345 (Behavior), 428 (Proxy), 444 (Security). Amber warning copy "Clipboard sync is off by default for a reason." present once. "passwords and 2FA codes" risk language present. AlertTriangle imported and used. |
| `frontend/src/components/TemplateList.tsx` | empty state + table with edit/delete | ✓ VERIFIED | 140 lines. "No templates yet" + "Create your first vendor template" + "New Template" CTA twice (empty + header). Vendor Type / Label / Created columns + edit/delete actions. |
| `frontend/src/components/DeleteBlockedModal.tsx` | role=dialog + aria-modal + aria-labelledby + Copy IDs + Escape dismiss + initial focus | ✓ VERIFIED | 91 lines. role="dialog" + aria-modal="true" + aria-labelledby="delete-blocked-title". Singular/plural handling. navigator.clipboard.writeText on L34. 2-second "Copied" toggle on L36. Escape key listener on L24-30. Initial focus to copy button on L20-22. **Minor:** missing aria-describedby (IN-05 in code review) — does not block goal. |
| `frontend/src/App.tsx` | Surface switcher (Profiles first) + content dispatch + DeleteBlockedModal mount | ⚠️ WIRED-WITH-BUG | Surface switcher in top bar with Profiles before Templates (L234-261). useTemplates() hook called (L108-117). DeleteBlockedModal rendered when deleteBlocked is non-null (L381-387). **BL-02:** handleDeleteTemplateFromForm reads stale `deleteBlocked` closure (L142-149). |
| `frontend/src/components/ProfileForm.tsx` | clipboard_sync default flipped to false | ✓ VERIFIED | grep returns: L67 `clipboard_sync: false`, L97 reads existing profile.clipboard_sync, L440 `checked={form.clipboard_sync ?? false}`. No `clipboard_sync: true` in file. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| backend/main.py::lifespan | _check_required_env() | called before db.init_db() | ✓ WIRED | Line 412 calls _check_required_env, line 413 calls db.init_db. Order verified. |
| backend/main.py | templates_router | from .routers.templates + app.include_router AFTER add_middleware | ✓ WIRED | L40 import + L423 include_router immediately after L422 add_middleware. |
| AuthMiddleware | /api/templates/* | _AUTH_EXEMPT does not contain /api/templates | ✓ WIRED | Live TestClient run: GET /api/templates with no Authorization → 401; with `Bearer test-token-abc` → 200. |
| backend/database.py::create_profile_from_template | profiles row | snapshot copy of blueprint + random fingerprint_seed (10000-99999) | ✓ WIRED | TestClient run confirms snapshot independence: PUT to template's screen_width=1280 leaves existing profile's screen_width=1920. |
| backend/routers/templates.py::delete_template | db.list_profiles_by_template + 409 + IntegrityError catch | two-layer guard per D-06 | ✓ WIRED | TestClient run: 409 with `{detail, blocking_profile_ids}` when profiles attached. Sqlite IntegrityError handler present. FK ON DELETE RESTRICT verified by direct DB delete attempt. |
| backend/routers/templates.py::create_template | db.create_template + IntegrityError → 409 | UNIQUE(vendor_type) | ✓ WIRED | Duplicate POST returns 409 with exact copy "A template for vendor_type 'shopify' already exists". |
| frontend/src/hooks/useTemplates.ts::remove | api.templates.remove + ApiError 409 → setDeleteBlocked | runtime type guard | ✓ WIRED | isDeleteBlockedBody handles BOTH flat and nested 409 shapes (more defensive than plan required). |
| frontend/src/App.tsx | useTemplates + TemplateList + TemplateForm + DeleteBlockedModal | surface === "templates" branch + dispatch on templateView | ⚠️ WIRED-WITH-BUG | All components rendered correctly per surface/templateView state. BL-02 stale-closure breaks delete-from-edit-form unmount logic. |
| entrypoint.sh | /data/profiles ownership | chown -R ${CHROME_UID:-0} BEFORE pkill | ✓ WIRED | Line ordering and `set -e` confirmed. |
| TemplateForm Security section | amber warning + clipboard_sync checkbox | warning ABOVE checkbox | ✓ WIRED | AlertTriangle + amber-500/10 bg + amber-500/30 border + locked copy block precede the checkbox label. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| TemplateList.tsx | templates | useTemplates() → api.templates.list() → request<VendorTemplate[]>("/api/templates") → backend/routers/templates.py::list_templates → db.list_templates() → SELECT FROM vendor_templates | Yes (TestClient confirmed real DB query, real rows returned) | ✓ FLOWING |
| TemplateForm.tsx | blueprint state | template prop or EMPTY_BLUEPRINT (clipboard_sync=false) | Yes — initial state hydrated from VendorTemplate.blueprint when editing; create handler ships full blueprint to api.templates.create | ✓ FLOWING |
| DeleteBlockedModal.tsx | blockingIds prop | useTemplates.deleteBlocked.blockingIds (set on 409 response with real profile IDs from /api/templates/{id}::list_profiles_by_template) | Yes (TestClient confirmed real profile IDs surface in 409 body) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Schema migration creates vendor_templates table on fresh DB and idempotent re-init | python3 -c "from backend import database as db; db.DATA_DIR=...; db.init_db(); db.init_db()" | First call: vendor_templates exists, profiles has vendor_type/vendor_connection_id/template_id, idx_profiles_vendor_pair exists. Second call: no error, no duplicate index. | ✓ PASS |
| Templates router CRUD round-trip via FastAPI TestClient | python3 (embedded in 01-04 verify) | 201 create, 409 duplicate, 422 invalid slug, 200 GET, 404 unknown, 200 PUT, 409 delete-blocked + blocking_profile_ids, 200 delete after profiles cleared | ✓ PASS |
| TMPL-05 snapshot independence | PUT template after creating profile-from-template | Profile screen_width frozen at 1920 even after template updated to 1280 | ✓ PASS |
| FK ON DELETE RESTRICT | direct DELETE FROM vendor_templates while profile references | sqlite3.IntegrityError raised | ✓ PASS |
| Legacy create_profile() coexists with UNIQUE(vendor_type, vendor_connection_id) | two back-to-back create_profile(name='legacy-N') calls | Both succeed, distinct vendor_connection_id (uuid4 placeholders) | ✓ PASS |
| Fail-closed startup with both secrets missing in production mode | _check_required_env() with VIEWER_SECRET=None, MAIN_APP_API_KEY=None, DEV_MODE=False | RuntimeError mentioning VIEWER_SECRET, MAIN_APP_API_KEY, DEV_MODE=1 escape hatch | ✓ PASS |
| DEV_MODE bypass logs warning, no raise | _check_required_env() with both secrets None and DEV_MODE=True | WARNING logged naming missing vars; returns None | ✓ PASS |
| AuthMiddleware blocks /api/templates without Authorization | TestClient with AUTH_TOKEN=test-token-abc, no Authorization header | 401 (vs. 200 with `Bearer test-token-abc`) | ✓ PASS |
| TypeScript strict-mode compile | npx tsc --noEmit --skipLibCheck | Cannot run in current verification environment (node_modules absent), but plan 01-06 SUMMARY records "ts_compile: clean (0 errors)" and "vite_build: clean (1637 modules in 1.38s)" from execution-time run. | ? SKIP (environment) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| TMPL-01 | 01-01, 01-05, 01-06 | Admin can create vendor templates via dashboard with full blueprint | ⚠️ PARTIAL | Backend + frontend + UI wiring all present. Live UX flow routed to human verification. BL-02 flags a delete-from-form UX bug but does not break create/edit. |
| TMPL-02 | 01-04 | Templates uniquely keyed by vendor_type; DB rejects duplicates | ✓ SATISFIED | UNIQUE constraint on column + IntegrityError caught and surfaced as 409 with locked copy. TestClient verified. |
| TMPL-03 | 01-04 | Admin can edit vendor templates; edits don't mutate existing profiles | ✓ SATISFIED | PUT /api/templates/{id} with new blueprint verified to leave profile snapshot row unchanged. |
| TMPL-04 | 01-04 | Admin can delete; blocked while profiles exist | ✓ SATISFIED | Two-layer delete guard verified end-to-end (app-layer 409 + FK RESTRICT IntegrityError catch + 200 success path). |
| TMPL-05 | 01-01 | Template fields snapshot-copied at profile creation; warm pool never re-reads | ✓ SATISFIED | create_profile_from_template snapshot-copies 13 fields + generates fresh fingerprint_seed. Snapshot independence verified by PUT-then-read. Phase 2 will consume this helper. |
| SEC-05 | 01-03 | Service refuses to start when VIEWER_SECRET or MAIN_APP_API_KEY unset/blank in production | ✓ SATISFIED | _check_required_env raises RuntimeError in lifespan before db.init_db(); DEV_MODE parser strict; verified across 4 cases. |
| SEC-06 | 01-01, 01-02, 01-03, 01-06 | clipboard_sync defaults to false in template schema and any profile created without explicit value | ⚠️ PARTIAL | 4 of 5 touchpoints flipped (CREATE TABLE default, ProfileCreate, ProfileResponse + coerce, TemplateBlueprint default + validator, ProfileForm React state, TemplateForm React state, create_profile fallback). **BL-01: legacy ALTER on line 86 still has DEFAULT 1.** Wipe block masks current impact, but the column-level DEFAULT survives the wipe. |
| OPS-03 | 01-01 | Schema migration adds vendor_templates table + new profiles columns | ✓ SATISFIED | Migration wipe block runs once on legacy DB, adds vendor_type/vendor_connection_id/template_id with FK ON DELETE RESTRICT, creates UNIQUE INDEX. Idempotent. |
| OPS-04 | 01-02 | Docker entrypoint chown -R to CHROME_UID before service start | ✓ SATISFIED (static) | Line ordering verified; `set -e` preserved; no swallow. Live container-recreate test routed to human verification. |
| OPS-05 | 01-02 | docker-compose.yml + .env.example document new env vars | ✓ SATISFIED | All 8 vars (5 new + 3 existing/related) declared in docker-compose.yml with correct fallback semantics; .env.example documents all 8 with placeholder values + section dividers. |

**Coverage:** 8/10 SATISFIED, 2/10 PARTIAL (TMPL-01, SEC-06). No ORPHANED requirements — all 10 phase requirement IDs are claimed by at least one plan, and REQUIREMENTS.md maps no additional IDs to Phase 1.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| backend/database.py | 86 | `ALTER TABLE … DEFAULT 1` for clipboard_sync | 🛑 Blocker | Violates CLAUDE.md security rule 2 + Plan 01-01 acceptance criterion. Currently dormant (wipe block clears affected rows + create_profile passes explicit value), but leaves a long-tail footgun. **Mapped to gap[1].** |
| frontend/src/App.tsx | 142-149 | Stale-closure read of `deleteBlocked` after async action | ⚠️ Warning | Breaks the planned "form stays open while modal blocks delete" UX. Modal still surfaces 409. **Mapped to gap[0].** |
| backend/database.py | 331, 442 | `assert result is not None` after get_*() — stripped under `python -O` | ℹ️ Info | IN-03 in code review. Phase 1 acceptable. |
| backend/database.py | 335-356 | update_template always bumps updated_at even when no recognized fields | ℹ️ Info | WR-04 in code review. Currently unreachable (Pydantic guards), but a hazard for future callers. |
| backend/routers/templates.py | 24 | Unused logger | ℹ️ Info | IN-01 in code review. Cosmetic. |
| frontend/src/lib/api.ts | 144-148 | 422 detail (Pydantic list) → falls back to "Unprocessable Entity" | ⚠️ Warning | WR-03 in code review. User who types invalid slug sees generic toast, not actionable error. |
| frontend/src/components/DeleteBlockedModal.tsx | 42-48 | Missing aria-describedby | ℹ️ Info | IN-05. Plan 01-06 SUMMARY claims it; reality is aria-modal + aria-labelledby only. Screen-reader minor regression. |
| .env.example | 11 | Comment says API key guards `/profiles/*` (Phase 2 ambiguity) | ⚠️ Warning | WR-06. Risks Phase 2 misimplementation if comment is taken literally — CLAUDE.md rule 3 keeps /profiles/* on admin auth. |
| entrypoint.sh | 9 | Unquoted ${CHROME_UID:-0} in chown | ℹ️ Info | WR-05. Defense-in-depth; not exploitable from compose-controlled CHROME_UID. |
| frontend/src/components/TemplateForm.tsx | 165-179 | vendor_type field disabled on edit but no visual cue | ℹ️ Info | WR-07. UX dead-end if operator clicks the field expecting to type. |

### Human Verification Required

1. **Templates UI smoke flow (TMPL-01)** — open dashboard, click Templates pill, create + edit + delete a template; confirm visual flow.
2. **Edit-then-update flow (TMPL-03)** — change Label on existing template, save; row updates within 3s polling.
3. **Delete-blocked modal (TMPL-04)** — trigger 409, observe modal copy + Copy IDs button + Escape dismiss. **Note BL-02** when delete is triggered from the Edit-Template form's own Delete button.
4. **Delete success (TMPL-04)** — clear blocking profile, retry delete; row disappears.
5. **Container UID-mismatch test (OPS-04)** — recreate container with mismatched volume UID, confirm cookies flush without permission errors.
6. **Container-level fail-closed (SEC-05)** — boot service with both secrets missing, no DEV_MODE; container exits with the descriptive RuntimeError, port 8080 unbound.

### Gaps Summary

Two real gaps:

1. **BL-01 (security rule violation):** `backend/database.py:86` retains `ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1` against an explicit Plan 01-01 acceptance criterion (`grep -c 'clipboard_sync BOOLEAN DEFAULT 1' backend/database.py == 0`) and against CLAUDE.md security rule 2 ("clipboard_sync defaults to false on every vendor template and every profile"). Currently masked by the wipe block on lines 97-114, but the column-level DEFAULT persists for any future INSERT that omits the column. Single-line fix: change `DEFAULT 1` → `DEFAULT 0`.

2. **BL-02 (UX correctness):** `frontend/src/App.tsx:142-149` stale-closure read of `deleteBlocked` causes the Edit-Template form to unmount the moment a 409 fires, breaking the planned "form stays open while modal blocks the delete" UX. The DeleteBlockedModal still appears (state did update), so the user still sees the 409 explanation; the failure mode is "form unmounts under modal" rather than total breakage. Fix: refactor `useTemplates.remove` to return `{blocked: boolean}` and gate the form unmount on the returned value.

Both gaps were already flagged by the standalone code review (`01-REVIEW.md`) and are reachable in normal operation. They do NOT prevent the phase from materially advancing — the schema, security defaults, env-var scaffolding, and API surface are all in place — but they do degrade Success Criteria 1 (UI flow) and 2 (clipboard default invariant) below the locked acceptance bar set by Plan 01-01 and the UI-SPEC.

The remaining warnings (WR-01..WR-07, IN-01..IN-05) are quality-of-life and defense-in-depth items that should be tracked but do not gate the phase.

---

_Verified: 2026-05-08T09:40:00Z_
_Verifier: Claude (gsd-verifier, goal-backward, adversarial)_
