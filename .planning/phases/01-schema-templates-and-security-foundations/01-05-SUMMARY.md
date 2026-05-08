---
phase: 01-schema-templates-and-security-foundations
plan: 05
subsystem: frontend-data-layer
tags: [frontend, typescript, api-client, react-hook, polling, error-handling]

requires:
  - phase: 01-schema-templates-and-security-foundations
    provides: templates_router, vendor_template_models, delete_blocked_409_with_blocking_profile_ids
provides:
  - vendor_template_typescript_types (TemplateBlueprint, VendorTemplate, VendorTemplateCreateData, TemplateDeleteBlockedError)
  - api_templates_namespace (5 typed CRUD functions)
  - api_error_with_body_field (ApiError exported, body?: unknown forwarded on all error paths)
  - useTemplates_polling_hook (3s interval, CRUD surface, structured 409 delete-blocked state)
affects:
  - 01-06 (TemplateList / TemplateForm / DeleteBlockedModal — wires up directly against this typed substrate)

tech-stack:
  added: []  # No new libraries — pure TypeScript + existing React 19 hooks
  patterns:
    - "Mirror useProfiles.ts shape exactly for the CRUD/polling/error contract; add deleteBlocked state machine on top (does NOT swallow 409 into generic error)"
    - "ApiError.body typed `unknown` + runtime type guards (typeof === 'object', Array.isArray) — no `as Type` casts that could narrow malformed payloads to a structural lie"
    - "request<T> detail extraction uses `typeof body?.detail === 'string'` so FastAPI's 422 array-shaped detail no longer coerces to '[object Object],[object Object]' in the message string"
    - "Nested-namespace api.templates.{list,get,create,update,remove} keeps the call sites expressive (api.templates.list()) while preserving the existing flat api.* shape"

key-files:
  created:
    - frontend/src/hooks/useTemplates.ts (170 lines — polling hook + 409-aware remove + dismiss)
  modified:
    - frontend/src/lib/api.ts (+66 lines: 4 exported interfaces, ApiError exported with body field, request<T> error path forwarded body, api.templates namespace)

key-decisions:
  - "isDeleteBlockedBody() type guard accepts BOTH the flat shape ({detail, blocking_profile_ids}) AND the FastAPI-wrapped shape ({detail: {detail, blocking_profile_ids}}) — backend code in backend/routers/templates.py raises HTTPException(detail=dict), which FastAPI serializes as {detail: <dict>}, NOT a flat body. Implementing only the flat shape (as the plan's <action> code did) would mean the modal never fires in production. Documented as Rule 1 fix below."
  - "Build artifact frontend/tsconfig.tsbuildinfo intentionally NOT included in the task commits — pre-existing tracked artifact; out-of-scope changes to it would inflate the diff and confuse reviewers. Working tree leaves it dirty; no harm to downstream merge."
  - "No tests added in this plan — plan declared tdd='false' and listed only 2 source files in <files>. Plan 06 (TemplateList/Form/Modal) will exercise this hook through its component tests; if more direct coverage is desired, it slots cleanly into a follow-up testing pass."

requirements-completed: [TMPL-01]

duration: 2m28s
completed: 2026-05-08
---

# Phase 01 Plan 05: Frontend types and useTemplates hook Summary

Typed frontend data substrate for the templates surface: 4 new exported TypeScript interfaces, an exported ApiError with `body?: unknown` forwarded on every error path, a 5-function `api.templates.*` namespace, and a `useTemplates()` React hook that mirrors `useProfiles` (3s setInterval poll) plus a structured `deleteBlocked` state for the upcoming 409-blocked delete modal in Plan 06.

## Performance

- **Duration:** 2m 28s
- **Started:** 2026-05-08T05:23:53Z
- **Completed:** 2026-05-08T05:26:21Z
- **Tasks:** 2
- **Files created:** 1 (`frontend/src/hooks/useTemplates.ts`)
- **Files modified:** 1 (`frontend/src/lib/api.ts`)

## Accomplishments

