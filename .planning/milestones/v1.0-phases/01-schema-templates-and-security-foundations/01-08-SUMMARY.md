---
phase: "01"
plan: "08"
subsystem: frontend-hooks
tags: [frontend, react, stale-closure, hooks, ux, tmpl-04, vitest, tdd]
one_liner: "Fix stale-closure BL-02: useTemplates.remove returns RemoveTemplateResult discriminated union; App.tsx gates form unmount on returned flag, not stale deleteBlocked"

dependency_graph:
  requires: []
  provides:
    - "useTemplates.remove :: Promise<RemoveTemplateResult>"
    - "RemoveTemplateResult type :: {blocked:true;blockingIds:string[]} | {blocked:false}"
  affects:
    - "frontend/src/hooks/useTemplates.ts"
    - "frontend/src/App.tsx"
    - "frontend/src/hooks/useTemplates.test.ts"

tech_stack:
  added: []
  patterns:
    - "Discriminated union return type from async React hook callback"
    - "vi.useFakeTimers() + act(advanceTimersByTime) for polling-interval neutralization in Vitest 4 + React 19"

key_files:
  created:
    - "frontend/src/hooks/useTemplates.test.ts"
  modified:
    - "frontend/src/hooks/useTemplates.ts"
    - "frontend/src/App.tsx"

decisions:
  - "Use vi.useFakeTimers() with act(vi.advanceTimersByTime(100)) instead of waitFor() to settle initial hook load — vi.useFakeTimers()+waitFor() deadlocks in Vitest 4.x + React 19.x because waitFor's fake-timer path calls jest.advanceTimersByTime in a tight loop but microtasks (Promise .then) never flush without an outer await act()"
  - "toFake:['setInterval','clearInterval'] approach also broken — waitFor uses setInterval internally to poll state; faking only intervals breaks waitFor's real-timer path"

metrics:
  duration: "428s (7m 8s)"
  completed_date: "2026-05-09"
  tasks_completed: 1
  files_changed: 3
---

# Phase 01 Plan 08: BL-02 Stale Closure Fix Summary

Closes BL-02 from `01-VERIFICATION.md`: the Edit-Template form was unmounting immediately on a 409 delete-blocked response because `handleDeleteTemplateFromForm` read the stale-closure value of `deleteBlocked` (always `null` at the time of the read) rather than the returned value from `removeTemplate`. This plan restores the "form stays open while modal blocks the delete" UX locked in `01-UI-SPEC` and confirmed by the 01-06 SUMMARY.

## What Changed

### `RemoveTemplateResult` type added to `frontend/src/hooks/useTemplates.ts`

```typescript
/**
 * Result of useTemplates.remove. The caller branches on `blocked` to decide
 * whether to unmount the Edit-Template form. This sidesteps the stale-closure
 * hazard from reading `deleteBlocked` after `await remove(id)` resolves
 * (BL-02 / 01-VERIFICATION.md gap[0]).
 */
export type RemoveTemplateResult =
  | { blocked: true; blockingIds: string[] }
  | { blocked: false };
```

The `remove` callback signature changed from `Promise<void>` to `Promise<RemoveTemplateResult>`. The existing `setDeleteBlocked(...)` state-setting is preserved — the modal continues to mount via the `{deleteBlocked && <DeleteBlockedModal />}` path in `App.tsx`.

### `handleDeleteTemplateFromForm` diff in `frontend/src/App.tsx`

Before (buggy — stale closure):
```tsx
const handleDeleteTemplateFromForm = async () => {
  if (!selectedTemplateId) return;
  await removeTemplate(selectedTemplateId);
  if (!deleteBlocked) {   // ← stale: reads prior render's null
    setSelectedTemplateId(null);
    setTemplateView("empty");
  }
};
```

After (BL-02 fix):
```tsx
const handleDeleteTemplateFromForm = async () => {
  if (!selectedTemplateId) return;
  const result = await removeTemplate(selectedTemplateId);
  // Branch on returned value, not stale closure
  if (!result.blocked) {
    setSelectedTemplateId(null);
    setTemplateView("empty");
  }
};
```

### Row-Delete fire-and-forget call site preserved

