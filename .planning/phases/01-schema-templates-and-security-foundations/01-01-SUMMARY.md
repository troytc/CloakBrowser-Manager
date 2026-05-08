---
phase: 01-schema-templates-and-security-foundations
plan: 01
subsystem: backend-foundation
tags: [schema, pydantic, sqlite, migration, clipboard_sync, pyjwt, sec-05, tmpl-01, tmpl-05]
requires: []
provides:
  - vendor_templates_table
  - profiles_vendor_columns
  - unique_vendor_pair_index
  - template_crud_helpers
  - create_profile_from_template
  - template_blueprint_model
  - vendor_template_models
  - clipboard_sync_default_false
  - pyjwt_dependency
affects:
  - backend/database.py
  - backend/models.py
  - backend/requirements.txt
tech_stack_added:
  - PyJWT>=2.12.1 (Phase 3 viewer-token signing scaffolding)
patterns:
  - Pydantic v2 Literal-union enums for typed enum-like fields
  - Pydantic v2 field_validator(mode=before) for null-coercion (clipboard_sync)
  - SQLite ALTER TABLE migration with PRAGMA table_info() detection
  - Idempotent CREATE INDEX IF NOT EXISTS
  - Snapshot-copy from template[blueprint] -> profile row at create time (D-03/D-04)
  - Parameterized queries throughout (no f-string SQL)
key_files_created: []
key_files_modified:
  - backend/database.py
  - backend/models.py
  - backend/requirements.txt
decisions:
  - "Kept the legacy `ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1` migration line per the plan's explicit action instruction ('MUST remain for backwards compatibility'); this conflicts with the plan's grep-based acceptance criterion that requires the literal `clipboard_sync BOOLEAN DEFAULT 1` to occur 0 times — action instruction took precedence over grep count."
  - "On a brand-new database, the wipe block fires once with all-zero counts: the executescript creates profiles without vendor_type, then the migration block ALTERs it in. Plan-level idempotency (no log on second run of an already-migrated DB) is preserved."
metrics:
  duration_seconds: 229
  duration_human: "3m49s"
  completed_utc: "2026-05-08T05:03:21Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 1   # 01-01-SUMMARY.md
  files_modified: 3
---

# Phase 01 Plan 01: Schema, Templates, and Security Foundations Summary

JWT-ready vendor-template schema, Pydantic blueprint models, and clipboard-sync default flip — landing the SQLite migration, the snapshot-copy helper that Phase 2's warm-pool will call, and the SEC-05 hardening at the model layer in a single compact change.

## What Shipped

### `backend/database.py` (220 → 443 lines)

- **vendor_templates table** — `(id TEXT PK, vendor_type TEXT UNIQUE NOT NULL, label, notes, blueprint TEXT NOT NULL, created_at, updated_at)` per D-01.
- **Schema migration wipe** — when `vendor_type` column is missing on `profiles`, drop all profile rows + on-disk dirs at `WARNING` log level, then `ALTER TABLE` in `vendor_type`, `vendor_connection_id`, `template_id` (FK `ON DELETE RESTRICT`) per D-07. Idempotent: second run is a silent no-op.
- **UNIQUE INDEX `idx_profiles_vendor_pair`** on `(vendor_type, vendor_connection_id)` per D-05; created with `IF NOT EXISTS` so it's safe on every boot.
- **clipboard_sync DEFAULT flipped** from `1` to `0` in the `CREATE TABLE` shape (D-18, SEC-05 schema-level touchpoint).
- **`create_profile()` patched** to inject `vendor_type="__legacy__"` + fresh `vendor_connection_id=uuid4()` placeholders when caller doesn't provide them (Pitfall 2 fix), and to flip the in-INSERT `clipboard_sync` fallback from `True` → `False`.
- **8 new helpers:** `list_templates`, `get_template`, `get_template_by_vendor_type`, `create_template`, `update_template`, `delete_template`, `count_profiles_by_template`, `list_profiles_by_template`, plus the snapshot helper `create_profile_from_template`.

### `backend/models.py` (132 → 202 lines)

- **`TemplateBlueprint`** — Pydantic v2 model that mirrors `ProfileCreate` minus `fingerprint_seed` (D-04). Literal unions on `platform`, `human_preset`, `color_scheme`. `clipboard_sync: bool = False` with a `field_validator(mode="before")` that coerces null/missing → `False` (D-18).
- **`VendorTemplateCreate`** — `vendor_type` constrained by `Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")` (Pitfall 6 — slug-only, rejects spaces/uppercase/punctuation).
- **`VendorTemplateUpdate`** — intentionally omits `vendor_type` (lookup key, not editable; rename = delete + recreate).
- **`VendorTemplateResponse`** — round-trip shape for GET endpoints.
- **`TemplateDeleteBlockedResponse`** — 409 body shape `{detail, blocking_profile_ids}` (D-06, D-13).
- **`ProfileCreate.clipboard_sync`** flipped `True` → `False` (D-18 touchpoint 2).
- **`ProfileResponse.clipboard_sync`** flipped `True` → `False` and the `coerce_clipboard_sync` validator now returns `False` on null (D-18 touchpoint 3).

### `backend/requirements.txt` (6 → 7 lines)

