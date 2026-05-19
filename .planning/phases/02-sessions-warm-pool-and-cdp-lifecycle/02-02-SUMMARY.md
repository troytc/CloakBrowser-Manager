---
phase: 02-sessions-warm-pool-and-cdp-lifecycle
plan: 02
subsystem: security
tags: [api-key, hmac, websocket, auth]
requires: []
provides:
  - require_api_key Depends for machine routes
  - CDP WS X-API-Key validation before accept
affects: [02-07, 02-08]
tech-stack:
  added: []
  patterns: [request-time-env-read, segregated-auth-surfaces]
key-files:
  created: [backend/auth_api_key.py, backend/tests/test_auth_api_key.py]
  modified: [backend/main.py]
key-decisions:
  - "MAIN_APP_API_KEY read at request time for test monkeypatch compatibility"
requirements-completed: [SEC-01]
duration: 15min
completed: 2026-05-19
---

# Phase 2 Plan 02: Machine API Auth Summary

**X-API-Key auth for /sessions, /profiles, and CDP WebSocket upgrades with timing-safe compare.**

## Task Commits
1. **auth_api_key module** - `a18c31a`
2. **main.py AuthMiddleware + CDP WS** - `cda70c2` (bundled with 02-05 wiring)

## Deviations from Plan
Main.py auth middleware edits landed in commit `cda70c2` (plan 02-05) because lifespan/CDP changes shared the same file in one integration pass.
