---
phase: "01"
plan: "07"
subsystem: backend/database
tags: [security, clipboard_sync, sqlite, migration, sec-06, gap-closure, bl-01]
depends_on:
  requires: []
  provides: [clipboard_sync-default-0-migration]
  affects: [backend/database.py]
tech_stack:
  added: []
  patterns: [sqlite-conditional-alter, defense-in-depth-update]
key_files:
  created: []
  modified:
    - backend/database.py
decisions:
  - "Legacy ALTER kept at DEFAULT 0 (not 1) to match CREATE TABLE default and CLAUDE.md security rule 2"
  - "Defense-in-depth UPDATE runs immediately after ALTER, before wipe block, to normalize any rows that landed under old DEFAULT 1"
metrics:
  duration: "< 5 minutes"
  completed: "2026-05-08"
  tasks_completed: 1
  tasks_total: 1
---

# Phase 01 Plan 07: BL-01 clipboard_sync Default Fix Summary

**One-liner:** Flipped legacy ALTER TABLE clipboard_sync migration from DEFAULT 1 to DEFAULT 0, closing the security defect (BL-01) that leaked clipboard access on any DB migrated before the CREATE TABLE default was corrected.

---

## What Was Done

### Task 1: Flip legacy clipboard_sync ALTER from DEFAULT 1 to DEFAULT 0 + defense-in-depth UPDATE

**Exact change — `backend/database.py` line 86 (before):**
```python
conn.execute("ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1")
conn.commit()
```

**After:**
```python
# SEC-06 / CLAUDE.md security rule 2: clipboard_sync defaults to false on every profile.
# Note: in the original v0.0.7 schema this column did not exist, so this ALTER only
# runs once per legacy DB. The DEFAULT 0 here aligns with the CREATE TABLE default.
conn.execute("ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 0")
# Defense-in-depth: any DB that landed between Plan 01-01's flip and this fix
# (i.e., the column was added under DEFAULT 1) carries clipboard_sync=1 rows.
# Normalize them now, BEFORE the wipe block below has a chance to run, so any
# row that survives the wipe (or a DB that no longer triggers the wipe path) is safe.
conn.execute("UPDATE profiles SET clipboard_sync = 0 WHERE clipboard_sync = 1")
conn.commit()
```

**Commit:** `e3cfae0`

---

## Verification Results

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| `grep -c 'clipboard_sync BOOLEAN DEFAULT 1'` | 0 | 0 | PASS |
| `grep -c 'clipboard_sync BOOLEAN DEFAULT 0'` | 2 | 2 | PASS |
| `grep -c 'UPDATE profiles SET clipboard_sync = 0'` | 1 | 1 | PASS |
| `grep -c 'if "vendor_type" not in cols:'` | 1 | 1 | PASS |
| `grep -c 'shutil.rmtree(pdir, ignore_errors=True)'` | 1 | 1 | PASS |
| `grep -c 'ALTER TABLE profiles ADD COLUMN vendor_type'` | 1 | 1 | PASS |
| `grep -c 'ALTER TABLE profiles ADD COLUMN vendor_connection_id'` | 1 | 1 | PASS |
| `grep -c 'ALTER TABLE profiles ADD COLUMN template_id TEXT REFERENCES vendor_templates'` | 1 | 1 | PASS |
| Python `ast.parse()` exits 0 | yes | yes | PASS |
| `init_db()` idempotent (runs twice clean) | yes | yes | PASS |

**Wipe block preserved byte-for-byte.** No logic in the wipe block (lines 97-129) was touched.

---

## Deviations from Plan

### Plan Criterion Discrepancy (pre-existing, not caused by this fix)

The plan stated `grep -c 'DELETE FROM profile_tags' == 1` and `grep -c 'DELETE FROM profiles' == 1`. Both return `2` — and they returned `2` before this fix as well.

The extra occurrences come from existing CRUD functions:
- `update_profile()` (line 275): `DELETE FROM profile_tags WHERE profile_id = ?`
- `delete_profile()` (line 288): `DELETE FROM profiles WHERE id = ?`

These were present before this plan and my fix touched neither line. The wipe block itself is intact — verified by the surrounding `if "vendor_type" not in cols:` guard (returns 1) and the `shutil.rmtree` unique sentinel (returns 1). The plan's intent (wipe block preserved) is satisfied; the raw grep criterion was under-specified.

**Classified as:** Pre-existing plan criterion error. No code change required.

---

## Known Stubs

None. This is a pure security-defect fix with no UI or data-flow stubs.

---

## Threat Flags

None. This fix *reduces* clipboard exposure by correcting a DEFAULT that was too permissive.

---

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `backend/database.py` exists | FOUND |
| `01-07-SUMMARY.md` exists | FOUND |
| Commit `e3cfae0` exists | FOUND |
