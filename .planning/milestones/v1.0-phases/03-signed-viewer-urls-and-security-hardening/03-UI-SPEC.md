# Phase 3 UI-SPEC: Main App Embed Viewer

**Phase:** 03-signed-viewer-urls-and-security-hardening  
**Scope:** Standalone iframe viewer page (`/viewer/{profile_id}`) — **not** admin dashboard chrome  
**Status:** Design contract for Plan 03-03

---

## User & context

| Actor | Goal |
|-------|------|
| End user (via Main App iframe) | See live vendor portal in browser for 2FA / manual steps |
| Main App (embedder) | iframe `src` = `vnc_viewer_url` from `POST /sessions` |

The viewer must be **chromeless**: no admin nav, no profile list, no auth login UI.

---

## Layout

```
┌─────────────────────────────────────────────┐
│  [optional thin status bar — 32px max]      │
│  ┌─────────────────────────────────────────┐│
│  │                                         ││
│  │         VNC canvas (100% flex)          ││
│  │                                         ││
│  └─────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
```

- **Viewport:** `100vh` / `100vw`, `overflow: hidden`, dark background `#0a0a0a` (match admin `ProfileViewer` feel).
- **Status bar (optional):** Connection state only — "Connecting…" / "Connected" / "Session ended". No toolbar buttons in v1 (read-only embed is deferred).
- **No** clipboard toggle in embed page v1 (clipboard follows profile `clipboard_sync` server-side; UI toggle is admin-only).

---

## States

| State | UI |
|-------|-----|
| Loading | Centered spinner or "Connecting…" text on dark bg |
| Connected | Status hidden or subtle green dot; canvas full bleed |
| Auth failure (4401) | "This viewer link has expired or is invalid." — no token details |
| Profile not running (4004) | "Browser session is not available. Request a new session from your application." |
| noVNC securityfailure | Show `detail.reason` if present, else generic error |

---

## Typography & color

Reuse existing admin palette variables where possible (`frontend/src/styles/globals.css`):

- Background: near-black `#0a0a0a`
- Text: `#e5e5e5` / muted `#9ca3af` for status
- Error: `#f87171` (red-400 equivalent)
- Font: system-ui stack already in globals — **do not** import Inter or other admin fonts into static page unless already bundled with noVNC copy

---

## Interaction

- **Keyboard/mouse:** Passed through to noVNC canvas (standard RFB).
- **Clipboard:** If profile has `clipboard_sync=true`, same Host↔VNC behavior as admin `ProfileViewer` only if implemented in static page; otherwise rely on VNC-native copy inside remote browser (v1 acceptable per CONTEXT discretion).
- **Resize:** `rfb.scaleViewport = true`, `resizeSession = false` (match `ProfileViewer.tsx`).

---

## Client bootstrap (functional contract)

1. Parse `profile_id` from path segment `/viewer/{profile_id}`.
2. Parse JWT from `window.location.hash`: `#token=<jwt>` (strip leading `#`, handle `token=` key).
3. If missing token → show auth error state (do not open WS).
4. Build `wsUrl = ${wsProtocol}//${host}/viewer/${profile_id}/ws?token=${encodeURIComponent(jwt)}`.
5. `new RFB(container, wsUrl, { wsProtocols: ["binary"] })`.

---

## Accessibility

- Status messages in a `role="status"` live region.
- Canvas container `tabindex="0"` so keyboard focus reaches VNC.

---

## Out of scope (Phase 3)

- Admin dashboard changes (Phase 4)
- Read-only viewer / pointer suppression (deferred)
- Custom branding per vendor template

---

*Consumed by: 03-03-PLAN.md*
