"""Pydantic models for profile CRUD operations."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class ProfileCreate(BaseModel):
    name: str
    fingerprint_seed: int | None = None  # random if not set
    proxy: str | None = None  # "http://user:pass@host:port" or null
    timezone: str | None = None  # "America/New_York"
    locale: str | None = None  # "en-US"
    platform: Literal["windows", "macos", "linux"] = "windows"
    user_agent: str | None = None
    screen_width: int = 1920
    screen_height: int = 1080
    gpu_vendor: str | None = None
    gpu_renderer: str | None = None
    hardware_concurrency: int | None = None
    humanize: bool = False
    human_preset: Literal["default", "careful"] = "default"
    headless: bool = False
    geoip: bool = False
    clipboard_sync: bool = False
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    launch_args: list[str] = Field(default_factory=list)
    notes: str | None = None
    tags: list[TagCreate] | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    fingerprint_seed: int | None = None
    proxy: str | None = Field(default=None)
    timezone: str | None = Field(default=None)
    locale: str | None = Field(default=None)
    platform: Literal["windows", "macos", "linux"] | None = None
    user_agent: str | None = Field(default=None)
    screen_width: int | None = None
    screen_height: int | None = None
    gpu_vendor: str | None = Field(default=None)
    gpu_renderer: str | None = Field(default=None)
    hardware_concurrency: int | None = Field(default=None)
    humanize: bool | None = None
    human_preset: Literal["default", "careful"] | None = None
    headless: bool | None = None
    geoip: bool | None = None
    clipboard_sync: bool | None = None
    color_scheme: Literal["light", "dark", "no-preference"] | None = Field(default=None)
    launch_args: list[str] | None = None
    notes: str | None = Field(default=None)
    tags: list[TagCreate] | None = None


class TagCreate(BaseModel):
    tag: str
    color: str | None = None  # hex color


class TagResponse(BaseModel):
    tag: str
    color: str | None = None


class ProfileResponse(BaseModel):
    id: str
    name: str
    fingerprint_seed: int
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    platform: str = "windows"
    user_agent: str | None = None
    screen_width: int = 1920
    screen_height: int = 1080
    gpu_vendor: str | None = None
    gpu_renderer: str | None = None
    hardware_concurrency: int | None = None
    humanize: bool = False
    human_preset: str = "default"
    headless: bool = False
    geoip: bool = False
    clipboard_sync: bool = False

    @field_validator("clipboard_sync", mode="before")
    @classmethod
    def coerce_clipboard_sync(cls, v: object) -> bool:
        return v if v is not None else False

    color_scheme: str | None = None
    launch_args: list[str] = []
    notes: str | None = None
    user_data_dir: str
    created_at: str
    updated_at: str
    tags: list[TagResponse] = []
    status: str = "stopped"  # "running" | "stopped"
    vnc_ws_port: int | None = None
    cdp_url: str | None = None


class LaunchResponse(BaseModel):
    profile_id: str
    status: str = "running"
    vnc_ws_port: int
    display: str
    cdp_url: str | None = None


class StatusResponse(BaseModel):
    running_count: int
    binary_version: str
    profiles_total: int


class ProfileStatusResponse(BaseModel):
    status: str  # "running" | "stopped"
    vnc_ws_port: int | None = None
    display: str | None = None
    cdp_url: str | None = None


class ClipboardRequest(BaseModel):
    text: str = Field(max_length=1_048_576)  # 1MB max


class LoginRequest(BaseModel):
    token: str


class TemplateBlueprint(BaseModel):
    """JSON payload stored in vendor_templates.blueprint (D-02).

    Mirrors ProfileCreate fields EXCEPT fingerprint_seed — seed is generated
    per-profile at creation time (D-04) to ensure each (vendor_type,
    vendor_connection_id) has an identity-unique fingerprint.
    """
    # Fingerprint
    timezone: str | None = None
    locale: str | None = None
    platform: Literal["windows", "macos", "linux"] = "windows"
    user_agent: str | None = None

    # Screen
    screen_width: int = 1920
    screen_height: int = 1080
    color_scheme: Literal["light", "dark", "no-preference"] | None = None

    # GPU
    gpu_vendor: str | None = None
    gpu_renderer: str | None = None
    hardware_concurrency: int | None = None

    # Behavior
    humanize: bool = False
    human_preset: Literal["default", "careful"] = "default"
    launch_args: list[str] = Field(default_factory=list)

    # Security — D-18: DEFAULT FALSE
    clipboard_sync: bool = False

    # Proxy
    proxy: str | None = None

    @field_validator("clipboard_sync", mode="before")
    @classmethod
    def enforce_clipboard_default(cls, v: object) -> bool:
        """SEC-05 / D-18: null or missing coerces to False. Never True-by-default."""
        return bool(v) if v is not None else False


class VendorTemplateCreate(BaseModel):
    vendor_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    label: str | None = None
    notes: str | None = None
    blueprint: TemplateBlueprint


class VendorTemplateUpdate(BaseModel):
    # vendor_type is the lookup key; changing it means delete+recreate
    label: str | None = None
    notes: str | None = None
    blueprint: TemplateBlueprint | None = None


class VendorTemplateResponse(BaseModel):
    id: str
    vendor_type: str
    label: str | None = None
    notes: str | None = None
    blueprint: TemplateBlueprint
    created_at: str
    updated_at: str


class TemplateDeleteBlockedResponse(BaseModel):
    """409 response body shape when template is in use (D-06, D-13)."""
    detail: str
    blocking_profile_ids: list[str]


# Phase 2 machine-API models (CONTEXT.md D-10 / D-16 / D-18 / D-20)

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class SessionRequest(BaseModel):
    """POST /sessions request body (SESS-01, SESS-02)."""
    model_config = ConfigDict(extra="forbid")
    vendor_type: NonEmptyStr
    vendor_connection_id: NonEmptyStr


class SessionResponse(BaseModel):
    """POST /sessions response body (SESS-02).

    Phase 2: vnc_viewer_url is the empty string (Phase 3 wires the signed URL).
    """
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    cdp_url: str  # /api/profiles/{id}/cdp (D-13)
    vnc_viewer_url: str = ""  # Phase 3 wires
    state: Literal["running", "idle", "stopped"]


class SessionStatusResponse(BaseModel):
    """GET /sessions/{profile_id} response body (SESS-13, D-18).

    Mirrors SessionStatusEnvelope from session_manager.py.
    """
    model_config = ConfigDict(extra="forbid")
    state: Literal["running", "idle", "stopped"]
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
    idle_expires_at: str | None = None
    last_launched_at: str | None = None


class AdminSessionListItem(BaseModel):
    """GET /api/admin/sessions row (ADM-02)."""
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    name: str
    vendor_type: str
    vendor_connection_id: str
    state: Literal["running", "idle", "stopped"]
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
    idle_expires_at: str | None = None
    last_launched_at: str | None = None
    uptime_seconds: int | None = None
    clipboard_sync: bool = False


class SessionListItem(BaseModel):
    """One entry in GET /sessions response (D-14)."""
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    vendor_type: str
    vendor_connection_id: str
    state: Literal["running", "idle", "stopped"]
    cdp_attach_count: int = 0
    viewer_attach_count: int = 0
    idle_expires_at: str | None = None
    last_launched_at: str | None = None


class ProfilePatch(BaseModel):
    """PATCH /profiles/{id} request body (PROF-03).

    Phase 2 v1 surface: notes only. Identity keys (vendor_type,
    vendor_connection_id, template_id) are NOT patchable. clipboard_sync is
    NOT patchable from the Main App per CLAUDE.md security rule 2.
    """
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None)


class MachineProfileResponse(BaseModel):
    """GET /profiles, GET /profiles/{id} response body (PROF-01, PROF-02)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    vendor_type: str
    vendor_connection_id: str
    template_id: str | None = None
    notes: str | None = None
    user_data_dir: str
    created_at: str
    updated_at: str
    timezone: str | None = None
    locale: str | None = None
    platform: str = "windows"
    screen_width: int = 1920
    screen_height: int = 1080
    clipboard_sync: bool = False

    @field_validator("clipboard_sync", mode="before")
    @classmethod
    def coerce_clipboard_sync(cls, v: object) -> bool:
        return bool(v) if v is not None else False
