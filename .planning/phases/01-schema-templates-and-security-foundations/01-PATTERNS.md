# Phase 1: Schema, Templates, and Security Foundations — Pattern Map

**Mapped:** 2026-04-22
**Files in scope:** 14 (5 new, 9 modified)
**Analogs found:** 12 / 14 (2 files are net-new with no in-repo analog — `.env.example`, `backend/routers/__init__.py`)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/routers/__init__.py` | package seed | — | n/a (0-byte `backend/__init__.py`) | trivial |
| `backend/routers/templates.py` | controller (FastAPI router) | CRUD / request-response | `backend/main.py` profile routes L431–512 | exact (role), adapted (router vs inline) |
| `backend/database.py` (EDIT) | data access + migration | CRUD + schema migration | `backend/database.py::init_db` L30–76, `create_profile` L83–133 | self-analog (same file) |
| `backend/models.py` (EDIT) | Pydantic models | validation / request-response | `backend/models.py::ProfileCreate`/`ProfileUpdate`/`ProfileResponse` L10–103 | self-analog |
| `backend/main.py` (EDIT) | app composition + lifespan | config / startup | `backend/main.py::lifespan` L372–383, `_AUTH_EXEMPT` L54 | self-analog |
| `backend/requirements.txt` (EDIT) | dependency manifest | config | `backend/requirements.txt` | self-analog |
| `frontend/src/components/TemplateList.tsx` | component (list + table) | polling / read-only | `frontend/src/components/ProfileList.tsx` | role-match (table vs sidebar-list) |
| `frontend/src/components/TemplateForm.tsx` | component (section-grouped form) | request-response | `frontend/src/components/ProfileForm.tsx` | exact (layout) |
| `frontend/src/components/DeleteBlockedModal.tsx` | component (modal dialog) | event-driven / UI | n/a (no existing modal) | no analog — UI-SPEC supplies skeleton |
| `frontend/src/hooks/useTemplates.ts` | hook (CRUD + polling) | polling / CRUD | `frontend/src/hooks/useProfiles.ts` | exact |
| `frontend/src/lib/api.ts` (EDIT) | typed fetch client | request-response | `api.profiles.*` in `api.ts` L108–156 | self-analog |
| `frontend/src/App.tsx` (EDIT) | view dispatcher + nav | UI state machine | `App.tsx::AppContent` L91–257 | self-analog |
| `entrypoint.sh` (EDIT) | container init | shell startup | `entrypoint.sh` (whole file, 26 lines) | self-analog |
| `docker-compose.yml` (EDIT) | compose config | env declaration | `docker-compose.yml` L8–9 (`AUTH_TOKEN`) | self-analog |
| `.env.example` (NEW) | infra config doc | static | n/a (no `.env*` files today) | no analog — docs-only |

---

## Pattern Assignments

### `backend/database.py` — schema migration + vendor_templates table + helpers

**Analog:** same file (`backend/database.py`) — existing `init_db()` L30–76 and `create_profile()` L83–133.

**Imports already in place** (L1–12) — no additions needed except `shutil` for the wipe step:
```python
from __future__ import annotations
import datetime
import json
import random
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
```

**`init_db` migration pattern to mirror** (L30–76):
```python
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                fingerprint_seed INTEGER NOT NULL,
                /* ... */
                clipboard_sync BOOLEAN DEFAULT 1,  /* ← D-18 flips this to 0 */
                /* ... */
                user_data_dir TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profile_tags (
                profile_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
                tag TEXT NOT NULL,
                color TEXT,
                PRIMARY KEY (profile_id, tag)
            );
        """)
        conn.commit()

        # Migrations for existing databases
        cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if "clipboard_sync" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1")
            conn.commit()
        if "launch_args" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN launch_args TEXT DEFAULT '[]'")
            conn.commit()
```

**Key style rules extracted from the analog:**

1. `cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}` — set comprehension on the column-name index. Phase 1 reuses the exact `cols` variable name for symmetry when adding `vendor_type` / `vendor_connection_id` / `template_id` detection.
2. `conn.executescript("""...""")` for CREATE TABLE IF NOT EXISTS (idempotent DDL); `conn.execute("ALTER TABLE ...")` + `conn.commit()` for per-column additions.
3. No `if/elif` chain — each migration step is its own `if "<col>" not in cols:` block and commits independently.
4. `get_db()` context manager (L18–27) already enables `PRAGMA foreign_keys=ON` — the new `ON DELETE RESTRICT` on `profiles.template_id` will actually be enforced (do not change the pragma setup).
5. `DATA_DIR = Path("/data")` at module level; `DB_PATH = DATA_DIR / "profiles.db"`. The wipe step uses `DATA_DIR / "profiles" / pid`, not a new constant.

**`create_profile` signature pattern to mirror for new `create_profile_from_template`** (L83–133):
```python
def create_profile(
    name: str,
    fingerprint_seed: int | None = None,
    **fields: Any,
) -> dict[str, Any]:
    profile_id = str(uuid.uuid4())
    seed = fingerprint_seed if fingerprint_seed is not None else random.randint(10000, 99999)
    user_data_dir = str(DATA_DIR / "profiles" / profile_id)
    now = _now()
    tags = fields.pop("tags", None) or []

    with get_db() as conn:
        conn.execute(
            """INSERT INTO profiles (
                id, name, fingerprint_seed, proxy, timezone, locale, platform,
                user_agent, screen_width, screen_height, gpu_vendor, gpu_renderer,
                hardware_concurrency, humanize, human_preset, headless, geoip,
                clipboard_sync, color_scheme, launch_args, notes,
                user_data_dir, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id, name, seed,
                fields.get("proxy"),
                /* ... */
                fields.get("clipboard_sync", True),   /* ← D-18 flips to False */
                /* ... */
            ),
        )
        /* ... */
        conn.commit()
    return get_profile(profile_id)
