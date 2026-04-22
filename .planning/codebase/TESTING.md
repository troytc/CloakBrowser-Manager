# Testing Patterns

**Analysis Date:** 2026-04-22

## Test Framework

**Runner:**
- **Frontend**: Vitest (v4.1.0) with globals enabled
- **Backend**: pytest via pyproject.toml config
- Config: `frontend/vitest.config.ts` and `backend/pyproject.toml`

**Assertion Library:**
- Frontend: vitest assertions (`expect(...).toBe()`, `expect(...).toEqual()`)
- Backend: pytest assertions (`assert resp.status_code == 200`)

**Run Commands:**
```bash
# Frontend
npm test              # Run all tests (vitest run)
npm run test:watch   # Watch mode

# Backend
pytest                # Run all tests in backend/tests/
pytest -v             # Verbose output
pytest backend/tests/test_api.py  # Run specific test file
```

## Test File Organization

**Location:**
- **Frontend**: Co-located with source (e.g., `src/hooks/useProfiles.test.ts`, `src/lib/api.test.ts`)
- **Backend**: Separate `backend/tests/` directory with `test_*.py` pattern
- TypeScript tsconfig excludes test files: `"exclude": ["src/**/*.test.ts", "src/**/*.test.tsx"]`

**Naming:**
- Frontend: `.test.ts` or `.test.tsx` suffix
- Backend: `test_` prefix (e.g., `test_api.py`, `test_auth.py`, `test_models.py`)

**Structure:**
```
frontend/src/
├── lib/api.test.ts
├── hooks/useProfiles.test.ts
└── (source files co-located)

backend/tests/
├── conftest.py        # Shared fixtures
├── test_api.py
├── test_auth.py
├── test_models.py
├── test_database.py
├── test_browser_manager.py
├── test_vnc_manager.py
└── test_rfb.py
```

## Test Structure

**Frontend Suite Organization:**
```typescript
// Typical pattern from api.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";

beforeEach(() => {
  mockFetch.mockReset();
});

describe("api.listProfiles", () => {
  it("returns profile array on success", async () => {
    const profiles = [{ id: "1", name: "Test" }];
    mockFetch.mockResolvedValueOnce(jsonResponse(profiles));
    const result = await api.listProfiles();
    expect(result).toEqual(profiles);
    expect(mockFetch).toHaveBeenCalledWith("/api/profiles", {
      headers: { "Content-Type": "application/json" },
    });
  });
});
```

**Backend Suite Organization:**
```python
# Typical pattern from test_api.py
def test_list_profiles_empty(app_client: TestClient):
    resp = app_client.get("/api/profiles")
    assert resp.status_code == 200
    assert resp.json() == []

def test_create_profile(app_client: TestClient):
    resp = app_client.post("/api/profiles", json={"name": "Test"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test"
    assert "id" in data
```

**Patterns:**
- **Setup**: `beforeEach()` for frontend, test-local setup for backend
- **Teardown**: `afterEach(() => vi.restoreAllMocks())` in frontend tests
- **Assertion**: Descriptive test names following `test_<action>_<expected_result>` pattern
- **Sectioning**: Comment sections with `// ── Feature Name ────────────────────────` (in `api.test.ts`)

## Mocking

**Framework:**
- **Frontend**: vitest (`vi.fn()`, `vi.mock()`, `vi.stubGlobal()`)
- **Backend**: unittest.mock (`AsyncMock`, `MagicMock`, `patch`)

**Patterns (Frontend):**
```typescript
// Module mocking
vi.mock("../lib/api", () => ({
  api: {
    listProfiles: vi.fn(),
    createProfile: vi.fn(),
    updateProfile: vi.fn(),
    deleteProfile: vi.fn(),
    launchProfile: vi.fn(),
    stopProfile: vi.fn(),
  },
}));

// Global fetch mocking
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Mock resolution
mockFetch.mockResolvedValueOnce(jsonResponse(profiles));
mockFetch.mockRejectedValue(new Error("Network error"));
```

**Patterns (Backend):**
```python
# Module mocking via sys.modules (in conftest.py)
_mock_cloakbrowser = types.ModuleType("cloakbrowser")
_mock_cloakbrowser.launch_persistent_context_async = AsyncMock()
sys.modules.setdefault("cloakbrowser", _mock_cloakbrowser)

# Monkeypatch fixtures
monkeypatch.setattr(db, "DB_PATH", db_file)
monkeypatch.setattr(main.browser_mgr, "cleanup_stale", AsyncMock())

# Patch decorator
with patch("backend.main.browser_mgr.vnc.cleanup_stale", AsyncMock()):
    # Test code
```

