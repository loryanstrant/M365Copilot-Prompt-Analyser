"""The user-only refresh — ``sync_users`` and ``POST /admin/users/refresh``.

Three things are worth pinning down, because each is a way the button could be
quietly useless:

- it actually writes the directory and licence snapshots the Tenant users page
  reads, and records a ``users`` job so Scan history can show it;
- a second click while one is running answers ``already_running`` rather than
  starting a concurrent Graph sweep;
- it does **not** drag the prompt pull or the Azure OpenAI analysis stage along.
  That is the whole reason it exists next to "Run now", so it is asserted rather
  than assumed.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from sqlalchemy import func, select

from shared.db import SessionLocal
from shared.models import (
    AppConfig,
    AppUser,
    ConversationAnalysis,
    EntraUser,
    IngestState,
    JobRun,
    LicenseCount,
    LicensedUser,
    Prompt,
    PromptAnalysis,
)
from shared.security import hash_password
from worker.ingest import UserSyncProgress, sync_users

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
SKU = "639dec6b-bb19-468b-871c-c5c441c4b0cb"
COPILOT_PLAN = "3f30311c-6b1e-48a4-ab79-725b469da960"


class FakeGraph:
    """The subset of GraphClient a user sync may call — and no more.

    ``iter_enterprise_interactions`` raises rather than returning nothing: a
    user refresh that reaches the prompt endpoint has stopped being cheap, and a
    fake that answered politely would hide that.
    """

    def __init__(self, *, licensed, skus, directory):
        self._licensed = licensed
        self._skus = skus
        self._directory = directory
        self.closed = False

    async def iter_licensed_users(self, sku_ids):
        for u in self._licensed:
            yield u

    async def get_subscribed_skus(self):
        return self._skus

    async def iter_directory_users(self):
        for u in self._directory:
            yield u

    async def iter_enterprise_interactions(self, user_id, since, until, *, page_size=100):
        raise AssertionError("A user refresh must not fetch prompts.")
        yield  # pragma: no cover - keeps this an async generator

    async def aclose(self):
        self.closed = True


def _config() -> AppConfig:
    return AppConfig(
        id=1,
        tenant_id="tenant",
        client_id="client",
        client_secret_encrypted="x",
        copilot_sku_ids=[SKU],
        backfill_days=30,
    )


def _fake_graph() -> FakeGraph:
    assigned = [{"skuId": SKU, "disabledPlans": []}]
    return FakeGraph(
        licensed=[
            {"id": "user-1", "assignedLicenses": assigned},
            {"id": "user-2", "assignedLicenses": assigned},
        ],
        skus=[
            {
                "skuId": SKU,
                "capabilityStatus": "Enabled",
                "servicePlans": [{"servicePlanId": COPILOT_PLAN}],
                "consumedUnits": 2,
                "prepaidUnits": {
                    "enabled": 5,
                    "suspended": 0,
                    "warning": 0,
                    "lockedOut": 0,
                },
            },
            {"skuId": "other-sku", "consumedUnits": 100, "prepaidUnits": {"enabled": 200}},
        ],
        directory=[
            {
                "id": "user-1",
                "userPrincipalName": "alice@contoso.com",
                "mail": "alice@contoso.com",
                "userType": "Member",
                "accountEnabled": True,
                "displayName": "Alice",
                "assignedLicenses": assigned,
            },
            {
                "id": "user-3",
                "userPrincipalName": "bob@contoso.com",
                "mail": "bob@contoso.com",
                "userType": "Member",
                "accountEnabled": True,
                "displayName": "Bob",
                "assignedLicenses": [],
            },
        ],
    )


@pytest.fixture(autouse=True)
def _reset_progress():
    """Module-level progress is process state; keep it from leaking between tests."""
    import worker.ingest as ingest

    ingest._user_sync = UserSyncProgress()
    yield
    ingest._user_sync = UserSyncProgress()


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- it runs -------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_users_populates_the_user_tables():
    stats = await sync_users(
        SessionLocal, graph=_fake_graph(), config=_config(), now=NOW
    )

    assert stats["licensed_users"] == 2
    assert stats["license_counts"] == 1  # only the Copilot-granting SKU
    assert stats["entra_users"] == 2

    async with SessionLocal() as s:
        assert (
            await s.scalar(select(func.count()).select_from(LicensedUser))
        ) == 2
        assert (
            await s.scalar(select(func.count()).select_from(LicenseCount))
        ) == 1

        by_id = {u.user_id: u for u in (await s.execute(select(EntraUser))).scalars()}
        assert set(by_id) == {"user-1", "user-3"}
        # The flag the Tenant users page filters and counts on — the whole point
        # of being able to run this on demand.
        assert by_id["user-1"].has_copilot_license is True
        assert by_id["user-3"].has_copilot_license is False

        job = (await s.execute(select(JobRun))).scalars().one()
        assert job.job_name == "users"
        assert job.status == "success"
        assert job.finished_at is not None


@pytest.mark.asyncio
async def test_sync_users_reports_its_progress():
    from worker.ingest import get_user_sync_progress, user_sync_running

    assert user_sync_running() is False
    await sync_users(SessionLocal, graph=_fake_graph(), config=_config(), now=NOW)

    progress = get_user_sync_progress()
    assert progress["status"] == "completed"
    assert progress["licensed_users"] == 2
    assert progress["directory_users"] == 2
    assert user_sync_running() is False


@pytest.mark.asyncio
async def test_a_failure_is_recorded_and_not_left_looking_busy():
    class Broken(FakeGraph):
        async def get_subscribed_skus(self):
            raise RuntimeError("Graph said no")

    from worker.ingest import get_user_sync_progress, user_sync_running

    broken = Broken(licensed=[], skus=[], directory=[])
    with pytest.raises(RuntimeError):
        await sync_users(SessionLocal, graph=broken, config=_config(), now=NOW)

    assert user_sync_running() is False
    assert get_user_sync_progress()["status"] == "failed"
    async with SessionLocal() as s:
        job = (await s.execute(select(JobRun))).scalars().one()
        assert job.job_name == "users"
        assert job.status == "failed"
        assert job.stats["error"] == "Graph said no"


@pytest.mark.asyncio
async def test_half_configured_credentials_do_not_jam_the_button():
    """The nastiest way this could fail: stuck at "running" with nothing running.

    A tenant ID saved without a client secret makes ``build_graph_client`` raise
    before there is a job row to mark failed. If that path skipped clearing the
    progress flag, ``user_sync_running()`` would stay true for the life of the
    process and every later refresh would answer ``already_running`` forever.
    """
    from worker.ingest import get_user_sync_progress, user_sync_running

    async with SessionLocal() as s:
        s.add(AppConfig(id=1, tenant_id="tenant"))  # no client_id, no secret
        await s.commit()

    with pytest.raises(Exception):
        await sync_users(SessionLocal, now=NOW)

    assert user_sync_running() is False
    assert get_user_sync_progress()["status"] == "failed"
    async with SessionLocal() as s:
        # Nothing got as far as a job row, so Scan history gains no empty entry.
        assert (await s.scalar(select(func.count()).select_from(JobRun))) == 0


@pytest.mark.asyncio
async def test_unconfigured_graph_fails_without_jamming_the_button():
    from worker.ingest import IngestError, get_user_sync_progress, user_sync_running

    with pytest.raises(IngestError):
        await sync_users(SessionLocal, now=NOW)

    assert user_sync_running() is False
    assert get_user_sync_progress()["detail"] == "Graph is not configured yet."


@pytest.mark.asyncio
async def test_endpoint_starts_a_refresh(client, monkeypatch):
    from api.routers import admin

    calls: list[str] = []

    async def fake_sync(session_factory, **kwargs):
        calls.append("ran")
        return {}

    monkeypatch.setattr(admin, "sync_users", fake_sync)
    headers = await _admin_headers(client)

    r = await client.post("/admin/users/refresh", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "started"
    # The work is a background task, so it has run by the time the response has
    # been fully consumed.
    assert calls == ["ran"]


# --- it refuses to run twice at once ------------------------------------
@pytest.mark.asyncio
async def test_endpoint_refuses_a_concurrent_refresh(client, monkeypatch):
    from api.routers import admin

    monkeypatch.setattr(admin, "sync_users", _never_called)
    headers = await _admin_headers(client)

    async with admin._user_sync_lock:
        r = await client.post("/admin/users/refresh", headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "already_running"
    assert "already in progress" in body["detail"]


@pytest.mark.asyncio
async def test_a_refresh_started_elsewhere_also_blocks(client, monkeypatch):
    """The lock only covers refreshes this process started through the endpoint."""
    import worker.ingest as ingest
    from api.routers import admin

    monkeypatch.setattr(admin, "sync_users", _never_called)
    ingest._user_sync.status = "running"
    headers = await _admin_headers(client)

    r = await client.post("/admin/users/refresh", headers=headers)
    assert r.json()["status"] == "already_running"


async def _never_called(session_factory, **kwargs):  # pragma: no cover
    raise AssertionError("A second refresh must not start.")


# --- it does not drag the expensive stages along -------------------------
@pytest.mark.asyncio
async def test_refresh_touches_neither_prompts_nor_analysis(client, monkeypatch):
    """End to end: no prompt rows, no analysis rows, no analysis job.

    ``FakeGraph.iter_enterprise_interactions`` raises, so reaching the prompt
    endpoint fails the test rather than merely leaving the table empty.
    """
    import worker.analysis as analysis_mod
    from api.routers import admin

    async def boom(*args, **kwargs):  # pragma: no cover
        raise AssertionError("A user refresh must not run the analysis stage.")

    monkeypatch.setattr(analysis_mod, "run_analysis", boom)
    monkeypatch.setattr(admin, "run_analysis", boom)

    graph, config = _fake_graph(), _config()

    async def scoped_sync(session_factory, **kwargs):
        return await sync_users(session_factory, graph=graph, config=config, now=NOW)

    monkeypatch.setattr(admin, "sync_users", scoped_sync)
    headers = await _admin_headers(client)

    r = await client.post("/admin/users/refresh", headers=headers)
    assert r.json()["status"] == "started"

    async with SessionLocal() as s:
        assert (await s.scalar(select(func.count()).select_from(Prompt))) == 0
        assert (
            await s.scalar(select(func.count()).select_from(PromptAnalysis))
        ) == 0
        assert (
            await s.scalar(select(func.count()).select_from(ConversationAnalysis))
        ) == 0
        # No per-user prompt watermark was written, so a later collection run
        # still looks back over the window it would have anyway.
        assert (await s.scalar(select(func.count()).select_from(IngestState))) == 0
        names = {j.job_name for j in (await s.execute(select(JobRun))).scalars()}
        assert names == {"users"}
