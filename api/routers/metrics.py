"""Metrics routes for the five prompt-analysis dashboards (any authenticated user).

All routes require a valid token but not the admin role, so viewers can read the
reports. Report routes accept the shared slicers (date range, app, category).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api import metrics
from api.auth import get_current_user
from api.metrics import PromptFilter
from shared.db import get_session

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(get_current_user)],
)


def get_filters(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    app: list[str] | None = Query(default=None),
    category: list[str] | None = Query(default=None),
) -> PromptFilter:
    return PromptFilter(
        date_from=date_from,
        date_to=date_to,
        apps=app or [],
        categories=category or [],
    )


@router.get("/filters")
async def get_filter_options(session: AsyncSession = Depends(get_session)):
    return await metrics.filter_options(session)


@router.get("/summary")
async def get_summary(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.summary(session, f=f)


@router.get("/quality-distribution")
async def get_quality_distribution(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.quality_distribution(session, f=f)


@router.get("/conversation-quality-distribution")
async def get_conversation_quality_distribution(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.conversation_quality_distribution(session, f=f)


@router.get("/category-mix")
async def get_category_mix(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.category_mix(session, f=f)


@router.get("/sentiment")
async def get_sentiment(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.sentiment_mix(session, f=f)


@router.get("/by-app")
async def get_by_app(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.by_app(session, f=f)


@router.get("/by-intent")
async def get_by_intent(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.by_intent(session, f=f)


@router.get("/gcse-by-intent")
async def get_gcse_by_intent(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.gcse_by_intent(session, f=f)


@router.get("/governance")
async def get_governance(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.governance(session, f=f)


@router.get("/prompts")
async def get_prompts(
    f: PromptFilter = Depends(get_filters),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.prompts_table(
        session, f=f, limit=limit, offset=offset, search=search
    )


@router.get("/conversations")
async def get_conversations(
    f: PromptFilter = Depends(get_filters),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.conversations_table(session, f=f, limit=limit)


@router.get("/conversations/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
):
    return await metrics.conversation_detail(session, conversation_id)


@router.get("/personal/{conversation_id}")
async def get_personal(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
):
    return await metrics.personal(session, conversation_id)


@router.get("/freshness")
async def get_freshness(session: AsyncSession = Depends(get_session)):
    return await metrics.freshness(session)