**What to Mock:**
- External API calls (fetch in frontend)
- Heavy dependencies (cloakbrowser module in backend)
- Browser manager operations (cleanup, launch)
- Database in-memory for unit tests (use fixtures for integration tests)

**What NOT to Mock:**
- Database operations in integration tests (use tmp_db fixture)
- Pydantic model validation
- Core business logic
- FastAPI request/response handling

## Fixtures and Factories

**Frontend Test Data:**
```typescript
// From useProfiles.test.ts
const fakeProfile = {
  id: "abc-123",
  name: "Test",
  fingerprint_seed: 12345,
  proxy: null,
  timezone: null,
  // ... full Profile object
  status: "stopped" as const,
  vnc_ws_port: null,
  cdp_url: null,
};
```

**Backend Fixtures:**
```python
# From conftest.py
@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point database module at a temp directory and init schema."""
    db_file = tmp_path / "profiles.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    db.init_db()
    return tmp_path

@pytest.fixture()
def sample_profile(tmp_db: Path):
    """Create and return a sample profile dict."""
    return db.create_profile(name="Test Profile", fingerprint_seed=12345)

@pytest.fixture()
def app_client(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """FastAPI TestClient with mocked DB and browser manager."""
    from backend import main
    monkeypatch.setattr(main.browser_mgr, "cleanup_stale", AsyncMock())
    from starlette.testclient import TestClient
    with TestClient(main.app) as client:
        yield client
```

**Location:**
- Frontend: Inline in test files (e.g., `fakeProfile` in `useProfiles.test.ts`)
- Backend: Centralized in `backend/tests/conftest.py` with pytest fixture pattern

## Coverage

**Requirements:** No coverage target enforced; no coverage config in project

**View Coverage:**
- Frontend: Not configured (vitest supports `--coverage` flag if desired)
- Backend: Not configured (pytest-cov can be added)

## Test Types

**Unit Tests:**
- **Frontend**: Hook tests (useProfiles.test.ts) using renderHook + mocked API
- **Backend**: Model validation (test_models.py), database operations (test_database.py)
- **Scope**: Single function/module behavior with all dependencies mocked
- **Approach**: Fast execution, no I/O, comprehensive assertion coverage

**Integration Tests:**
- **Frontend**: API client tests (api.test.ts) with mocked fetch response parsing
- **Backend**: Full API tests (test_api.py) using TestClient against in-memory database
- **Scope**: Component interaction with mocked external services
- **Approach**: TestClient avoids actual HTTP, database uses tmp_db fixture

**E2E Tests:**
- **Framework**: Not detected in codebase
- **Note**: Manual testing or external tools would be used for browser automation

## Common Patterns

**Async Testing (Frontend):**
```typescript
// From useProfiles.test.ts
it("fetches profiles on mount", async () => {
  const { result } = renderHook(() => useProfiles());
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.profiles).toEqual([fakeProfile]);
  expect(mockApi.listProfiles).toHaveBeenCalled();
});

// With act() for state updates
await act(async () => {
  await result.current.create({ name: "New" });
});
```

**Async Testing (Backend):**
```python
# FastAPI routes are async; TestClient handles internally
def test_launch_profile(app_client: TestClient):
    resp = app_client.post("/api/profiles/1/launch")
    assert resp.status_code == 200
    # TestClient internally runs event loop

# Explicit async test (if needed)
@pytest.mark.asyncio
async def test_browser_manager_async():
    # Async test code
    pass
```

**Error Testing (Frontend):**
```typescript
describe("error handling", () => {
  it("throws ApiError with detail on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ detail: "Profile not found" }),
    });
    await expect(api.getProfile("bad")).rejects.toThrow("Profile not found");
  });

  it("falls back to statusText when response is not JSON", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });
    await expect(api.getStatus()).rejects.toThrow("Internal Server Error");
  });
});
```

**Error Testing (Backend):**
```python
def test_get_profile_not_found(app_client: TestClient):
    resp = app_client.get("/api/profiles/nonexistent")
    assert resp.status_code == 404

def test_create_profile_invalid_platform(app_client: TestClient):
    resp = app_client.post("/api/profiles", json={"name": "Bad", "platform": "android"})
    assert resp.status_code == 422  # Pydantic validation error
```

---

*Testing analysis: 2026-04-22*
