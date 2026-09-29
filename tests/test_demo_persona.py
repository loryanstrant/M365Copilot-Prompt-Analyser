"""The demo persona binding, which is what makes the personal pages evaluable.

The personal view needs a directory identity, and the local password admin has
none — so before this existed, anyone evaluating with demo data could never open
the personal pages the README advertises. Loading demo data now binds the local
admin to one of the seeded directory users.

The claims worth holding onto:

- with no binding stored, nothing changes: the local admin still has no personal
  view, so a real deployment that never seeded demo data is unaffected;
- with a binding, the local admin sees that person's prompts and nobody else's,
  and the sidebar names the person rather than the account;
- the binding comes from stored config, never from the request, so it is not a
  way to ask for somebody else's coaching.
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from shared.db import SessionLocal
from shared.models import (
    AppConfig,
    AppUser,
    EntraUser,
    Prompt,
    PromptAnalysis,
)
from shared.security import hash_password

PERSONA = "user-02"
PERSONA_NAME = "Elsie Duarte"
PERSONA_UPN = "elsie.duarte@contoso.com"
SOMEONE_ELSE = "user-07"


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _seed(*, bind: bool) -> None:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        s.add(
            EntraUser(
                user_id=PERSONA, display_name=PERSONA_NAME, upn=PERSONA_UPN
            )
        )
        s.add(EntraUser(user_id=SOMEONE_ELSE, display_name="Grace Mbeki"))
        for uid, n in ((PERSONA, 2), (SOMEONE_ELSE, 5)):
            for i in range(n):
                pid = f"{uid}-p{i}"
                s.add(
                    Prompt(
                        prompt_id=pid,
                        user_id=uid,
                        conversation_id=f"{uid}-conv",
                        prompt_date=date(2026, 9, 1),
                        analysed=True,
                    )
                )
                s.add(
                    PromptAnalysis(
                        prompt_id=pid,
                        conversation_id=f"{uid}-conv",
                        quality_score=7,
                        user_generated=True,
                    )
                )
        s.add(
            AppConfig(id=1, demo_persona_user_id=PERSONA if bind else None)
        )
        await s.commit()


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_without_a_binding_the_local_admin_has_no_personal_view(client):
    """A deployment that never seeded demo data behaves exactly as before."""
    await _seed(bind=False)
    headers = await _admin_headers(client)

    me = (await client.get("/auth/me", headers=headers)).json()
    assert me["has_personal_view"] is False

    r = await client.get("/metrics/me/coaching", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_a_bound_local_admin_sees_that_person_and_no_one_else(client):
    await _seed(bind=True)
    headers = await _admin_headers(client)

    me = (await client.get("/auth/me", headers=headers)).json()
    assert me["has_personal_view"] is True
    # The sidebar names the person on screen, not the account they signed in as.
    assert me["display_name"] == PERSONA_NAME
    assert me["upn"] == PERSONA_UPN
    assert me["username"] == "admin"

    coaching = (await client.get("/metrics/me/coaching", headers=headers)).json()
    assert coaching["user_id"] == PERSONA
    assert coaching["name"] == PERSONA_NAME
    # Their two prompts, not the other person's five.
    assert coaching["prompts"] == 2


@pytest.mark.asyncio
async def test_the_binding_cannot_be_overridden_by_the_request(client):
    """The personal routes take no user parameter, and adding one changes
    nothing — otherwise the binding would be a way to read anyone's coaching."""
    await _seed(bind=True)
    headers = await _admin_headers(client)

    body = (
        await client.get(
            f"/metrics/me/summary?users={SOMEONE_ELSE}", headers=headers
        )
    ).json()
    assert body["prompts"] == 2
