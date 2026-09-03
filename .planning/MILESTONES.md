# Milestones

## v1.0 Warm-pool / Templates / Signed-Viewer (Shipped: 2026-05-19)

**Phases completed:** 5 phases, 25 plans

**Stats:** 85 commits since codebase map; 281 backend + 10 frontend tests passing (2026-05-19)

**Key accomplishments:**

- Vendor template CRUD with snapshot profiles, `clipboard_sync=false` defaults, Docker UID fix, and fail-closed production env checks (`MAIN_APP_API_KEY`, `VIEWER_SECRET`).
- `POST /sessions` idempotent warm-pool: per-key locks, dual attach-count idle detection, machine `/profiles` API, and API-key auth on `/sessions` / `/profiles` / CDP WebSocket.
- Signed viewer URLs: HS256 JWT in URL fragment, JTI single-use, CSP `frame-ancestors`, viewer-scoped clipboard, external embed script for CSP compliance.
- Admin dashboard pivot: `SessionList` ops view, templates surface, legacy admin profile CRUD returns 410.
- Admin VNC integrated with warm-pool (`viewer_attach_count`, idle timer, admin clipboard, idle-session viewer).
- Merged upstream fixes: VNC wheel containment, CDP port rotation, profile auto-launch on container start.

**Tech debt (accepted at close):** VIEW-09 human iframe smoke on Main App origin (**still open**); SESS-12 slow e2e deselected in default CI (**still open**); ADM-03 admin VNC not manually QA'd (**✓ cleared 2026-09-03**). See [milestones/v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md).

**Post-ship verification (2026-09-03):** 7 of the 10 outstanding human-verification items
closed — all six Phase 01 items (Phase 01 UAT now 7/7, including the delete-blocked modal /
BL-02 fix and the OPS-04 container UID-mismatch recreate) plus Phase 04/05 ADM-03 admin VNC
and clipboard. OPS-04 and SEC-05 move from static to live verification.

Three items remain open, each gated on a resource outside this repo: SESS-12 slow E2E (needs
the CloakBrowser binary), Main App integration smoke (needs the consuming application), and
VIEW-09 viewer iframe smoke (needs the real Main App origin).

Known deferred items at close: 1 — ✓ resolved 2026-09-03; 3 environment-gated items still
open (see STATE.md Deferred Items)

---
