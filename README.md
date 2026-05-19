<p align="center">
<img src="https://i.imgur.com/cqkp6fG.png" width="500" alt="VendorBrowser">
</p>

<h3 align="center">VendorBrowser — powered by CloakBrowser</h3>

<p align="center">
Create, manage, and launch isolated browser profiles with unique fingerprints.<br>
Free, self-hosted alternative to Multilogin, GoLogin, and AdsPower.
</p>

<p align="center">
<a href="https://github.com/CloakHQ/CloakBrowser"><img src="https://img.shields.io/github/stars/cloakhq/cloakbrowser?label=CloakBrowser" alt="Stars"></a>
<a href="https://hub.docker.com/r/nowkickback/vendorbrowser"><img src="https://img.shields.io/docker/pulls/nowkickback/vendorbrowser?label=docker&logo=docker&logoColor=white" alt="Docker Pulls"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"></a>
</p>

---

<p align="center">
<img src="https://i.imgur.com/twdX81Q.png" width="800" alt="VendorBrowser — Browser View">
<br>
<img src="https://i.imgur.com/XFYn1qY.png" width="800" alt="VendorBrowser — Profile Settings">
</p>

Each profile is an isolated CloakBrowser instance with its own fingerprint, proxy, cookies, and session data. Profiles persist across restarts. Everything runs in one Docker container.

```bash
docker run -p 8080:8080 -v vendorprofiles:/data nowkickback/vendorbrowser
```

Or build from source:

