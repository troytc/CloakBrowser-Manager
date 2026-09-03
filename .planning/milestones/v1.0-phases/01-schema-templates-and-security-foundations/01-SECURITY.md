---
phase: 1
slug: schema-templates-and-security-foundations
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-08
---

# Phase 1 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
>
> **This SECURITY.md was generated via `/gsd-secure-phase 1` with disposition "Accept all open — document in accepted risks."** The auditor agent was not spawned. Every threat in the register below is recorded as CLOSED on operator authority. The mitigations listed reflect the controls declared in the per-plan threat models (PLAN 01-01 through 01-06); they have not been independently verified against the implementation. For verifier-grade evidence, re-run `/gsd-secure-phase 1` and choose "Verify all open threats."

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Admin → FastAPI `/api/*` | AuthMiddleware (bearer/cookie) gates the surface; Pydantic validates request bodies before any DB write. | Untrusted user input → typed Python objects → SQLite |
| Python → SQLite | Parameterized-query boundary in `backend/database.py` helpers. No f-string interpolation of user input into SQL. | Validated Python values → SQLite rows |
| Template → Profile snapshot | Blueprint JSON copied into profile columns at create-time (TMPL-05); template is never re-read on warm-pool wake. Mutating a template never mutates existing profiles. | Static blueprint snapshot |
| Host FS → container `/data/profiles` | Named Docker volume; container chowns to `${CHROME_UID:-0}` in entrypoint before any read/write. | Chromium profile directories (cookies, prefs, SingletonLock) |
| Shell env → Python process | `docker-compose.yml` env block; `lifespan` in `backend/main.py` enforces fail-closed startup when `MAIN_APP_API_KEY` / `VIEWER_SECRET` are blank and `DEV_MODE != 1`. | Secrets, config strings |
| `.env.example` → `.env` | `.env.example` is git-tracked with non-functional placeholder values; `.env` is git-ignored. | Operator-supplied secrets |
| User UI input → useTemplates → backend | Client-side validation is UX-only. Server-side Pydantic regex/Literal unions are the security authority. | Form values (vendor_type, blueprint, clipboard_sync) |
| `ApiError.body` → React UI | Typed `unknown`; runtime type guards (`typeof === "object"`, `Array.isArray`) gate every field access in hooks. | 409 response bodies |

---

## Threat Register