```

**Key rules for the new `create_profile_from_template(template: dict, vendor_connection_id: str) -> dict`:**
- Same `uuid.uuid4()` / `random.randint(10000, 99999)` / `_now()` shape.
- Pull defaults from `template["blueprint"]` (a dict, already JSON-decoded) — NOT from `**fields`.
- `fingerprint_seed` is generated per-profile (D-04) — do not read any seed from the blueprint.
- Snapshot copy: write the blueprint's 13 fields into the corresponding `profiles` columns; never store `template["blueprint"]` as JSON in a second column (D-03).
- `clipboard_sync` default when absent from blueprint: `False` (D-18).
- Return `get_profile(profile_id)` (same return contract as `create_profile`).

**Delete-guard helper pattern (new `list_profiles_by_template(template_id)`):** mirror the shape of `list_profiles()` L151–164 — `conn.execute("SELECT id FROM profiles WHERE template_id = ?", (template_id,)).fetchall()` returning a `list[str]` (IDs only, not full rows). Keep it cheap; the router only needs the ID list for the 409 body.

---

### `backend/models.py` — Pydantic v2 template models

**Analog:** same file — `ProfileCreate` L10–32, `ProfileUpdate` L34–55, `ProfileResponse` L68–102.

**Import header to mirror** (L1–7):
```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator
```
No new imports needed for the template models.

**`ProfileCreate` shape to mirror for `TemplateBlueprint`** (L10–32):
```python
class ProfileCreate(BaseModel):
    name: str
    fingerprint_seed: int | None = None
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    platform: Literal["windows", "macos", "linux"] = "windows"
    /* ... */
    clipboard_sync: bool = True   /* ← D-18 flips to False */
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    launch_args: list[str] = Field(default_factory=list)
    notes: str | None = None
    tags: list[TagCreate] | None = None
```

**Critical flip for D-18** — these exact three lines in this file change:
- L27: `clipboard_sync: bool = True` → `clipboard_sync: bool = False`
- L86: `clipboard_sync: bool = True` (on `ProfileResponse`) → `clipboard_sync: bool = False`
- L88–91: `coerce_clipboard_sync` validator fallback `return v if v is not None else True` → `return v if v is not None else False`

**`field_validator` default-coerce pattern to reuse** (L88–91):
```python
@field_validator("clipboard_sync", mode="before")
@classmethod
def coerce_clipboard_sync(cls, v: object) -> bool:
    return v if v is not None else True   /* flip to False */
```
Apply the same `@field_validator("clipboard_sync", mode="before")` pattern inside `TemplateBlueprint` so null blueprint JSON coerces to `False`.

**`ProfileUpdate` "all-fields-Optional" pattern to mirror for `VendorTemplateUpdate`** (L34–55): every field becomes `T | None = None` (or `T | None = Field(default=None)`), enabling `model_dump(exclude_unset=True)` in the router — see the `update_profile` handler in `main.py` L476–478:
```python
async def update_profile(profile_id: str, req: ProfileUpdate):
    data = req.model_dump(exclude_unset=True)
    /* ... */
```

**Model placement:** add the four new classes (`TemplateBlueprint`, `VendorTemplateCreate`, `VendorTemplateUpdate`, `VendorTemplateResponse`) at the bottom of the file, after `LoginRequest` L130–131 (current EOF). Keep file-level grouping: input models first (`Create`/`Update`/`Blueprint`), response model last.

---

### `backend/routers/templates.py` — admin CRUD router

**Analog:** `backend/main.py` profile routes L431–512 (list/create/get/update/delete).

**Create-new-directory convention:**
- `backend/__init__.py` (existing, 0 bytes) is the seed for the `backend` package.
- `backend/routers/__init__.py` (NEW) should be identical — empty file, 0 bytes. This matches the existing convention; no re-export needed because `main.py` will `from .routers.templates import router as templates_router`.

**Router module skeleton (derive from `main.py` imports L21–39):**
```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from .. import database as db
from ..models import (
    VendorTemplateCreate,
    VendorTemplateUpdate,
    VendorTemplateResponse,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])
```

**List pattern from `main.py` L431–442:**
```python
@app.get("/api/profiles", response_model=list[ProfileResponse])
async def list_profiles():
    profiles = db.list_profiles()
    result = []
    for p in profiles:
        /* ... enrich with status, tags ... */
        result.append(ProfileResponse(**p))
    return result
