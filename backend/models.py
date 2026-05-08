"""Pydantic models for profile CRUD operations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
