---
phase: 01-schema-templates-and-security-foundations
reviewed: 2026-05-08T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - .env.example
  - .gitignore
  - backend/database.py
  - backend/main.py
  - backend/models.py
  - backend/requirements.txt
  - backend/routers/__init__.py
  - backend/routers/templates.py
  - backend/tests/conftest.py
  - backend/tests/test_api.py
  - docker-compose.yml
  - entrypoint.sh
  - frontend/src/App.tsx
  - frontend/src/components/DeleteBlockedModal.tsx
  - frontend/src/components/ProfileForm.tsx
  - frontend/src/components/TemplateForm.tsx
  - frontend/src/components/TemplateList.tsx
  - frontend/src/hooks/useProfiles.test.ts
  - frontend/src/hooks/useTemplates.ts
  - frontend/src/lib/api.ts
findings:
  blocker: 2
  warning: 7
  info: 5
  total: 14
status: issues_found
---

# Phase 01 Code Review Report

**Reviewed:** 2026-05-08
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Phase 1 ships the vendor-template schema, /api/templates router, fail-closed startup check, env-var scaffolding, and the full Templates admin UI. The wiring is largely correct and the SEC-05 sweep is clean at the *typed* model layer, but two concrete defects compromise the phase's stated security & UX guarantees:

1. **The legacy migration ALTER still injects `clipboard_sync BOOLEAN DEFAULT 1`** — directly contradicting CLAUDE.md security rule 2 ("clipboard_sync defaults to false on every vendor template and every profile"). The plan executor flagged the conflict but kept the line; it remains a footgun for any pre-D-18 dev DB and any future code path that relies on the column default.
2. **The TemplateForm's "delete" affordance has a stale-closure bug** that unmounts the form even when the server returns 409 Delete Blocked — meaning the user is bounced back to the empty list while the modal floats above empty space, contradicting the planned "form stays open when delete is blocked" UX.

Both issues are reachable in normal operation. Five additional warnings cover defense-in-depth gaps (un-validated blueprint round-trip in the snapshot helper, FastAPI 422 detail being swallowed by the frontend hook, no test coverage for the new templates router, etc.).

The phase's stated CLAUDE.md invariants — strict admin-auth on /api/templates, no `_AUTH_EXEMPT` entry, snapshot-copy on profile create, no querystring tokens — all hold under inspection.

## Blocker Issues

### BL-01: clipboard_sync migration column default is still `1` — violates CLAUDE.md security rule 2

**File:** `backend/database.py:85-87`
**Issue:** The retained legacy migration block executes `ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1` for any database that pre-dates the column. CLAUDE.md security rule 2 reads: *"`clipboard_sync` defaults to `false` on every vendor template and every profile."* Plan 01-01's deviations note documents the conflict and chose to keep the line; that decision violates the security rule.

The wipe block on lines 97-114 currently masks the impact (rows are deleted before they leak), but:
- The wipe is conditional on `vendor_type` being missing. A future schema change that lands `vendor_type` separately would leave clipboard_sync=1 rows alive.
- The column-level DEFAULT 1 persists after the wipe. Any future INSERT that omits clipboard_sync — including tests, raw SQL fixtures, or future helper code — gets a clipboard-leaking default. The current `create_profile()` always passes the value explicitly, so the default is dormant; that is a maintenance hazard, not a guarantee.
- The plan's own grep-based acceptance criterion (`grep -c "clipboard_sync BOOLEAN DEFAULT 1" backend/database.py == 0`) explicitly forbade this line.

**Fix:** Change the legacy ALTER's default to `0` to match the CREATE TABLE default and the SEC-05 contract:
```python
if "clipboard_sync" not in cols:
    conn.execute("ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 0")
    conn.commit()
```
If backwards compatibility with pre-existing rows is a concern, add a follow-on `UPDATE profiles SET clipboard_sync = 0 WHERE clipboard_sync = 1` to forcibly normalise. Then verify with `grep -c "DEFAULT 1" backend/database.py` returns 0.

---

### BL-02: TemplateForm closes on delete-blocked due to stale-closure read of `deleteBlocked`

