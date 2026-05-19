# Phase 3: Signed Viewer URLs and Security Hardening — Research

**Researched:** 2026-05-19  
**Phase:** 03-signed-viewer-urls-and-security-hardening  
**Confidence:** HIGH (brownfield; PyJWT + patterns locked in CONTEXT/ROADMAP)

---

## Summary

Phase 3 completes the Main App integration surface: `POST /sessions` must return a fragment-delivered `vnc_viewer_url`, a dedicated `/viewer/*` route must validate HS256 JWTs with JTI single-use before VNC proxying, and security headers must segregate viewer embed (frame-ancestors Main App origin) from admin (`frame-ancestors 'none'`). The VNC proxy logic already exists in `backend/main.py::vnc_proxy` (~160 lines with RFB filter); the work is extraction + a thin viewer auth wrapper, not a rewrite.

**Critical pre-step (ROADMAP):** Inspect `@novnc/novnc` 1.4.0 RFB client usage. Admin dashboard uses `new RFB(container, wsUrl, { wsProtocols: ["binary"] })` in `frontend/src/components/ProfileViewer.tsx`. The iframe viewer will be a **standalone static page** (not the React SPA) so Main App embeds `/viewer/{profile_id}#token=...` without loading the admin bundle.

---

## Standard Stack (locked)

| Component | Choice | Notes |
|-----------|--------|-------|
| Token signing | `PyJWT >= 2.12.1` | Already in `backend/requirements.txt` (Phase 1) |
| Algorithm | HS256 + `VIEWER_SECRET` | No asymmetric keys; Main App never verifies |
| Claims | `profile_id`, `exp`, `jti`, `iat` | CONTEXT D-01/D-02 — use `profile_id` not `sub` |
| JTI store | In-process `dict[str, float]` + TTL eviction | Single-host v1; no SQLite unless planner chooses persistence |
| VNC reuse | Extract `_run_vnc_proxy()` from `main.py::vnc_proxy` | D-05; admin `/api/profiles/{id}/vnc` unchanged auth |
| Viewer HTML | `backend/static/viewer/` or single `viewer.html` + vendored noVNC from npm | Served via FastAPI before SPA catch-all |

---

## Architecture Decisions

### 1. URL shapes

| Surface | Shape | Requirement |
|---------|-------|-------------|
| `POST /sessions` response | `/viewer/{profile_id}#token={jwt}` | VIEW-01, VIEW-04 — fragment never in iframe `src` query |
| Viewer page (GET) | `/viewer/{profile_id}` | Serves HTML; hash stays client-side |
| Viewer WebSocket | `/viewer/{profile_id}/ws` | VIEW-05 — validate before `websocket.accept()` |

**WS token carriage (D-06):** The iframe `src` uses only the path + fragment. Client-side JS reads `window.location.hash` (`#token=...`), then builds the WebSocket URL. **Recommended:** append `?token=` only on the **WebSocket URL** (not the page URL). Rationale: noVNC `RFB` constructor takes a single `wsUrl` string; JWT length exceeds practical `Sec-WebSocket-Protocol` name limits; WS upgrade query is not the same leak surface as iframe `src` querystrings (VIEW-04). **Spike task** in Plan 03-03 confirms noVNC accepts the constructed URL.

**Reject with 4401** on all auth failures; use a single generic reason string (e.g. `"Unauthorized"`) — do not distinguish expired vs wrong profile vs replay (CONTEXT, VIEW-05).

### 2. JTI single-use flow

1. `mint()` generates `jti = uuid4().hex`, registers in `_used_jtis` / pending registry with expiry timestamp.
2. On viewer WS: after `validate()` passes, **before** `accept()`, call `consume_jti(jti)` — if already consumed → 4401.
3. Background eviction: drop entries where `exp < now` (align with token TTL).

### 3. `viewer_attach_count` seam (VIEW-07)

Mirror Phase 2 CDP pattern in `main.py::cdp_proxy` (lines ~1077–1108):

- After successful token validation + `accept()`: increment under `browser_mgr._lock`, `sm.on_attach(profile_id)`.
- `try/finally`: decrement, `on_all_detached` when both counts zero.

### 4. Auth middleware interaction (SEC-02)

