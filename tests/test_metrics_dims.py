"""Tests for the enriched metrics layer: user dimensions, governance flags,
distinct conversation scores and per-user personal coaching.

Runs against the SQLite session fixture (no Postgres needed). We seed a tiny
directory + a couple of conversations, then assert the SQL metrics slice and
aggregate correctly.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from api import metrics
from api.metrics import PromptFilter
from shared.models import (
    ConversationAnalysis,
    EntraUser,
    Prompt,
    PromptAnalysis,
)


async def _seed(session) -> None:
    # Two users, one with a manager + department, one bare.
    session.add_all(
        [
            EntraUser(
                user_id="mgr1", display_name="Mia Manager", department="Eng"
            ),
            EntraUser(
                user_id="u1",
                display_name="Alice",
                department="Eng",
                country="Australia",
                manager_id="mgr1",
            ),
            EntraUser(user_id="u2", display_name="Bob", department=None),
        ]
    )

    def add_prompt(pid, uid, conv, text, q, *, ug=True, name=1, sens=1, curse=1,
                   app="Copilot Chat", cat="ask", when=1):
        session.add(
            Prompt(
                prompt_id=pid,
                user_id=uid,
                conversation_id=conv,
                app_name=app,
                prompt_date=date(2026, 8, 1),
                created_at=datetime(2026, 8, 1, 9, when, tzinfo=timezone.utc),
                prompt_text=text,
                name_confidence=name,
                sensitive_confidence=sens,
                curse_confidence=curse,
                analysed=True,
            )
        )
        session.add(
            PromptAnalysis(
                prompt_id=pid,
                conversation_id=conv,
                user_generated=ug,
                sentiment="neutral",
                quality_score=q,
                quality_rationale="r",
                category=cat,
                gcse_goal=q,
                gcse_context=q,
                gcse_source=max(1, q - 3),
                gcse_expectation=q,
            )
        )

    # Alice: conversation c1 with two prompts (avg 5), one flagged sensitive.
    add_prompt("p1", "u1", "c1", "first", 4, sens=9, when=1)
    add_prompt("p2", "u1", "c1", "second", 6, when=2)
    # Bob: conversation c2, one prompt.
    add_prompt("p3", "u2", "c2", "third", 8, name=8, when=1)

    session.add_all(
        [
            ConversationAnalysis(
                conversation_id="c1",
                sentiment="neutral",
                avg_quality_score=5.0,
                conversation_quality_score=7,  # holistic != avg-of-prompts
                user_generated_ratio=100.0,
                theme="Alice theme",
                category="ask",
                prompt_count=2,
            ),
            ConversationAnalysis(
                conversation_id="c2",
                sentiment="positive",
                avg_quality_score=8.0,
                conversation_quality_score=8,
                user_generated_ratio=100.0,
                theme="Bob theme",
                category="ask",
                prompt_count=1,
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_filter_options_and_people(session) -> None:
    await _seed(session)
    opts = await metrics.filter_options(session)
    assert {u["id"] for u in opts["users"]} == {"u1", "u2"}
    assert "Eng" in opts["departments"]
    assert "Australia" in opts["countries"]
    assert any(m["name"] == "Mia Manager" for m in opts["managers"])

    ppl = await metrics.people(session)
    alice = next(p for p in ppl if p["user_id"] == "u1")
    assert alice["name"] == "Alice"
    assert alice["manager"] == "Mia Manager"
    assert alice["prompts"] == 2


@pytest.mark.asyncio
async def test_user_and_department_filter(session) -> None:
    await _seed(session)
    # Filter to Alice by user id.
    s = await metrics.summary(session, f=PromptFilter(users=["u1"]))
    assert s["prompts"] == 2
    assert s["conversations"] == 1
    # Filter by department (only Alice is in Eng with data... Bob has no dept).
    s2 = await metrics.summary(session, f=PromptFilter(departments=["Eng"]))
    assert s2["prompts"] == 2  # only Alice's prompts


@pytest.mark.asyncio
async def test_governance_flag_filter(session) -> None:
    await _seed(session)
    # Sensitive flag (>=7) matches only p1.
    rows = await metrics.prompts_table(
        session, f=PromptFilter(flags=["sensitive"]), limit=100
    )
    assert [r["prompt_id"] for r in rows] == ["p1"]
    # Name flag (>=7) matches only p3.
    rows2 = await metrics.prompts_table(
        session, f=PromptFilter(flags=["name"]), limit=100
    )
    assert [r["prompt_id"] for r in rows2] == ["p3"]
    # summary exposes flagged counts.
    s = await metrics.summary(session, f=PromptFilter())
    assert s["flagged_sensitive"] == 1
    assert s["flagged_name"] == 1


@pytest.mark.asyncio
async def test_source_filter(session) -> None:
    await _seed(session)
    rows = await metrics.prompts_table(
        session, f=PromptFilter(sources=["user"]), limit=100
    )
    assert len(rows) == 3
    assert all(r["source"] == "User" for r in rows)


@pytest.mark.asyncio
async def test_conversations_avg_vs_overall(session) -> None:
    await _seed(session)
    convs = await metrics.conversations_table(session, f=PromptFilter())
    c1 = next(c for c in convs if c["conversation_id"] == "c1")
    # avg-of-prompts (5.0) is distinct from the holistic conversation score (7).
    assert c1["avg_prompt_quality"] == 5.0
    assert c1["conversation_quality_score"] == 7
    assert c1["user_name"] == "Alice"
    assert c1["avg_sensitive_confidence"] == 5.0  # (9 + 1) / 2


@pytest.mark.asyncio
async def test_conversation_detail_ordered_and_scored(session) -> None:
    await _seed(session)
    detail = await metrics.conversation_detail(session, "c1")
    ids = [p["prompt_id"] for p in detail["prompts"]]
    assert ids == ["p1", "p2"]  # chronological by created_at
    assert detail["conversation"]["avg_of_prompts"] == 5.0
    assert detail["conversation"]["conversation_quality_score"] == 7
    assert detail["conversation"]["user_name"] == "Alice"


@pytest.mark.asyncio
async def test_personal_per_user(session) -> None:
    await _seed(session)
    p = await metrics.personal(session, "u1")
    assert p["name"] == "Alice"
    assert p["prompts"] == 2
    assert p["conversations"] == 1
    assert p["avg_quality"] == 5.0
    assert p["weakest_lever"] == "source"  # gcse_source is the lowest lever
    # team GCSE differs from mine (team spans all users).
    assert p["gcse_mine"]["source"] is not None
    assert p["gcse_team"]["source"] is not None
