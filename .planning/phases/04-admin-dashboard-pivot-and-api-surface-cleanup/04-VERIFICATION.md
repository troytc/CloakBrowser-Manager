# Phase 4 Verification

**Status:** passed  
**Date:** 2026-05-19

## Criteria

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Admin dashboard shows Sessions + Templates surfaces | pass |
| 2 | Session ops list via GET /api/admin/sessions | pass |
| 3 | Running session opens admin VNC viewer (ProfileViewer) | pass |
| 4 | Legacy profile create/launch UI removed from App | pass |
| 5 | POST launch/stop and legacy CRUD return 410 | pass |

## Tests

- `backend`: 273 passed (2 slow e2e deselected)
- `frontend`: vitest 9 passed

## Notes

- SPA catch-all excludes `viewer/*` GET paths so mistaken `/viewer/{id}/ws` HTTP requests return 404 instead of index.html.
- Legacy admin surface returns 410 for `GET/POST /api/profiles`, `GET/PUT /api/profiles/{id}`, and `POST .../launch`/`.../stop`. `DELETE /api/profiles/{id}` (`main.py:571`) remains live and destructive — it stops the browser, deletes the row, and `rmtree`s the profile dir.

## Human Verification — COMPLETE (2026-09-03)

✓ **Admin VNC smoke (ADM-03)** — confirmed by operator 2026-09-03, closing the deferral
accepted at v1.0 close. Admin dashboard opened the VNC viewer for both `idle` and `running`
sessions; automated admin-sessions and 410 regression tests already covered the contract.
