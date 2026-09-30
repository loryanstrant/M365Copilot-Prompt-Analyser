"""The demo data has to exercise the features the demo exists to show.

Two things went wrong before this test existed, and both were invisible from the
code alone:

- Departments were small enough that "How you compare" withheld the team series
  for everybody, so the comparison never appeared on a freshly seeded instance.
  The disclosure rule was right and the data was too thin for it.
- Nothing seeded ``job_runs``, so Scan history was empty — and the in-progress
  indicator, though mapped, had never been rendered anywhere at all.

So this asserts the *seeded* data, not the aggregation: those are covered by
test_peer_comparison.py and test_scan_history.py.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from api import metrics
from scripts.seed_demo import DEMO_PERSONA_USER_ID, clear, seed
from shared.models import JobRun


@pytest.mark.asyncio
async def test_the_bound_persona_gets_a_team_comparison(session) -> None:
    await seed(conversations=140, reset=True)

    result = await metrics.peer_comparison(session, user_id=DEMO_PERSONA_USER_ID)

    # The person the local admin is bound to is the one who will be looked at
    # first, so theirs is the team that must clear the threshold.
    assert result["team"] is not None, (
        "the demo persona's team was withheld — the comparison the demo exists "
        "to show would not appear on a freshly seeded instance"
    )
    assert result["team_size"] >= metrics.MIN_TEAM_PEERS
    assert result["team_label"]
    assert result["organisation_size"] > result["team_size"]
    # Three distinct series, not the same number three times.
    assert result["team"] != result["organisation"]


@pytest.mark.asyncio
async def test_some_teams_are_still_withheld(session) -> None:
    """The withheld state is part of what a demo should show.

    Marketing, People, Technology and Legal are deliberately under the
    threshold: a demo in which every team is comparable would never show the
    disclosure rule working.
    """
    await seed(conversations=140, reset=True)

    withheld = []
    for uid in ("user-08", "user-11", "user-22"):
        result = await metrics.peer_comparison(session, user_id=uid)
        if result["team"] is None:
            withheld.append((uid, result["team_withheld"]))

    assert withheld, "no persona demonstrates a withheld team"
    assert all(reason == "too_small" for _, reason in withheld)


@pytest.mark.asyncio
async def test_scan_history_has_runs_a_failure_and_one_in_progress(session) -> None:
    await seed(conversations=20, reset=True)

    runs = await metrics.scan_history(session, limit=500)
    assert runs, "Scan history would be empty on a freshly seeded instance"

    states = [r["state"] for r in runs]
    assert "succeeded" in states
    # A log where everything always succeeded teaches nobody what a failure
    # looks like, and the in-progress indicator had never been rendered.
    assert "failed" in states
    assert "running" in states

    failed = next(r for r in runs if r["state"] == "failed")
    assert failed["error"], "a failed run has to show why"

    running = next(r for r in runs if r["state"] == "running")
    assert running["finished_at"] is None
    assert running["duration_seconds"] is None

    # The analysis kinds are this repo's own, and an administrator looking for
    # "did the analysis pass run?" needs them labelled rather than raw.
    kinds = {r["raw_kind"] for r in runs}
    assert "scheduled-analysis" in kinds
    labels = {r["kind"] for r in runs}
    assert "Scheduled analysis" in labels
    assert "Historical backfill" in labels

    # Newest first.
    started = [r["started_at"] for r in runs if r["started_at"]]
    assert started == sorted(started, reverse=True)


@pytest.mark.asyncio
async def test_clearing_the_demo_removes_its_runs_only(session) -> None:
    """Clearing demo data must not delete a record of something that really ran."""
    await seed(conversations=10, reset=True)
    session.add(
        JobRun(job_name="scheduled", status="success", stats={"prompts": 5})
    )
    await session.commit()

    await clear()

    rows = (await session.execute(select(JobRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].stats == {"prompts": 5}
