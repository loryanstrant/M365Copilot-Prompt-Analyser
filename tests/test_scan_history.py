"""Tests for ``api.metrics.scan_history`` — the collection/analysis run log.

``job_runs`` has recorded every ingest since the first release and nothing
ever displayed it (docs/specs/comparisons-and-timelines.md). The two things
worth pinning down are the status/kind vocabulary collapse (six raw statuses
become three states; job_name is a per-repo superset, not a tidy enum) and
that an unrecognised job_name still renders rather than vanishing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api import metrics
from shared.models import JobRun


def _run(job_name, status, *, started, finished=None, stats=None, id=None):
    kwargs = dict(
        job_name=job_name,
        status=status,
        started_at=started,
        finished_at=finished,
        stats=stats,
    )
    if id is not None:
        kwargs["id"] = id
    return JobRun(**kwargs)


@pytest.mark.asyncio
async def test_newest_first(session) -> None:
    t0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _run("daily", "success", started=t0),
            _run("daily", "success", started=t0 + timedelta(hours=1)),
            _run("daily", "success", started=t0 + timedelta(hours=2)),
        ]
    )
    await session.commit()

    rows = await metrics.scan_history(session)
    starts = [r["started_at"] for r in rows]
    assert starts == sorted(starts, reverse=True)


@pytest.mark.asyncio
async def test_success_and_completed_are_one_state(session) -> None:
    t0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _run("daily", "success", started=t0),
            _run("scheduled", "completed", started=t0 + timedelta(hours=1)),
        ]
    )
    await session.commit()

    rows = await metrics.scan_history(session)
    states = {r["state"] for r in rows}
    # Two different raw statuses, written by two different modules, but a
    # single display state — the display layer absorbs the discrepancy so
    # the UI is never asked to explain why they differ.
    assert states == {"succeeded"}


@pytest.mark.asyncio
async def test_status_state_mapping(session) -> None:
    t0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _run("daily", "running", started=t0),
            _run("daily", "preparing", started=t0 + timedelta(hours=1)),
            _run("daily", "failed", started=t0 + timedelta(hours=2)),
            _run("daily", "cancelled", started=t0 + timedelta(hours=3)),
        ]
    )
    await session.commit()

    rows = await metrics.scan_history(session)
    by_status = {r["raw_status"]: r["state"] for r in rows}
    assert by_status["running"] == "running"
    assert by_status["preparing"] == "running"
    assert by_status["failed"] == "failed"
    assert by_status["cancelled"] == "cancelled"


@pytest.mark.asyncio
async def test_job_kind_labels_cover_this_repos_kinds(session) -> None:
    t0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    kinds = [
        "daily",
        "scheduled",
        "manual",
        "analysis",
        "scheduled-analysis",
        "manual-analysis",
        "backfill",
    ]
    session.add_all(
        [
            _run(k, "success", started=t0 + timedelta(hours=i))
            for i, k in enumerate(kinds)
        ]
    )
    await session.commit()

    rows = await metrics.scan_history(session)
    labels = {r["raw_kind"]: r["kind"] for r in rows}
    for k in kinds:
        # Every recognised kind must render as the readable label this repo
        # defines, not the raw slug.
        assert labels[k] == metrics.JOB_KIND_LABELS[k]

    # The three analysis kinds are unique to this repo (no sibling app writes
    # them) and must be labelled distinctly from each other.
    assert labels["analysis"] == "Analysis"
    assert labels["scheduled-analysis"] == "Scheduled analysis"
    assert labels["manual-analysis"] == "Manual analysis"


@pytest.mark.asyncio
async def test_unrecognised_job_name_still_renders(session) -> None:
    t0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    session.add(_run("some-future-job", "success", started=t0))
    await session.commit()

    rows = await metrics.scan_history(session)
    # A run that happened and isn't in the label map must still show up,
    # under its raw value, rather than being dropped from the list.
    assert len(rows) == 1
    assert rows[0]["raw_kind"] == "some-future-job"
    assert rows[0]["kind"] == "some-future-job"


@pytest.mark.asyncio
async def test_duration_computed_or_none_when_still_running(session) -> None:
    t0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            _run("daily", "success", started=t0, finished=t0 + timedelta(seconds=90)),
            _run("daily", "running", started=t0 + timedelta(hours=1), finished=None),
        ]
    )
    await session.commit()

    rows = await metrics.scan_history(session)
    by_status = {r["raw_status"]: r for r in rows}
    assert by_status["success"]["duration_seconds"] == 90
    assert by_status["running"]["duration_seconds"] is None


@pytest.mark.asyncio
async def test_error_surfaces_and_is_excluded_from_stats(session) -> None:
    t0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    session.add(
        _run(
            "daily",
            "failed",
            started=t0,
            finished=t0 + timedelta(seconds=5),
            stats={"error": "Graph API 429", "prompts_seen": 12},
        )
    )
    await session.commit()

    rows = await metrics.scan_history(session)
    row = rows[0]
    assert row["error"] == "Graph API 429"
    assert "error" not in row["stats"]
    assert row["stats"]["prompts_seen"] == 12
