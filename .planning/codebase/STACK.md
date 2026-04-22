# Technology Stack

**Analysis Date:** 2026-04-22

## Languages

**Primary:**
- Python 3.12 - Backend FastAPI application
- TypeScript 5.7 - React frontend with strict mode enabled
- JavaScript - Vite build configuration

**Secondary:**
- Bash - Docker entrypoint script
- YAML - Docker Compose configuration

## Runtime

**Environment:**
- Python 3.12-slim (Docker production image)
- Node.js 20-slim (Docker build stage for frontend)

**Package Manager:**
- pip (Python) - Version constraints in `backend/requirements.txt`
- npm (Node.js) - Lockfile present: `frontend/package-lock.json`

## Frameworks

**Core:**
- FastAPI 0.115+ - REST API and static file serving
- React 19.0.0 - Frontend UI framework
- Starlette - ASGI framework (via FastAPI)

**Testing:**
- Vitest 4.1.0 - JavaScript/TypeScript test runner
- pytest - Python testing (configured in `pyproject.toml`)
- Testing Library - React component testing (@testing-library/react 16.3.2, @testing-library/jest-dom 6.9.1)

**Build/Dev:**
- Vite 6.0.0 - Frontend build tool and dev server
- TypeScript Compiler (tsc ~5.7.0) - TypeScript compilation
- Tailwind CSS 3.4.17 - Utility-first CSS framework
- PostCSS 8.4.49 - CSS processing with Autoprefixer

## Key Dependencies

**Critical:**
- fastapi (0.115+) - Web framework for REST API and HTML serving
- uvicorn[standard] (0.34+) - ASGI server (runs in production via entrypoint.sh)
- websockets (14.0+) - WebSocket support for VNC streaming
- pydantic (2.0+) - Request/response validation (ProfileCreate, ProfileResponse, etc.)
- httpx (0.27+) - HTTP client for internal requests
- cloakbrowser[geoip] (0.3.14+) - Headless browser library with fingerprint spoofing and GeoIP support

**Infrastructure:**
- @novnc/novnc (1.4.0) - Browser-based VNC client (frontend)
- lucide-react (0.468.0) - Icon library for React UI
- react-dom (19.0.0) - React DOM rendering

**DevDependencies:**
- @vitejs/plugin-react (4.3.0) - React support in Vite
- jsdom (28.1.0) - DOM implementation for testing
- tailwindcss (3.4.17) - CSS framework

## Configuration

**Environment:**
- AUTH_TOKEN (optional) - Bearer token for API authentication
  - If not set: all routes open (local development)
  - If set: all /api/* routes require Bearer token or auth_token cookie
  - Checked via `os.environ.get("AUTH_TOKEN")` in `backend/main.py`
- DISPLAY - X11 display variable (set per-process for each browser instance)

**Build:**
- `pyproject.toml` - Pytest configuration (testpaths: backend/tests, asyncio_mode: auto)
- `frontend/tsconfig.json` - TypeScript strict mode enabled, JSX react-jsx, target ES2022
- `frontend/vite.config.ts` - Proxy configuration (routes /api to http://localhost:8080)
- `frontend/tailwind.config.ts` - Custom dark mode colors and theme extensions
- `frontend/postcss.config.js` - PostCSS pipeline with Tailwind and Autoprefixer
- `.prettierrc`, `.eslintrc*` - Not detected

## Platform Requirements

**Development:**
- Node.js 20.x
- Python 3.12
- npm (package manager)

**Production:**
- Docker (multi-stage build)
- Linux x86_64 or ARM64 (aarch64) - Dockerfile uses TARGETARCH for platform-specific builds
- Chromium system dependencies: libnss3, libatk-bridge, libcups, libdbus, libdrm, libxkbcommon, libatspi, libxcomposite, libxdamage, libxfixes, libxrandr, libgbm, libpango, libcairo, libasound, libx11, libfontconfig, libxcb, libxext, libxshmfence, libglib, libgtk, libcairo-gobject, libgdk-pixbuf, libxss, libxtst, fonts-liberation, libgl1-mesa-dri, libegl-mesa, procps, wget, ca-certificates, xclip
- KasmVNC 1.3.3 (auto-installs platform-appropriate .deb via Dockerfile ARG TARGETARCH)
- Windows core fonts (TTF: Arial, Times New Roman, Verdana, etc.) for rendering consistency

## API & Service Integration

**Internal APIs:**
- REST endpoints under `/api/` - Profile CRUD, authentication, status
- WebSocket endpoints `/api/profiles/{id}/vnc` - Live VNC streaming
- Static file serving - React build from `frontend/dist/`

**External Binary:**
- CloakBrowser CLI binary (managed by cloakbrowser package)
  - Pre-downloaded during Docker build: `python -c "from cloakbrowser.download import ensure_binary; ensure_binary()"`
  - Launched per-profile via `launch_persistent_context_async()`

---

*Stack analysis: 2026-04-22*