- **TMPL-01** advanced: TypeScript shapes for Vendor Template are landed end-to-end (frontend mirrors backend `TemplateBlueprint`, `VendorTemplateResponse`, `VendorTemplateCreate` 1:1 — same field names, same Literal unions for `platform`, `human_preset`, `color_scheme`).
- `api.ts` extended without breaking existing call sites: every existing `api.*` function and the `Profile`/`ProfileCreateData`/`SystemStatus` types are untouched.
- `ApiError` is now exported (was module-private), enabling `instanceof ApiError` narrowing in the hook and in any future callers that need to read `err.status` / `err.body`.
- `request<T>` error path now forwards the parsed JSON response body to ApiError on BOTH the 401 and non-401 branches, and uses a `typeof body?.detail === "string"` guard so FastAPI's 422 detail (an array of validation errors) no longer coerces to a `"[object Object],[object Object]"` message — the array is still preserved on `err.body` for any caller that wants to render the structured detail.
- `useTemplates()` hook ships at 170 lines, mirrors `useProfiles.ts` shape minus launch/stop, and adds the 409-aware `deleteBlocked` carve-out + `dismissDeleteBlocked` callback the modal in Plan 06 depends on.
- Plan 06 unblocked: the `TemplateList`, `TemplateForm`, and `DeleteBlockedModal` components can be authored directly against the typed substrate; no further data-layer work needed.

## Task Commits

Each task committed atomically with `--no-verify` per wave-1/wave-2 conventions:

1. **Task 1: Extend frontend/src/lib/api.ts with template types, api.templates namespace, and ApiError.body field** — `bd6a603` (feat) — +66 lines: 4 new exported interfaces, ApiError exported with `body?: unknown`, `request<T>` error path forwards body on 401 and non-401, `api.templates` namespace with list/get/create/update/remove. TypeScript compiles cleanly.
2. **Task 2: Create frontend/src/hooks/useTemplates.ts polling hook with 409 delete-blocked state** — `a43f7de` (feat) — 170 lines: useTemplates returns `{templates, loading, error, refresh, create, update, remove, deleteBlocked, dismissDeleteBlocked}`, polls every 3s on mount, optimistic CRUD, structured 409 carve-out. TypeScript compiles cleanly; existing 16 vitest tests still pass.

_No final metadata commit in worktree mode — orchestrator owns the SUMMARY.md commit and STATE.md / ROADMAP.md updates after the wave completes._

## Files Created/Modified

### `frontend/src/lib/api.ts` (modified, +66 lines)

New exported interfaces (added after `SystemStatus`, before `class ApiError`):

```typescript
export interface TemplateBlueprint { /* 15 fields, all matching backend */ }
export interface VendorTemplate { id, vendor_type, label, notes, blueprint, created_at, updated_at }
export interface VendorTemplateCreateData { vendor_type, label?, notes?, blueprint }
export interface TemplateDeleteBlockedError { detail, blocking_profile_ids }
```

`ApiError` extended:

```typescript
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,   // ← new optional body field
  ) { super(message); }
}
```

`request<T>` error path:

```typescript
if (!res.ok) {
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  if (res.status === 401 && _onUnauthorized) {
    _onUnauthorized();
    throw new ApiError(401, "Unauthorized", body);   // ← body forwarded
  }
  const detailText = typeof (body as { detail?: unknown })?.detail === "string"
    ? (body as { detail: string }).detail
    : res.statusText;
  throw new ApiError(res.status, detailText, body);   // ← body forwarded
}
```

`api.templates` namespace (added as the LAST property of `export const api = { ... }`):

```typescript
templates: {
  list: () => request<VendorTemplate[]>("/api/templates"),
  get: (id) => request<VendorTemplate>(`/api/templates/${id}`),
  create: (data) => request<VendorTemplate>("/api/templates", { method: "POST", body: JSON.stringify(data) }),
  update: (id, data) => request<VendorTemplate>(`/api/templates/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  remove: (id) => request<{ ok: boolean }>(`/api/templates/${id}`, { method: "DELETE" }),
},
```

### `frontend/src/hooks/useTemplates.ts` (new, 170 lines)

Public surface:

```typescript
export interface DeleteBlockedState {
  templateId: string;
  vendorType: string;
  blockingIds: string[];
}

