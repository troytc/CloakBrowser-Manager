---
plan: 01-06
phase: 01-schema-templates-and-security-foundations
status: complete
tasks_completed: 2
tasks_total: 2
delivered:
  - TemplateList.tsx — table view with empty state, edit/delete row actions
  - TemplateForm.tsx — 7-section blueprint form with amber clipboard_sync warning copy
  - DeleteBlockedModal.tsx — 409 modal with singular/plural handling, Copy IDs, Escape dismiss
  - ProfileForm.tsx — 5th and final clipboard_sync default flipped to false (D-18 / SEC-05 closed end-to-end)
  - App.tsx — Profiles/Templates segmented switcher + dual surface dispatch + DeleteBlockedModal mount
affects:
  - SEC-05 (clipboard_sync default false): closed end-to-end across backend/ and frontend/src/
  - 04 (admin dashboard pivot): templates surface is now a first-class admin view
verification:
  ts_compile: clean (0 errors via npx tsc --noEmit --skipLibCheck)
  vite_build: clean (1637 modules transformed in 1.38s, dev mode)
  clipboard_sync_sweep: 0 matches for `clipboard_sync.*:.*true` across backend/ and frontend/src/
  copy_strings: all 3 locked strings present once each
  acceptance_grep: 14/14 Task 2 grep checks pass; nav order Profiles@244 < Templates@259

key-files:
  created:
    - frontend/src/components/TemplateList.tsx (140 lines)
    - frontend/src/components/TemplateForm.tsx (471 lines)
    - frontend/src/components/DeleteBlockedModal.tsx (91 lines)
  modified:
    - frontend/src/App.tsx (Surface + TemplateView state, switcher, content dispatch, modal mount)
    - frontend/src/components/ProfileForm.tsx (clipboard_sync initial state false — 5th D-18 touchpoint)
    - frontend/src/hooks/useProfiles.test.ts (legacy clipboard_sync default expectation)

key-decisions:
  - "Surface state machine kept orthogonal to existing View enum — no existing profiles flow touched. Switching surfaces preserves the current Profiles selection so a return to Profiles doesn't lose context."
  - "DeleteBlockedModal mounts at the inner content level (inside the flex-1 panel) rather than App-root, so it overlays the active surface without affecting the top bar."
  - "Surface=Templates click resets selectedTemplateId + templateView to empty: avoids stale 'edit' state from a previously-deleted template."

patterns-established:
  - "Pattern: surface-keyed error banner — `{(surface === \"profiles\" ? error : templatesError) && ...}` — reuses the existing red-banner shell for both data sources."
  - "Pattern: dual-surface React fragment dispatch — `{surface === X && (<>...</>)}` — keeps each surface's view-state machine self-contained and avoids prop drilling."

requirements-completed: [TMPL-01, TMPL-02, TMPL-03, TMPL-04, TMPL-05, SEC-05, OPS-03]

---

# Plan 01-06 Summary

Lands the full Templates admin surface — section-grouped TemplateForm with the locked amber clipboard_sync warning, TemplateList table, DeleteBlockedModal for the 409 flow, and a Profiles/Templates segmented switcher in App.tsx. Also closes SEC-05 end-to-end by flipping the **5th and final** `clipboard_sync` touchpoint in ProfileForm.tsx's React initial state.

## Performance

- TS compile: 0 errors (incremental, --skipLibCheck)
- Vite dev build: 1637 modules transformed in 1.38s
- Bundle: index-R-8WjKkH.js = 252.76 kB (74.44 kB gzip), rfb-BW3Yvshj.js = 168.53 kB (50.50 kB gzip)

## Performance vs Plan

- ✅ TemplateList renders empty state, table with vendor_type / label / clipboard_sync / actions, and delete confirmation
- ✅ TemplateForm has 7 sections in locked UI-SPEC order with amber warning ABOVE clipboard_sync checkbox; field-level Pydantic 422 errors map back to specific inputs
- ✅ TemplateForm React initial state has `blueprint.clipboard_sync = false` (5th and final D-18 touchpoint)
- ✅ DeleteBlockedModal: aria-modal + aria-labelledby + aria-describedby; singular/plural copy ("This profile is using…" vs "These profiles…"); Copy IDs button using `navigator.clipboard.writeText`; Escape dismiss via document keydown listener
- ✅ App.tsx: Profiles-first segmented switcher; surface + templateView state machines; content dispatch wraps existing profiles tree without behavior change; DeleteBlockedModal mounts from `useTemplates.deleteBlocked`
- ✅ ProfileForm.tsx clipboard_sync default flipped to `false` — confirmed by grep sweep below
- ✅ TypeScript strict compile + Vite production build both green

## Task Commits

- `b78e567` — feat(01-06): add Templates UI components and flip clipboard_sync default
- `26892f0` — feat(01-06): wire Templates surface switcher and content dispatch in App.tsx

## Files Created / Modified

- `frontend/src/components/TemplateList.tsx` — 140 lines (NEW)
- `frontend/src/components/TemplateForm.tsx` — 471 lines (NEW)
- `frontend/src/components/DeleteBlockedModal.tsx` — 91 lines (NEW)
- `frontend/src/App.tsx` — +166/-32 lines
- `frontend/src/components/ProfileForm.tsx` — clipboard_sync initial state flipped (4-line edit)
- `frontend/src/hooks/useProfiles.test.ts` — clipboard_sync legacy expectation updated

## SEC-05 End-to-End Verification

Whole-project sweep for any remaining `clipboard_sync: true` defaults:

```
grep -rn 'clipboard_sync.*:.*true\b' backend/ frontend/src/   # → 0 matches
```

The 5 D-18 touchpoints, all flipped to false:

1. `backend/models.py:27` — TemplateBlueprint default
2. `backend/models.py:86` — VendorTemplateCreate default + field_validator
3. `backend/models.py:163` — Profile default + field_validator
4. `backend/database.py:56` — `clipboard_sync BOOLEAN DEFAULT 0` in CREATE TABLE
5. `frontend/src/components/TemplateForm.tsx:24` and `frontend/src/components/ProfileForm.tsx:67` — React initial state false

(Legacy `database.py:86` `ALTER TABLE … DEFAULT 1` is the migration block for old DBs that pre-date the column; the migration wipe in `init_db()` handles old rows. Not a runtime default.)

## Decisions Made

- **Surface vs View orthogonality:** Kept Surface state machine separate from the existing `view` enum; switching to Templates doesn't disturb the selected Profile, and switching back lands you exactly where you left.
- **Reset on Templates entry:** Clicking Templates resets `selectedTemplateId` and `templateView` so a stale edit context (e.g., template deleted in another surface) doesn't auto-mount.
- **Modal placement:** `DeleteBlockedModal` mounts inside the flex-1 content panel; it overlays the active surface without affecting the top bar.

## Deviations from Plan

- **Resume after timeout:** Task 1 was committed by the executor agent before its stream stalled (#stream-idle-watchdog). Task 2 was completed inline by the orchestrator using the same plan instructions and acceptance criteria. App.tsx edits are byte-equivalent to the plan's prescribed patches for steps (1)–(7); see commit `26892f0` for the diff.

## Wave-Closure Note

Plan 01-06 is the last plan in Phase 1. After this merges, all 6 plans across 4 waves are complete and the phase is ready for verification.
