# Phase 1: Schema, Templates, and Security Foundations - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 01-schema-templates-and-security-foundations
**Areas discussed:** Schema, Migration, Admin Templates UI scope, Docker UID, Production-mode enforcement

---

## Schema

### Q1: How should the template snapshot land on the profile row?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing profile columns | vendor_templates.blueprint is a JSON blob; on upsert, service flattens blueprint into the profile row's existing fingerprint_seed/timezone/locale/... columns. Adds vendor_type, vendor_connection_id, template_id. | ✓ |
| Dedicated template_snapshot JSON column | Single opaque JSON col on profiles holding the frozen blueprint; existing normalized cols become legacy. | |
| Hybrid: normalized cols + raw JSON snapshot | Flatten + also store raw blueprint as JSON for audit/rollback. | |

**User's choice:** Reuse existing profile columns (Recommended)
**Notes:** Aligns with research recommendation (SUMMARY.md: "normalizing blueprint fields into 15 columns gains nothing" for the template side, but the profile side already has those columns — the snapshot lands there naturally).

### Q2: How should vendor_templates store its blueprint?

| Option | Description | Selected |
|--------|-------------|----------|
| Single TEXT JSON blueprint column | vendor_templates: id, vendor_type UNIQUE, blueprint TEXT NOT NULL (JSON), created_at, updated_at. | ✓ |
| Fully normalized columns | ~15 columns mirroring profile schema; easier to SQL-query, harder to evolve. | |
| Hybrid: normalize vendor_type + indexed, JSON for rest | Normalize vendor_type + a few admin-facing fields; everything else in JSON. | |

**User's choice:** Single TEXT JSON blueprint column (Recommended)

### Q3: Template 'fingerprint_seed rules' — single seed or generation rule?

| Option | Description | Selected |
|--------|-------------|----------|
| Random per profile, within template constraint | Template has no fixed seed; each profile gets a random fingerprint_seed at creation. | ✓ |
| Fixed seed shared by all profiles of the vendor | Template sets a seed; all profiles share it — trivially clusterable by vendor portal. | |
| Range/rule in blueprint (min/max), random within bounds | Template carries seed_min/max; service picks within. Overkill for v1. | |

**User's choice:** Random per profile, within template constraint (Recommended)
**Notes:** Critical anti-detection posture per Pitfall 7.

### Q4: Template delete enforcement (TMPL-04) — where enforced?

| Option | Description | Selected |
|--------|-------------|----------|
| App-layer check + FK ON DELETE RESTRICT | Handler returns 409 with clear message; FK is the DB-level safety net. | ✓ |
| FK ON DELETE RESTRICT only | Catch IntegrityError and translate. Error message harder to shape. | |
| App-layer check only, no FK | Loose FK; app is sole guard. Simpler migration, no DB safety. | |

**User's choice:** App-layer check + FK ON DELETE RESTRICT (Recommended)

**After Q4:** User chose "Next area".

---

## Migration

### Q5: How to handle existing profile rows when the new schema lands?

| Option | Description | Selected |
|--------|-------------|----------|
| Wipe on migration | init_db() detects old-schema rows, deletes them and /data/profiles/{id} dirs, then adds new NOT NULL columns. | ✓ |
| Backfill with 'legacy' sentinel vendor_type | Synthetic legacy template; backfill existing rows. Pollutes new model. | |
| Keep columns nullable during transition, tighten later | Defer UNIQUE constraint; adds race risk (Pitfall 2). | |

**User's choice:** Wipe on migration (Recommended)
**Notes:** Brownfield refocus; old data is dev/test only.

### Q6: What about on-disk profile directories for wiped rows?

| Option | Description | Selected |
|--------|-------------|----------|
| Delete matching directories in same migration step | Atomic wipe of DB rows + /data/profiles/{id} dirs. | ✓ |
| Leave directories, just delete rows | Rows go; dirs remain; operator cleans up manually. | |
| Migration script, not automatic | Ship separate one-shot script; slower rollout. | |

**User's choice:** Delete matching directories in same migration step (Recommended)

### Q7: Wipe gated by a safety flag, or unconditional?

| Option | Description | Selected |
|--------|-------------|----------|
| Unconditional — old schema means wipe runs | init_db() detects and wipes without prompting; logs what it wiped. | ✓ |
| Require FORCE_MIGRATE=1 env var | Explicit operator confirmation required; adds deploy step. | |
| Unconditional in dev, gated in production | Mixes two concerns; overkill. | |

