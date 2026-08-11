"""SQL metrics for the five prompt-analysis dashboards.

All aggregation happens here (never in the client), over three tables:
``prompts`` (text + governance confidences), ``prompt_analysis`` (per-prompt
quality / GCSE / sentiment / category) and ``conversation_analysis`` (per
conversation). Scores are on a 1-10 scale; RAG thresholds are >=7 / 4-6 / <4.

A light :class:`PromptFilter` slices by date range, app and category — enough for
the dashboards without the heavy directory-join filtering the usage reporter uses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import Float, and_, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import ConversationAnalysis, Prompt, PromptAnalysis

GCSE_LEVERS = ("goal", "context", "source", "expectation")
_HIGH_QUALITY = 7
_WELL_GROUNDED = 7


def _clean(values: list[str] | None) -> list[str]:
    return [v for v in (values or []) if v not in (None, "")]


@dataclass
class PromptFilter:
    date_from: date | None = None
    date_to: date | None = None
    apps: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    def prompt_conds(self) -> list[Any]:
        conds: list[Any] = []
        if self.date_from is not None:
            conds.append(Prompt.prompt_date >= self.date_from)
        if self.date_to is not None:
            conds.append(Prompt.prompt_date <= self.date_to)
        if _clean(self.apps):
            conds.append(Prompt.app_name.in_(_clean(self.apps)))
        return conds

    def analysis_conds(self) -> list[Any]:
        conds: list[Any] = []
        if _clean(self.categories):
            conds.append(PromptAnalysis.category.in_(_clean(self.categories)))
        return conds


def _round(value: Any, digits: int = 1) -> float | None:
    return round(float(value), digits) if value is not None else None


# --- shared base query: prompts joined to their analysis -----------------
def _pa_query(f: PromptFilter):
    """SELECT-able join of prompt_analysis to prompts under the active filter."""
    q = select(PromptAnalysis).join(Prompt, Prompt.prompt_id == PromptAnalysis.prompt_id)
    conds = [*f.prompt_conds(), *f.analysis_conds()]
    if conds:
        q = q.where(and_(*conds))
    return q


# --- filter options ------------------------------------------------------
async def filter_options(session: AsyncSession) -> dict[str, list[str]]:
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
    return {
        "apps": sorted(a for a in apps if a),
        "categories": sorted(c for c in cats if c),
    }


# --- headline summary (feeds cards across pages) -------------------------
async def summary(session: AsyncSession, *, f: PromptFilter) -> dict[str, Any]:
    base = _pa_query(f).subquery()

    prompts_analysed = await session.scalar(
        select(func.count()).select_from(base)
    ) or 0
    conversations = await session.scalar(
        select(func.count(distinct(base.c.conversation_id)))
    ) or 0
    avg_quality = await session.scalar(select(func.avg(base.c.quality_score)))
    high_quality = await session.scalar(
        select(func.count()).select_from(base).where(
            base.c.quality_score >= _HIGH_QUALITY
        )
    ) or 0
    user_generated = await session.scalar(
        select(func.count()).select_from(base).where(base.c.user_generated.is_(True))
    ) or 0
    well_grounded = await session.scalar(
        select(func.count()).select_from(base).where(base.c.gcse_source >= _WELL_GROUNDED)
    ) or 0

    # GCSE levers (overall) — to find the weakest.
    gcse = {
        lever: await session.scalar(
            select(func.avg(getattr(base.c, f"gcse_{lever}")))
        )
        for lever in GCSE_LEVERS
    }
    weakest = None
    known = {k: v for k, v in gcse.items() if v is not None}
    if known:
        weakest = min(known, key=known.get)

    # Conversation-level sentiment mix.
    conv_rows = (
        await session.execute(
            select(ConversationAnalysis.sentiment, func.count())
            .group_by(ConversationAnalysis.sentiment)
        )
    ).all()
    conv_total = sum(c for _, c in conv_rows) or 0
    neutral = sum(c for s, c in conv_rows if (s or "").lower() == "neutral")
    positive = sum(c for s, c in conv_rows if (s or "").lower() == "positive")

    avg_conv_quality = await session.scalar(
        select(func.avg(ConversationAnalysis.conversation_quality_score))
    )
    avg_name = await session.scalar(select(func.avg(Prompt.name_confidence)))
    avg_sensitive = await session.scalar(select(func.avg(Prompt.sensitive_confidence)))

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
    }


# --- distributions -------------------------------------------------------
async def quality_distribution(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    base = _pa_query(f).subquery()
    rows = (
        await session.execute(
            select(base.c.quality_score, func.count())
            .group_by(base.c.quality_score)
            .order_by(base.c.quality_score)
        )
    ).all()
    counts = {int(s): c for s, c in rows if s is not None}
    return [{"score": i, "count": counts.get(i, 0)} for i in range(1, 11)]


async def conversation_quality_distribution(
    session: AsyncSession, *, f: PromptFilter
) -> list[dict]:
    rows = (
        await session.execute(
            select(
                ConversationAnalysis.conversation_quality_score, func.count()
            ).group_by(ConversationAnalysis.conversation_quality_score)
        )
    ).all()
    counts = {int(s): c for s, c in rows if s is not None}
    return [{"score": i, "count": counts.get(i, 0)} for i in range(1, 11)]


async def category_mix(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    base = _pa_query(f).subquery()
    rows = (
        await session.execute(
            select(base.c.category, func.count())
            .group_by(base.c.category)
            .order_by(func.count().desc())
        )
    ).all()
    return [{"name": c or "Unknown", "count": n} for c, n in rows]


async def sentiment_mix(session: AsyncSession, *, f: PromptFilter) -> dict[str, list]:
    base = _pa_query(f).subquery()
    prompt_rows = (
        await session.execute(
            select(base.c.sentiment, func.count()).group_by(base.c.sentiment)
        )
    ).all()
    conv_rows = (
        await session.execute(
            select(ConversationAnalysis.sentiment, func.count()).group_by(
                ConversationAnalysis.sentiment
            )
        )
    ).all()
    return {
        "prompt": [{"name": s or "Unknown", "count": n} for s, n in prompt_rows],
        "conversation": [{"name": s or "Unknown", "count": n} for s, n in conv_rows],
    }


# --- by app / by intent --------------------------------------------------
async def by_app(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    base = _pa_query(f).subquery()
    j = select(
        Prompt.app_name.label("app"),
        func.count().label("prompts"),
        func.avg(base.c.quality_score).label("avg_quality"),
    ).select_from(base).join(Prompt, Prompt.prompt_id == base.c.prompt_id).group_by(
        Prompt.app_name
    ).order_by(func.count().desc())
    rows = (await session.execute(j)).all()
    return [
        {"app": a or "Unknown", "prompts": p, "avg_quality": _round(q)}
        for a, p, q in rows
    ]


async def by_intent(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    base = _pa_query(f).subquery()
    rows = (
        await session.execute(
            select(
                base.c.category,
                func.count(),
                func.avg(base.c.quality_score),
            )
            .group_by(base.c.category)
            .order_by(func.count().desc())
        )
    ).all()
    return [
        {"category": c or "Unknown", "prompts": n, "avg_quality": _round(q)}
        for c, n, q in rows
    ]


async def gcse_by_intent(session: AsyncSession, *, f: PromptFilter) -> list[dict]:
    base = _pa_query(f).subquery()
    rows = (
        await session.execute(
            select(
                base.c.category,
                func.avg(base.c.gcse_goal),
                func.avg(base.c.gcse_context),
                func.avg(base.c.gcse_source),
                func.avg(base.c.gcse_expectation),
            ).group_by(base.c.category)
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
    async def dist(col) -> list[dict]:
        rows = (
            await session.execute(
                select(col, func.count()).where(col.is_not(None)).group_by(col)
            )
        ).all()
        counts = {int(s): c for s, c in rows}
        return [{"score": i, "count": counts.get(i, 0)} for i in range(1, 11)]

    return {
        "name_confidence": await dist(Prompt.name_confidence),
        "sensitive_confidence": await dist(Prompt.sensitive_confidence),
        "curse_confidence": await dist(Prompt.curse_confidence),
    }


# --- tables --------------------------------------------------------------
async def prompts_table(
    session: AsyncSession,
    *,
    f: PromptFilter,
    limit: int = 200,
    offset: int = 0,
    search: str | None = None,
) -> list[dict]:
    q = (
        select(
            Prompt.prompt_id,
            Prompt.prompt_text,
            Prompt.app_name,
            Prompt.prompt_date,
            PromptAnalysis.category,
            PromptAnalysis.sentiment,
            PromptAnalysis.user_generated,
            PromptAnalysis.quality_score,
            PromptAnalysis.quality_rationale,
            PromptAnalysis.gcse_goal,
            PromptAnalysis.gcse_context,
            PromptAnalysis.gcse_source,
            PromptAnalysis.gcse_expectation,
            Prompt.name_confidence,
            Prompt.sensitive_confidence,
        )
        .join(Prompt, Prompt.prompt_id == PromptAnalysis.prompt_id)
    )
    conds = [*f.prompt_conds(), *f.analysis_conds()]
    if search:
        conds.append(Prompt.prompt_text.ilike(f"%{search}%"))
    if conds:
        q = q.where(and_(*conds))
    q = q.order_by(PromptAnalysis.quality_score.desc().nullslast()).limit(limit).offset(offset)
    rows = (await session.execute(q)).all()
    return [
        {
            "prompt_id": r.prompt_id,
            "prompt_text": r.prompt_text,
            "app": r.app_name,
            "date": r.prompt_date.isoformat() if r.prompt_date else None,
            "category": r.category,
            "sentiment": r.sentiment,
            "user_generated": r.user_generated,
            "quality_score": r.quality_score,
            "quality_rationale": r.quality_rationale,
            "gcse_goal": r.gcse_goal,
            "gcse_context": r.gcse_context,
            "gcse_source": r.gcse_source,
            "gcse_expectation": r.gcse_expectation,
            "name_confidence": r.name_confidence,
            "sensitive_confidence": r.sensitive_confidence,
        }
        for r in rows
    ]


async def conversations_table(
    session: AsyncSession, *, f: PromptFilter, limit: int = 200
) -> list[dict]:
    rows = (
        await session.execute(
            select(ConversationAnalysis)
            .order_by(ConversationAnalysis.conversation_quality_score.desc().nullslast())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "conversation_id": c.conversation_id,
            "sentiment": c.sentiment,
            "avg_quality_score": _round(c.avg_quality_score),
            "conversation_quality_score": c.conversation_quality_score,
            "user_generated_ratio": _round(c.user_generated_ratio),
            "theme": c.theme,
            "insight": c.insight,
            "category": c.category,
            "improvement": c.improvement,
            "suggested_starter_prompt": c.suggested_starter_prompt,
            "prompt_count": c.prompt_count,
        }
        for c in rows
    ]


async def conversation_detail(session: AsyncSession, conversation_id: str) -> dict:
    conv = await session.get(ConversationAnalysis, conversation_id)
    prompt_rows = (
        await session.execute(
            select(
                Prompt.prompt_id,
                Prompt.prompt_text,
                Prompt.prompt_date,
                Prompt.app_name,
                PromptAnalysis.category,
                PromptAnalysis.sentiment,
                PromptAnalysis.user_generated,
                PromptAnalysis.quality_score,
                PromptAnalysis.quality_rationale,
            )
            .join(PromptAnalysis, PromptAnalysis.prompt_id == Prompt.prompt_id)
            .where(Prompt.conversation_id == conversation_id)
            .order_by(Prompt.prompt_date, Prompt.prompt_id)
        )
    ).all()
    return {
        "conversation": (
            {
                "conversation_id": conv.conversation_id,
                "sentiment": conv.sentiment,
                "avg_quality_score": _round(conv.avg_quality_score),
                "conversation_quality_score": conv.conversation_quality_score,
                "user_generated_ratio": _round(conv.user_generated_ratio),
                "theme": conv.theme,
                "insight": conv.insight,
                "category": conv.category,
                "improvement": conv.improvement,
                "suggested_starter_prompt": conv.suggested_starter_prompt,
                "prompt_count": conv.prompt_count,
            }
            if conv
            else None
        ),
        "prompts": [
            {
                "prompt_id": r.prompt_id,
                "prompt_text": r.prompt_text,
                "date": r.prompt_date.isoformat() if r.prompt_date else None,
                "app": r.app_name,
                "category": r.category,
                "sentiment": r.sentiment,
                "user_generated": r.user_generated,
                "quality_score": r.quality_score,
                "quality_rationale": r.quality_rationale,
            }
            for r in prompt_rows
        ],
    }


# --- personal coaching (keyed by conversation until an identity exists) --
async def personal(session: AsyncSession, conversation_id: str) -> dict:
    detail = await conversation_detail(session, conversation_id)
    # This conversation's GCSE averages vs the team (all conversations).
    mine = {}
    team = {}
    for lever in GCSE_LEVERS:
        col = getattr(PromptAnalysis, f"gcse_{lever}")
        mine[lever] = _round(
            await session.scalar(
                select(func.avg(col)).where(PromptAnalysis.conversation_id == conversation_id)
            )
        )
        team[lever] = _round(await session.scalar(select(func.avg(col))))
    return {"detail": detail, "gcse_mine": mine, "gcse_team": team}


async def freshness(session: AsyncSession) -> dict:
    total_prompts = await session.scalar(select(func.count()).select_from(Prompt)) or 0
    analysed = await session.scalar(
        select(func.count()).select_from(Prompt).where(Prompt.analysed.is_(True))
    ) or 0
    conversations = await session.scalar(
        select(func.count()).select_from(ConversationAnalysis)
    ) or 0
    latest = await session.scalar(select(func.max(Prompt.prompt_date)))
    earliest = await session.scalar(select(func.min(Prompt.prompt_date)))
    return {
        "total_prompts": total_prompts,
        "analysed_prompts": analysed,
        "conversations": conversations,
        "earliest": earliest.isoformat() if earliest else None,
        "latest": latest.isoformat() if latest else None,
    }
