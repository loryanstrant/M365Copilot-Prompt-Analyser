"""SQL metrics for the prompt-analysis dashboards.

All aggregation happens here (never in the client), over four tables:
``prompts`` (text + governance confidences), ``prompt_analysis`` (per-prompt
quality / GCSE / sentiment / category), ``conversation_analysis`` (per
conversation) and ``entra_users`` (directory attributes for slicing by person,
department, manager and country). Scores are 1-10; RAG thresholds >=7 / 4-6 / <4.

Everything funnels through one **filtered base** (:func:`_base`) that joins a
prompt to its analysis and (left) to the directory, so every metric slices by
the same dimensions consistently: date range, app, category, user, department,
manager, country, source (user/system-generated), governance flag (name /
sensitive info / profanity) and a quality-score range.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Integer, and_, cast, distinct, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import (
    ConversationAnalysis,
    EntraUser,
    JobRun,
    Prompt,
    PromptAnalysis,
)

GCSE_LEVERS = ("goal", "context", "source", "expectation")
_HIGH_QUALITY = 7
# Below this is the red band the dashboards already use (>=7 / 4-6 / <4).
_LOW_QUALITY = 4
_WELL_GROUNDED = 7
# A confidence >= this counts as "contains a name / sensitive info / profanity".
FLAG_THRESHOLD = 7

# Manager directory alias (self-join on entra_users for the manager's name).
_Mgr = aliased(EntraUser, name="mgr")


def _clean(values: list[str] | None) -> list[str]:
    return [v for v in (values or []) if v not in (None, "")]


def _round(value: Any, digits: int = 1) -> float | None:
    return round(float(value), digits) if value is not None else None


@dataclass
class PromptFilter:
    date_from: date | None = None
    date_to: date | None = None
    apps: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)          # user_ids
    departments: list[str] = field(default_factory=list)
    managers: list[str] = field(default_factory=list)       # manager user_ids
    countries: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)        # "user" | "system"
    flags: list[str] = field(default_factory=list)          # name|sensitive|profanity
    quality_min: int | None = None
    quality_max: int | None = None

    @property
    def needs_user_join(self) -> bool:
        return bool(
            _clean(self.departments)
            or _clean(self.managers)
            or _clean(self.countries)
        )

    def conditions(self) -> list[Any]:
        conds: list[Any] = []
        if self.date_from is not None:
            conds.append(Prompt.prompt_date >= self.date_from)
        if self.date_to is not None:
            conds.append(Prompt.prompt_date <= self.date_to)
        if _clean(self.apps):
            conds.append(Prompt.app_name.in_(_clean(self.apps)))
        if _clean(self.users):
            conds.append(Prompt.user_id.in_(_clean(self.users)))
        if _clean(self.categories):
            conds.append(PromptAnalysis.category.in_(_clean(self.categories)))
        # Source = user-generated vs system-generated.
        srcs = {s.lower() for s in _clean(self.sources)}
        if srcs == {"user"}:
            conds.append(PromptAnalysis.user_generated.is_(True))
        elif srcs == {"system"}:
            conds.append(PromptAnalysis.user_generated.is_(False))
        # Governance flags — a prompt matching ANY selected flag is included.
        flag_map = {
            "name": Prompt.name_confidence,
            "sensitive": Prompt.sensitive_confidence,
            "profanity": Prompt.curse_confidence,
        }
        flag_conds = [
            flag_map[f] >= FLAG_THRESHOLD
            for f in {x.lower() for x in _clean(self.flags)}
            if f in flag_map
        ]
        if flag_conds:
            conds.append(or_(*flag_conds))
        if self.quality_min is not None:
            conds.append(PromptAnalysis.quality_score >= self.quality_min)
        if self.quality_max is not None:
            conds.append(PromptAnalysis.quality_score <= self.quality_max)
        # Directory conditions.
        if _clean(self.departments):
            conds.append(EntraUser.department.in_(_clean(self.departments)))
        if _clean(self.managers):
            conds.append(EntraUser.manager_id.in_(_clean(self.managers)))
        if _clean(self.countries):
            conds.append(EntraUser.country.in_(_clean(self.countries)))
        return conds


def _base(f: PromptFilter):
    """A filtered subquery with every column the metrics need.

    One prompt has exactly one analysis row (1:1 on ``prompt_id``); the directory
    joins are LEFT so unmatched users still appear (as null attributes) unless a
    directory filter is applied.
    """
    q = (
        select(
            Prompt.prompt_id.label("prompt_id"),
            Prompt.user_id.label("user_id"),
            Prompt.conversation_id.label("conversation_id"),
            Prompt.app_name.label("app_name"),
            Prompt.prompt_date.label("prompt_date"),
            Prompt.created_at.label("created_at"),
            Prompt.prompt_text.label("prompt_text"),
            Prompt.name_confidence.label("name_confidence"),
            Prompt.sensitive_confidence.label("sensitive_confidence"),
            Prompt.curse_confidence.label("curse_confidence"),
            PromptAnalysis.user_generated.label("user_generated"),
            PromptAnalysis.sentiment.label("sentiment"),
            PromptAnalysis.quality_score.label("quality_score"),
            PromptAnalysis.quality_rationale.label("quality_rationale"),
            PromptAnalysis.category.label("category"),
            PromptAnalysis.gcse_goal.label("gcse_goal"),
            PromptAnalysis.gcse_context.label("gcse_context"),
            PromptAnalysis.gcse_source.label("gcse_source"),
            PromptAnalysis.gcse_expectation.label("gcse_expectation"),
            EntraUser.display_name.label("user_name"),
            EntraUser.department.label("department"),
            EntraUser.country.label("country"),
            EntraUser.manager_id.label("manager_id"),
            _Mgr.display_name.label("manager_name"),
        )
        .join(PromptAnalysis, PromptAnalysis.prompt_id == Prompt.prompt_id)
        .outerjoin(EntraUser, EntraUser.user_id == Prompt.user_id)
        .outerjoin(_Mgr, _Mgr.user_id == EntraUser.manager_id)
    )
    conds = f.conditions()
    if conds:
        q = q.where(and_(*conds))
    return q.subquery()


# --- scan history --------------------------------------------------------
#
# ``job_runs.job_name`` is not a tidy enum, and the set differs per repo. These
# seven are what *this* code writes: ``daily`` (the ingest default),
# ``scheduled`` and ``manual`` for collections, ``analysis`` /
# ``scheduled-analysis`` / ``manual-analysis`` for the analysis pass nobody else
# in the suite has, and ``backfill``. The rest are the siblings' values, carried
# so a row written under another schema still reads.
#
# An unrecognised kind is shown as its raw value rather than filtered out: a run
# that happened and is not listed is worse than one labelled awkwardly. See
# docs/specs/comparisons-and-timelines.md.
JOB_KIND_LABELS = {
    # This app's own
    "daily": "Scheduled collection",
    "scheduled": "Scheduled collection",
    "manual": "Manual collection",
    "analysis": "Analysis",
    "scheduled-analysis": "Scheduled analysis",
    "manual-analysis": "Manual analysis",
    "backfill": "Historical backfill",
    # The siblings', so their rows read if a database is ever shared
    "users": "User sync",
    "csv-cowork-usage": "Cowork usage import",
    "csv-credit-consumption": "Credit consumption import",
}

# Six status values exist across the suite, and ``success`` and ``completed``
# mean the same thing — they differ only by which module wrote the row. The
# display layer absorbs that; this is the one place the mapping is decided.
JOB_STATUS_STATE = {
    "success": "succeeded",
    "completed": "succeeded",
    "running": "running",
    "preparing": "running",
    "failed": "failed",
    "cancelled": "cancelled",
}


async def scan_history(
    session: AsyncSession, *, limit: int = 100
) -> list[dict[str, Any]]:
    """Every collection and analysis run, newest first.

    ``job_runs`` has recorded this since the first release and nothing ever
    displayed it, so "did last night's pull actually work?" had no answer in
    the UI.
    """
    rows = (
        await session.execute(
            select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)
        )
    ).scalars().all()

    out: list[dict[str, Any]] = []
    for r in rows:
        stats = r.stats if isinstance(r.stats, dict) else {}
        duration = None
        if r.started_at and r.finished_at:
            duration = max(0, int((r.finished_at - r.started_at).total_seconds()))
        out.append(
            {
                "id": r.id,
                "kind": JOB_KIND_LABELS.get(r.job_name, r.job_name),
                "raw_kind": r.job_name,
                "state": JOB_STATUS_STATE.get(r.status, r.status),
                "raw_status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "duration_seconds": duration,
                # The error lives in stats on a failed run; surfacing it is the
                # difference between a log people can act on and one they cannot.
                "error": stats.get("error"),
                "stats": {k: v for k, v in stats.items() if k != "error"},
            }
        )
    return out


# --- filter options ------------------------------------------------------
async def filter_options(session: AsyncSession) -> dict[str, Any]:
    """Distinct slicer values, scoped to users/apps that actually have data."""
    apps = (
        await session.execute(
            select(distinct(Prompt.app_name)).where(Prompt.app_name.is_not(None))
        )
    ).scalars().all()
    cats = (
        await session.execute(
            select(distinct(PromptAnalysis.category)).where(
                PromptAnalysis.category.is_not(None)
            )
        )
    ).scalars().all()
    # People with prompt data (for the user filter + person picker).
    people_rows = (
        await session.execute(
            select(
                Prompt.user_id,
                func.max(EntraUser.display_name),
                func.max(EntraUser.department),
                func.count().label("n"),
            )
            .outerjoin(EntraUser, EntraUser.user_id == Prompt.user_id)
            .group_by(Prompt.user_id)
            .order_by(func.count().desc())
        )
    ).all()
    users = [
        {"id": uid, "name": name or uid, "department": dept, "prompts": n}
        for uid, name, dept, n in people_rows
    ]
    # Departments / countries present among users who have data.
    user_ids = [u["id"] for u in users]
    departments: list[str] = []
    countries: list[str] = []
    managers: list[dict[str, str]] = []
    if user_ids:
        departments = sorted(
            d for (d,) in (
                await session.execute(
                    select(distinct(EntraUser.department)).where(
                        EntraUser.user_id.in_(user_ids),
                        EntraUser.department.is_not(None),
                    )
                )
            ).all() if d
        )
        countries = sorted(
            c for (c,) in (
                await session.execute(
                    select(distinct(EntraUser.country)).where(
                        EntraUser.user_id.in_(user_ids),
                        EntraUser.country.is_not(None),
                    )
                )
            ).all() if c
        )
        mgr_rows = (
            await session.execute(
                select(distinct(EntraUser.manager_id), _Mgr.display_name)
                .outerjoin(_Mgr, _Mgr.user_id == EntraUser.manager_id)
                .where(
                    EntraUser.user_id.in_(user_ids),
                    EntraUser.manager_id.is_not(None),
                )
            )
        ).all()
        managers = [
            {"id": mid, "name": name or mid} for mid, name in mgr_rows if mid
        ]
    return {
        "apps": sorted(a for a in apps if a),
        "categories": sorted(c for c in cats if c),
        "sources": ["user", "system"],
        "flags": ["name", "sensitive", "profanity"],
        "users": users,
        "departments": departments,
        "countries": countries,
        "managers": managers,
    }


async def people(session: AsyncSession) -> list[dict[str, Any]]:
    """Users who have prompt data, with directory attributes (person picker)."""
    rows = (
        await session.execute(
            select(
                Prompt.user_id,
                func.max(EntraUser.display_name),
                func.max(EntraUser.department),
                func.max(EntraUser.country),
                func.max(_Mgr.display_name),
                func.count().label("n"),
            )
            .outerjoin(EntraUser, EntraUser.user_id == Prompt.user_id)
            .outerjoin(_Mgr, _Mgr.user_id == EntraUser.manager_id)
            .group_by(Prompt.user_id)
            .order_by(func.count().desc())
        )
    ).all()
    return [
        {
            "user_id": uid,
            "name": name or uid,
            "department": dept,
            "country": country,
            "manager": manager,
            "prompts": n,
        }
        for uid, name, dept, country, manager, n in rows
    ]


async def directory_users(session: AsyncSession) -> list[dict[str, Any]]:
    """The imported tenant directory, with each person's prompt count.

    Distinct from :func:`people`, which lists only those who have prompt data
    because it drives the person picker. This one starts from the directory, so
    somebody with a licence and no activity still appears — that is the row this
    list actually gets opened to find, and dropping it would answer the opposite
    of the question.

    Ordered by name so the page opens on something readable. Manager is resolved
    to a name: manager_id is a GUID, and a directory listing showing GUIDs is no
    use to anyone reading it.
    """
    prompts = (
        select(Prompt.user_id, func.count().label("prompts"))
        .group_by(Prompt.user_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(
                EntraUser,
                func.coalesce(prompts.c.prompts, 0).label("prompts"),
                _Mgr.display_name.label("manager_name"),
            )
            .outerjoin(prompts, prompts.c.user_id == EntraUser.user_id)
            .outerjoin(_Mgr, _Mgr.user_id == EntraUser.manager_id)
            .order_by(EntraUser.display_name)
        )
    ).all()
    return [
        {
            "user_id": u.user_id,
            "user_principal_name": u.upn,
            "display_name": u.display_name,
            "job_title": u.job_title,
            "department": u.department,
            "company_name": u.company_name,
            "office_location": u.office_location,
            "country": u.country,
            "manager_name": manager_name,
            "user_type": u.user_type,
            "has_copilot_license": bool(u.has_copilot_license),
            "prompts": int(prompt_count or 0),
        }
        for u, prompt_count, manager_name in rows
    ]


# --- headline summary ----------------------------------------------------
async def summary(session: AsyncSession, *, f: PromptFilter) -> dict[str, Any]:
    b = _base(f)

    prompts_analysed = await session.scalar(select(func.count()).select_from(b)) or 0
    conversations = await session.scalar(
        select(func.count(distinct(b.c.conversation_id)))
    ) or 0
    avg_quality = await session.scalar(select(func.avg(b.c.quality_score)))
    high_quality = await session.scalar(
        select(func.count()).select_from(b).where(b.c.quality_score >= _HIGH_QUALITY)
    ) or 0
    user_generated = await session.scalar(
        select(func.count()).select_from(b).where(b.c.user_generated.is_(True))
    ) or 0
    well_grounded = await session.scalar(
        select(func.count()).select_from(b).where(b.c.gcse_source >= _WELL_GROUNDED)
    ) or 0
    avg_name = await session.scalar(select(func.avg(b.c.name_confidence)))
    avg_sensitive = await session.scalar(select(func.avg(b.c.sensitive_confidence)))
    flagged_name = await session.scalar(
        select(func.count()).select_from(b).where(b.c.name_confidence >= FLAG_THRESHOLD)
    ) or 0
    flagged_sensitive = await session.scalar(
        select(func.count()).select_from(b).where(
            b.c.sensitive_confidence >= FLAG_THRESHOLD
        )
    ) or 0
    flagged_profanity = await session.scalar(
        select(func.count()).select_from(b).where(
            b.c.curse_confidence >= FLAG_THRESHOLD
        )
    ) or 0

    gcse = {
        lever: await session.scalar(select(func.avg(getattr(b.c, f"gcse_{lever}"))))
        for lever in GCSE_LEVERS
    }
    known = {k: v for k, v in gcse.items() if v is not None}
    weakest = min(known, key=known.get) if known else None

    # Conversation-level sentiment mix (over the conversations in scope).
    conv_ids = select(distinct(b.c.conversation_id)).scalar_subquery()
    conv_rows = (
        await session.execute(
            select(ConversationAnalysis.sentiment, func.count())
            .where(ConversationAnalysis.conversation_id.in_(conv_ids))
            .group_by(ConversationAnalysis.sentiment)
        )
    ).all()
    conv_total = sum(c for _, c in conv_rows) or 0
    neutral = sum(c for s, c in conv_rows if (s or "").lower() == "neutral")
    positive = sum(c for s, c in conv_rows if (s or "").lower() == "positive")
    avg_conv_quality = await session.scalar(
        select(func.avg(ConversationAnalysis.conversation_quality_score)).where(
            ConversationAnalysis.conversation_id.in_(conv_ids)
        )
    )

    def pct(n: int, d: int) -> float:
        return round(100.0 * n / d, 1) if d else 0.0

    return {
        "prompts": prompts_analysed,
        "conversations": conversations,
        "avg_prompt_quality": _round(avg_quality),
        "avg_conversation_quality": _round(avg_conv_quality),
        "pct_high_quality": pct(high_quality, prompts_analysed),
        "user_generated_pct": pct(user_generated, prompts_analysed),
        "pct_well_grounded": pct(well_grounded, prompts_analysed),
        "pct_neutral_conversations": pct(neutral, conv_total),
        "pct_positive_conversations": pct(positive, conv_total),
        "gcse": {k: _round(v) for k, v in gcse.items()},
        "weakest_gcse_lever": weakest,
        "avg_name_confidence": _round(avg_name),
        "avg_sensitive_confidence": _round(avg_sensitive),
        "flagged_name": flagged_name,
        "flagged_sensitive": flagged_sensitive,
        "flagged_profanity": flagged_profanity,
    }


# --- distributions -------------------------------------------------------
async def quality_distribution(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    b = _base(f)
    rows = (
        await session.execute(
            select(b.c.quality_score, func.count())
            .group_by(b.c.quality_score)
            .order_by(b.c.quality_score)
        )
    ).all()
    counts = {int(s): c for s, c in rows if s is not None}
    return [{"score": i, "count": counts.get(i, 0)} for i in range(1, 11)]


async def conversation_quality_distribution(
    session: AsyncSession, *, f: PromptFilter
) -> list[dict]:
    b = _base(f)
    conv_ids = select(distinct(b.c.conversation_id)).scalar_subquery()
    rows = (
        await session.execute(
            select(ConversationAnalysis.conversation_quality_score, func.count())
            .where(ConversationAnalysis.conversation_id.in_(conv_ids))
            .group_by(ConversationAnalysis.conversation_quality_score)
        )
    ).all()
    counts = {int(s): c for s, c in rows if s is not None}
    return [{"score": i, "count": counts.get(i, 0)} for i in range(1, 11)]


async def category_mix(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    b = _base(f)
    rows = (
        await session.execute(
            select(b.c.category, func.count())
            .group_by(b.c.category)
            .order_by(func.count().desc())
        )
    ).all()
    return [{"name": c or "Unknown", "count": n} for c, n in rows]


async def sentiment_mix(session: AsyncSession, *, f: PromptFilter) -> dict[str, list]:
    b = _base(f)
    prompt_rows = (
        await session.execute(
            select(b.c.sentiment, func.count()).group_by(b.c.sentiment)
        )
    ).all()
    conv_ids = select(distinct(b.c.conversation_id)).scalar_subquery()
    conv_rows = (
        await session.execute(
            select(ConversationAnalysis.sentiment, func.count())
            .where(ConversationAnalysis.conversation_id.in_(conv_ids))
            .group_by(ConversationAnalysis.sentiment)
        )
    ).all()
    return {
        "prompt": [{"name": s or "Unknown", "count": n} for s, n in prompt_rows],
        "conversation": [{"name": s or "Unknown", "count": n} for s, n in conv_rows],
    }


# --- by app / intent / user ---------------------------------------------
async def by_app(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    b = _base(f)
    rows = (
        await session.execute(
            select(b.c.app_name, func.count(), func.avg(b.c.quality_score))
            .group_by(b.c.app_name)
            .order_by(func.count().desc())
        )
    ).all()
    return [
        {"app": a or "Unknown", "prompts": n, "avg_quality": _round(q)}
        for a, n, q in rows
    ]


async def by_intent(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    b = _base(f)
    rows = (
        await session.execute(
            select(b.c.category, func.count(), func.avg(b.c.quality_score))
            .group_by(b.c.category)
            .order_by(func.count().desc())
        )
    ).all()
    return [
        {"category": c or "Unknown", "prompts": n, "avg_quality": _round(q)}
        for c, n, q in rows
    ]


async def by_user(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    """Per-user rollup — prompts, avg quality, user-gen %, department."""
    b = _base(f)
    rows = (
        await session.execute(
            select(
                b.c.user_id,
                func.max(b.c.user_name),
                func.max(b.c.department),
                func.count(),
                func.avg(b.c.quality_score),
                func.sum(cast(b.c.user_generated, Integer)),
                func.count(distinct(b.c.conversation_id)),
            )
            .group_by(b.c.user_id)
            .order_by(func.count().desc())
        )
    ).all()
    out = []
    for uid, name, dept, n, avgq, ug, convs in rows:
        out.append(
            {
                "user_id": uid,
                "name": name or uid,
                "department": dept,
                "prompts": n,
                "conversations": convs,
                "avg_quality": _round(avgq),
                "user_generated_pct": round(100.0 * (ug or 0) / n, 1) if n else 0.0,
            }
        )
    return out


async def gcse_by_intent(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    b = _base(f)
    rows = (
        await session.execute(
            select(
                b.c.category,
                func.avg(b.c.gcse_goal),
                func.avg(b.c.gcse_context),
                func.avg(b.c.gcse_source),
                func.avg(b.c.gcse_expectation),
            ).group_by(b.c.category)
        )
    ).all()
    return [
        {
            "category": c or "Unknown",
            "goal": _round(g),
            "context": _round(ctx),
            "source": _round(s),
            "expectation": _round(e),
        }
        for c, g, ctx, s, e in rows
    ]


# --- governance ----------------------------------------------------------
async def governance(session: AsyncSession, *, f: PromptFilter) -> dict[str, list]:
    b = _base(f)

    async def dist(col) -> list[dict]:
        rows = (
            await session.execute(
                select(col, func.count()).where(col.is_not(None)).group_by(col)
            )
        ).all()
        counts = {int(s): c for s, c in rows}
        return [{"score": i, "count": counts.get(i, 0)} for i in range(1, 11)]

    return {
        "name_confidence": await dist(b.c.name_confidence),
        "sensitive_confidence": await dist(b.c.sensitive_confidence),
        "curse_confidence": await dist(b.c.curse_confidence),
    }


# --- tables --------------------------------------------------------------
def _prompt_row(r: Any) -> dict[str, Any]:
    return {
        "prompt_id": r.prompt_id,
        "prompt_text": r.prompt_text,
        "app": r.app_name,
        "date": r.prompt_date.isoformat() if r.prompt_date else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "user_id": r.user_id,
        "user_name": r.user_name,
        "department": r.department,
        "category": r.category,
        "sentiment": r.sentiment,
        "source": "User" if r.user_generated else "System",
        "user_generated": r.user_generated,
        "quality_score": r.quality_score,
        "quality_rationale": r.quality_rationale,
        "gcse_goal": r.gcse_goal,
        "gcse_context": r.gcse_context,
        "gcse_source": r.gcse_source,
        "gcse_expectation": r.gcse_expectation,
        "name_confidence": r.name_confidence,
        "sensitive_confidence": r.sensitive_confidence,
        "curse_confidence": r.curse_confidence,
    }


async def prompts_table(
    session: AsyncSession,
    *,
    f: PromptFilter,
    limit: int = 500,
    offset: int = 0,
    search: str | None = None,
) -> list[dict]:
    b = _base(f)
    q = select(b)
    if search:
        q = q.where(b.c.prompt_text.ilike(f"%{search}%"))
    q = q.order_by(b.c.quality_score.desc().nullslast()).limit(limit).offset(offset)
    rows = (await session.execute(q)).all()
    return [_prompt_row(r) for r in rows]


async def conversations_table(
    session: AsyncSession, *, f: PromptFilter, limit: int = 500
) -> list[dict]:
    """Per-conversation rows: avg-of-prompts (from base) + overall (from ca)."""
    b = _base(f)
    agg = (
        select(
            b.c.conversation_id.label("conversation_id"),
            func.max(b.c.user_id).label("user_id"),
            func.max(b.c.user_name).label("user_name"),
            func.max(b.c.department).label("department"),
            func.count().label("prompt_count"),
            func.avg(b.c.quality_score).label("avg_prompt_quality"),
            func.avg(b.c.name_confidence).label("avg_name"),
            func.avg(b.c.sensitive_confidence).label("avg_sensitive"),
            func.max(b.c.curse_confidence).label("max_curse"),
        )
        .where(b.c.conversation_id.is_not(None))
        .group_by(b.c.conversation_id)
        .subquery()
    )
    ca = ConversationAnalysis
    rows = (
        await session.execute(
            select(
                agg.c.conversation_id,
                agg.c.user_id,
                agg.c.user_name,
                agg.c.department,
                agg.c.prompt_count,
                agg.c.avg_prompt_quality,
                agg.c.avg_name,
                agg.c.avg_sensitive,
                agg.c.max_curse,
                ca.conversation_quality_score,
                ca.sentiment,
                ca.category,
                ca.user_generated_ratio,
                ca.theme,
                ca.insight,
                ca.improvement,
                ca.suggested_starter_prompt,
            )
            .outerjoin(ca, ca.conversation_id == agg.c.conversation_id)
            .order_by(ca.conversation_quality_score.desc().nullslast())
            .limit(limit)
        )
    ).all()
    out = []
    for r in rows:
        out.append(
            {
                "conversation_id": r.conversation_id,
                "user_id": r.user_id,
                "user_name": r.user_name,
                "department": r.department,
                "prompt_count": r.prompt_count,
                "avg_prompt_quality": _round(r.avg_prompt_quality),
                "avg_name_confidence": _round(r.avg_name),
                "avg_sensitive_confidence": _round(r.avg_sensitive),
                "max_curse_confidence": r.max_curse,
                "conversation_quality_score": r.conversation_quality_score,
                "sentiment": r.sentiment,
                "category": r.category,
                "user_generated_ratio": _round(r.user_generated_ratio),
                "theme": r.theme,
                "insight": r.insight,
                "improvement": r.improvement,
                "suggested_starter_prompt": r.suggested_starter_prompt,
            }
        )
    return out


async def conversation_detail(session: AsyncSession, conversation_id: str) -> dict:
    conv = await session.get(ConversationAnalysis, conversation_id)
    # Ordered prompt thread (chronological) with full per-prompt detail.
    rows = (
        await session.execute(
            select(
                Prompt.prompt_id,
                Prompt.prompt_text,
                Prompt.prompt_date,
                Prompt.created_at,
                Prompt.app_name,
                Prompt.name_confidence,
                Prompt.sensitive_confidence,
                Prompt.curse_confidence,
                PromptAnalysis.category,
                PromptAnalysis.sentiment,
                PromptAnalysis.user_generated,
                PromptAnalysis.quality_score,
                PromptAnalysis.quality_rationale,
                PromptAnalysis.gcse_goal,
                PromptAnalysis.gcse_context,
                PromptAnalysis.gcse_source,
                PromptAnalysis.gcse_expectation,
            )
            .join(PromptAnalysis, PromptAnalysis.prompt_id == Prompt.prompt_id)
            .where(Prompt.conversation_id == conversation_id)
            .order_by(Prompt.created_at.nullslast(), Prompt.prompt_id)
        )
    ).all()
    prompts = [
        {
            "prompt_id": r.prompt_id,
            "prompt_text": r.prompt_text,
            "date": r.prompt_date.isoformat() if r.prompt_date else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "app": r.app_name,
            "category": r.category,
            "sentiment": r.sentiment,
            "source": "User" if r.user_generated else "System",
            "user_generated": r.user_generated,
            "quality_score": r.quality_score,
            "quality_rationale": r.quality_rationale,
            "gcse_goal": r.gcse_goal,
            "gcse_context": r.gcse_context,
            "gcse_source": r.gcse_source,
            "gcse_expectation": r.gcse_expectation,
            "name_confidence": r.name_confidence,
            "sensitive_confidence": r.sensitive_confidence,
            "curse_confidence": r.curse_confidence,
        }
        for r in rows
    ]
    scored = [p["quality_score"] for p in prompts if p["quality_score"] is not None]
    avg_of_prompts = round(sum(scored) / len(scored), 1) if scored else None
    # Owner of the conversation (from its prompts).
    owner = await session.scalar(
        select(EntraUser.display_name)
        .join(Prompt, Prompt.user_id == EntraUser.user_id)
        .where(Prompt.conversation_id == conversation_id)
        .limit(1)
    )
    return {
        "conversation": (
            {
                "conversation_id": conv.conversation_id,
                "sentiment": conv.sentiment,
                "avg_quality_score": _round(conv.avg_quality_score),
                "avg_of_prompts": avg_of_prompts,
                "conversation_quality_score": conv.conversation_quality_score,
                "user_generated_ratio": _round(conv.user_generated_ratio),
                "theme": conv.theme,
                "insight": conv.insight,
                "category": conv.category,
                "improvement": conv.improvement,
                "suggested_starter_prompt": conv.suggested_starter_prompt,
                "prompt_count": conv.prompt_count,
                "user_name": owner,
            }
            if conv
            else {"avg_of_prompts": avg_of_prompts, "user_name": owner}
        ),
        "prompts": prompts,
    }


# --- executive briefing --------------------------------------------------
async def daily(session: AsyncSession, *, f: PromptFilter) -> list[dict[str, Any]]:
    """Prompts and conversations per day, oldest first.

    The first time-bucketed query in this app: everything else here aggregates
    over the whole filtered set. ``prompts.prompt_date`` is already indexed, and
    it is a DATE rather than a timestamp, so the grouping needs no truncation and
    no timezone argument — the day is whatever Graph called the day.
    """
    b = _base(f)
    rows = (
        await session.execute(
            select(
                b.c.prompt_date,
                func.count().label("prompts"),
                func.count(distinct(b.c.conversation_id)).label("conversations"),
            )
            .where(b.c.prompt_date.is_not(None))
            .group_by(b.c.prompt_date)
            .order_by(b.c.prompt_date)
        )
    ).all()
    return [
        {"date": d.isoformat(), "prompts": int(p), "conversations": int(c)}
        for d, p, c in rows
    ]


async def briefing(
    session: AsyncSession, *, today: date | None = None, window_days: int = 30
) -> dict[str, Any]:
    """An executive snapshot: this period against the one before it.

    Deliberately deterministic — pure SQL here, and prose assembled in the
    browser from fixed thresholds. This app has Azure OpenAI configured and
    still does not use it for the briefing: a narrated summary read out in front
    of a customer must never contain a number the app invented.

    Everything is a plain window over ``prompt_date`` rather than the shared
    filter set, because a briefing that silently inherited somebody's saved
    slicers would be quoting a subset while claiming to describe the
    organisation.
    """
    today = today or date.today()
    cur_start = today - timedelta(days=window_days)
    prev_start = today - timedelta(days=2 * window_days)

    async def _period(lo: date, hi: date | None) -> dict[str, Any]:
        conds: list[Any] = [Prompt.prompt_date >= lo]
        if hi is not None:
            conds.append(Prompt.prompt_date < hi)
        joined = (
            select(
                Prompt.prompt_id,
                Prompt.user_id,
                Prompt.conversation_id,
                PromptAnalysis.quality_score,
                PromptAnalysis.user_generated,
            )
            .join(PromptAnalysis, PromptAnalysis.prompt_id == Prompt.prompt_id)
            .where(*conds)
            .subquery()
        )
        prompts = await session.scalar(select(func.count()).select_from(joined)) or 0
        conversations = (
            await session.scalar(
                select(func.count(distinct(joined.c.conversation_id)))
            )
            or 0
        )
        people = (
            await session.scalar(select(func.count(distinct(joined.c.user_id)))) or 0
        )
        avg_quality = await session.scalar(select(func.avg(joined.c.quality_score)))
        user_gen = (
            await session.scalar(
                select(func.count())
                .select_from(joined)
                .where(joined.c.user_generated.is_(True))
            )
            or 0
        )
        return {
            "prompts": int(prompts),
            "conversations": int(conversations),
            "people": int(people),
            "avg_quality": _round(avg_quality),
            "user_generated_pct": (
                round(100.0 * int(user_gen) / int(prompts), 1) if prompts else 0.0
            ),
        }

    current = await _period(cur_start, None)
    previous = await _period(prev_start, cur_start)

    cur = PromptFilter(date_from=cur_start)
    prev = PromptFilter(date_from=prev_start, date_to=cur_start - timedelta(days=1))

    async def _intents(f: PromptFilter) -> dict[str, tuple[int, float | None]]:
        b = _base(f)
        rows = (
            await session.execute(
                select(b.c.category, func.count(), func.avg(b.c.quality_score))
                .group_by(b.c.category)
            )
        ).all()
        return {(c or "Unknown"): (int(n), _round(q)) for c, n, q in rows}

    cur_intents = await _intents(cur)
    prev_intents = await _intents(prev)
    top_intents = [
        {
            "name": name,
            "prompts": count,
            "prev_prompts": prev_intents.get(name, (0, None))[0],
            "avg_quality": quality,
        }
        for name, (count, quality) in sorted(
            cur_intents.items(), key=lambda kv: kv[1][0], reverse=True
        )[:5]
    ]

    # Conversation themes, not prompt categories again. The category on a prompt
    # is what somebody asked Copilot to do; the theme on a conversation is what
    # the work was about, which is the one an executive recognises.
    cur_conv_ids = select(distinct(_base(cur).c.conversation_id)).scalar_subquery()
    theme_rows = (
        await session.execute(
            select(ConversationAnalysis.theme, func.count())
            .where(
                ConversationAnalysis.conversation_id.in_(cur_conv_ids),
                ConversationAnalysis.theme.is_not(None),
            )
            .group_by(ConversationAnalysis.theme)
            .order_by(func.count().desc())
            .limit(5)
        )
    ).all()
    top_themes = [{"name": t, "conversations": int(n)} for t, n in theme_rows]

    # Coaching watch-outs. The weakest lever across the organisation says where
    # enablement would pay; the count of people below the low-quality threshold
    # says how many would feel it.
    b_cur = _base(cur)
    levers = []
    for lever in GCSE_LEVERS:
        avg = await session.scalar(select(func.avg(getattr(b_cur.c, f"gcse_{lever}"))))
        if avg is not None:
            levers.append({"lever": lever, "score": _round(avg)})
    levers.sort(key=lambda r: r["score"])

    low_quality = (
        await session.scalar(
            select(func.count())
            .select_from(b_cur)
            .where(b_cur.c.quality_score < _LOW_QUALITY)
        )
        or 0
    )
    per_user = (
        select(b_cur.c.user_id, func.avg(b_cur.c.quality_score).label("avg_q"))
        .group_by(b_cur.c.user_id)
        .subquery()
    )
    people_needing_coaching = (
        await session.scalar(
            select(func.count())
            .select_from(per_user)
            .where(per_user.c.avg_q < _LOW_QUALITY)
        )
        or 0
    )

    total_prompts = await session.scalar(select(func.count()).select_from(Prompt)) or 0

    return {
        "window_days": window_days,
        "period_start": cur_start.isoformat(),
        "period_end": today.isoformat(),
        "previous_period_start": prev_start.isoformat(),
        "current": current,
        "previous": previous,
        "total_prompts": int(total_prompts),
        "top_intents": top_intents,
        "top_themes": top_themes,
        "levers": levers,
        "low_quality_prompts": int(low_quality),
        "people_needing_coaching": int(people_needing_coaching),
    }


# --- how you compare -----------------------------------------------------
#
# A team series is only drawn when the grouping holds at least this many people
# besides the viewer. Below it, the team average plus the viewer's own figure
# gives away an individual's number — at two people exactly, and at three or
# four closely enough to matter. This is a disclosure rule, not a presentation
# preference, so it does not vary by data source. See
# docs/specs/comparisons-and-timelines.md.
MIN_TEAM_PEERS = 5


def _percentile(value: float | None, population: list[float]) -> int | None:
    """Where ``value`` sits in ``population``, 0-100. None when nothing to rank against.

    Always measured against the organisation, never the team: in a team of four
    a team-relative percentile says more about the size of the team than about
    the person, and the panel says which population it used.
    """
    if value is None or not population:
        return None
    at_or_below = sum(1 for v in population if v <= value)
    return round(100.0 * at_or_below / len(population))


# A lever average out of 10 has nothing like the spread of a prompt count, so an
# exact percentile over it claims precision the figure does not have: on the
# seeded demo directory, two people whose averages both display as 4.8 (0.009
# apart in truth) land on the 38th and 43rd percentile, because with 21 other
# people every rank step is worth about five points. A band is what the data
# actually supports, and it still names the population it was measured against.
def _percentile_band(pct: int | None) -> str | None:
    if pct is None:
        return None
    if pct >= 75:
        return "top quarter"
    if pct >= 50:
        return "upper half"
    if pct >= 25:
        return "lower half"
    return "bottom quarter"


async def peer_comparison(
    session: AsyncSession, *, user_id: str, f: PromptFilter | None = None
) -> dict[str, Any]:
    """This person, their team and the organisation, on the four GCSE levers.

    Returns aggregates only — a mean per group, never a list of people. The team
    is the viewer's department, falling back to everyone who shares their
    manager, and it is **omitted entirely** below :data:`MIN_TEAM_PEERS` rather
    than drawn from a group small enough to identify somebody.

    All three series come from one pass over the same filtered window, so they
    cannot silently disagree about which period they describe. What replaced the
    original ``avg(gcse_lever)`` with no filter at all, which was the whole
    tenant wearing a "Team average" label.
    """
    f = f or PromptFilter()
    # The viewer's own ``users`` filter must not narrow the population they are
    # being compared against, or "the organisation" would be one person.
    org_f = replace(f, users=[])
    b = _base(org_f)

    lever_cols = [
        func.avg(getattr(b.c, f"gcse_{lever}")).label(lever) for lever in GCSE_LEVERS
    ]
    rows = (
        await session.execute(
            select(b.c.user_id, b.c.department, b.c.manager_id, *lever_cols).group_by(
                b.c.user_id, b.c.department, b.c.manager_id
            )
        )
    ).all()

    def levers_of(row: Any) -> dict[str, float | None]:
        return {lever: _round(getattr(row, lever)) for lever in GCSE_LEVERS}

    me = next((r for r in rows if r.user_id == user_id), None)
    others = [r for r in rows if r.user_id != user_id]

    # Who counts as "my team". Department first, because that is what people
    # mean; the manager group only as a fallback for tenants that leave
    # department empty.
    peers: list[Any] = []
    team_label: str | None = None
    grouping_known = False
    if me is not None:
        dept = (me.department or "").strip()
        if dept:
            grouping_known = True
            peers = [r for r in others if (r.department or "").strip() == dept]
            team_label = dept
        if len(peers) < MIN_TEAM_PEERS and me.manager_id:
            grouping_known = True
            mgr_peers = [r for r in others if r.manager_id == me.manager_id]
            if len(mgr_peers) > len(peers):
                peers = mgr_peers
                team_label = "your manager's team"

    def mean(values: list[float]) -> float | None:
        return _round(sum(values) / len(values)) if values else None

    def group_levers(group: list[Any]) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for lever in GCSE_LEVERS:
            vals = [
                float(getattr(r, lever))
                for r in group
                if getattr(r, lever) is not None
            ]
            out[lever] = mean(vals)
        return out

    mine = levers_of(me) if me is not None else {k: None for k in GCSE_LEVERS}
    # Ranked on the unrounded average, against unrounded averages. Ranking a
    # value rounded to one decimal against a population that is not rounded puts
    # somebody on 4.84 behind everybody on 4.81, which is backwards.
    mine_raw = {
        lever: (
            float(getattr(me, lever))
            if me is not None and getattr(me, lever) is not None
            else None
        )
        for lever in GCSE_LEVERS
    }

    # The window every series was computed over, so the panel can name it. With
    # no date filter the honest answer is not "the selected period" — it is the
    # span the data actually covers, so that is looked up rather than left for
    # the UI to paper over.
    period_from, period_to = f.date_from, f.date_to
    if period_from is None or period_to is None:
        observed = (
            await session.execute(
                select(func.min(b.c.prompt_date), func.max(b.c.prompt_date))
            )
        ).one_or_none()
        if observed:
            period_from = period_from or observed[0]
            period_to = period_to or observed[1]

    percentile = {
        lever: _percentile(
            mine_raw[lever],
            [float(getattr(r, lever)) for r in others if getattr(r, lever) is not None],
        )
        for lever in GCSE_LEVERS
    }

    result: dict[str, Any] = {
        "period_from": period_from.isoformat() if period_from else None,
        "period_to": period_to.isoformat() if period_to else None,
        "mine": mine,
        "organisation": group_levers(others),
        "organisation_size": len(others),
        # Per lever, and against the organisation — stated in the UI, because a
        # percentile without its population is a number pretending to be a fact.
        # Kept in the payload because it is the honest underlying number; the UI
        # shows the band, which is the precision it can defend.
        "percentile": percentile,
        "percentile_band": {
            lever: _percentile_band(percentile[lever]) for lever in GCSE_LEVERS
        },
        "team": None,
        "team_label": None,
        "team_size": len(peers),
        # Why the team series is missing, so the UI can distinguish "your team is
        # too small to show" from "we don't know which team you're in". Those are
        # different facts and an empty bar tells neither.
        "team_withheld": None,
        "min_team_peers": MIN_TEAM_PEERS,
    }

    if len(peers) >= MIN_TEAM_PEERS:
        result["team"] = group_levers(peers)
        result["team_label"] = team_label
    else:
        result["team_withheld"] = "too_small" if grouping_known else "unknown_team"
    return result


# --- personal coaching (per user) ---------------------------------------
async def personal(session: AsyncSession, user_id: str) -> dict:
    """Everything one person would see: their stats, how they compare, and focus."""
    f = PromptFilter(users=[user_id])
    b = _base(f)

    total = await session.scalar(select(func.count()).select_from(b)) or 0
    avg_quality = await session.scalar(select(func.avg(b.c.quality_score)))
    user_gen = await session.scalar(
        select(func.count()).select_from(b).where(b.c.user_generated.is_(True))
    ) or 0
    conversations = await session.scalar(
        select(func.count(distinct(b.c.conversation_id)))
    ) or 0
    # Days this person actually prompted on, and the organisation's average
    # quality: both exist so the stat tiles can say something ("across 11 days",
    # "above the organisation average") instead of restating their own labels.
    active_days = await session.scalar(
        select(func.count(distinct(b.c.prompt_date)))
    ) or 0
    org_avg_quality = await session.scalar(select(func.avg(PromptAnalysis.quality_score)))

    mine: dict[str, float | None] = {}
    for lever in GCSE_LEVERS:
        mine[lever] = _round(
            await session.scalar(
                select(func.avg(getattr(b.c, f"gcse_{lever}")))
            )
        )

    # You / your team / your organisation, from one pass. The team is a real
    # team here — it used to be the whole tenant with a "Team average" label.
    comparison = await peer_comparison(session, user_id=user_id)

    known = {k: v for k, v in mine.items() if v is not None}
    weakest = min(known, key=known.get) if known else None
    strongest = max(known, key=known.get) if known else None

    profile = await session.scalar(
        select(EntraUser.display_name).where(EntraUser.user_id == user_id)
    )
    return {
        "user_id": user_id,
        "name": profile or user_id,
        "prompts": total,
        "conversations": conversations,
        "avg_quality": _round(avg_quality),
        "org_avg_quality": _round(org_avg_quality),
        "active_days": active_days,
        "user_generated_prompts": user_gen,
        "user_generated_pct": round(100.0 * user_gen / total, 1) if total else 0.0,
        "gcse_mine": mine,
        "comparison": comparison,
        "weakest_lever": weakest,
        "strongest_lever": strongest,
    }


async def freshness(session: AsyncSession) -> dict:
    total_prompts = await session.scalar(select(func.count()).select_from(Prompt)) or 0
    analysed = await session.scalar(
        select(func.count()).select_from(Prompt).where(Prompt.analysed.is_(True))
    ) or 0
    conversations = await session.scalar(
        select(func.count()).select_from(ConversationAnalysis)
    ) or 0
    users = await session.scalar(select(func.count(distinct(Prompt.user_id)))) or 0
    latest = await session.scalar(select(func.max(Prompt.prompt_date)))
    earliest = await session.scalar(select(func.min(Prompt.prompt_date)))
    return {
        "total_prompts": total_prompts,
        "analysed_prompts": analysed,
        "conversations": conversations,
        "users": users,
        "earliest": earliest.isoformat() if earliest else None,
        "latest": latest.isoformat() if latest else None,
    }
