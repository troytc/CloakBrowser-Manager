# Coding Conventions

**Analysis Date:** 2026-04-22

## Naming Patterns

**Files:**
- Components: PascalCase (e.g., `ProfileForm.tsx`, `StatusIndicator.tsx`)
- Hooks: camelCase with `use` prefix (e.g., `useProfiles.ts`)
- Utilities/libraries: camelCase (e.g., `api.ts`)
- Python modules: snake_case (e.g., `browser_manager.py`, `vnc_manager.py`)

**Functions:**
- TypeScript/React: camelCase (e.g., `createProfile`, `launchProfile`, `useCallback`)
- Python: snake_case (e.g., `create_profile`, `_check_auth`, `_normalize_proxy`)
- Private/internal functions prefixed with underscore in Python: `_check_auth`, `_now`

**Variables:**
- TypeScript/React: camelCase (e.g., `isEdit`, `mockApi`, `tagInput`)
- Python: snake_case (e.g., `origin_port`, `host_normalized`, `running_count`)
- State/ref variables use same case rules

**Types:**
- Interfaces/types: PascalCase (e.g., `Profile`, `ProfileCreateData`, `ProfileResponse`)
- Unions/literal types: maintained as literal strings (e.g., `"windows" | "macos" | "linux"`)
- TypeScript uses strict typing throughout (no `any` except in mock setups)

**Constants:**
- Uppercase with underscores in Python: `DB_PATH`, `DATA_DIR`, `AUTH_TOKEN`, `_AUTH_EXEMPT`
- Uppercase in TypeScript: `RESOLUTION_PRESETS`, `TAG_COLORS`, `GPU_PRESETS`

## Code Style

**Formatting:**
- **Tool**: No ESLint or Prettier config detected; hand-formatted
- **Line length**: Practical line wrapping observed
- **Spacing**: Consistent 2-space indentation in TypeScript/frontend files
- **Indentation**: Python uses standard 4-space indentation

**Linting:**
- **Frontend**: No ESLint or Prettier config found
- **Backend**: No pylint/black config in pyproject.toml
- **TypeScript strict mode**: Enabled in `tsconfig.json` with:
  - `strict: true`
  - `noUnusedLocals: true`
  - `noUnusedParameters: true`
  - `noFallthroughCasesInSwitch: true`
  - `noUncheckedIndexedAccess: true`

## Import Organization

**Order (TypeScript/React):**
1. React/third-party libraries (`import { useState, useCallback } from "react"`)
2. Third-party components (`import { Lock, PanelLeft } from "lucide-react"`)
3. Local hooks (`import { useProfiles } from "./hooks/useProfiles"`)
4. Local utilities/api (`import { api, setOnUnauthorized, type ProfileCreateData } from "./lib/api"`)
5. Local components (`import { ProfileList } from "./components/ProfileList"`)
6. Type imports separated with `type` keyword: `import type { Profile, ProfileCreateData }`

**Order (Python):**
1. Standard library (`import asyncio`, `import logging`)
2. Third-party libraries (`from fastapi import FastAPI`)
3. Local modules (`from .database import get_db`)
4. Conditional imports via `sys.modules` for mocking (test setup)

**Path Aliases:**
- Not used in frontend (relative imports throughout)
- Python uses relative imports with dots: `from .database as db`, `from .models import ProfileCreate`

## Error Handling

**TypeScript/Frontend:**
- Errors caught with `instanceof Error` checks: `err instanceof Error ? err.message : "Failed to fetch profiles"`
- Error state stored in component state: `[error, setError]`
- API errors wrapped in custom `ApiError` class with detail extraction from response JSON
- Async operations wrapped in try-catch with proper error message fallbacks
- Network errors and JSON parse errors handled separately in api.test.ts

**Python/Backend:**
- FastAPI HTTPException used for API errors with status codes: `HTTPException(status_code=404, detail="Profile not found")`
- Custom exceptions for validation: `ValueError` for invalid proxy formats
- Context managers used for resource cleanup: `@contextmanager def get_db():`
- Database operations return `None` on missing resource vs raising exception
- Async error handling with proper exception propagation in WebSocket handlers

## Logging

**Framework:** 
- **TypeScript**: `console.warn`, `console.log` for frontend (e.g., `console.warn("[auth] status check failed:", err)`)
- **Python**: Standard `logging` module via `logger = logging.getLogger("cloakbrowser.manager")`

**Patterns:**
- Python: DEBUG/INFO/WARNING/ERROR levels configured at module initialization
- Suppressed noisy loggers: `logging.getLogger("websockets").setLevel(logging.WARNING)`
- Async operation logging: Errors logged before propagation to UI
- TypeScript: Conditional logging in dev mode for auth status checks

## Comments

**When to Comment:**
- Module docstrings present for all Python files describing purpose
- Class docstrings for main components: `"""Raw ASGI middleware for optional token auth."""`
- Inline comments for complex logic (auth checks, RFB protocol handling, proxy normalization)
- Section separators used (e.g., `# ── Profile CRUD ────────────────────────────────────────`)

**JSDoc/TSDoc:**
- Frontend: JSDoc used sparsely but present for exported functions
- API module exports JSDoc comment: `/** API client for CloakBrowser Manager backend. */`
- Python: Module-level docstrings with `"""..."""` format

## Function Design

**Size:**
- Prefer small, single-purpose functions (50-100 lines typical)
- Larger files like `main.py` (~450 lines) separate concerns with clear sections
- React components stay under 200 lines, with complex forms broken into sections

**Parameters:**
- Minimal parameter passing; React hooks manage state instead
- Python functions use type hints throughout (e.g., `def create_profile(name: str, fingerprint_seed: int | None = None)`)
- Optional parameters with sensible defaults (e.g., `platform: Literal["windows", "macos", "linux"] = "windows"`)

**Return Values:**
- TypeScript: Return union types with null for missing resources (e.g., `Profile | undefined`)
- Python: Return dicts or None for missing resources, exceptions for validation errors
- Async functions return Promises in TS, coroutines in Python with proper awaiting

## Module Design

**Exports:**
- Frontend: Named exports for components/hooks (e.g., `export function ProfileForm(...)`)
- Default export for App.tsx: `export default function App()`
- API client exports interface definitions and api object: `export interface Profile {...}` + `export const api = {...}`
- Python: All public functions at module level, private helpers prefixed with underscore

**Barrel Files:**
- No barrel files (`index.ts`) found in frontend
- Direct imports from specific modules (e.g., `from ./lib/api`, `from ./hooks/useProfiles`)

---

*Convention analysis: 2026-04-22*