**File:** `frontend/src/App.tsx:142-149`
**Issue:** `handleDeleteTemplateFromForm` reads `deleteBlocked` from its render-time closure to decide whether to unmount the form:
```tsx
const handleDeleteTemplateFromForm = async () => {
    if (!selectedTemplateId) return;
    await removeTemplate(selectedTemplateId);
    if (!deleteBlocked) {                       // ← stale read
      setSelectedTemplateId(null);
      setTemplateView("empty");
    }
};
```
Inside `useTemplates.remove`, a 409 response calls `setDeleteBlocked({...})` synchronously after `await api.templates.remove(id)` rejects. Crucially, `removeTemplate(id)` does NOT throw on 409 (the catch block returns void after setting state). So `await removeTemplate(...)` resolves, control returns to the handler, and the handler reads `deleteBlocked` from the closure — which still holds the *previous* render's value (`null` on the first delete attempt).

Result: on the very first 409, `if (!deleteBlocked)` evaluates true, `setSelectedTemplateId(null)` and `setTemplateView("empty")` fire, the edit form unmounts, and the user is bounced to the templates list. The DeleteBlockedModal does still appear (it reads from the freshly-set state on the next render), but the planned "form stays open while modal blocks the delete" UX is broken — the 01-06 SUMMARY's "form stays open when blocked" claim does not hold.

**Fix:** Either (a) make `useTemplates.remove` return a discriminated result the caller can branch on, or (b) read state from `useTemplates`'s output after the await resolves but before deciding to unmount. The cleanest fix returns a result:
```tsx
// In useTemplates.ts:
const remove = useCallback(async (id: string): Promise<{ blocked: boolean }> => {
    try {
        await api.templates.remove(id);
        setTemplates((prev) => prev.filter((x) => x.id !== id));
        setError(null);
        return { blocked: false };
    } catch (err) {
        if (err instanceof ApiError && err.status === 409 && isDeleteBlockedBody(err.body)) {
            setDeleteBlocked({ ... });
            return { blocked: true };
        }
        setError(err instanceof Error ? err.message : "Failed to delete template");
        return { blocked: false };
    }
}, [templates]);

// In App.tsx:
const handleDeleteTemplateFromForm = async () => {
    if (!selectedTemplateId) return;
    const { blocked } = await removeTemplate(selectedTemplateId);
    if (!blocked) {
        setSelectedTemplateId(null);
        setTemplateView("empty");
    }
};
```

## Warnings

### WR-01: Phase-1 templates router has zero backend test coverage

**File:** `backend/tests/test_api.py` (entire file)
**Issue:** `grep -c "templates" backend/tests/test_api.py` returns 0. The new `/api/templates` CRUD surface — including the two-layer delete guard, duplicate-vendor-type 409 with exact copy, slug regex 422, and the AuthMiddleware integration — has no committed pytest coverage. Plan 01-04's verification block ran TestClient assertions inline in the executor's shell but did not commit them. Regression risk on Phase 2 is high: any future change that touches `backend/routers/templates.py` or the AuthMiddleware boundary lands without an automated safety net.
**Fix:** Add `backend/tests/test_templates_api.py` covering at minimum: 401-without-token, 200-empty-list, 201 + 409 duplicate, 422 invalid slug, 200 update preserves vendor_type, 404 unknown id, 409 delete-blocked with `blocking_profile_ids`, 200 delete after profiles cleared. The plan-04 SUMMARY's embedded TestClient block is a near-verbatim seed for these tests.

### WR-02: `create_profile_from_template` reads JSON blueprint without re-validating against `TemplateBlueprint`

**File:** `backend/database.py:395-443`
**Issue:** `create_profile_from_template` calls `json.loads(template["blueprint"])` and reads fields via `bp.get(...)` directly into the INSERT. The `TemplateBlueprint` Pydantic model — which exists specifically to coerce `clipboard_sync=null → False` (D-18) and to constrain Literal unions — is never re-applied here. Lines 433 (`bool(bp.get("clipboard_sync", False))`) protects the clipboard default specifically, but `platform`, `human_preset`, `color_scheme` are passed through unchecked.

If a template's blueprint JSON is ever corrupted (manual SQLite edit, partial migration, future bug) the snapshot will faithfully copy the corruption into the profile row, and Phase 2's launcher will see a value Pydantic would have rejected. Defence-in-depth would re-validate before insertion.
**Fix:**
```python
from .models import TemplateBlueprint
bp = template["blueprint"]
if isinstance(bp, str):
    bp = json.loads(bp)
bp = TemplateBlueprint.model_validate(bp).model_dump()
```
Then read fields from the validated dict. Adds ~3 lines and closes the loophole.

