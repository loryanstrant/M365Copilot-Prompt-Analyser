"""Metrics routes for the prompt-analysis dashboards.

Routes are split by who may see what:

``router`` — organisation-wide data. Gated by :func:`require_org_view`, so it
needs both a valid token and membership of the configured organisation-view
group (admins always pass). Report routes accept the shared slicers (date
range, app, category, user, department, manager, country, source, governance
flag, quality range).

``common_router`` — data any signed-in user may see regardless of that group:
slicer options, data freshness and build info.

``me_router`` — the personal view. Every route derives the person from the
token, never from a client-supplied id, so one user cannot read another's
coaching by editing a URL.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api import metrics
from api.auth import CurrentUser, get_current_user, require_org_view
from api.metrics import PromptFilter
from shared.db import get_session
from shared.models import Prompt

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_org_view)],
)

common_router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(get_current_user)],
)

me_router = APIRouter(prefix="/metrics/me", tags=["metrics", "personal"])


def get_filters(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    app: list[str] | None = Query(default=None),
    category: list[str] | None = Query(default=None),
    user: list[str] | None = Query(default=None),
    department: list[str] | None = Query(default=None),
    manager: list[str] | None = Query(default=None),
    country: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    flag: list[str] | None = Query(default=None),
    quality_min: int | None = Query(default=None, ge=1, le=10),
    quality_max: int | None = Query(default=None, ge=1, le=10),
) -> PromptFilter:
    return PromptFilter(
        date_from=date_from,
        date_to=date_to,
        apps=app or [],
        categories=category or [],
        users=user or [],
        departments=department or [],
        managers=manager or [],
        countries=country or [],
        sources=source or [],
        flags=flag or [],
        quality_min=quality_min,
        quality_max=quality_max,
    )


@common_router.get("/filters")
async def get_filter_options(session: AsyncSession = Depends(get_session)):
    return await metrics.filter_options(session)


@router.get("/people")
async def get_people(session: AsyncSession = Depends(get_session)):
    """The person picker.

    This lists everybody who has prompt data, so it is an organisation tool and
    sits behind the org gate — not something a rank-and-file viewer should see.
    """
    return await metrics.people(session)


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


@router.get("/by-user")
async def get_by_user(
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.by_user(session, f=f)


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
    limit: int = Query(default=1000, ge=1, le=5000),
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
    limit: int = Query(default=1000, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.conversations_table(session, f=f, limit=limit)


@router.get("/conversations/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
):
    return await metrics.conversation_detail(session, conversation_id)


@router.get("/personal/{user_id}")
async def get_personal(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Coaching for a named person — an organisation tool, not a personal one.

    It takes an arbitrary user id, so anyone who can call it can read anyone
    else's coaching. That is legitimate for people with organisation-wide
    access (managers, enablement leads) and must stay behind the gate. The
    signed-in person's own view is ``/metrics/me/coaching``, which takes no id.
    """
    return await metrics.personal(session, user_id)


@common_router.get("/freshness")
async def get_freshness(session: AsyncSession = Depends(get_session)):
    return await metrics.freshness(session)


@common_router.get("/about")
async def get_about() -> dict:
    """Version and build metadata for the About page."""
    from shared.version import APP_VERSION, BUILD_DATE, BUILD_TIME

    return {
        "version": APP_VERSION,
        "build_date": BUILD_DATE,
        "build_time": BUILD_TIME,
    }


# --------------------------------------------------------------------------- #
# Personal view
#
# Every route here scopes to the signed-in person using the object ID carried in
# their token. There is deliberately no "which user?" parameter: if the caller
# could name the user, any viewer could read anyone's prompts by editing a URL.
# --------------------------------------------------------------------------- #
def _me_user_id(user: CurrentUser) -> str:
    """The signed-in person's Entra object ID, or 404."""
    if not user.oid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There is no personal view for this account. Sign in with your "
                "work account to see your own coaching."
            ),
        )
    return user.oid


def _me_filters(user: CurrentUser, base: PromptFilter) -> PromptFilter:
    """Narrow the shared slicers down to just this person.

    Whatever else the caller filtered on, ``users`` is overwritten — never
    extended — so the personal view can only ever narrow, not widen.
    """
    base.users = [_me_user_id(user)]
    return base


@me_router.get("/coaching")
async def get_my_coaching(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """This person's own coaching: quality, GCSE levers vs the team, focus."""
    return await metrics.personal(session, _me_user_id(user))


@me_router.get("/summary")
async def get_my_summary(
    user: CurrentUser = Depends(get_current_user),
    f: PromptFilter = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.summary(session, f=_me_filters(user, f))


@me_router.get("/conversations")
async def get_my_conversations(
    user: CurrentUser = Depends(get_current_user),
    f: PromptFilter = Depends(get_filters),
    limit: int = Query(default=1000, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.conversations_table(
        session, f=_me_filters(user, f), limit=limit
    )


@me_router.get("/prompts")
async def get_my_prompts(
    user: CurrentUser = Depends(get_current_user),
    f: PromptFilter = Depends(get_filters),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.prompts_table(
        session, f=_me_filters(user, f), limit=limit, offset=offset, search=search
    )


@me_router.get("/conversations/{conversation_id}")
async def get_my_conversation_detail(
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """One of this person's own conversations.

    The id names a conversation rather than a user, but it is still somebody's
    data, so ownership is confirmed against the token before anything is
    returned — otherwise guessing ids would read other people's threads.
    """
    me = _me_user_id(user)
    owners = set(
        (
            await session.execute(
                select(Prompt.user_id)
                .where(Prompt.conversation_id == conversation_id)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if not owners or owners - {me}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return await metrics.conversation_detail(session, conversation_id)