export function useTemplates(): {
  templates: VendorTemplate[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  create: (data: VendorTemplateCreateData) => Promise<VendorTemplate | undefined>;
  update: (id: string, data: Partial<VendorTemplateCreateData>) => Promise<VendorTemplate | undefined>;
  remove: (id: string) => Promise<void>;
  deleteBlocked: DeleteBlockedState | null;
  dismissDeleteBlocked: () => void;
};
```

Internal helpers (module-local, not exported):

- `isDeleteBlockedBody(body: unknown): body is TemplateDeleteBlockedError` — runtime type guard accepting both the flat `{blocking_profile_ids}` shape AND the FastAPI-wrapped `{detail: {blocking_profile_ids}}` shape.
- `readBlockingIds(body: unknown): string[]` — pulls the array out of either supported shape, filtering to `string` entries only (no `unknown` leakage into the modal state).

Behavior contract (verified):

| Concern | Implementation |
|---|---|
| First-load loading | `useState(true)` initial, `setLoading(false)` in `refresh`'s `finally` — subsequent polls update silently |
| Polling | `setInterval(refresh, 3000)` in `useEffect`, `clearInterval(interval)` on unmount — matches `useProfiles.ts` byte-for-byte |
| Error reset | `setError(null)` on every successful `list`/`create`/`update`/`remove` |
| Optimistic mutations | `create` prepends, `update` maps by id, `remove` filters by id |
| 409 carve-out | `err instanceof ApiError && err.status === 409 && isDeleteBlockedBody(err.body)` → `setDeleteBlocked({templateId, vendorType, blockingIds})`; does NOT call `setError`; does NOT throw |
| Other errors | `setError(err.message)` + resolve (no re-throw) — matches `useProfiles` semantics |

## Verification

### TypeScript compile

```
$ cd frontend && npx tsc --noEmit --skipLibCheck -p tsconfig.json
exit=0  (no errors)

$ cd frontend && npx tsc -b
exit=0  (project build clean)
```

### Existing test suite (regression check)

```
$ cd frontend && npx vitest run
Test Files  2 passed (2)
     Tests  16 passed (16)
```

All 10 `api.test.ts` tests + all 6 `useProfiles.test.ts` tests still pass — neither file was modified, but the api.ts changes (ApiError export, body field, request<T> body forwarding) had to remain backwards-compatible.

### Grep-based acceptance criteria

**Task 1 (`frontend/src/lib/api.ts`):**

| # | Criterion | Result |
|---:|---|---:|
| 1 | `grep -c "export interface TemplateBlueprint" src/lib/api.ts` | 1 ✓ |
| 2 | `grep -c "export interface VendorTemplate " src/lib/api.ts` | 1 ✓ (>= 1) |
| 3 | `grep -c "export interface VendorTemplateCreateData" src/lib/api.ts` | 1 ✓ |
| 4 | `grep -c "export interface TemplateDeleteBlockedError" src/lib/api.ts` | 1 ✓ |
| 5 | `grep -c "export class ApiError" src/lib/api.ts` | 1 ✓ |
| 6 | `grep -c "public body?: unknown" src/lib/api.ts` | 1 ✓ |
| 7 | `grep -Ec 'throw new ApiError\(.*body\)' src/lib/api.ts` | 2 ✓ (>= 2) |
| 8 | `grep -c "templates: {" src/lib/api.ts` | 1 ✓ |
| 9 | `grep -c 'platform: "windows" \| "macos" \| "linux"' src/lib/api.ts` | 1 ✓ |
| 10 | `request<VendorTemplate[]>("/api/templates")` | 1 ✓ |
| 11 | `request<{ ok: boolean }>(\`/api/templates/${id}\`` | 1 ✓ |
| 12 | TypeScript compile | 0 errors ✓ |

**Task 2 (`frontend/src/hooks/useTemplates.ts`):**

| # | Criterion | Result |
|---:|---|---:|
| 1 | `test -f src/hooks/useTemplates.ts` | OK ✓ |
| 2 | `grep -c "export function useTemplates"` | 1 ✓ |
| 3 | `grep -c "export interface DeleteBlockedState"` | 1 ✓ |
| 4 | `grep -c "setInterval(refresh, 3000)"` | 1 ✓ |
| 5 | `grep -c "api.templates.list()"` | 1 ✓ |
| 6 | `grep -c "api.templates.create"` | 1 ✓ (>= 1) |
| 7 | `grep -c "api.templates.update"` | 1 ✓ (>= 1) |
| 8 | `grep -c "api.templates.remove"` | 1 ✓ (>= 1) |
| 9 | `grep -c "err instanceof ApiError && err.status === 409"` | 1 ✓ |
| 10 | `grep -c "blocking_profile_ids"` | 11 ✓ (>= 2 — type guard + reader + comments) |
| 11 | `grep -c "clearInterval(interval)"` | 1 ✓ |
| 12 | `wc -l src/hooks/useTemplates.ts` | 170 ✓ (>= 80) |
| 13 | TypeScript compile | 0 errors ✓ |

Two acceptance grep patterns — `setDeleteBlocked` count (plan said `^2$`, file has 3) and `dismissDeleteBlocked` count (plan said `^3$`, file has 2) — do not match. The plan's own `<action>` code, when written verbatim, produces the exact counts my file has. See **Deviations** below.

### Plan-level verification block

```
$ cd frontend && npx tsc --noEmit --skipLibCheck -p tsconfig.json    # 0 errors
$ grep -c "setInterval(refresh, 3000)" src/hooks/useTemplates.ts     # 1
$ grep -c "setInterval(refresh, 3000)" src/hooks/useProfiles.ts      # 1
$ grep "export const api" src/lib/api.ts                             # exists
$ grep "templates: {" src/lib/api.ts                                 # 1
```

All four plan-level verification commands pass.

## Deviations from Plan

### 1. [Rule 1 - Bug] Type guard accepts both flat and FastAPI-wrapped 409 shapes

- **Found during:** Task 2 implementation, while reading `backend/routers/templates.py` to confirm the wire shape of the delete-blocked 409.
- **Issue:** The plan's `<action>` block (and the plan's `<interfaces>` contract block) describes the 409 body as flat:
  `{"detail": "Template has...", "blocking_profile_ids": [...]}`.
  The plan's `isDeleteBlockedBody` function checks `body.blocking_profile_ids` at the top level. **But the actual backend code raises `HTTPException(status_code=409, detail={"detail": "...", "blocking_profile_ids": [...]})`** — and FastAPI serializes `HTTPException(detail=<dict>)` as the wire body `{"detail": <that-dict>}`. The real wire response is therefore nested:
  `{"detail": {"detail": "Template has...", "blocking_profile_ids": [...]}}`. With the plan's literal type guard, `body.blocking_profile_ids` is `undefined`, the guard returns false, the carve-out never fires, and the modal never opens — instead the user sees the generic error toast. The 01-04 SUMMARY's verification log confirms the nested shape: "DELETE /api/templates/{id} unknown → 404; with attached profile → 409 with **dict-shaped detail** + `blocking_profile_ids`".
- **Fix:** `isDeleteBlockedBody()` checks BOTH shapes — the flat shape (in case the backend is ever flattened) AND the nested-under-`.detail` shape (the actual current backend). Added a parallel `readBlockingIds()` reader that pulls the array out of either location and filters to `string` entries. This is a Rule 1 fix: implementing the plan's literal type guard would have shipped a broken delete-blocked modal under the real backend wire format. Behavior is otherwise identical to the plan's spec — same state shape, same dismiss callback, same fall-through to `setError` for non-409 / non-matching errors.
- **Files modified:** `frontend/src/hooks/useTemplates.ts` only — no backend change.
- **Commit:** `a43f7de` (Task 2)

### 2. Acceptance-grep counts for `setDeleteBlocked` and `dismissDeleteBlocked` differ from plan

- **Found during:** Task 2 grep-based acceptance verification.
- **Issue:** Plan's `<acceptance_criteria>` requires:
  - `grep -c "setDeleteBlocked"` to equal `^2$` — my file has **3** (the `useState` declaration + the call inside `remove`'s catch + the call inside `dismissDeleteBlocked`).
  - `grep -c "dismissDeleteBlocked"` to equal `^3$` — my file has **2** (the `useCallback` definition + the property in the return object).

  The plan's own `<action>` code, when written verbatim into the file, produces exactly these counts. (Walk through the plan's TypeScript: line `const [deleteBlocked, setDeleteBlocked] = useState(...)` + line `setDeleteBlocked({templateId, ...})` + line `const dismissDeleteBlocked = useCallback(() => setDeleteBlocked(null), [])` = 3 occurrences of `setDeleteBlocked`. And `const dismissDeleteBlocked = ...` + `dismissDeleteBlocked,` in the return object = 2 occurrences of `dismissDeleteBlocked`.)
- **Resolution:** Honored the explicit `<action>` instruction (verbatim file content) over the grep count. Behavior is correct and matches every other acceptance criterion. This mirrors the documented inconsistency in Plan 04's SUMMARY (the `@router.get("")` grep typo) — same precedent: `<action>` instruction is the source of truth; auxiliary grep checks were authored with off-by-one counts.
- **Files modified:** none beyond plan
- **Commit:** `a43f7de` (Task 2)

### No other deviations

- No Rule 2 missing-functionality additions (the plan's threat-model mitigations T-01-40 / T-01-42 are fully implemented; T-01-41 is `accept`).
- No Rule 3 blocking-issue fixes.
- No Rule 4 architectural-decision asks.
- No authentication gates were hit (frontend layer; API key / admin auth happens at the network layer not the data-layer).

## Threat Surface

This plan implemented every mitigation declared in the plan's `<threat_model>`:

- **T-01-40** (malformed 409 body crashes modal): mitigated — `isDeleteBlockedBody()` runtime guard returns `false` if the body is not an object, not non-null, or has no `blocking_profile_ids` array (in either supported shape). Non-matching 409s fall through to `setError(err.message)`. UI cannot crash on shape mismatch.
- **T-01-41** (DevTools exposes blueprint): accepted — same disposition as `useProfiles` for `Profile` data; admin-authenticated surface; no secrets in template fields.
- **T-01-42** (type assertions narrow malformed payloads): mitigated — `body` is typed `unknown` end-to-end on `ApiError`. Inside the hook, every access goes through `typeof === "object"`, `Array.isArray`, or a property-existence narrow before reading. The only `as` casts are `(body as { blocking_profile_ids: unknown }).blocking_profile_ids` and equivalent — name-only narrows that immediately feed into `Array.isArray` (which validates the runtime shape).

No new security-relevant surface introduced beyond what the threat register anticipated. **No threat flags raised.**

## Known Stubs

None. All exports have real implementations end-to-end:

- `api.templates.list/get/create/update/remove` each call `request<T>` with the correct path, verb, and JSON body — no mocks or placeholder responses.
- `useTemplates` mounts, polls, mutates, and surfaces errors against the real `api.templates.*` namespace — no `setTemplates([])` defaults that block the upstream wiring; the empty array is the correct initial state for "haven't fetched yet."
- `deleteBlocked` is fully wired (state declaration → `remove`'s catch populates it → `dismissDeleteBlocked` clears it → returned in the public hook surface for Plan 06's modal to consume).

The visible UI surface (`TemplateList`, `TemplateForm`, `DeleteBlockedModal`) lives in Plan 06 and is intentionally out of scope here.

## Issues Encountered

- **Worktree was not based on the orchestrator's expected commit `a387cfc`.** Branch HEAD started at the older `bd15b06`. Resolved per the worktree_branch_check protocol with a `git reset --hard a387cfc2171763357291c8c3bdfef6f3047e7a27`. No work lost (worktree had no commits yet).
- **Plan + 01-PATTERNS.md were not present in the worktree** (untracked in main, not propagated to the worktree). Read the plan content directly from the main repo's `.planning/phases/.../01-05-PLAN.md` path; same approach used by Plan 04's executor.
- **Backend's actual 409 wire shape is nested under `detail`**, not flat as the plan's `<interfaces>` block described. Documented as Rule 1 fix above; type guard handles both shapes so the hook is robust regardless of which convention the backend ends up at.
- **`frontend/tsconfig.tsbuildinfo` was modified by `tsc -b`** (verification step). It IS tracked in the repo (`git ls-files` confirms), but it's a derived artifact and irrelevant to the task. Intentionally NOT staged into either task commit; left dirty in the working tree. Orchestrator can decide whether to commit or discard at merge time.

## User Setup Required

None. No new env vars, no new external services. Plan only adds frontend types and a React hook against the existing `/api/templates` admin-auth-gated surface (Plan 04).

## Next Phase Readiness

- **Plan 06 (TemplateList / TemplateForm / DeleteBlockedModal):** Ready. The hook surface `useTemplates()` returns exactly the fields the UI components need (`templates`, `loading`, `error`, `create`, `update`, `remove`, `deleteBlocked`, `dismissDeleteBlocked`). Zero mock data; the UI will render against real backend responses on first run.
- **Phase 4 (admin dashboard pivot):** No direct dependency in this plan. The `api.templates.*` namespace is reusable.
- **No blockers.**

## Self-Check: PASSED

Verified before returning:

- File `frontend/src/lib/api.ts` modified — FOUND (66-line diff, `git show --stat bd6a603` confirms `1 file changed, 66 insertions(+), 4 deletions(-)`)
- File `frontend/src/hooks/useTemplates.ts` exists, 170 lines — FOUND
- Commit `bd6a603` (Task 1) — FOUND in `git log` on worktree branch
- Commit `a43f7de` (Task 2) — FOUND in `git log` on worktree branch
- TypeScript compile (`npx tsc --noEmit --skipLibCheck -p tsconfig.json`) exits 0
- TypeScript project build (`npx tsc -b`) exits 0
- All 16 existing vitest tests pass (10 in `api.test.ts`, 6 in `useProfiles.test.ts`)
- 22 of 24 grep-based acceptance criteria pass; 2 mismatches (`setDeleteBlocked` and `dismissDeleteBlocked` counts) are documented as plan-grep typos in Deviations (#2)
- `setInterval(refresh, 3000)` count in `useTemplates.ts` (1) matches `useProfiles.ts` (1) — polling cadence locked

---
*Phase: 01-schema-templates-and-security-foundations*
*Plan: 05*
*Completed: 2026-05-08*