```
For templates, no status/browser_mgr enrichment — just `db.list_templates()` → `[VendorTemplateResponse(**t) for t in templates]`.

**Create pattern (409-on-dup) from `main.py` L445–459:**
```python
@app.post("/api/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(req: ProfileCreate):
    data = req.model_dump()
    /* ... */
    profile = db.create_profile(**data)
    /* ... */
    return ProfileResponse(**profile)
```
For templates, wrap the `db.create_template(...)` call in `try: ... except sqlite3.IntegrityError as exc: raise HTTPException(409, detail=f"A template for vendor_type '{req.vendor_type}' already exists")`. The `sqlite3.IntegrityError` is raised by SQLite when the `UNIQUE` constraint on `vendor_type` fires. The copy in the `detail` field matches UI-SPEC's "Error Payloads" table verbatim.

**Update pattern (exclude_unset) from `main.py` L475–490:**
```python
@app.put("/api/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: str, req: ProfileUpdate):
    data = req.model_dump(exclude_unset=True)
    /* ... */
    profile = db.update_profile(profile_id, **data)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    /* ... */
    return ProfileResponse(**profile)
```
Identical shape for templates; also bump `updated_at` in the DB helper (per Claude's Discretion in CONTEXT.md — no SQLite trigger).

**Delete pattern (409-on-blocked) — adapted from `main.py` L493–512:**
Reuse the 404-check idiom (`if not profile: raise HTTPException(status_code=404, detail=...)`), then **before** deleting:
```python
blocking_ids = db.list_profiles_by_template(template_id)  # list[str]
if blocking_ids:
    raise HTTPException(
        status_code=409,
        detail={
            "detail": f"Template has {len(blocking_ids)} attached profile(s); delete or reassign them first",
            "blocking_profile_ids": blocking_ids,
        },
    )
```
Note: `HTTPException(detail=<dict>)` serializes the dict into the response body — FastAPI idiomatic. The UI-SPEC "Error Payloads" row expects this exact shape.

**Router registration in `main.py`:** insert **after** `app.add_middleware(AuthMiddleware)` (L383) and **before** the first `@app.get("/api/auth/status")` (L389):
```python
from .routers.templates import router as templates_router
app.include_router(templates_router)
```
Because the prefix is `/api/templates`, the router sits under `/api/*` and is automatically gated by `AuthMiddleware`. **Do not touch `_AUTH_EXEMPT`** (L54) — per CLAUDE.md and D-17, admin routes must stay behind AuthMiddleware.

---

### `backend/main.py` — lifespan fail-closed check + router registration

**Analog:** `lifespan` L372–379 and `AUTH_TOKEN` env-var pattern L51–54.

**Lifespan pattern to extend** (L372–383):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    await browser_mgr.cleanup_stale()
    logger.info("CloakBrowser Manager started")
    yield
    logger.info("Shutting down — stopping all browsers...")
    await browser_mgr.cleanup_all()


app = FastAPI(title="CloakBrowser Manager", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
```

**Fail-closed env var read pattern to mirror (D-17)** — copy the shape of `AUTH_TOKEN` at L51:
```python
AUTH_TOKEN: str | None = os.environ.get("AUTH_TOKEN") or None
```
Add module-level reads for `VIEWER_SECRET`, `MAIN_APP_API_KEY`, `DEV_MODE` at the same location (L48–54 zone). In the `lifespan` function, **before** `db.init_db()`:
```python
if not DEV_MODE:
    missing = [v for v in ("VIEWER_SECRET", "MAIN_APP_API_KEY") if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Service refuses to start: required env vars unset: {', '.join(missing)}. "
            f"Set DEV_MODE=1 to bypass (not for production)."
        )
else:
    logger.warning(
        "⚠ DEV_MODE=1: VIEWER_SECRET and/or MAIN_APP_API_KEY not set. "
        "Authentication is bypassed. Do not use in production."
    )
```
Raising `RuntimeError` inside `lifespan` before `yield` halts FastAPI startup before uvicorn binds — the fail-closed contract. The warning copy matches CONTEXT.md Claude's Discretion verbatim.

**Router registration** (see `backend/routers/templates.py` section above) goes immediately after `app.add_middleware(AuthMiddleware)` at L383.

---

### `backend/requirements.txt` — add PyJWT

**Analog:** existing file (6 lines). Append one line preserving alphabetical-ish order:
```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.0
cloakbrowser[geoip]>=0.3.14
websockets>=14.0
httpx>=0.27.0
PyJWT>=2.12.1
```
One-line addition; no other changes. PyJWT is not imported anywhere in Phase 1 — it's scaffolding for Phase 3 (D-19).

---

### `frontend/src/hooks/useTemplates.ts` — polling + CRUD hook

**Analog:** `frontend/src/hooks/useProfiles.ts` (92 lines, exact-shape mirror).

**Full hook skeleton from `useProfiles.ts` L1–27 + L28–91:**
```typescript
import { useCallback, useEffect, useState } from "react";
import { api, type Profile, type ProfileCreateData } from "../lib/api";

export function useProfiles() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listProfiles();
      setProfiles(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch profiles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh]);

  const create = useCallback(async (data: ProfileCreateData): Promise<Profile | undefined> => {
    try {
      const profile = await api.createProfile(data);
      setProfiles((prev) => [profile, ...prev]);
      return profile;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create profile");
    }
  }, []);

  const update = useCallback(/* ... same try/catch/setState shape ... */, []);
  const remove = useCallback(/* ... */, []);

  return { profiles, loading, error, refresh, create, update, remove, launch, stop };
}
```

**Rules locked from the analog:**
1. `loading` starts `true`, set to `false` only in the `finally` of `refresh` — silent on subsequent polls (UI-SPEC "Polling and Loading State").
2. `error` cleared on each successful poll (`setError(null)` inside try block).
3. `setInterval(refresh, 3000)` — 3 seconds exactly, per UI-SPEC Source Traceability row for polling.
4. Each CRUD action wraps its own try/catch and mutates `templates` state optimistically (`[template, ...prev]` on create, `filter` on remove, `map` on update).
5. Return object names must match what `App.tsx` destructures: `{ templates, loading, error, refresh, create, update, remove }`. **No `launch` / `stop`** — templates have no runtime counterpart (UI-SPEC Component Inventory).
6. **Special for D-13:** the `remove` action must re-throw (or return an error object) when the server responds 409 so the caller in `App.tsx` can open `DeleteBlockedModal`. The `useProfiles.remove` swallows errors into `setError`; `useTemplates.remove` must NOT do that for 409 — re-throw so the caller can inspect `err.status === 409` and read `err.blocking_profile_ids` from the body.

---

### `frontend/src/lib/api.ts` — add `api.templates.*`

**Analog:** `api.profiles.*` section L108–156 of the same file, plus the `ApiError` class at L74–81 and `request<T>` helper L89–106.

**ApiError class to extend (or mirror) for 409 body decoding** — L74–81:
```typescript
class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
```
**Extension needed:** add an optional `body?: unknown` field to `ApiError` so 409 responses can surface `blocking_profile_ids` to the caller. Modify `request<T>` L102–103 to attach the parsed body:
```typescript
const body = await res.json().catch(() => ({ detail: res.statusText }));
throw new ApiError(res.status, body.detail || res.statusText, body);  // ← pass body
```
This is a minimal, backward-compatible change — existing call sites ignore `body` and still read `err.message`.

**`api.profiles.*` function shape to mirror** — L121–138:
```typescript
listProfiles: () => request<Profile[]>("/api/profiles"),
getProfile: (id: string) => request<Profile>(`/api/profiles/${id}`),
createProfile: (data: ProfileCreateData) =>
  request<Profile>("/api/profiles", {
    method: "POST",
    body: JSON.stringify(data),
  }),