### WR-03: FastAPI 422 detail is silently coerced to "Unprocessable Entity" — TemplateForm shows no field-level error

**File:** `frontend/src/lib/api.ts:144-148`, `frontend/src/components/TemplateForm.tsx:62-87`
**Issue:** When the server returns 422 (e.g., `vendor_type="MyVendor"` fails the slug regex), FastAPI emits `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` — a list, not a string. The api.ts request helper has the right idea (`typeof body?.detail === "string"` guard) but falls back to `res.statusText` ("Unprocessable Entity") instead of digging into the array. `useTemplates.create`'s catch handler then surfaces the generic `"Unprocessable Entity"` to the global error banner.

TemplateForm's `fieldErrors.vendor_type` is wired to render an inline `role="alert"` (line 174-178), and the comment block on lines 77-83 explicitly notes the gap: *"more precise 422 field-error wiring would require useTemplates to surface the ApiError directly. Phase 1 keeps that simple."* The simple version means: a user who types "Shopify" and presses Save sees only "Unprocessable Entity" with no clue what's wrong.

**Fix:** In `request<T>`, detect Pydantic 422 list-shaped detail and stringify:
```typescript
const detailField = (body as { detail?: unknown })?.detail;
const detailText =
  typeof detailField === "string" ? detailField :
  Array.isArray(detailField) ? detailField.map((e: any) => `${(e?.loc ?? []).join(".")}: ${e?.msg ?? ""}`).join("; ") :
  res.statusText;
```
Then have TemplateForm's catch surface the message into `fieldErrors.vendor_type` when the message contains `vendor_type`. Even without per-field wiring, the toast text becomes actionable.

### WR-04: `update_template` always bumps `updated_at`, even when caller passes only unrecognised kwargs

**File:** `backend/database.py:335-356`
**Issue:** The early-return `if not fields: return get_template(template_id)` on line 336-337 only triggers when `fields` is empty. If the caller passes `update_template(id, foo="bar")`, `fields` is non-empty but the loop on line 340 finds no recognized keys, so `sets` ends up as `["updated_at = ?"]` and the SQL bumps only `updated_at`. The current router doesn't pass unknown kwargs (Pydantic guards), but the helper is now publicly importable from `database.py` and a future caller (Phase 2 SessionManager?) could trip the silent updated_at bump. Worse, no test catches this.
**Fix:** Track whether any recognised key was found:
```python
recognized = False
for key in ("label", "notes", "blueprint_json"):
    if key in fields:
        col = "blueprint" if key == "blueprint_json" else key
        sets.append(f"{col} = ?")
        values.append(fields[key])
        recognized = True
if not recognized:
    return get_template(template_id)
sets.append("updated_at = ?")
...
```

### WR-05: `entrypoint.sh` chown uses unquoted `${CHROME_UID}` interpolation

**File:** `entrypoint.sh:9`
**Issue:** `chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles` lacks double-quotes around the parameter expansion. If `CHROME_UID` ever contains whitespace or a colon (admin error, env-var injection from a future compose change), bash word-splits the value into separate tokens and `chown` receives malformed arguments. The current `set -e` will catch a chown failure, but the failure mode is opaque ("invalid user", not "your CHROME_UID env var contains a space"). Source CHROME_UID flows through docker-compose so direct exploitation is implausible, but quoting is the standard hardening.
**Fix:**
```bash
chown -R "${CHROME_UID:-0}:${CHROME_UID:-0}" /data/profiles
```

### WR-06: `.env.example` comment misrepresents which routes API-key guards (says `/profiles/*`, but `/api/profiles/*` is admin-auth-only)

**File:** `.env.example:11`
**Issue:** The comment reads: *"Shared secret the Main App presents in the X-API-Key header on /sessions/* and /profiles/*."* But Phase 1 has not added an API-key middleware, and `/api/profiles/*` is currently guarded by `AuthMiddleware` (admin Bearer/cookie). Phase 2 is expected to introduce machine auth on `/sessions/*` only — per CLAUDE.md security rule 3, `/profiles/*` belongs to the admin surface. If Phase 2 follows the .env.example wording literally, it will install API-key auth on `/profiles/*` and create the path overlap CLAUDE.md explicitly forbids.
**Fix:** Trim the comment to match CLAUDE.md rule 3 verbatim:
```
# Shared secret the Main App presents in the X-API-Key header on /sessions/*.
```
Add a single-line cross-reference if helpful: `# Admin /api/profiles/* remains guarded by AUTH_TOKEN (AuthMiddleware).`

