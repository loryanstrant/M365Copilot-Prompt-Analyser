"""Tests for ``api.metrics.peer_comparison`` — the "how you compare" panel.

This replaced a tenant-wide average mislabelled "Team average" (see
docs/specs/comparisons-and-timelines.md). The two things worth locking down
with tests are the disclosure rule (a team series is withheld below
MIN_TEAM_PEERS, and the reason distinguishes "too small" from "unknown team")
and that the team series is genuinely the team's own mean, not a repaint of
the organisation's.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from api import metrics
from api.metrics import MIN_TEAM_PEERS, PromptFilter
from shared.models import EntraUser, Prompt, PromptAnalysis


def _add_person(session, uid, *, department=None, manager_id=None, name=None):
    session.add(
        EntraUser(
            user_id=uid,
            display_name=name or uid,
            department=department,
            manager_id=manager_id,
        )
    )


def _add_prompt(session, pid, uid, *, goal=5, context=5, source=5, expectation=5, when=1):
    # One prompt per person is enough: peer_comparison averages per-user across
    # whatever prompts exist, and every test here needs exactly one lever value
    # per person, not a distribution.
    session.add(
        Prompt(
            prompt_id=pid,
            user_id=uid,
            conversation_id=f"c-{pid}",
            app_name="Copilot Chat",
            prompt_date=date(2026, 8, 1),
            created_at=datetime(2026, 8, 1, 9, when, tzinfo=timezone.utc),
            prompt_text="hello",
            name_confidence=1,
            sensitive_confidence=1,
            curse_confidence=1,
            analysed=True,
        )
    )
    session.add(
        PromptAnalysis(
            prompt_id=pid,
            conversation_id=f"c-{pid}",
            user_generated=True,
            sentiment="neutral",
            quality_score=5,
            quality_rationale="r",
            category="ask",
            gcse_goal=goal,
            gcse_context=context,
            gcse_source=source,
            gcse_expectation=expectation,
        )
    )


@pytest.mark.asyncio
async def test_team_withheld_when_too_small(session) -> None:
    # Viewer + 4 department peers = 5 people total, i.e. 4 peers besides the
    # viewer — one short of MIN_TEAM_PEERS (5). The team must be withheld.
    assert MIN_TEAM_PEERS == 5
    _add_person(session, "me", department="Eng")
    for i in range(4):
        _add_person(session, f"peer{i}", department="Eng")
    _add_prompt(session, "p-me", "me")
    for i in range(4):
        _add_prompt(session, f"p-peer{i}", f"peer{i}")
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me")
    assert result["team"] is None
    assert result["team_withheld"] == "too_small"
    assert result["team_size"] == 4


@pytest.mark.asyncio
async def test_team_drawn_and_distinct_from_organisation(session) -> None:
    # 5 peers besides the viewer clears MIN_TEAM_PEERS, so a team series is
    # drawn. Peers and an outsider are seeded with different lever scores so
    # the team mean cannot accidentally equal the organisation mean — that
    # equality is exactly the bug this function replaced.
    _add_person(session, "me", department="Eng")
    for i in range(5):
        _add_person(session, f"peer{i}", department="Eng")
    _add_person(session, "outsider", department="Sales")

    _add_prompt(session, "p-me", "me", goal=5, context=5, source=5, expectation=5)
    for i in range(5):
        _add_prompt(
            session, f"p-peer{i}", f"peer{i}",
            goal=9, context=9, source=9, expectation=9,
        )
    # A very different score keeps the org mean far from the team mean.
    _add_prompt(
        session, "p-outsider", "outsider",
        goal=1, context=1, source=1, expectation=1,
    )
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me")
    assert result["team"] is not None
    assert result["team_label"] == "Eng"
    for lever in metrics.GCSE_LEVERS:
        assert result["team"][lever] == 9.0
        # The organisation includes the low-scoring outsider, so its mean is
        # pulled well below the team's — proving these are two real series,
        # not the same average shown twice.
        assert result["organisation"][lever] != result["team"][lever]


@pytest.mark.asyncio
async def test_manager_fallback_when_department_missing(session) -> None:
    # Viewer has no department at all, but shares a manager with 5+ others.
    _add_person(session, "me", department=None, manager_id="mgr1")
    for i in range(5):
        _add_person(session, f"rep{i}", department=None, manager_id="mgr1")
    _add_prompt(session, "p-me", "me")
    for i in range(5):
        _add_prompt(session, f"p-rep{i}", f"rep{i}")
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me")
    assert result["team"] is not None
    assert result["team_label"] == "your manager's team"


@pytest.mark.asyncio
async def test_unknown_team_when_no_department_or_manager(session) -> None:
    # Neither department nor manager: there is nothing to group on at all,
    # which is a different fact from "the group was too small" and the UI
    # needs to tell them apart.
    _add_person(session, "me", department=None, manager_id=None)
    for i in range(5):
        _add_person(session, f"other{i}", department=None, manager_id=None)
    _add_prompt(session, "p-me", "me")
    for i in range(5):
        _add_prompt(session, f"p-other{i}", f"other{i}")
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me")
    assert result["team"] is None
    assert result["team_withheld"] == "unknown_team"


@pytest.mark.asyncio
async def test_organisation_excludes_viewer(session) -> None:
    _add_person(session, "me", department="Eng")
    for i in range(3):
        _add_person(session, f"other{i}", department="Sales")
    _add_prompt(session, "p-me", "me")
    for i in range(3):
        _add_prompt(session, f"p-other{i}", f"other{i}")
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me")
    assert result["organisation_size"] == 3


@pytest.mark.asyncio
async def test_percentile_reflects_extremes_against_organisation(session) -> None:
    # The viewer tops the org on "goal" and bottoms it on "source". The
    # percentile must reflect that asymmetry, not just report some number.
    _add_person(session, "me", department="Eng")
    for i in range(5):
        _add_person(session, f"peer{i}", department="Eng")
    _add_prompt(session, "p-me", "me", goal=10, source=1, context=5, expectation=5)
    for i in range(5):
        _add_prompt(
            session, f"p-peer{i}", f"peer{i}",
            goal=2, source=9, context=5, expectation=5,
        )
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me")
    assert set(result["percentile"].keys()) == set(metrics.GCSE_LEVERS)
    assert result["percentile"]["goal"] == 100  # top of the organisation
    assert result["percentile"]["source"] == 0  # bottom of the organisation


@pytest.mark.asyncio
async def test_period_defaults_to_observed_data_span(session) -> None:
    # With no date filter, the panel must name the actual window the data
    # covers, not leave the caller to guess "the selected period".
    _add_person(session, "me", department="Eng")
    for i in range(5):
        _add_person(session, f"peer{i}", department="Eng")

    def add_on(pid, uid, day):
        session.add(
            Prompt(
                prompt_id=pid,
                user_id=uid,
                conversation_id=f"c-{pid}",
                app_name="Copilot Chat",
                prompt_date=day,
                created_at=datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc),
                prompt_text="hello",
                name_confidence=1,
                sensitive_confidence=1,
                curse_confidence=1,
                analysed=True,
            )
        )
        session.add(
            PromptAnalysis(
                prompt_id=pid,
                conversation_id=f"c-{pid}",
                user_generated=True,
                sentiment="neutral",
                quality_score=5,
                quality_rationale="r",
                category="ask",
                gcse_goal=5,
                gcse_context=5,
                gcse_source=5,
                gcse_expectation=5,
            )
        )

    add_on("p-early", "me", date(2026, 7, 1))
    add_on("p-late", "peer0", date(2026, 8, 15))
    for i in range(1, 5):
        add_on(f"p-mid{i}", f"peer{i}", date(2026, 8, 1))
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me", f=None)
    assert result["period_from"] == date(2026, 7, 1).isoformat()
    assert result["period_to"] == date(2026, 8, 15).isoformat()


@pytest.mark.asyncio
async def test_users_filter_does_not_shrink_the_organisation(session) -> None:
    # A viewer-scoped users=[...] filter must not narrow who counts as "the
    # organisation" — otherwise the comparison population becomes one person.
    _add_person(session, "me", department="Eng")
    for i in range(5):
        _add_person(session, f"peer{i}", department="Eng")
    _add_prompt(session, "p-me", "me")
    for i in range(5):
        _add_prompt(session, f"p-peer{i}", f"peer{i}")
    await session.commit()

    result = await metrics.peer_comparison(
        session, user_id="me", f=PromptFilter(users=["me"])
    )
    assert result["organisation_size"] == 5
    assert result["team"] is not None


@pytest.mark.asyncio
async def test_the_band_is_what_the_lever_scale_can_support(session) -> None:
    """A band as well as the exact percentile, and the band is what the UI shows.

    A lever average out of 10 has nothing like the spread of a prompt count, so
    an exact percentile over it claims precision the figure has not got: on the
    seeded demo directory two people whose averages both display as 4.8 land on
    the 38th and the 43rd percentile, purely because with 21 other people every
    rank step is worth about five points.
    """
    _add_person(session, "me", department="Eng")
    for i in range(6):
        _add_person(session, f"peer{i}", department="Eng")
    _add_prompt(session, "p-me", "me", goal=5, context=5, source=5, expectation=5)
    for i in range(6):
        _add_prompt(
            session,
            f"p-peer{i}",
            f"peer{i}",
            goal=4 + i % 3,
            context=4 + i % 3,
            source=4 + i % 3,
            expectation=4 + i % 3,
        )
    await session.commit()

    result = await metrics.peer_comparison(session, user_id="me")

    for lever in metrics.GCSE_LEVERS:
        pct = result["percentile"][lever]
        band = result["percentile_band"][lever]
        assert (band is None) == (pct is None)
        if pct is not None:
            assert band in {"top quarter", "upper half", "lower half", "bottom quarter"}

    assert metrics._percentile_band(100) == "top quarter"
    assert metrics._percentile_band(75) == "top quarter"
    assert metrics._percentile_band(74) == "upper half"
    assert metrics._percentile_band(50) == "upper half"
    assert metrics._percentile_band(49) == "lower half"
    assert metrics._percentile_band(25) == "lower half"
    assert metrics._percentile_band(24) == "bottom quarter"
    assert metrics._percentile_band(None) is None