updateProfile: (id: string, data: Partial<ProfileCreateData>) =>
  request<Profile>(`/api/profiles/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  }),
deleteProfile: (id: string) =>
  request<{ ok: boolean }>(`/api/profiles/${id}`, { method: "DELETE" }),
```

**New types to add (mirror the `Profile` / `ProfileCreateData` shape from L5–58):**
```typescript
export interface TemplateBlueprint {
  timezone?: string | null;
  locale?: string | null;
  platform: "windows" | "macos" | "linux";
  screen_width: number;
  screen_height: number;
  gpu_vendor?: string | null;
  gpu_renderer?: string | null;
  hardware_concurrency?: number | null;
  humanize: boolean;
  human_preset: "default" | "careful";
  launch_args: string[];
  clipboard_sync: boolean;
  proxy?: string | null;
  color_scheme?: "light" | "dark" | "no-preference" | null;
  user_agent?: string | null;
}

export interface VendorTemplate {
  id: string;
  vendor_type: string;
  label: string | null;
  notes: string | null;
  blueprint: TemplateBlueprint;
  created_at: string;
  updated_at: string;
}

export interface VendorTemplateCreateData {
  vendor_type: string;
  label?: string | null;
  notes?: string | null;
  blueprint: TemplateBlueprint;
}
```

**New `api.templates.*` surface** — same return-type pattern as profiles:
```typescript
templates: {
  list: () => request<VendorTemplate[]>("/api/templates"),
  get: (id: string) => request<VendorTemplate>(`/api/templates/${id}`),
  create: (data: VendorTemplateCreateData) =>
    request<VendorTemplate>("/api/templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<VendorTemplateCreateData>) =>
    request<VendorTemplate>(`/api/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  remove: (id: string) =>
    request<{ ok: boolean }>(`/api/templates/${id}`, { method: "DELETE" }),
},
```
Nesting under `api.templates.*` (not flat `listTemplates`) matches CONTEXT.md integration-points guidance. The existing profile API is flat (`api.listProfiles`) — the new namespace is a deliberate cleaner shape that can coexist.

---

### `frontend/src/components/TemplateForm.tsx` — section-grouped create/edit form

**Analog:** `frontend/src/components/ProfileForm.tsx` (574 lines).

**Imports pattern to mirror** (L1–3):
```typescript
import { Save, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Profile, ProfileCreateData } from "../lib/api";
```
For TemplateForm add `AlertTriangle` (amber warning badge) and import `VendorTemplate` / `VendorTemplateCreateData` types.

**Top-level JSX structure to copy verbatim** (ProfileForm L172–202):
```tsx
<form onSubmit={handleSubmit} className="p-6 max-w-2xl mx-auto">
  <div className="flex items-center justify-between mb-6">
    <div className="flex items-center gap-2">
      <h2 className="text-lg font-semibold">
        {isEdit ? "Edit Profile" : "New Profile"}
      </h2>
      {isEdit && onDelete && (
        <button
          type="button"
          onClick={handleDelete}
          disabled={deleting}
          className="btn-danger flex items-center gap-1.5"
        >
          <Trash2 className="h-3.5 w-3.5" />
          <span>{deleting ? "Deleting..." : "Delete"}</span>
        </button>
      )}
    </div>
    <div className="flex items-center gap-2">
      <button type="button" onClick={onCancel} className="btn-secondary">
        Cancel
      </button>
      <button type="submit" disabled={saving} className="btn-primary flex items-center gap-1.5">
        <Save className="h-3.5 w-3.5" />
        <span>{saving ? "Saving..." : isEdit ? "Save" : "Create"}</span>
      </button>
    </div>
  </div>

  <div className="space-y-5">
    {/* sections here */}
  </div>