**User's choice:** Unconditional — old schema means wipe runs (Recommended)

**After Q7:** User chose "Next area".

---

## Admin Templates UI scope

### Q8: How polished should the Templates admin UI be in Phase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| Functional MVP now, Phase 4 refines | TemplateList + TemplateForm with section grouping, delete-confirm modal; no search/sort/bulk. | ✓ |
| Near-final polish now | Final design quality; search, inline-edit, toasts. Costs Phase 1 scope. | |
| Backend + mock UI only | Violates Phase 1 goal as written. | |

**User's choice:** Functional MVP now, Phase 4 refines (Recommended)

### Q9: Form field layout?

| Option | Description | Selected |
|--------|-------------|----------|
| Sections mirroring profile concerns | Identity / Fingerprint / Screen / GPU / Behavior / Proxy / Security groups. | ✓ |
| Flat form with all fields | Single long form; fast to build, harder to scan. | |
| JSON editor + vendor_type/label inputs | Power-user UX; sharp edges. Defer to v2. | |

**User's choice:** Sections mirroring profile concerns (Recommended)

### Q10: Where does Templates UI sit in the dashboard in Phase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| New top-level 'Templates' nav item alongside Profiles | Simple toggle; Profiles survives Phase 1 intact. | ✓ |
| Replace Profiles nav with Templates now | Requires partial Phase 4 nav work now. | |
| Hidden route, only reachable via URL | Worse UX for operators actually using Phase 1. | |

**User's choice:** New top-level 'Templates' nav item alongside existing Profiles (Recommended)

**After Q10:** User chose "Next area".

---

## Docker UID

### Q11: How should the container handle the Chrome UID?

| Option | Description | Selected |
|--------|-------------|----------|
| Chown-only, keep service running as root | entrypoint.sh chowns /data/profiles; no USER directive. Smallest diff; Pitfall 10 solved. | ✓ |
| Add USER 1000 + chown to 1000:1000 | Tighter posture; more test surface (Xvnc, KasmVNC, Playwright). | |
| Split: privileged init-container chowns, main runs unprivileged | Cleanest unix model; most moving parts. | |

**User's choice:** Chown-only, keep service running as root (Recommended)

### Q12: Where does CHROME_UID come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded in entrypoint.sh | CHROME_UID=${CHROME_UID:-0}; declarative; easy to flip later. | ✓ |
| Detect at runtime via 'id -u' | Mirrors whatever user container runs as; less declarative. | |
| ENV in Dockerfile only | Same outcome; tighter coupling to image. | |

**User's choice:** Hardcoded in entrypoint.sh (Recommended)

**After Q12:** User chose "Done with discussion".

---

## Production-mode enforcement (roll-up)

### Q13: When does the service refuse to start on missing VIEWER_SECRET / MAIN_APP_API_KEY?

| Option | Description | Selected |
|--------|-------------|----------|
| Default strict + DEV_MODE=1 opt-out | Fail-closed; DEV_MODE=1 allows missing vars + logs warning on every request. | ✓ |
| ENV=production required to enforce | Easy to misconfigure prod by forgetting the flag. | |
| Auto-detect from AUTH_TOKEN shape | Clever but fragile. | |

**User's choice:** Default strict + DEV_MODE=1 opt-out (Recommended)

---

## Claude's Discretion

- `updated_at` column refreshed by app code on every update (no SQLite trigger).
- `TemplateList.tsx` polling interval matches existing `useProfiles.ts` (3s).
- 409 delete-blocked response shape: `{detail, blocking_profile_ids[]}`.
- Modal editing (matches existing ProfileForm); optional Phase 4 refinement.
- Dev-mode warning copy and log levels.
- Tailwind design tokens: reuse existing `globals.css` palette.

## Deferred Ideas

- `is_active` soft-disable on templates (GOV-01) — v2.
- Per-template `idle_timeout_minutes` override (SAFE-03) — v2.
- Template inheritance chains — explicit anti-feature.
- Admin UI polish (search, sort, bulk actions) — Phase 4.
- Navigation redesign — Phase 4.
- USER 1000 switch in Dockerfile — future hardening.
- CSRF tokens on admin mutating routes — SameSite=Strict sufficient (Phase 3).
