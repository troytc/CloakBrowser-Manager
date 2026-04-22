# External Integrations

**Analysis Date:** 2026-04-22

## APIs & External Services

**CloakBrowser Binary:**
- CloakBrowser headless browser - Provides fingerprint spoofing, proxy support, geolocation spoofing
  - SDK: `cloakbrowser[geoip]` >= 0.3.14
  - Binary location: Auto-downloaded and cached by cloakbrowser package
  - Auth: None (binary is self-contained)
  - Entry point: `backend/browser_manager.py` imports `launch_persistent_context_async`

**HTTP Client:**
- httpx - Internal HTTP requests library
  - Package: `httpx` >= 0.27.0
  - Usage: Found in `backend/main.py` imports
  - No external service dependency — used for internal communication

## Data Storage

**Databases:**
- SQLite (file-based)
  - Connection: `/data/profiles.db` (created in `/data` directory, persistent Docker volume)
  - Client: Python sqlite3 (built-in)
  - Schema: Two tables — `profiles` and `profile_tags`
  - Features: WAL (Write-Ahead Logging), foreign key constraints
  - Implementation: `backend/database.py`

**File Storage:**
- Local filesystem only
  - Profile user data directories: `/data/profiles/{profile_id}/` (persistent volume)
  - Frontend build artifacts: `frontend/dist/` (copied into Docker image)
  - Mounted at `/data` in Docker container

**Caching:**
- None (no Redis, Memcached, or similar)

## Authentication & Identity

**Auth Provider:**
- Custom token-based (optional)
  - Implementation: Bearer token via Authorization header or auth_token cookie
  - Token source: AUTH_TOKEN environment variable (plain text comparison with hmac.compare_digest)
  - Scope: Optional—if AUTH_TOKEN not set, all routes open (local dev mode)
  - Protection: Endpoints `/api/auth/status`, `/api/auth/login`, `/api/status` are exempt
  - All other `/api/*` routes require valid token when AUTH_TOKEN is configured
  - Implementation: `backend/main.py` lines 48-80 (AuthMiddleware)

**Session Management:**
- HTTP cookies (auth_token) — optional, checked in cookie jar if Authorization header not present
- State maintained server-side via in-memory BrowserManager singleton (`backend/main.py`)

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry, Rollbar, etc.)

**Logs:**
- Python logging module - configured in `backend/main.py`
  - Root logger level: INFO
  - Format: `"%(asctime)s %(name)s %(levelname)s %(message)s"`
  - Suppressed loggers: websockets, httpcore, httpx, asyncio (set to WARNING)
  - Log output: stdout/stderr (captured by Docker/systemd)

**System Health:**
- Docker HEALTHCHECK - Pings `http://localhost:8080/api/status` every 30s, 5s timeout, 3 retries

## CI/CD & Deployment

**Hosting:**
- Docker container
  - Base image: python:3.12-slim
  - Multi-stage build: frontend compiled with Node.js 20-slim, then copied into Python image
  - Entrypoint: `entrypoint.sh` (bash script)
  - Port: 8080 (localhost via docker-compose)

**CI Pipeline:**
- Not detected (no GitHub Actions, GitLab CI, etc.)

**Build Process:**
- Frontend: npm build via Vite in Docker build stage
- Backend: pip install from requirements.txt
- Binary prep: CloakBrowser binary pre-downloaded during build
- Cleanup: Stale X11/Chrome lock files removed at container startup

## Environment Configuration

**Required env vars:**
- None are strictly required (all have defaults or are optional)

**Optional env vars:**
- `AUTH_TOKEN` - Bearer token for API authentication (if not set, auth disabled)
- `DISPLAY` - X11 display (set per-process, not user-configurable)

**Secrets location:**
- Docker environment variables (passed via docker-compose.yml or `docker run -e`)
- No `.env` file detected in codebase
- `.gitignore` likely prevents env files from being committed

## Webhooks & Callbacks

**Incoming:**
- WebSocket endpoint: `/api/profiles/{profile_id}/vnc` - VNC frame streaming from KasmVNC server
- No traditional webhooks detected

**Outgoing:**
- None detected—no calls to external APIs for notifications, logging, etc.

## RFB Protocol & VNC Integration

**KasmVNC Server:**
- Version 1.3.3 (installed via .deb package in Docker)
- Protocol: RFB (Remote Framebuffer)
- WebSocket endpoint: `/api/profiles/{profile_id}/vnc`
  - Proxies WebSocket frames to KasmVNC RFB server
  - Uses custom RFB message filtering to strip unsupported extension types
  - Clipboard sync: Translates KasmVNC BinaryClipboard (type 180) to standard RFB ServerCutText (type 3)
  - Origin validation: CSWSH protection via Host/Origin header comparison (browser-only, non-browser clients allowed)

**noVNC Client:**
- Version 1.4.0 (@novnc/novnc npm package)
- Browser-based VNC viewer in React frontend
- Communicates with KasmVNC via WebSocket proxy in backend

## Clipboard Sync

**Two-way clipboard:**
- X11 clipboard via xclip (installed in Docker)
- Frontend: POST `/api/profiles/{profile_id}/clipboard` with text payload (max 1MB)
- Backend: Copies text to X11 selection inside the headless browser's container

## Chrome/Chromium Integration

**Headless Browser:**
- Launched by CloakBrowser (managed by backend/browser_manager.py)
- Chrome DevTools Protocol (CDP): Optional CDP URL returned in launch response
- Profile-specific data directories: `/data/profiles/{profile_id}/`
- Supports proxy, timezone, locale, platform spoofing, fingerprint seed, GPU vendor/renderer hints
- Launch arguments: Custom Chromium flags via launch_args field

---

*Integration audit: 2026-04-22*
