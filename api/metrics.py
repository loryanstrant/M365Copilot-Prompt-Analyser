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

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import Integer, and_, cast, distinct, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import ConversationAnalysis, EntraUser, Prompt, PromptAnalysis

GCSE_LEVERS = ("goal", "context", "source", "expectation")
_HIGH_QUALITY = 7
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


# --- personal coaching (per user) ---------------------------------------
async def personal(session: AsyncSession, user_id: str) -> dict:
    """Everything one person would see: their stats, GCSE vs team, and focus."""
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

    mine: dict[str, float | None] = {}
    team: dict[str, float | None] = {}
    for lever in GCSE_LEVERS:
        col = getattr(PromptAnalysis, f"gcse_{lever}")
        mine[lever] = _round(
            await session.scalar(
                select(func.avg(getattr(b.c, f"gcse_{lever}")))
            )
        )
        team[lever] = _round(await session.scalar(select(func.avg(col))))

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
        "user_generated_pct": round(100.0 * user_gen / total, 1) if total else 0.0,
        "gcse_mine": mine,
        "gcse_team": team,
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