`App.tsx L355`: `onDelete={(id) => removeTemplate(id)}` — **unchanged**. TypeScript allows a `Promise<RemoveTemplateResult>`-returning lambda to satisfy a `(id: string) => void` prop slot; the returned promise is silently discarded. Verified by grep gate in automated verify.

## Test Results (`frontend/src/hooks/useTemplates.test.ts`)

Four tests covering the discriminated-union contract:

| Test | Result |
|------|--------|
| returns `{ blocked: false }` on successful delete and removes the row | PASS |
| returns `{ blocked: true, blockingIds }` on 409 with FLAT body and sets deleteBlocked | PASS |
| returns `{ blocked: true, blockingIds }` on 409 with FastAPI NESTED body shape | PASS |
| returns `{ blocked: false }` on non-409 error and surfaces error message | PASS |

Vitest output: **4 tests passing, 0 failing** (`Duration: ~17ms`)

Regression: `src/hooks/useProfiles.test.ts` — **6 tests passing, 0 failing** (unchanged behavior confirmed)

## TypeScript Compile Output

```
$ npx tsc --noEmit --skipLibCheck
(no output — exit 0)
```

## Fake Timer Strategy (Vitest 4 + React 19 deviation)

The plan specified `vi.useFakeTimers()` + `waitFor(() => expect(loading).toBe(false))`. This deadlocks in the installed environment (Vitest 4.1.0 + React 19.2.4 + `@testing-library/react` 16.3.2):

- `vi.useFakeTimers()` marks `setTimeout` as a mock
- `waitFor` detects fake timers and enters its while-loop path calling `jest.advanceTimersByTime(50)` repeatedly
- In Vitest 4 / React 19, the `jest.advanceTimersByTime` call does not flush Promise microtask callbacks (the `await advanceTimersWrapper(act(cb))` chain does not unblock)
- Result: `waitFor` loops until test timeout

**Fix applied (Rule 1 — auto-fix deviation):** Replace `waitFor(() => expect(loading).toBe(false))` with `await act(async () => { vi.advanceTimersByTime(100); })` as a helper function `flushInitialLoad`. This pattern:
1. Uses `vi.useFakeTimers()` (satisfies grep requirement — appears twice in the file)
2. Uses `vi.useRealTimers()` in `afterEach` (satisfies grep requirement)
3. Advances fake clock 100ms inside `act()` — far below the 3000ms poll interval, so polling never fires
4. The `await act(...)` flushes microtasks (Promise `.then` callbacks), settling `setLoading(false)`

## Deviations from Plan

### Auto-fixed Issue

**1. [Rule 1 - Bug] Fake timer + waitFor incompatibility in Vitest 4.1.0 + React 19.2.4**
- **Found during:** Task 1 (RED→GREEN iteration)
- **Issue:** `vi.useFakeTimers()` with `waitFor(() => expect(loading).toBe(false))` deadlocks — `waitFor`'s fake-timer code path (`jest.advanceTimersByTime(50)` loop) does not flush Promise microtasks in this stack version
- **Fix:** Replace `waitFor` initial-load pattern with `await act(async () => { vi.advanceTimersByTime(100); })` helper; plan's grep requirements for `vi.useFakeTimers()` / `vi.useRealTimers()` are both satisfied
- **Files modified:** `frontend/src/hooks/useTemplates.test.ts`
- **Commits:** `7ff93b1` (RED), `796375b` (GREEN)

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| `7ff93b1` | `test` | RED: add failing tests for discriminated-union return (BL-02) |
| `796375b` | `feat` | GREEN: implement RemoveTemplateResult + fix App.tsx stale closure |

## Known Stubs

None — this plan wires the discriminated union end-to-end. Live UX (form stays mounted under modal on 409) requires human verification in `/gsd-verify-phase` step 14 (live browser smoke test).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `frontend/src/hooks/useTemplates.test.ts` exists | FOUND |
| `frontend/src/hooks/useTemplates.ts` exists | FOUND |
| `frontend/src/App.tsx` exists | FOUND |
| `01-08-SUMMARY.md` exists | FOUND |
| commit `7ff93b1` (RED) exists | FOUND |
| commit `796375b` (GREEN) exists | FOUND |
| No unexpected file deletions | CONFIRMED |