- Appended `PyJWT>=2.12.1` for Phase 3 viewer-token HS256 signing. Existing 6 lines unchanged.

## Verification

Both embedded Python verification scripts in the plan ran clean:

```
$ python3 -c '<task-1 verification — fresh init, idempotent re-init, vendor_templates exists,
              UNIQUE index exists, template CRUD round-trip, create_profile_from_template
              with snapshot + random seed, legacy back-to-back creates, FK ON DELETE RESTRICT>'
Schema migration: wiped 0 profile rows (+ 0 tag rows) and 0 profile directories (dev/test data)
OK

$ python3 -c '<task-2 verification — defaults flipped, TemplateBlueprint shape + null coercion,
              vendor_type regex accepts shopify/amazon-sp/my_vendor_2 and rejects
              Shopify/"my vendor"/"shopify!"/""/"UPPER", VendorTemplateUpdate has no
              vendor_type field, TemplateDeleteBlockedResponse round-trip>'
OK

$ grep -c "PyJWT>=2.12.1" backend/requirements.txt
1

$ grep -rn "clipboard_sync.*True" backend/database.py backend/models.py
(no matches)

$ python3 -c "import backend.database as db; import backend.models as m; print('imports OK')"
imports OK
```

### Idempotency check

```
FIRST RUN log lines: ['Schema migration: wiped 0 profile rows (+ 0 tag rows) and 0 profile directories (dev/test data)']
SECOND RUN log lines: []
OK (idempotent)
```

The first-run wipe-with-zeros is structural: a brand-new DB gets the `CREATE TABLE` shape (without the new columns), then the migration block ALTERs them in. The second run sees `vendor_type in cols` and skips the wipe entirely — satisfies the plan's idempotency requirement ("running init_db() twice against a migrated DB produces no wipe log line on the second run").

### Final file line counts

| File | Lines |
|------|------:|
| `backend/database.py` | 443 |
| `backend/models.py` | 202 |
| `backend/requirements.txt` | 7 |

## Commits

| Task | Commit | Type | Summary |
|-----:|--------|------|---------|
| 1 | `86b0ed5` | feat | vendor_templates schema, migration wipe, template helpers |
| 2 | `e56a7e9` | feat | TemplateBlueprint + VendorTemplate Pydantic models |
| 3 | `342dab1` | chore | PyJWT>=2.12.1 dependency |

## Deviations from Plan

### Documented inconsistency in plan acceptance grep (Task 1)

- **Found during:** Task 1 acceptance criteria verification.
- **Issue:** Plan's `<acceptance_criteria>` says `grep -c "clipboard_sync BOOLEAN DEFAULT 1" backend/database.py` should equal `0`, but the plan's `<action>` block explicitly says: *"the existing `if "clipboard_sync" not in cols:` + `if "launch_args" not in cols:` migration blocks MUST remain for backwards compatibility with any DB that was migrated once already under the old schema. Leave them exactly as they are."* The legacy `ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1` line is inside that retained block, so the literal string occurs once.
- **Resolution:** Honored the explicit action instruction (keep the legacy migration block) over the grep count. The retained legacy ALTER only fires on databases migrated under the very old pre-D-18 schema where `clipboard_sync` column was missing entirely; new DBs land at `DEFAULT 0` directly via the `CREATE TABLE` shape. No correctness impact — it's strictly a backwards-compat path for already-migrated dev databases.
- **Files modified:** none beyond plan
- **Commit:** `86b0ed5` (Task 1)

### No other deviations

- No Rule 1 bug fixes, no Rule 2 missing-functionality additions, no Rule 3 blocking-issue fixes, no Rule 4 architectural-decision asks. Plan executed as written aside from the grep-vs-action conflict above.
- No authentication gates were hit (this plan is pure backend-data layer; no external services touched).

## Threat Surface

This plan implemented the mitigations declared in the plan's `<threat_model>` (T-01-01 through T-01-09 with disposition `mitigate`). No new security-relevant surface was introduced beyond what the threat register anticipated. No threat flags raised.

## Known Stubs

None. All functionality wired end-to-end:

- `create_profile_from_template` is a complete implementation (not a stub) — Phase 2's warm-pool will be its first caller.
- `clipboard_sync` is plumbed all the way from schema → Pydantic → coercion validator. The 5th touchpoint (React form default) is explicitly out of scope per the plan and lands in Plan 05.
- `PyJWT` import is dependency-only (no consumer code yet); Phase 3 will import and use it.

## Self-Check: PASSED

- File `backend/database.py` modified: FOUND
- File `backend/models.py` modified: FOUND
- File `backend/requirements.txt` modified: FOUND
- File `.planning/phases/01-schema-templates-and-security-foundations/01-01-SUMMARY.md`: will be FOUND after this commit
- Commit `86b0ed5` (Task 1): FOUND in `git log`
- Commit `e56a7e9` (Task 2): FOUND in `git log`
- Commit `342dab1` (Task 3): FOUND in `git log`
- Both embedded verification scripts exit 0 with `OK`
- Plan-level grep `clipboard_sync.*True` returns 0 matches across both backend files
- `import backend.database` and `import backend.models` both succeed
