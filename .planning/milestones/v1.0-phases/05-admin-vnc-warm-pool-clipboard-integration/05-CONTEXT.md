# Phase 5: Admin VNC warm-pool + clipboard integration - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning (executed inline via autonomous)
**Source:** v1.0-MILESTONE-AUDIT.md integration gaps

## Phase Boundary

Close milestone audit gaps for the **admin dashboard** VNC path without changing the Main App signed-viewer contract.

## Decisions

1. **Admin VNC uses `viewer_attach_count`** — `vnc_proxy` in `main.py` mirrors `routers/viewer.py` attach/decrement + `SessionManager.on_attach` / `on_all_detached`.
2. **Admin clipboard read stays on `/api/profiles/{id}/clipboard`** — AuthMiddleware-gated admin route; machine `/profiles/{id}/clipboard` remains viewer-token-only (SEC-07).
3. **Idle sessions are viewable** — `idle` means Chromium is up with zero attaches; admin UI opens `ProfileViewer` for `running` and `idle`.

## Out of scope

- Minting viewer JWTs for admin dashboard (admin uses cookie-auth VNC + admin clipboard).
- Removing legacy 410 stubs or orphaned `ProfileForm.tsx`.