### WR-07: TemplateForm vendor_type field is locked on edit but the same form's Identity section claims "Vendor Type" with no read-only styling

**File:** `frontend/src/components/TemplateForm.tsx:165-179`
**Issue:** The `<input>` for vendor_type sets `disabled={isEdit}` but no visual cue (e.g., `cursor-not-allowed`, helper text "vendor_type cannot be changed; delete and re-create to rename") is shown. Browser default greyed-out styling depends on the global `.input` class; a user staring at an "Edit Template" form will likely click the field, see nothing happen, and assume the field is broken. The 01-UI-SPEC's Identity section is the natural place to surface this.
**Fix:** Either add a small helper line under the disabled input ("Vendor type is the lookup key — delete + re-create to rename"), or add a tooltip via `title=`. Cosmetic but reduces a real UX dead-end.

## Info

### IN-01: Unused `logger` in templates router

**File:** `backend/routers/templates.py:24`
**Issue:** `logger = logging.getLogger("cloakbrowser.manager.templates")` is declared but never invoked anywhere in the file. `import logging` and the logger declaration are dead code.
**Fix:** Either remove both, or actually log the 409 delete-blocked / IntegrityError race-window cases (the latter would aid post-mortem debugging if the race ever fires).

### IN-02: `backend/routers/__init__.py` is 0 bytes — fine, but consider an `__all__` re-export of `templates_router`

**File:** `backend/routers/__init__.py`
**Issue:** Empty package init is valid, but importing `from backend.routers import templates_router` would be cleaner than today's `from backend.routers.templates import router as templates_router` (used in main.py). Trivial style nit; matches existing `backend/__init__.py` convention.
**Fix:** Optional. If desired:
```python
from .templates import router as templates_router
__all__ = ["templates_router"]
```

### IN-03: `assert result is not None` in `create_template` and `create_profile_from_template` is stripped under `python -O`

**File:** `backend/database.py:331, 442`
**Issue:** Two `assert result is not None` statements after a `get_*()` call. Under `python -O` (or a future stripped-bytecode container), these asserts vanish and `None` could propagate up despite the `dict[str, Any]` return type annotation. The chance of `get_*()` returning None immediately after the matching INSERT is low (would require concurrent DELETE in the same connection's snapshot), but the assert is the wrong tool for the job.
**Fix:** Replace with a runtime check + raise:
```python
result = get_template(template_id)
if result is None:
    raise RuntimeError(f"Template {template_id} disappeared between INSERT and SELECT")
return result
```

### IN-04: `console.warn` in App.tsx auth-status catch leaks dev-mode noise into production console

**File:** `frontend/src/App.tsx:39`
**Issue:** `console.warn("[auth] status check failed:", err);` ships in production builds. Low-impact, but production browser consoles ideally stay quiet so real warnings stand out.
**Fix:** Either gate behind `if (import.meta.env.DEV) console.warn(...)`, or remove (the UI already shows a "Unable to reach the server" banner which is the user-actionable path).

### IN-05: DeleteBlockedModal lacks `aria-describedby` even though Plan 01-06 SUMMARY claims it

**File:** `frontend/src/components/DeleteBlockedModal.tsx:42-48`
**Issue:** The 01-06 SUMMARY claims *"aria-modal + aria-labelledby + aria-describedby"*, but the rendered dialog has only `aria-modal` and `aria-labelledby`. Screen readers will announce the title but miss the body explaining *why* the delete was blocked.
**Fix:** Add an id to the descriptive `<p>` element and reference it:
```tsx
<div role="dialog" aria-modal="true" aria-labelledby="delete-blocked-title" aria-describedby="delete-blocked-desc">
  ...
  <p id="delete-blocked-desc" className="...">
    The template <span ...>{vendorType}</span> has <span ...>{n}</span> ...
  </p>
```

---

_Reviewed: 2026-05-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