35 threats consolidated from PLAN 01-01 through PLAN 01-06. Plans 01-07 (BL-01 clipboard_sync legacy ALTER fix) and 01-08 (BL-02 stale-closure UX fix) introduced no new security surface; 01-07's summary explicitly notes "None — this fix *reduces* clipboard exposure."

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01 | Tampering | Blueprint JSON values crossing into SQLite | mitigate | `TemplateBlueprint` Pydantic model with Literal unions for platform/human_preset/color_scheme; `?` placeholders throughout `backend/database.py` | closed |
| T-01-02 | Tampering | SQL injection via vendor_type or template_id in helper calls | mitigate | All `backend/database.py` helpers use `conn.execute("... WHERE x = ?", (val,))`; no f-string interpolation | closed |
| T-01-03 | Information Disclosure | `clipboard_sync` defaulting True leaks credentials from vendor portal clipboard to Main App | mitigate | D-18: default flipped to False at 5 touchpoints (CREATE TABLE, ProfileCreate, ProfileResponse, `coerce_clipboard_sync` fallback, `TemplateBlueprint`); legacy ALTER also fixed in 01-07 (BL-01) | closed |
| T-01-04 | Denial of Service | Template DELETE cascades into live profiles | mitigate | `profiles.template_id REFERENCES vendor_templates(id) ON DELETE RESTRICT`; `PRAGMA foreign_keys=ON`; app-layer 409 in PLAN 01-04 | closed |
| T-01-05 | Denial of Service | Concurrent profile create produces duplicate `(vendor_type, vendor_connection_id)` pairs | mitigate | `CREATE UNIQUE INDEX` on `profiles(vendor_type, vendor_connection_id)` | closed |
| T-01-06 | Denial of Service | Schema-migration wipe destroys production data | accept | D-08: old schema is dev/test only; no production deployment under new shape exists. Wipe logs row + directory counts at WARNING. | closed |
| T-01-07 | Tampering | `vendor_type` slug contains spaces/uppercase/Unicode → breaks downstream URL routing | mitigate | `Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=64)` on `VendorTemplateCreate.vendor_type` | closed |
| T-01-08 | Tampering | Legacy `POST /api/profiles` path collides with UNIQUE constraint on empty-string defaults | mitigate | `create_profile()` injects `vendor_type="__legacy__"` + `vendor_connection_id=str(uuid.uuid4())` when caller omits them | closed |
| T-01-09 | Tampering | Blueprint round-trip loses fields when Pydantic defaults change later | mitigate | Always emit with `model_dump_json()` (no `exclude_defaults`); read with `model_validate(json.loads(...))` in `create_template`/`update_template` | closed |
| T-01-10 | Information Disclosure | Unbounded `launch_args` list lets admin inflate blueprint JSON size | accept | Single trusted admin surface; DB write is bounded by admin session. `Field(max_length=N)` deferred. | closed |
| T-01-11 | Denial of Service | UID mismatch on mounted volume blocks Chrome cookie flush | mitigate | `chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles` in entrypoint with `set -e` for loud failure | closed |
| T-01-12 | Information Disclosure | Operator commits real secrets to `.env` | accept | `.env.example` is tracked; `.env` is git-ignored (`.gitignore` rule). Sample values are obvious placeholders. | closed |
| T-01-13 | Spoofing | Missing `MAIN_APP_API_KEY`/`VIEWER_SECRET` allows any caller to hit machine routes | mitigate | Empty-string fallback in env declaration triggers PLAN 01-03 fail-closed startup | closed |
| T-01-14 | Elevation of Privilege | Entrypoint runs as root; future USER 1000 switch silently breaks chown | accept | D-14 keeps USER root for now; future flip is a deferred hardening item documented in CONTEXT.md | closed |
| T-01-15 | Information Disclosure | `.env.example` sample values get copied to production unchanged | mitigate | Placeholder values are non-functional (`change-me-to-a-long-random-string`, `http://localhost:3000`) | closed |
| T-01-20 | Information Disclosure | Service starts with no `MAIN_APP_API_KEY` — any caller hits `/sessions/*` unauthenticated | mitigate | `_check_required_env` raises `RuntimeError` inside `lifespan` when key is unset/blank and `DEV_MODE != 1` | closed |
| T-01-21 | Spoofing | Service starts with no `VIEWER_SECRET` — viewer JWTs forgeable | mitigate | Same `_check_required_env` covers `VIEWER_SECRET` | closed |
| T-01-22 | Elevation of Privilege | `DEV_MODE=1` used in production | accept | D-17: cannot prevent deliberate misuse; logs loud WARNING naming missing secrets so operator gets unmissable signal | closed |
| T-01-23 | Denial of Service | Import-time `RuntimeError` prevents module load even in test contexts | accept | D-17: tests that need to import `main.py` set `DEV_MODE=1` in conftest/env. Documented in failure message. | closed |
| T-01-24 | Spoofing | "0" / "false" in `DEV_MODE` env bypasses check unintentionally | mitigate | `DEV_MODE` parser accepts ONLY `1/true/yes` (case-insensitive, trimmed); any other value treated as production | closed |
| T-01-30 | Tampering | Admin submits blueprint with extra/unknown fields | mitigate | Pydantic v2 default `model_config` silently drops unknown fields on `TemplateBlueprint.model_validate()` | closed |
| T-01-31 | Spoofing | `/api/templates/*` reached without authentication | mitigate | No `_AUTH_EXEMPT` entry added; `AuthMiddleware` gates all `/api/*` except existing exemptions | closed |
| T-01-32 | Denial of Service | Two concurrent DELETE requests race with profile INSERT | mitigate | D-06 belt-and-suspenders: `list_profiles_by_template` check + `sqlite3.IntegrityError` catch around `db.delete_template()` → 409 | closed |
| T-01-33 | Tampering | Caller attempts to mutate `vendor_type` via PUT | mitigate | `VendorTemplateUpdate` has no `vendor_type` field; DB helper never reads a `vendor_type` kwarg on update | closed |
| T-01-34 | Information Disclosure | 409 detail leaks blocking profile IDs to admin | accept | Admin caller is trusted (AuthMiddleware); `blocking_profile_ids` powers UI's "copy IDs" affordance (D-13) | closed |
| T-01-35 | Tampering | SQL injection via `template_id` path parameter | mitigate | All DB helpers use parameterized queries; `template_id` from path flows through `?` placeholders | closed |
| T-01-36 | Tampering | Pydantic 422 error messages leak internal field types | accept | Standard FastAPI 422 shape; no secrets/keys in field names; admin-authenticated surface | closed |
| T-01-40 | Tampering | Malformed 409 body (missing `blocking_profile_ids`) crashes modal | mitigate | `useTemplates.remove` runtime-guards body shape (`typeof`, `Array.isArray`); falls back to `setError` on non-matching 409 | closed |
| T-01-41 | Information Disclosure | Hook state leaks template config to React DevTools | accept | Template blueprint is admin-only config (timezones, locales); no secrets stored. Same exposure as existing `useProfiles`. | closed |
| T-01-42 | Tampering | Type assertions in hook erroneously narrow unknown body types | mitigate | `ApiError.body` typed `unknown`; runtime guards before every field access; only `as` casts feed immediately into `Array.isArray` | closed |
| T-01-50 | Information Disclosure | Operator flips `clipboard_sync=true` without understanding risk | mitigate | Amber warning badge with locked 3-sentence copy renders ABOVE the toggle (UI-SPEC-locked placement); D-18 default false is layer two | closed |
| T-01-51 | Tampering | Client-side form submits invalid `vendor_type` slug | mitigate | Server-side Pydantic regex is the authority (PLAN 01-04 Task 2); client shows inline 422 error; no client-side regex (single source of truth) | closed |
| T-01-52 | Information Disclosure | `DeleteBlockedModal` lists profile IDs that a compromised session could exfiltrate | accept | Admin session is the trust boundary; IDs are already admin-visible on the profiles surface; copy-to-clipboard is UX, not privilege escalation | closed |
| T-01-53 | Tampering | Legacy `ProfileForm.tsx` keeps `clipboard_sync=true` as React initial state | mitigate | D-18 5th touchpoint: flipped existing `useState({clipboard_sync: true})` to `false`; completes the end-to-end clipboard_sync default flip | closed |
| T-01-54 | Denial of Service | Form submission race with polling clobbers in-flight user edits | accept | `useTemplates.refresh` is polling-driven (3s); user form state is local. Polling can update list but not active form. Same as existing `useProfiles`. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-01 | T-01-06 | Schema-migration wipe acceptable: old schema is dev/test only; no production deployment with new shape exists. Destruction is logged at WARNING with row + directory counts. (D-08) | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-02 | T-01-10 | Unbounded `launch_args` list acceptable: single trusted admin surface; DB write per template is bounded by admin session. `Field(max_length=N)` deferred until/unless it becomes an issue. | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-03 | T-01-12 | `.env` secret-leak risk acceptable: `.env.example` is tracked with non-functional placeholders; `.env` is git-ignored. Operator discipline relied on for real secret values. | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-04 | T-01-14 | Container running as root acceptable for v1: D-14. Future USER 1000 switch is a deferred hardening item; documented in DEFERRED. | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-05 | T-01-22 | `DEV_MODE=1` misuse risk acceptable: cannot prevent deliberate operator misuse. Mitigation in place — loud WARNING log naming each missing secret on startup. (D-17) | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-06 | T-01-23 | Test-import friction acceptable: tests that need to import `main.py` set `DEV_MODE=1` in conftest. Failure message documents this. (D-17) | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-07 | T-01-34 | 409 detail leaking blocking profile IDs acceptable: admin caller is authenticated via AuthMiddleware; the field is the data backing the UI's "copy IDs" affordance. (D-13) | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-08 | T-01-36 | Pydantic 422 leaks field types acceptable: admin-authenticated surface; no secrets/keys in field names; standard FastAPI shape. | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-09 | T-01-41 | React DevTools exposing template config acceptable: blueprint is admin-only (timezones, locales); no secrets in fields; same exposure as existing `useProfiles`. | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-10 | T-01-52 | `DeleteBlockedModal` exposing profile IDs acceptable: IDs are already admin-visible on the profiles surface; trust boundary is the admin session. | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-11 | T-01-54 | Form submission vs polling race acceptable: polling updates list but not active form state; matches `useProfiles` behavior with no observed regressions. | Operator (subs@rosserresults.com) | 2026-05-08 |
| AR-01-12 | T-01-01 through T-01-05, T-01-07 through T-01-09, T-01-11, T-01-13, T-01-15, T-01-20, T-01-21, T-01-24, T-01-30 through T-01-33, T-01-35, T-01-40, T-01-42, T-01-50, T-01-51, T-01-53 | **Operator-accept of unaudited mitigations.** Operator chose "Accept all open" at the threat-plan gate of `/gsd-secure-phase 1`. The 24 mitigation dispositions above are recorded as CLOSED on operator authority based on the per-plan threat models and SUMMARY "Threat Surface" sections in PLAN 01-01, 01-04, 01-05, and 01-07. The `gsd-security-auditor` agent was not invoked for independent code-level verification. Re-run `/gsd-secure-phase 1` and choose "Verify all open threats" for verifier-grade evidence. | Operator (subs@rosserresults.com) | 2026-05-08 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-08 | 35 | 35 | 0 | Operator-accept (no auditor agent) via `/gsd-secure-phase 1` |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-08 (operator-accept; mitigations not independently audited)
