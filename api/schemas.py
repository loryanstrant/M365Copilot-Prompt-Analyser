"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- auth ---------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserOut(BaseModel):
    username: str
    role: str
    # Whether this user may see organisation-wide data. Drives whether the SPA
    # offers the org view or shows it locked.
    can_view_org: bool = True
    # Whether there is an Entra identity to filter a personal view down to.
    # False for the password admin, who therefore lands on the org view.
    has_personal_view: bool = False


class AuthConfigOut(BaseModel):
    entra_enabled: bool
    redirect_uri: str


# --- admin config -------------------------------------------------------
class AppConfigIn(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    # Write-only: only applied when a non-empty value is supplied.
    client_secret: str | None = None
    copilot_sku_ids: list[str] | None = None
    report_access_group_id: str | None = None
    org_view_group_id: str | None = None
    backfill_days: int | None = Field(default=None, ge=1, le=3650)
    schedule_cron: str | None = None
    # Friendly recurring-ingest cadence: run every N hours (1..24; 24 = daily).
    schedule_interval_hours: int | None = Field(default=None, ge=1, le=24)
    # --- Azure OpenAI (analysis engine) ---
    aoai_endpoint: str | None = None
    aoai_deployment: str | None = None
    # Accepted but ignored: the Azure OpenAI v1 surface takes no api-version.
    # Kept so an older client PUTting it gets a 200 rather than a 422.
    aoai_api_version: str | None = None
    # Write-only: only applied when a non-empty value is supplied.
    aoai_key: str | None = None
    analysis_mode: str | None = Field(default=None, pattern="^(combined|split)$")


class AppConfigOut(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    copilot_sku_ids: list[str] = []
    report_access_group_id: str | None = None
    org_view_group_id: str | None = None
    backfill_days: int = 30
    schedule_cron: str | None = None
    schedule_interval_hours: int = 24
    # --- Azure OpenAI (analysis engine) ---
    aoai_endpoint: str | None = None
    aoai_deployment: str | None = None
    has_aoai_key: bool = False
    analysis_mode: str = "combined"
    aoai_configured: bool = False
    configured: bool = False
    updated_at: datetime | None = None
    updated_by: str | None = None


class TestConnectionOut(BaseModel):
    ok: bool
    token_acquired: bool = False
    subscribed_skus: bool = False
    directory_read: bool = False
    copilot_licensed_users: int | None = None
    detail: str | None = None


class TestAoaiOut(BaseModel):
    ok: bool
    detail: str | None = None


class IngestRunOut(BaseModel):
    status: str
    detail: str


# --- status -------------------------------------------------------------
class JobRunOut(BaseModel):
    id: int
    job_name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict[str, Any] | None = None


class StatusOut(BaseModel):
    configured: bool
    last_run: JobRunOut | None = None
    prompts: int = 0
    conversations: int = 0
    licensed_users: int = 0
    entra_users: int = 0
