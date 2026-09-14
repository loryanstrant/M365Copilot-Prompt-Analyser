"""Personal coaching view and the organisation-view gate.

The security-relevant claims here are:

- a personal endpoint scopes to the caller's own identity, and offers no way to
  ask for somebody else's;
- the organisation view — including the people picker and the coach-anybody
  ``/metrics/personal/{user_id}`` route — is closed to people outside the
  configured group;
- but an unconfigured group leaves the org view open, so upgrading an existing
  deployment doesn't lock everyone out.

Prompts key on the Entra object ID (``prompts.user_id``), which is exactly the
``oid`` claim the token carries, so the personal view needs no extra lookup.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import (
    AppConfig,
    AppUser,
    ConversationAnalysis,
    EntraUser,
    Prompt,
    PromptAnalysis,
)
from shared.security import hash_password

ME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MY_UPN = "me@contoso.com"
SOMEONE_ELSE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
THEIR_UPN = "them@contoso.com"
GROUP = "cccccccc-cccc-cccc-cccc-cccccccccccc"

MY_CONVERSATION = "conv-mine"
THEIR_CONVERSATION = "conv-theirs"

MINE = 3
THEIRS = 9


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _add_prompts(s, *, user_id: str, conversation_id: str, prefix: str, count: int,
                 quality: int) -> None:
    for i in range(count):
        pid = f"{prefix}-{i}"
        s.add(
            Prompt(
                prompt_id=pid,
                user_id=user_id,
                conversation_id=conversation_id,
                app_name="Teams",
                prompt_date=date(2026, 9, 1),
                created_at=datetime(2026, 9, 1, 9, i, tzinfo=timezone.utc),
                prompt_text=f"{prefix} prompt {i}",
                name_confidence=1,
                sensitive_confidence=1,
                curse_confidence=1,
                analysed=True,
            )
        )
        s.add(
            PromptAnalysis(
                prompt_id=pid,
                conversation_id=conversation_id,
                user_generated=True,
                sentiment="Neutral",
                quality_score=quality,
                category="Drafting",
                gcse_goal=quality,
                gcse_context=quality,
                gcse_source=quality,
                gcse_expectation=quality,
            )
        )


async def _seed_activity() -> None:
    """Two people with clearly different volumes, so a leak is obvious."""
    async with SessionLocal() as s:
        s.add(EntraUser(user_id=ME, upn=MY_UPN, display_name="Me"))
        s.add(EntraUser(user_id=SOMEONE_ELSE, upn=THEIR_UPN, display_name="Them"))
        _add_prompts(
            s,
            user_id=ME,
            conversation_id=MY_CONVERSATION,
            prefix="mine",
            count=MINE,
            quality=8,
        )
        _add_prompts(
            s,
            user_id=SOMEONE_ELSE,
            conversation_id=THEIR_CONVERSATION,
            prefix="theirs",
            count=THEIRS,
            quality=4,
        )
        s.add(
            ConversationAnalysis(
                conversation_id=MY_CONVERSATION,
                sentiment="Neutral",
                avg_quality_score=8,
                conversation_quality_score=8,
                prompt_count=MINE,
            )
        )
        s.add(
            ConversationAnalysis(
                conversation_id=THEIR_CONVERSATION,
                sentiment="Neutral",
                avg_quality_score=4,
                conversation_quality_score=4,
                prompt_count=THEIRS,
            )
        )
        await s.commit()


async def _set_org_group(group_id: str | None) -> None:
    async with SessionLocal() as s:
        cfg = await s.get(AppConfig, 1)
        if cfg is None:
            cfg = AppConfig(id=1)
            s.add(cfg)
        cfg.org_view_group_id = group_id
        await s.commit()


def _viewer_headers(oid: str = ME, upn: str = MY_UPN) -> dict[str, str]:
    token = create_access_token(upn, "viewer", oid=oid, upn=upn)
    return {"Authorization": f"Bearer {token}"}


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(
            AppUser(username="admin", password_hash=hash_password("pw"), role="admin")
        )
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Personal view
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_personal_coaching_covers_only_my_own_prompts(client):
    await _seed_activity()
    r = await client.get("/metrics/me/coaching", headers=_viewer_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    # Three prompts of mine, nine of theirs. Anything higher is a leak.
    assert body["prompts"] == MINE
    assert body["conversations"] == 1
    assert body["avg_quality"] == 8
    assert body["user_id"] == ME


@pytest.mark.asyncio
async def test_personal_view_cannot_be_pointed_at_someone_else(client):
    """The caller is taken from the token, so a spoofed id changes nothing."""
    await _seed_activity()
    r = await client.get(
        f"/metrics/me/summary?user={SOMEONE_ELSE}&user_id={SOMEONE_ELSE}",
        headers=_viewer_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["prompts"] == MINE

    r = await client.get(
        f"/metrics/me/coaching?user_id={SOMEONE_ELSE}&user={SOMEONE_ELSE}",
        headers=_viewer_headers(),
    )
    assert r.status_code == 200
    assert r.json()["prompts"] == MINE
    assert r.json()["user_id"] == ME


@pytest.mark.asyncio
async def test_personal_conversations_list_only_my_own(client):
    await _seed_activity()
    r = await client.get("/metrics/me/conversations", headers=_viewer_headers())
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["conversation_id"] == MY_CONVERSATION
    assert SOMEONE_ELSE not in r.text
    assert THEIR_CONVERSATION not in r.text


@pytest.mark.asyncio
async def test_personal_conversation_detail_refuses_other_peoples_threads(client):
    """Conversation ids name a thread, not a user — ownership is still checked."""
    await _seed_activity()
    headers = _viewer_headers()
    mine = await client.get(
        f"/metrics/me/conversations/{MY_CONVERSATION}", headers=headers
    )
    assert mine.status_code == 200
    assert len(mine.json()["prompts"]) == MINE

    theirs = await client.get(
        f"/metrics/me/conversations/{THEIR_CONVERSATION}", headers=headers
    )
    assert theirs.status_code == 404


@pytest.mark.asyncio
async def test_personal_view_is_absent_without_an_entra_identity(client):
    """The password admin has no object ID, so there is nothing to show them."""
    headers = await _admin_headers(client)
    r = await client.get("/metrics/me/coaching", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_personal_view_is_empty_rather_than_broken_without_data(client):
    """Someone with no prompts yet should get an empty view, not an error."""
    await _seed_activity()
    r = await client.get(
        "/metrics/me/coaching",
        headers=_viewer_headers(oid="dddddddd-dddd-dddd-dddd-dddddddddddd",
                               upn="new@contoso.com"),
    )
    assert r.status_code == 200
    assert r.json()["prompts"] == 0


@pytest.mark.asyncio
async def test_personal_view_requires_authentication(client):
    r = await client.get("/metrics/me/coaching")
    assert r.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Organisation-view gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_org_view_open_when_no_group_configured(client):
    """Upgrades must not silently lock existing viewers out."""
    await _seed_activity()
    await _set_org_group(None)
    r = await client.get("/metrics/summary", headers=_viewer_headers())
    assert r.status_code == 200, r.text
    assert r.json()["prompts"] == MINE + THEIRS


@pytest.mark.asyncio
async def test_org_view_denied_to_non_members(client):
    await _seed_activity()
    await _set_org_group(GROUP)
    r = await client.get("/metrics/summary", headers=_viewer_headers())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_org_view_allowed_for_group_members(client, monkeypatch):
    await _seed_activity()
    await _set_org_group(GROUP)

    import api.oidc as oidc

    async def _member(principal, group_id, session):
        return group_id == GROUP

    monkeypatch.setattr(oidc, "is_group_member", _member)
    r = await client.get("/metrics/summary", headers=_viewer_headers())
    assert r.status_code == 200
    assert r.json()["prompts"] == MINE + THEIRS


@pytest.mark.asyncio
async def test_admin_bypasses_the_org_group(client):
    await _seed_activity()
    await _set_org_group(GROUP)
    headers = await _admin_headers(client)
    r = await client.get("/metrics/summary", headers=headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_people_picker_and_coach_anybody_route_are_org_tools(client):
    """Both expose other people, so both must sit behind the gate."""
    await _seed_activity()
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (await client.get("/metrics/people", headers=headers)).status_code == 403
    assert (
        await client.get(f"/metrics/personal/{SOMEONE_ELSE}", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_personal_view_survives_the_org_gate(client):
    """Losing org access must not cost someone their own data."""
    await _seed_activity()
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (await client.get("/metrics/summary", headers=headers)).status_code == 403
    r = await client.get("/metrics/me/coaching", headers=headers)
    assert r.status_code == 200
    assert r.json()["prompts"] == MINE


@pytest.mark.asyncio
async def test_auth_me_advertises_capabilities(client):
    await _set_org_group(GROUP)
    r = await client.get("/auth/me", headers=_viewer_headers())
    body = r.json()
    assert body["has_personal_view"] is True
    assert body["can_view_org"] is False


@pytest.mark.asyncio
async def test_shared_lookups_stay_open_to_everyone(client):
    """Slicer options, freshness and About sit outside the org gate."""
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (await client.get("/metrics/filters", headers=headers)).status_code == 200
    assert (await client.get("/metrics/freshness", headers=headers)).status_code == 200
    assert (await client.get("/metrics/about", headers=headers)).status_code == 200
