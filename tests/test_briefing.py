"""The executive briefing.

It is deterministic on purpose — pure SQL here and fixed thresholds in the
browser — because a narrated summary read out in front of a customer must never
contain a figure the app invented. These tests pin the two things that would
make it lie: the period boundary, and the comparison against the period before.
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api import metrics
from shared.db import SessionLocal
from shared.models import (
    AppUser,
    ConversationAnalysis,
    EntraUser,
    Prompt,
    PromptAnalysis,
)
from shared.security import hash_password

TODAY = date(2026, 9, 29)


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _add(s, *, pid: str, user: str, day: date, quality: int, category: str,
         conversation: str, user_generated: bool = True) -> None:
    s.add(
        Prompt(
            prompt_id=pid,
            user_id=user,
            conversation_id=conversation,
            app_name="Teams",
            prompt_date=day,
            analysed=True,
        )
    )
    s.add(
        PromptAnalysis(
            prompt_id=pid,
            conversation_id=conversation,
            user_generated=user_generated,
            quality_score=quality,
            category=category,
            gcse_goal=quality,
            gcse_context=max(1, quality - 3),
            gcse_source=quality,
            gcse_expectation=quality,
        )
    )


async def _seed() -> None:
    """Four prompts this period and two in the one before, so every
    period-on-period figure has a direction that is not zero."""
    async with SessionLocal() as s:
        s.add(EntraUser(user_id="u-1", display_name="Avery", department="Finance"))
        s.add(EntraUser(user_id="u-2", display_name="Blake", department="Legal"))
        recent = TODAY - timedelta(days=3)
        older = TODAY - timedelta(days=40)
        _add(s, pid="a", user="u-1", day=recent, quality=8, category="draft",
             conversation="c-1")
        _add(s, pid="b", user="u-1", day=recent, quality=8, category="draft",
             conversation="c-1")
        _add(s, pid="c", user="u-2", day=recent, quality=2, category="summarise",
             conversation="c-2")
        _add(s, pid="d", user="u-2", day=recent, quality=2, category="summarise",
             conversation="c-2", user_generated=False)
        _add(s, pid="e", user="u-1", day=older, quality=5, category="draft",
             conversation="c-3")
        _add(s, pid="f", user="u-1", day=older, quality=5, category="draft",
             conversation="c-3")
        s.add(
            ConversationAnalysis(
                conversation_id="c-1",
                theme="Drafting external communications",
                prompt_count=2,
            )
        )
        s.add(
            ConversationAnalysis(
                conversation_id="c-2", theme="Summarising long documents", prompt_count=2
            )
        )
        s.add(
            ConversationAnalysis(
                conversation_id="c-3", theme="Old work", prompt_count=2
            )
        )
        await s.commit()


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_the_current_period_excludes_the_previous_one(session):
    await _seed()
    b = await metrics.briefing(session, today=TODAY, window_days=30)
    assert b["current"]["prompts"] == 4
    assert b["previous"]["prompts"] == 2
    # Two people this period, one the period before.
    assert b["current"]["people"] == 2
    assert b["previous"]["people"] == 1


@pytest.mark.asyncio
async def test_quality_and_user_generated_share_are_this_period_only(session):
    await _seed()
    b = await metrics.briefing(session, today=TODAY, window_days=30)
    # (8 + 8 + 2 + 2) / 4 — the older 5s must not drag it to the middle.
    assert b["current"]["avg_quality"] == 5.0
    assert b["previous"]["avg_quality"] == 5.0
    assert b["current"]["user_generated_pct"] == 75.0


@pytest.mark.asyncio
async def test_intents_carry_their_own_previous_period_count(session):
    await _seed()
    b = await metrics.briefing(session, today=TODAY, window_days=30)
    by_name = {i["name"]: i for i in b["top_intents"]}
    assert by_name["draft"]["prompts"] == 2
    # Both of the older prompts were drafting, so it has a baseline to move
    # against; summarising is new this period.
    assert by_name["draft"]["prev_prompts"] == 2
    assert by_name["summarise"]["prev_prompts"] == 0


@pytest.mark.asyncio
async def test_themes_come_from_this_period_conversations(session):
    await _seed()
    b = await metrics.briefing(session, today=TODAY, window_days=30)
    names = [t["name"] for t in b["top_themes"]]
    assert "Drafting external communications" in names
    assert "Old work" not in names


@pytest.mark.asyncio
async def test_coaching_watch_outs_name_the_weakest_lever_and_count_people(session):
    await _seed()
    b = await metrics.briefing(session, today=TODAY, window_days=30)
    # Context is seeded three points below the others for everyone.
    assert b["levers"][0]["lever"] == "context"
    # Blake averages 2 out of 10; Avery averages 8.
    assert b["people_needing_coaching"] == 1
    assert b["low_quality_prompts"] == 2


@pytest.mark.asyncio
async def test_the_daily_series_is_one_row_per_day_oldest_first(session):
    await _seed()
    rows = await metrics.daily(session, f=metrics.PromptFilter())
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)
    assert len(rows) == 2
    assert rows[-1]["prompts"] == 4
    assert rows[-1]["conversations"] == 2


@pytest.mark.asyncio
async def test_the_briefing_is_organisation_data(client):
    """Unauthenticated callers get nothing; the route sits behind the org gate
    like every other organisation-wide page."""
    await _seed()
    assert (await client.get("/metrics/briefing")).status_code == 401
    r = await client.get("/metrics/briefing", headers=await _admin_headers(client))
    assert r.status_code == 200
    assert r.json()["window_days"] == 30