```bash
git clone https://github.com/nowkickback/VendorBrowser.git
cd VendorBrowser
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080) in your browser. Create a profile. Click Launch. Done.

> **Early alpha** — this project is under active development. Expect bugs. If you find one, please [open an issue](https://github.com/nowkickback/VendorBrowser/issues).

## Why Not Just Use a VPN?

A VPN only changes your IP. Incognito only clears cookies. Chrome profiles share the same hardware fingerprint underneath. Platforms use 50+ signals to link your accounts — canvas, WebGL, audio, GPU, fonts, screen size, timezone.

Each CloakBrowser profile generates a completely different device identity. To the website, each profile looks like a different computer.

| Solution | What it changes | Accounts linked? |
|----------|----------------|-----------------|
| VPN | IP address only | Yes — same fingerprint |
| Incognito | Clears cookies | Yes — same fingerprint |
| Chrome profiles | Separate bookmarks/cookies | Yes — same hardware fingerprint |
| **CloakBrowser** | **Everything — full device identity per profile** | **No** |

## Features

- **Profile management** — create, edit, delete browser profiles with unique fingerprints
- **Per-profile settings** — fingerprint seed, proxy, timezone, locale, user agent, screen size, platform
- **One-click launch/stop** — each profile runs as an isolated CloakBrowser instance
- **Session persistence** — cookies, localStorage, and cache survive browser restarts
- **In-browser viewing** — interact with launched browsers via noVNC, directly in the web GUI
- **Playwright/Puppeteer API** — connect to any running profile programmatically via CDP, while still watching it live in the browser
- **Optional authentication** — protect the web UI and API with a single token, or run wide open locally
- **Powered by CloakBrowser** — 32 source-level C++ patches, passes Cloudflare Turnstile, 0.9 reCAPTCHA v3 score

## Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React + Tailwind CSS
- **Browser viewer**: noVNC (WebSocket-based VNC client)
- **Database**: SQLite
- **Browser engine**: [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) (stealth Chromium binary)

## Development

### Prerequisites

| Tool | Version | Notes |
|------|---------|--------|
| Python | 3.11+ (3.12 in Docker) | Backend API and tests |
| Node.js | 20+ | Frontend dev server and build |
| Docker | 20.10+ | **Recommended** for running Chromium, KasmVNC, and noVNC together |

The API stores profiles under `/data` (SQLite + Chromium user-data dirs). Docker maps that to `~/.vendorbrowser` on the host. Native runs need a writable `/data` (see [Native backend](#native-backend) below).

### Environment

Copy the example env file and edit it for local work:

```bash
cp .env.example .env
```

| Variable | Local dev |
|----------|-----------|
| `DEV_MODE=1` | Lets the API start without `MAIN_APP_API_KEY` / `VIEWER_SECRET` (logs a warning). Use only on your machine. |
| `AUTH_TOKEN` | Optional. If set, the admin dashboard and `/api/*` (except health/auth) require this token. |
| `MAIN_APP_API_KEY` | Required for machine routes (`/sessions/*`, `/profiles/*`) unless `DEV_MODE=1`. |
| `VIEWER_SECRET` | Required for signed viewer URLs unless `DEV_MODE=1`. |
| `MAIN_APP_ORIGIN` | CSP `frame-ancestors` for `/viewer/*`. Use `http://localhost:5173` when using the Vite dev server. |

Docker Compose reads `.env` from the repo root automatically. For a native shell, export variables before starting uvicorn:

```bash
set -a && source .env && set +a
```

### Recommended: Docker Compose

Runs the full stack (API, built dashboard, CloakBrowser, VNC) the same way production does:

```bash
docker compose up --build
```

- Dashboard: [http://localhost:8080](http://localhost:8080)
- Data volume: `~/.vendorbrowser` → `/data` inside the container
- Override secrets and flags via `.env` (see [Environment](#environment))

Rebuild after backend or frontend changes:

```bash
docker compose up --build
```

### Split-stack dev (hot-reload UI)

Best when you are changing React code. The Vite dev server proxies `/api` to the backend on port 8080.

**Terminal 1 — API**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
set -a && source ../.env && set +a   # from repo root .env
uvicorn asgi:app --reload --port 8080
```

Run from `backend/` so Python loads `asgi.py`, which imports `backend.main:app` with the correct package path. Do **not** use `uvicorn main:app` — that breaks relative imports on reload.

Equivalent from the **repo root** (same module path as Docker):

```bash
cd /path/to/CloakBrowser-Manager
source backend/.venv/bin/activate
set -a && source .env && set +a
uvicorn backend.main:app --reload --port 8080
```

**Terminal 2 — frontend**

```bash
cd frontend
npm install
npm run dev
```

- UI: [http://localhost:5173](http://localhost:5173) (Vite; `/api` → `http://localhost:8080`)
- Set `MAIN_APP_ORIGIN=http://localhost:5173` in `.env` if you exercise signed viewer iframes locally.

**Limitation:** launching profiles and live VNC still need CloakBrowser, KasmVNC, and system libraries. For end-to-end browser work, use [Docker Compose](#recommended-docker-compose) or a Linux host with the same dependencies as the [Dockerfile](Dockerfile).

### Native backend

If you run the API outside Docker:

1. **Data directory** — the app writes to `/data`:

   ```bash
   sudo mkdir -p /data && sudo chown "$USER" /data
   ```

2. **Dependencies** — `pip install -r backend/requirements.txt` (includes `cloakbrowser[geoip]`). The CloakBrowser binary is downloaded on first launch.

3. **VNC stack** — profile viewing expects KasmVNC (installed in the Docker image). Without it, API and dashboard development still work; in-browser VNC will not.

4. **Serve the built dashboard from the API** (optional, single port):

   ```bash
   cd frontend && npm install && npm run build
   cd ../backend && uvicorn asgi:app --reload --port 8080
   ```

   Open [http://localhost:8080](http://localhost:8080) when `frontend/dist` exists.

### Tests

From the **repo root** (uses `pyproject.toml`):

```bash
# Backend (fast suite; excludes slow Chromium e2e by default)
pip install -r backend/requirements.txt pytest
pytest

# Slow warm-pool e2e (real browser + VNC; Docker or full native deps)
pytest -m slow

# Frontend
cd frontend && npm test
```

## Requirements

- Docker (20.10+)
- ~2 GB disk (image + binary)
- ~512 MB RAM per running profile

## Updating

Pull the latest image and restart:

```bash
docker pull nowkickback/vendorbrowser
docker stop <container-id>
docker run -p 8080:8080 -v vendorprofiles:/data nowkickback/vendorbrowser
```

Your profiles and session data are stored in the `vendorprofiles` volume and persist across updates.

## Automation API

Every running profile exposes a CDP (Chrome DevTools Protocol) endpoint. Connect Playwright or Puppeteer to automate a profile while watching it live in the browser.

```python
from playwright.async_api import async_playwright

async with async_playwright() as pw:
    browser = await pw.chromium.connect_over_cdp(
        "http://localhost:8080/api/profiles/<profile-id>/cdp"
    )
    page = browser.contexts[0].pages[0]
    await page.goto("https://example.com")
```

```javascript
const { chromium } = require("playwright");

const browser = await chromium.connectOverCDP(
  "http://localhost:8080/api/profiles/<profile-id>/cdp"
);
const page = browser.contexts()[0].pages()[0];
await page.goto("https://example.com");
```

The CDP URL is available in the toolbar (code icon) when a profile is running. The same browser session is accessible both visually through VNC and programmatically through the API.

## Remote Access

The container binds to localhost only. To access from a remote server:

```bash
ssh -L 8080:localhost:8080 your-server
```

Then open `http://localhost:8080`.

## Authentication

By default, there is no authentication (ideal for local use). To protect the web UI and API when hosting on a network, set the `AUTH_TOKEN` environment variable:

```bash
docker run -p 8080:8080 -v vendorprofiles:/data -e AUTH_TOKEN=your-secret-token nowkickback/vendorbrowser
```

Or in `docker-compose.yml`:

```yaml
environment:
  - AUTH_TOKEN=your-secret-token
```

When `AUTH_TOKEN` is set:

- The web UI shows a login page. Enter the token to unlock.
- API consumers pass the token via `Authorization: Bearer <token>` header.
- VNC WebSocket connections are authenticated via the login cookie.
- The `/api/status` endpoint remains unauthenticated (for Docker healthcheck).

> **Note**: The auth token is transmitted in cleartext over HTTP. If you expose VendorBrowser to the internet, put it behind a reverse proxy with HTTPS (Caddy, nginx, Traefik).

## License

- **This application** (GUI source code) — MIT. See [LICENSE](LICENSE).
- **CloakBrowser binary** (compiled Chromium) — free to use, no redistribution. See [BINARY-LICENSE.md](BINARY-LICENSE.md).

The GUI application requires the CloakBrowser Chromium binary to function. The binary is automatically downloaded on first launch and is governed by its own license terms. If you fork or redistribute this application, your users must comply with the [CloakBrowser Binary License](BINARY-LICENSE.md).

## Contributing

Contributions are welcome. Please [open an issue](https://github.com/nowkickback/VendorBrowser/issues) first to discuss what you'd like to change.

## Links

- **CloakBrowser** (browser engine) — [github.com/CloakHQ/CloakBrowser](https://github.com/CloakHQ/CloakBrowser)
- **CloakBrowser website** — [cloakbrowser.dev](https://cloakbrowser.dev)
- **Bug reports** — [GitHub Issues](https://github.com/nowkickback/VendorBrowser/issues)