</form>
```
Outer container: `p-6 max-w-2xl mx-auto`. Sections wrapper: `space-y-5` (20px gap). Page heading: `text-lg font-semibold`. Button cluster: `flex items-center gap-2`. **Copy change per UI-SPEC:** `Edit Template` / `New Template` in place of the profile copy.

**Section-grouping pattern to copy** (ProfileForm L203–273, "Basic" section as the template):
```tsx
<section>
  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Basic</h3>
  <div className="grid grid-cols-2 gap-3">
    <div className="col-span-2">
      <label className="label">Profile Name</label>
      <input
        className="input"
        value={form.name}
        onChange={(e) => set("name", e.target.value)}
        placeholder="e.g. Amazon Seller #1"
        required
      />
    </div>
    /* ... */
  </div>
</section>
```
Replicate this `<section><h3>...</h3><div class="grid grid-cols-2 gap-3 | space-y-3">...</div></section>` shape for each of the 7 UI-SPEC sections: Identity / Fingerprint / Screen / GPU / Behavior / Proxy / Security. Section heading text (source JSX): Title Case (`Identity`, `Fingerprint`, …) — Tailwind's `uppercase` renders the display.

**Form state + handlers pattern** (ProfileForm L55–130):
```typescript
const [form, setForm] = useState<ProfileCreateData>({
  name: "",
  platform: "windows",
  screen_width: 1920,
  screen_height: 1080,
  humanize: false,
  human_preset: "default",
  headless: false,
  geoip: false,
  clipboard_sync: true,   /* ← flip to false in TemplateForm */
  launch_args: [],
  tags: [],
});

const [saving, setSaving] = useState(false);
const [deleting, setDeleting] = useState(false);

const set = <K extends keyof ProfileCreateData>(key: K, value: ProfileCreateData[K]) => {
  setForm((prev) => ({ ...prev, [key]: value }));
};

const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  if (!form.name.trim()) return;
  setSaving(true);
  try {
    await onSave(form);
  } finally {
    setSaving(false);
  }
};

const handleDelete = async () => {
  if (!onDelete) return;
  if (!confirm("Delete this profile? Browser data will be permanently removed.")) return;
  setDeleting(true);
  try {
    await onDelete();
  } finally {
    setDeleting(false);
  }
};
```

**Key flips for TemplateForm initial state:**
- `clipboard_sync: false` (D-18 / UI-SPEC).
- `form` shape is `VendorTemplateCreateData` (flat top-level: `vendor_type`, `label`, `notes`) + nested `blueprint` (the fingerprint/screen/gpu/behavior/proxy/security fields).
- Required client-check in `handleSubmit`: `if (!form.vendor_type.trim()) return;` (UI-SPEC Field table marks `vendor_type` as Required).
- `confirm()` copy from UI-SPEC: `` `Delete template "${template.label || template.vendor_type}"? This cannot be undone.` `` — not ProfileForm's copy.

**Launch-args pill pattern to reuse verbatim** (ProfileForm L523–558) — the Behavior section's launch_args sub-input. `font-mono text-xs` pills + Enter-to-add. Copy lines 523–558 with only the `set("launch_args", ...)` targeting `form.blueprint.launch_args` via a nested setter.

**Checkbox pattern for humanize / clipboard_sync** (ProfileForm L415–423):
```tsx
<label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
  <input
    type="checkbox"
    checked={form.humanize ?? false}
    onChange={(e) => set("humanize", e.target.checked)}
    className="rounded border-border bg-surface-2"
  />
  Human-like mouse, keyboard, and scroll behavior
</label>
```
Reuse verbatim for `humanize`. For `clipboard_sync`, **copy the UI-SPEC amber warning badge markup verbatim** above the checkbox (UI-SPEC Amber Warning Badge section); the checkbox itself uses this same pattern.

**Inline validation error pattern (new — per D-13 / UI-SPEC):**
```tsx
{fieldErrors.vendor_type && (
  <p className="text-xs text-red-400 mt-1" role="alert">
    {fieldErrors.vendor_type}
  </p>
)}
```
Position: immediately below the input, before the next field. State: a new `useState<Record<string, string>>({})` for `fieldErrors`. On 422 from the server, populate by `loc[-1]` per UI-SPEC "Error Payloads".

---

### `frontend/src/components/TemplateList.tsx` — table list with edit/delete

**Analog:** `frontend/src/components/ProfileList.tsx` (104 lines — layout mirror; columns differ).

**Imports pattern** (ProfileList L1–4):
```typescript
import { Plus, Search, Monitor } from "lucide-react";
import { useState } from "react";
import type { Profile } from "../lib/api";
import { StatusIndicator } from "./StatusIndicator";
```
For TemplateList: drop `Search` (UI-SPEC: no search in Phase 1), drop `Monitor` / `StatusIndicator` (no runtime status), add `Pencil`, `Trash2` (row actions per UI-SPEC).

**Outer wrapper pattern to mirror** (ProfileList L22–46):
```tsx
<div className="flex flex-col h-full">
  <div className="p-4 border-b border-border">
    {/* header */}
  </div>
  <div className="flex-1 overflow-y-auto p-2">
    {/* list content */}
  </div>
  <div className="p-3 border-t border-border">
    {/* new button */}
  </div>