`AuthMiddleware` already exempts paths not starting with `/api/` (line ~240). `/viewer/*` is **not** admin-authenticated; JWT enforced in viewer handlers only. Machine routes `/sessions`, `/profiles` remain `APIKeyHeader`-only. **No** `_AUTH_EXEMPT_PREFIXES` change required for `/viewer`.

Register `/viewer` routes **before** the SPA `/{full_path:path}` catch-all (line ~1154).

### 5. CSP (VIEW-08, SEC-04)

| Response class | CSP |
|----------------|-----|
| Viewer HTML + viewer WS (if HTTP metadata) | `Content-Security-Policy: frame-ancestors {MAIN_APP_ORIGIN}` |
| `/api/*` admin JSON | `frame-ancestors 'none'` via middleware or response hook |

Implement `backend/security_csp.py` (or similar) with helpers; apply in viewer routes and a small Starlette middleware for `/api/*` only (not `/sessions` or `/profiles`).

`MAIN_APP_ORIGIN` must be non-empty in production when viewer routes are active (fail startup or log error — match PROJECT.md).

### 6. Clipboard (SEC-07)

- Keep existing **admin** `GET/POST /api/profiles/{id}/clipboard` (cookie auth) for dashboard `ProfileViewer`.
- Add **machine** `GET /profiles/{profile_id}/clipboard` on `profiles_router` with dependency `require_viewer_token` (validates JWT from `X-Viewer-Token` header or `Authorization: Bearer` viewer token).
- `require_api_key` alone → **403** (not 401) on clipboard GET.

### 7. SEC-03 status

`auth_login` already sets `httponly=True`, `samesite="strict"` (`main.py` ~501–507). Plan 03-02 includes a **verification task** only (grep test), not re-implementation.

---

## Codebase anchors

| File | Role |
|------|------|
| `backend/session_manager.py` | `SessionResult.vnc_viewer_url=""` → wire `mint()` |
| `backend/main.py::vnc_proxy` | Extract core loop; admin route stays |
| `backend/routers/sessions.py` | Returns `vnc_viewer_url` from `SessionResult` |
| `backend/browser_manager.py` | `RunningProfile.viewer_attach_count` |
| `frontend/src/components/ProfileViewer.tsx` | Reference noVNC RFB usage (admin WS path) |

---

## Testing strategy

| Layer | Scope |
|-------|--------|
| Unit | `test_viewer_tokens.py` — mint, validate, exp, wrong profile, tamper, JTI consume/replay |
| Router | `test_sessions_router.py` — non-empty `vnc_viewer_url`, fragment format |
| WS | `httpx`/`starlette` TestClient websocket — valid connect; replay/expired/wrong profile → 4401 |
| Security | Clipboard 403 with API key only; 200 with viewer token |
| Manual (VIEW-09) | Optional checkpoint: iframe embed from Main App origin |

Mark slow/real-browser tests with `@pytest.mark.slow` if needed.

---

## Pitfalls (from `.planning/research/PITFALLS.md`)

1. **Token in iframe querystring** — never; fragment only in `vnc_viewer_url`.
2. **Token replay** — JTI consume before proxy starts.
3. **Admin CSRF via viewer iframe** — CSP `frame-ancestors` + `SameSite=Strict` (cookie already strict).
4. **Clipboard OTP leak via API key** — SEC-07 machine route rejects API key.
5. **SPA catch-all swallows `/viewer`** — register viewer routes before `/{full_path:path}`.

---

## Requirement mapping (planning input)

| ID | Primary plan |
|----|----------------|
| VIEW-01 | 03-04 |
| VIEW-02, VIEW-03, VIEW-06 (registry) | 03-01 |
| VIEW-04, VIEW-05, VIEW-06 (consume), VIEW-07, VIEW-08, VIEW-09 | 03-03 |
| SEC-02, SEC-03, SEC-04, SEC-07 | 03-02 |

---

## Open questions (resolved for planning)

| Question | Decision |
|----------|----------|
| JWT claim `sub` vs `profile_id` | **`profile_id`** per CONTEXT D-02 |
| SQLite vs memory JTI | **In-memory** per CONTEXT discretion |
| Viewer UI in React SPA vs static | **Static embed page** — avoids admin bundle, clearer CSP |
| POST `/viewer/exchange` | **Deferred** unless noVNC spike blocks WS token carriage |

---

*Phase: 03-signed-viewer-urls-and-security-hardening*
