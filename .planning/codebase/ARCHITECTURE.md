# Architecture

**Analysis Date:** 2026-04-22

## Pattern Overview

**Overall:** Client-Server with Real-Time VNC Streaming

This is a **dual-layer web application** serving a React dashboard that manages headless browser instances. The backend is a FastAPI server that:
1. Manages lifecycle of Chromium profiles (launch, stop, cleanup)
2. Proxies VNC connections from noVNC client to KasmVNC server
3. Maintains profile state in SQLite
4. Provides REST API for CRUD and control operations

**Key Characteristics:**
- **Stateful backend** - Tracks running browser instances in memory (`BrowserManager.running`)
- **WebSocket streaming** - Real-time VNC framebuffer and input streaming between frontend and browser
- **RFB protocol translation** - Filters/rewrites RFB messages for KasmVNC compatibility
- **Async-first** - Uses asyncio throughout; Playwright for browser automation; uvicorn ASGI server
- **Static frontend** - React SPA served from `/frontend/dist` via FastAPI's StaticFiles

## Layers

**Frontend (React):**
- Purpose: Dashboard UI for profile management and live VNC viewing
- Location: `frontend/src/`
- Contains: React components, hooks, API client
- Depends on: Backend REST API, WebSocket proxy
- Used by: Browser users

**Backend API Layer:**
- Purpose: REST endpoints for CRUD operations and system status
- Location: `backend/main.py` (routes defined here)
- Contains: Route handlers for profiles, auth, clipboard, system status
- Depends on: Database layer, BrowserManager, Pydantic models
- Used by: Frontend, external clients (Playwright scripts)

**Backend Business Logic Layer:**
- Purpose: Browser lifecycle management and process orchestration
- Location: `backend/browser_manager.py`
- Contains: Profile launch/stop, running instance tracking, cleanup
- Depends on: CloakBrowser library, VNCManager, database
- Used by: API layer route handlers

**Backend Infrastructure Layer:**
- Purpose: Low-level coordination
- Location: `backend/vnc_manager.py`, `backend/database.py`
- Contains: VNC display allocation, WebSocket proxy, SQLite operations
- Depends on: System libraries (Xvnc, xclip), SQLite, asyncio
- Used by: BrowserManager, API layer

**Data Layer:**
- Purpose: Persistent profile storage
- Location: `backend/database.py`
- Contains: SQLite schema, CRUD functions for profiles and tags
- Depends on: SQLite3 (standard library)
- Used by: BrowserManager, API handlers

## Data Flow

**Profile Creation Flow:**

```
1. Frontend: User submits ProfileForm → POST /api/profiles
2. API Handler: Validates via ProfileCreate model
3. Database: Inserts new profile, generates UUID
4. API Response: Returns ProfileResponse with status="stopped"
5. Frontend: Updates profile list, renders in ProfileList
```

**Profile Launch Flow:**

```
1. Frontend: User clicks Launch → POST /api/profiles/{id}/launch
2. API Handler: Looks up profile in database
3. BrowserManager:
   a. VNCManager allocates display (e.g., :100) and WebSocket port (e.g., 6100)
   b. VNCManager starts Xvnc process with KasmVNC
   c. launch_persistent_context_async() starts Chromium via CloakBrowser
   d. Browser context stored in running[profile_id]
4. API Response: Returns LaunchResponse with vnc_ws_port, cdp_url
5. Frontend: Shows ProfileViewer with noVNC connected to WebSocket endpoint
```

**VNC Proxy Flow:**

```
1. Frontend: ProfileViewer connects via WebSocket to /api/profiles/{id}/vnc
2. API Handler: Accepts WebSocket, checks origin (CSWSH protection)
3. Backend:
   a. Connects to KasmVNC server on localhost:6100 (/websockify)
   b. client_to_vnc() loop: receives RFB messages from noVNC, filters for KasmVNC compatibility
   c. vnc_to_client() loop: receives server messages, relays to frontend
   d. RFB message filtering: strips unsupported types (150, 248, etc.)
4. RFB Protocol:
   - Standard types 0-6 allowed (SetPixelFormat, SetEncodings, FramebufferUpdateRequest, etc.)
   - PointerEvent expanded from 6-byte to 11-byte KasmVNC format
   - SetEncodings whitelist filters pseudo-encodings (quality, compress levels)
   - KasmVNC BinaryClipboard (type 180) parsed into text/plain
```

**Clipboard Sync Flow:**

```
1. When clipboard_sync=true (profile setting):
   - Frontend reads Chrome's clipboard via Playwright CDP
   - GET /api/profiles/{id}/clipboard reads window.__clipboardText from browser context
   - Falls back to xclip -o if script doesn't have content
   - Returns text (1MB max)
   
2. When setting clipboard from external source:
   - POST /api/profiles/{id}/clipboard with text body
   - Runs xclip -selection clipboard with text on STDIN
   - Process stays alive to serve paste requests
   - Frontend can inject via VNC keyboard events
```

**State Management:**

