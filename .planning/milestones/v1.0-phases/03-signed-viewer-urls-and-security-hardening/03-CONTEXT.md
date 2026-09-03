# Phase 3: Signed Viewer URLs and Security Hardening - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous / YOLO — ROADMAP + research + Phase 2 handoff)

<domain>
## Phase Boundary

After Phase 3:

- `POST /sessions` returns `vnc_viewer_url` of the form `/viewer/{profile_id}#token=<jwt>` (fragment, never querystring).
- JWT is HS256 via `VIEWER_SECRET`; claims `{profile_id, exp, jti, iat}`; TTL from `VIEWER_TOKEN_TTL_SECS` (default 300).
- `/viewer/{profile_id}/ws` (or equivalent viewer WS route per plan) validates token before `websocket.accept()`; replays/expiry/wrong-profile/tamper → close `4401` without leaking which check failed.
- JTI single-use: server-side registry marks `jti` consumed on first successful viewer WS upgrade.
- `viewer_attach_count` on `RunningProfile` incremented/decremented in viewer WS `try/finally`; feeds `SessionManager` idle (already wired for CDP in Phase 2).
- CSP: viewer HTML/WS responses carry `frame-ancestors <MAIN_APP_ORIGIN>`; admin API responses carry `frame-ancestors 'none'`.
- Admin `auth_token` cookie: `SameSite=Strict; HttpOnly`.
- `GET /api/profiles/{id}/clipboard` (or machine route if moved): 403 with API key only; succeeds with valid viewer-scoped token.

Out of scope: Phase 4 admin dashboard pivot, removal of legacy `/api/profiles/{id}/launch`, SessionList UI.

</domain>

<decisions>
## Implementation Decisions

### Viewer tokens (`viewer_tokens.py`)

- **D-01:** Pure module `backend/viewer_tokens.py` — no FastAPI/BrowserManager imports. `mint(profile_id) -> str`, `validate(token, claimed_profile_id) -> dict` (claims), raises `ViewerTokenError` on failure.
- **D-02:** PyJWT >= 2.12.1 only; HS256; `jti` = `uuid4().hex` per mint.
- **D-03:** JTI registry in-process (`dict[str, float]` or similar with TTL eviction aligned to token exp). Mark consumed on first successful viewer WS upgrade (after all crypto checks pass). Replay → 4401.
- **D-04:** Token delivery: URL path `/viewer/{profile_id}` + fragment `#token=<jwt>`. Never put token in querystring (SEC / Pitfall 3).

### Viewer route & VNC reuse

- **D-05:** Extract shared VNC proxy loop from `main.py::vnc_proxy` into `_run_vnc_proxy(websocket, profile_id, ...)` (or `vnc_proxy_core`) so admin `/api/profiles/{id}/vnc` and new `/viewer/*` route share one implementation. Viewer route adds token validation + `viewer_attach_count` + CSP.
- **D-06:** Viewer WS validates token in `Sec-WebSocket-Protocol` or first message OR query param on WS only if no alternative — **prefer**: noVNC reads hash and passes token on WS upgrade via subprotocol or dedicated header if supported; **fallback per research**: document noVNC hash hook in static bundle. Planner must spike noVNC 1.4.0 client location (ROADMAP pre-step ~30 min).
- **D-07:** Wire `SessionManager` / `POST /sessions` to call `viewer_tokens.mint(profile_id)` and set `vnc_viewer_url` on `WakeResult` / `SessionResponse`.

### Security hardening (same phase)

- **D-08:** `MAIN_APP_ORIGIN` env var drives `frame-ancestors` on viewer responses (already required in PROJECT.md).
- **D-09:** Admin login `Set-Cookie` for `auth_token`: add `SameSite=Strict` (keep `HttpOnly`; `Secure` when HTTPS).
- **D-10:** Middleware or route dependency adds `Content-Security-Policy: frame-ancestors 'none'` on `/api/*` admin JSON responses (not machine `/sessions`/`/profiles`).
- **D-11:** Clipboard endpoint: reject `X-API-Key`-only auth; accept viewer JWT (same validation as WS, or dedicated header `X-Viewer-Token` on GET). API key → 403.

### Auth surfaces (unchanged from Phase 2)

- **D-12:** Machine routes stay on `require_api_key`. Viewer HTML/WS exempt from admin `AuthMiddleware` but enforce viewer JWT at handler. Admin `/api/profiles/{id}/vnc` stays admin-cookie auth (not Main App path).

### Testing

- **D-13:** Unit tests for `viewer_tokens.py` (mint, validate, exp, wrong profile, tamper). Integration tests for `/sessions` returning non-empty `vnc_viewer_url`. WS tests with TestClient/httpx ws: valid token connects; replay/expired/wrong profile → 4401. Clipboard 403/200 matrix.

### Claude's Discretion

- Exact viewer URL path layout (`/viewer/{id}` static HTML + `/viewer/{id}/ws` vs single WS) — follow existing `main.py` VNC patterns and noVNC bundle layout.
- JTI storage: SQLite table vs in-memory — prefer in-memory for v1 single-host; planner may add small `used_viewer_jtis` table if persistence across restart is needed (not required for v1).
- Whether viewer static page is served from FastAPI `FileResponse` or embedded in existing frontend build.

</decisions>

<code_context>
## Existing Code Insights

- `backend/session_manager.py` — `WakeResult.vnc_viewer_url=""` placeholder; wire mint here or in sessions router.
- `backend/main.py::vnc_proxy` — full VNC proxy with RFB filter; refactor target for D-05.
- `backend/main.py` — CDP WS already has `_ws_api_key_valid`; viewer WS is separate auth (JWT not API key).
- `backend/auth_api_key.py` — do not use for viewer; segregated auth.
- `backend/models.py::SessionResponse` — `vnc_viewer_url: str = ""` ready to populate.
- Phase 2 `viewer_attach_count` on `RunningProfile` and `SessionManager.on_attach` / `on_all_detached` — reuse for viewer WS.

</code_context>

<specifics>
## Specific Ideas

- ROADMAP: read noVNC 1.4.0 client for `window.location.hash` / `#token=` extraction before implementing viewer HTML route.
- Research: fragment not querystring; JTI single-use; generic 4401 errors.

</specifics>

<deferred>
## Deferred Ideas

- Read-only viewer mode (encode in token) — v2.
- POST `/viewer/exchange` cookie exchange — only if fragment approach blocked by noVNC constraints.

</deferred>