</div>
```
For TemplateList the middle section is a **table** (UI-SPEC columns: Vendor Type / Label / Created / actions), not a button list. Header copy per UI-SPEC: `No templates yet` / CTA `New Template`.

**Empty-state copy pattern** (ProfileList L50–53):
```tsx
<div className="text-center text-gray-500 text-xs py-8">
  {profiles.length === 0 ? "No profiles yet" : "No matches"}
</div>
```
For TemplateList: `No templates yet` (UI-SPEC Copywriting Contract). Drop the "No matches" branch — no search in Phase 1.

**Table-row hover/selected state pattern** (ProfileList L56–65):
```tsx
<button
  key={profile.id}
  onClick={() => onSelect(profile.id)}
  className={`w-full text-left px-3 py-2.5 rounded-md mb-1 transition-colors ${
    selectedId === profile.id
      ? "bg-surface-3 border border-border-hover"
      : "hover:bg-surface-2 border border-transparent"
  }`}
>
```
UI-SPEC says table row padding `py-2.5` — matches this exact line. Selected state uses `bg-surface-3` (not accent — UI-SPEC is explicit).

---

### `frontend/src/components/DeleteBlockedModal.tsx` — NEW, no in-repo analog

**No existing modal component** in the repo. UI-SPEC (Delete Error Modal section) supplies the complete locked JSX skeleton + copy. The executor should copy the UI-SPEC block verbatim — it includes:
- `role="dialog" aria-modal="true" aria-labelledby="delete-blocked-title"` + `fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4`
- Inner container: `bg-surface-1 border border-border rounded-lg p-6 max-w-md w-full space-y-4`
- Title: `Cannot delete template`
- Body: singular/plural handling (`1 profile` / `3 profiles`)
- Copy IDs button (lucide `Copy` icon), toggles to `Copied` for 2s
- Focus trap: initial focus on Copy button (per UI-SPEC)
- Escape key dismisses (UI-SPEC Keyboard Interaction)

---

### `frontend/src/App.tsx` — surface switcher + Templates view dispatch

**Analog:** `App.tsx` `AppContent` component L91–257 of the same file.

**View union to extend** (L13):
```typescript
type View = "empty" | "create" | "edit" | "view";
```
Extension per UI-SPEC (Nav Pattern + Template Surface View State): add a sibling `surface` state, not a new view value:
```typescript
type Surface = "profiles" | "templates";
type TemplateView = "empty" | "create" | "edit";  // no "view" — templates have no runtime