- **Backend In-Memory State:** `BrowserManager.running` dictionary maps profile_id → RunningProfile (contains playwright.BrowserContext, display, ws_port)
- **Frontend State:** Uses `useProfiles()` hook with 3-second polling refresh for status updates
- **Database State:** SQLite profiles table (immutable except for updates via API), profile_tags junction table
- **VNC State:** Stateful WebSocket connection per viewer; KasmVNC maintains framebuffer per display

## Key Abstractions

**RunningProfile (dataclass):**
- Purpose: Represents an actively running browser instance
- Examples: `backend/browser_manager.py` line ~30 (dataclass definition)
- Pattern: Stored in dict[str, RunningProfile] for O(1) lookup
- Properties: display (X11 display :N), ws_port (WebSocket port), context (Playwright), playwright.Page

**Profile Model:**
- Purpose: Immutable schema for browser configuration
- Examples: `backend/models.py` ProfileCreate, ProfileUpdate, ProfileResponse
- Pattern: Pydantic BaseModel with validators; split into Create/Update/Response variants
- Properties: fingerprint_seed, proxy, timezone, locale, platform, screen dimensions, GPU, humanize settings, launch_args, clipboard_sync

**VNCInstance (dataclass):**
- Purpose: Track allocated VNC display/port pair
- Examples: `backend/vnc_manager.py` VNCInstance
- Pattern: Allocated by VNCManager, tracks Xvnc subprocess
- Properties: display (int), ws_port (int), process (subprocess.Popen)

**RFB Message (bytes):**
- Purpose: Binary VNC protocol messages
- Pattern: Concatenated in single WebSocket frames; parsed via fixed message types and sizes
- Filtering: `_filter_rfb_client_messages()` parses boundaries and strips unsupported types

## Entry Points

**Backend:**
- Location: `backend/main.py` line ~382
- Triggers: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- Responsibilities:
  - Initialize FastAPI app with AuthMiddleware
  - Mount static frontend files at `/`
  - Bind database on startup
  - Clean up stale VNC processes

**Frontend:**
- Location: `frontend/src/main.tsx`
- Triggers: Vite dev server or built-in static files served by FastAPI
- Responsibilities:
  - Render App component
  - Check auth status
  - Show LoginPage if required, AppContent if authenticated

**API Entry Points (key routes):**
- `POST /api/auth/login` - Authenticate and set cookie
- `GET /api/profiles` - List all profiles with live status
- `POST /api/profiles` - Create new profile
- `POST /api/profiles/{id}/launch` - Start browser and VNC
- `POST /api/profiles/{id}/stop` - Stop browser
- `WebSocket /api/profiles/{id}/vnc` - VNC framebuffer proxy
- `POST /api/profiles/{id}/clipboard` - Set clipboard
- `GET /api/profiles/{id}/clipboard` - Read clipboard

## Error Handling

**Strategy:** Layered error responses with HTTP status codes

**Patterns:**

**API Layer:**
- HTTPException(status_code=404, detail="...") for missing profiles
- HTTPException(status_code=409, detail="...") for conflicts (profile already running)
- HTTPException(status_code=400, detail="...") for validation errors (invalid proxy)
- HTTPException(status_code=401, detail="...") for auth failures
- HTTPException(status_code=500, detail="...") for unexpected errors

**Business Logic (BrowserManager):**
- Raises ValueError for user input errors (caught and converted to 400)
- Raises Exception for system errors (caught and converted to 500)
- Returns status dict with "stopped" status and None ports if process fails

**Frontend:**
- ApiError class wraps status code and message
- 401 errors trigger setOnUnauthorized callback (redirects to login)
- Other errors displayed in error state or toast notifications
- useProfiles hook catches and returns error strings in hook state

**WebSocket (VNC):**
- websocket.close(code=4401, reason="Unauthorized") for auth failures
- websocket.close(code=4403, reason="Origin not allowed") for CSWSH violations
- websocket.close(code=4004, reason="Profile not running") for missing profile

## Cross-Cutting Concerns

**Logging:**
- Backend: Python logging module with named loggers per file (`"cloakbrowser.manager"`, `"cloakbrowser.manager.browser"`)
- Approach: INFO for state changes, DEBUG for message flow, WARNING for retries/failures
- Frontend: console.warn/debug for API errors and connection events

**Validation:**
- Backend: Pydantic model validation at API layer (ProfileCreate, ProfileUpdate)
- Proxy validation: `_normalize_proxy()` and `_validate_proxy()` in BrowserManager
- Frontend: Form validation in ProfileForm component (HTML5 + custom rules)

**Authentication:**
- Method: Optional Bearer token or auth_token cookie
- Implementation: AuthMiddleware checks headers/cookies before routing
- Exempt routes: `/api/auth/login`, `/api/auth/status`, `/api/status`, static files
- Token comparison: Uses hmac.compare_digest() to prevent timing attacks

**Security (VNC):**
- CSWSH protection: WebSocket origin must match Host header
- RFB filtering: Strips unsupported extension types to prevent KasmVNC crashes
- Clipboard limits: 1MB max for both read and write
- Display isolation: KasmVNC runs on localhost:127.0.0.1, only accessible via proxy

---

*Architecture analysis: 2026-04-22*