const [surface, setSurface] = useState<Surface>("profiles");
const [templateView, setTemplateView] = useState<TemplateView>("empty");
```
This keeps the existing `view` state untouched for the profiles surface, satisfying the CONTEXT.md D-12 rule that profile CRUD UI "survives Phase 1 intact."

**Top-bar cluster pattern to extend** (L171–187):
```tsx
<div className="flex items-center justify-between px-4 py-2 border-b border-border bg-surface-1">
  <div className="flex items-center gap-3">
    <button
      onClick={() => setSidebarOpen(!sidebarOpen)}
      className="text-gray-500 hover:text-gray-300 p-1"
      title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
    >
      {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
    </button>
    {selected && (/* profile label cluster */)}
  </div>
  {/* right-side buttons */}
</div>
```
Insert the UI-SPEC "Nav Pattern" segmented-control markup **after** the PanelLeftClose toggle and **before** the `{selected && ...}` label cluster. UI-SPEC provides the exact JSX — copy verbatim.

**Content-dispatch switch pattern** (L217–253):
```tsx
{view === "empty" && (
  <div className="flex items-center justify-center h-full">
    <div className="text-center">
      <p className="text-gray-500 text-sm">Select a profile or create a new one</p>
    </div>
  </div>
)}

{view === "create" && (
  <ProfileForm
    profile={null}
    onSave={handleCreate}
    onCancel={() => setView("empty")}
  />
)}

{view === "edit" && selected && (
  <ProfileForm
    profile={selected}
    onSave={handleUpdate}
    onDelete={handleDelete}
    onCancel={() => { setSelectedId(null); setView("empty"); }}
  />
)}
```
Wrap the existing block in `{surface === "profiles" && (...)}` and add a mirror `{surface === "templates" && (...)}` block that dispatches on `templateView` → `TemplateList` / `TemplateForm`. Keep the empty-state markup structurally identical (UI-SPEC Loading/Error states).

**Error banner pattern to reuse verbatim** (L209–213):
```tsx
{error && (
  <div className="px-4 py-2 bg-red-600/15 border-b border-red-600/30 text-red-400 text-sm">
    {error}
  </div>
)}
```
Both surfaces share the same banner slot — combine `error` from `useProfiles` and `useTemplates` with a `||` (showing whichever surface is active).

---

### `entrypoint.sh` — chown insertion

**Analog:** the whole 26-line file `entrypoint.sh`.

**Exact insertion point** (current L5–7):
```bash
# Initialize data directories
mkdir -p /data/profiles

# Kill stale processes from previous container runs
pkill -f 'Xvnc :[0-9]' 2>/dev/null || true
```

**Insertion (D-14):** add between `mkdir -p /data/profiles` and the `pkill` block — immediately after L5, before L7:
```bash
mkdir -p /data/profiles

# Fix data volume ownership (OPS-04) — runs BEFORE stale-process kill / singleton cleanup
chown -R ${CHROME_UID:-0}:${CHROME_UID:-0} /data/profiles

# Kill stale processes from previous container runs
pkill -f 'Xvnc :[0-9]' 2>/dev/null || true
```

**Rules extracted from the analog:**
- `set -e` at L2 is in force — `chown` failure will abort startup. Acceptable for Phase 1 (single-host, root-by-default).
- The existing `pkill` / `find -delete` / `rm` lines all use `2>/dev/null || true` to tolerate first-run absence. The new `chown` does NOT need `|| true` — it's idempotent on an existing directory and we want abort-on-failure.
- `${CHROME_UID:-0}` defaults to root (D-14). The syntax matches the codebase's preference for inline defaults over separate `: ${CHROME_UID:=0}` blocks.

---

### `docker-compose.yml` — env var declarations

**Analog:** the whole 9-line file `docker-compose.yml`.

**Existing env block** (L8–9):
```yaml
environment:
  - AUTH_TOKEN=${AUTH_TOKEN:-}
```

**Extension (D-15):** extend the environment array; preserve the `VAR=${VAR:-}` shape so missing-vars behavior triggers the fail-closed check at startup (unset → empty string → `or None` in `main.py` → fail):
```yaml
    environment:
      - AUTH_TOKEN=${AUTH_TOKEN:-}
      - MAIN_APP_API_KEY=${MAIN_APP_API_KEY:-}
      - VIEWER_SECRET=${VIEWER_SECRET:-}
      - MAIN_APP_ORIGIN=${MAIN_APP_ORIGIN:-}
      - IDLE_TIMEOUT_SECONDS=${IDLE_TIMEOUT_SECONDS:-600}
      - VIEWER_TOKEN_TTL_SECS=${VIEWER_TOKEN_TTL_SECS:-300}
      - CHROME_UID=${CHROME_UID:-0}
      - DEV_MODE=${DEV_MODE:-}
```
Order: existing `AUTH_TOKEN` stays first (D-15: "Existing AUTH_TOKEN declaration stays"). Defaults for `IDLE_TIMEOUT_SECONDS` (600) and `VIEWER_TOKEN_TTL_SECS` (300) come from CLAUDE.md's "Required Environment Variables" table. `DEV_MODE` has no default (unset → off → fail-closed enforced).

---

### `.env.example` — NEW file, no in-repo analog

**No existing `.env*` file in the repo.** This is a greenfield docs file. Shape derives from `docker-compose.yml` env block (above) + CLAUDE.md "Required Environment Variables" table. One line per var, `KEY=sample_value` format, preceded by a one-line comment describing purpose. Example shape:
```
# Shared secret authenticating the Main App to machine routes (/sessions/*, /profiles/*)
MAIN_APP_API_KEY=change-me-to-a-long-random-string

# HMAC secret signing viewer JWTs (HS256)
VIEWER_SECRET=change-me-to-a-different-long-random-string
/* ... */
```
**Rule:** never include real secrets. Sample values should be obviously placeholder (`change-me-...`, `http://localhost:3000`, etc.) so an operator copying `.env.example` → `.env` without edits produces a fail-closed startup.

---

## Shared Patterns

### 1. FastAPI handler 404/409 idiom
**Source:** `backend/main.py` L462–472 (profile 404), L523–524 (launch conflict 409).
**Apply to:** every handler in `backend/routers/templates.py`.
```python
if not profile:
    raise HTTPException(status_code=404, detail="Profile not found")
```
For 409, `detail` may be a dict (see delete-blocked above) — FastAPI serializes dicts into the response body as-is.

### 2. SQLite migration via `PRAGMA table_info` + conditional `ALTER TABLE`
**Source:** `backend/database.py::init_db` L69–76.
**Apply to:** every schema change in Phase 1 (vendor_type/vendor_connection_id/template_id adds, `clipboard_sync` DEFAULT flip).
Already shown above. No Alembic, no second file.

### 3. `get_db()` context manager usage
**Source:** `backend/database.py` L18–27 + every helper L94, L137, L152, L168, L216.
**Apply to:** every DB helper in the new template CRUD (`list_templates`, `get_template`, `create_template`, `update_template`, `delete_template`, `list_profiles_by_template`, `create_profile_from_template`).
```python
with get_db() as conn:
    conn.execute(...)
    conn.commit()
```
Always `conn.commit()` before exiting the `with` block on writes. Row-factory is `sqlite3.Row` → rows behave like dicts.

### 4. Pydantic v2 `field_validator` default coercion
**Source:** `backend/models.py` L88–91 (`coerce_clipboard_sync`).
**Apply to:** `TemplateBlueprint.clipboard_sync` (and any other null-coerce-to-bool field). Matches Pydantic v2 `mode="before"` runtime-validation convention.

### 5. Tailwind `@layer components` class usage
**Source:** `frontend/src/styles/globals.css` L44–66. Classes: `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.input`, `.label`, `textarea.input`.
**Apply to:** every new frontend component — `TemplateList.tsx`, `TemplateForm.tsx`, `DeleteBlockedModal.tsx`. Do not reinvent with raw utilities when a named class exists.

### 6. React hook shape: `refresh` + `setInterval(refresh, 3000)` + CRUD callbacks
**Source:** `frontend/src/hooks/useProfiles.ts` L9–91 (complete pattern).
**Apply to:** `frontend/src/hooks/useTemplates.ts` — mirror exactly, minus launch/stop.

### 7. Typed `request<T>` helper + `ApiError`
**Source:** `frontend/src/lib/api.ts` L74–106.
**Apply to:** every `api.templates.*` function. No raw `fetch()` at call sites.

### 8. View-dispatch state machine in `App.tsx`
**Source:** `App.tsx` L91–258.
**Apply to:** adding Template surface — introduce `surface` + `templateView` states (never mutate the existing `view` union, keeps profile surface untouched).

### 9. Section-grouped form layout (7 sections max)
**Source:** `frontend/src/components/ProfileForm.tsx` L202–570.
**Apply to:** `TemplateForm.tsx` — 7 sections (Identity / Fingerprint / Screen / GPU / Behavior / Proxy / Security) with `space-y-5` between, `space-y-3` or `grid grid-cols-2 gap-3` within.

### 10. `window.confirm` for destructive actions (Phase 1)
**Source:** `ProfileForm.tsx` L123.
**Apply to:** TemplateForm single-delete confirm. Modal upgrade is explicitly out of scope (UI-SPEC "Destructive confirmation" + Deferred Ideas).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/routers/__init__.py` | package seed | — | Trivial — copy the 0-byte shape of `backend/__init__.py`. No code in either file. |
| `frontend/src/components/DeleteBlockedModal.tsx` | modal | UI / event-driven | No modal component exists in the repo. UI-SPEC (Delete Error Modal section) supplies the complete locked JSX + copy; executor uses that as the authoritative source. |
| `.env.example` | infra doc | static | No `.env*` file exists in the repo. UI-SPEC doesn't cover it; derive from `docker-compose.yml` env block + CLAUDE.md "Required Environment Variables" table. |

---

## Metadata

**Analog search scope:**
- `backend/` — `database.py`, `main.py`, `models.py`, `requirements.txt`, `__init__.py`
- `frontend/src/` — `App.tsx`, `components/*`, `hooks/*`, `lib/*`, `styles/globals.css`
- Repo root — `entrypoint.sh`, `docker-compose.yml`, `Dockerfile`, `frontend/tailwind.config.ts`

**Files scanned:** 16 source files; targeted greps on `main.py` for middleware, lifespan, and route decorators (no full-file read of the 1026-line main.py).

**Pattern extraction date:** 2026-04-22

---

## PATTERN MAPPING COMPLETE

**Phase:** 1 - schema-templates-and-security-foundations
**Files classified:** 14 (5 new, 9 modified)
**Analogs found:** 12 / 14

### Coverage
- Files with exact or role-match analog: 12
- Files with no analog: 2 (`.env.example`, `DeleteBlockedModal.tsx`) + 1 trivial (`routers/__init__.py`)

### Key Patterns Identified
- **SQLite migration** is PRAGMA-detect + conditional ALTER; `cols = {row[1] for row ...}` is the canonical idiom (`database.py` L69–76).
- **FastAPI routes** follow `@app.get(...)` + Pydantic `response_model` + `HTTPException(404 | 409)`; new routes go in `backend/routers/templates.py` with `APIRouter(prefix="/api/templates")` and `app.include_router(...)` registered AFTER `AuthMiddleware` (never touching `_AUTH_EXEMPT`).
- **Pydantic v2** uses `Literal` for enums, `Field(default_factory=list)` for mutable defaults, `@field_validator("x", mode="before")` for null-coerce — `coerce_clipboard_sync` is the reference.
- **React hook shape** is `{data, loading, error, refresh, create, update, remove}` with `setInterval(refresh, 3000)` and silent updates after first load — mirror `useProfiles.ts` exactly.
- **React form layout** is `<form class="p-6 max-w-2xl mx-auto">` with `<div class="space-y-5">` sections; section headings are `text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3`; `@layer components` classes (`.btn-*`, `.input`, `.label`) are reused, never reinvented.
- **Security discipline:** every D-18 touchpoint (`database.py` schema DEFAULT + `create_profile` fallback, `models.py` two fields + validator, `ProfileForm.tsx` initial state) must flip — 5 touchpoints, 1 atomic change.
- **Fail-closed startup** in `lifespan` before `db.init_db()` raises `RuntimeError` — halts FastAPI before uvicorn binds.

### File Created
`.planning/phases/01-schema-templates-and-security-foundations/01-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files with concrete file paths and line ranges.
