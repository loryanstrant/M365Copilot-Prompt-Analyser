"""Seed synthetic demo data so the dashboards render without live Graph/AOAI.

Generates a realistic spread of prompts, per-prompt analysis and per-conversation
analysis directly into the database — no Microsoft Graph or Azure OpenAI calls.
Use it to explore the UI locally or in a demo environment.

Run inside the container / venv::

    python -m scripts.seed_demo            # ~40 conversations
    python -m scripts.seed_demo --conversations 100 --reset

``--reset`` clears the prompts/analysis tables first. It also seeds matching
``entra_users`` rows and records one of them as the demo persona, so the
directory-shaped parts of the UI work; it never writes credentials or user
accounts.

The directory rows matter more than they look. Every person picker, department,
country and manager slicer in ``api.metrics`` is built by outer-joining
``EntraUser`` onto ``Prompt.user_id``, so a demo instance with prompts but no
directory shows people as raw ids (``user-00``) and every slicer empty — which
is what it did before these rows existed.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from scripts._demo_tenant import COMPANY, DOMAIN
from shared.db import SessionLocal
from shared.models import (
    AppConfig,
    ConversationAnalysis,
    EntraUser,
    JobRun,
    LicensedUser,
    Prompt,
    PromptAnalysis,
)

APPS = [
    "Copilot Chat",
    "Word",
    "Excel",
    "PowerPoint",
    "Outlook",
    "Teams",
    "Copilot Search",
]
CATEGORIES = ["summarise", "create", "draft", "review", "analyse", "ask", "transcribe"]
SENTIMENTS = ["positive", "neutral", "negative"]
CHAT_TYPES = ["Work", "Web", "Temporary", None]
CONV_LOCATIONS = ["App", "Chat"]

_SAMPLE_PROMPTS = [
    "Summarise this document into five key bullet points for the leadership team.",
    "create a deck",
    "Draft a professional email declining the vendor's proposal politely.",
    "Analyse the Q3 sales figures in this spreadsheet and highlight the top three trends.",
    "Rewrite this paragraph to be more concise and formal.",
    "What are the action items from yesterday's project meeting?",
    "Summarize this",
    "Help me write a 200-word LinkedIn post announcing our new product launch.",
    "Review this contract clause and flag any risks in plain English.",
    "Translate the attached message into French, keeping a friendly tone.",
    "Generate a project plan for a 6-week website migration with milestones.",
    "Check TXQIAY",
    "Create a table comparing the pros and cons of the three shortlisted suppliers.",
    "Draft talking points for a difficult conversation with an underperforming team member.",
]

# Prompts Copilot offered rather than the person writing them. The
# user-generated share is one of the report's headline figures, so demo data in
# which everybody hand-writes everything makes that figure — and the coaching
# built on it — look broken.
_SUGGESTED_PROMPTS = [
    "What did I miss while I was away?",
    "Summarise my unread emails from this week.",
    "Catch me up on this chat.",
    "What are my next steps after this meeting?",
    "Show me recent files shared with me.",
]
_SUGGESTED_SHARE = 0.18

_THEMES = [
    "Drafting external communications",
    "Analysing financial data",
    "Summarising long documents",
    "Preparing meeting follow-ups",
    "Creating presentation content",
    "Reviewing contracts and policies",
]
_INSIGHTS = [
    "The user is engaging deeply, iterating with contextual follow-ups.",
    "Prompts are short and command-like — a coaching opportunity on context.",
    "The user is exploring capabilities across several apps.",
    "Consistent, well-structured prompts showing mature adoption.",
]


# The directory behind the demo prompts. The first twelve line up with the
# ``user-NN`` ids the prompt loop generates; the last two hold a licence and
# have no prompts at all, which is the row a tenant most wants to find on the
# Tenant users listing and would never appear if everyone here had activity.
#
# Ids are ``user-NN`` rather than GUIDs on purpose: they cannot collide with a
# real Entra object ID, so demo data and live data can never be confused for
# each other even in the same database.
_PERSONAS: list[tuple[str, str, str, str, str, str, str | None]] = [
    # (id, name, job title, department, office, country, manager)
    ("user-00", "Nadia Okonjo", "Chief Operating Officer", "Executive", "Melbourne", "Australia", None),
    ("user-01", "Tomas Lindqvist", "Head of Finance", "Finance", "Melbourne", "Australia", "user-00"),
    ("user-02", "Elsie Duarte", "Programme Manager", "Operations", "Melbourne", "Australia", "user-00"),
    ("user-03", "Priya Raghunathan", "Financial Analyst", "Finance", "Sydney", "Australia", "user-01"),
    ("user-04", "Callum Reidy", "Management Accountant", "Finance", "Sydney", "Australia", "user-01"),
    ("user-05", "Marta Kowalczyk", "Operations Lead", "Operations", "Wellington", "New Zealand", "user-02"),
    ("user-06", "Dev Anand", "Business Analyst", "Operations", "Wellington", "New Zealand", "user-02"),
    ("user-07", "Grace Mbeki", "Marketing Manager", "Marketing", "Brisbane", "Australia", "user-00"),
    ("user-08", "Hiroshi Tanaka", "Content Strategist", "Marketing", "Brisbane", "Australia", "user-07"),
    ("user-09", "Aoife Brennan", "People Partner", "People", "Dublin", "Ireland", "user-00"),
    ("user-10", "Samir Haddad", "IT Service Manager", "Technology", "Melbourne", "Australia", "user-00"),
    ("user-11", "Jo Whitcombe", "Solution Architect", "Technology", "Melbourne", "Australia", "user-10"),
    ("user-12", "Rhiannon Pryce", "Legal Counsel", "Legal", "Cardiff", "United Kingdom", "user-00"),
    ("user-13", "Ben Osei", "Procurement Specialist", "Finance", "Manchester", "United Kingdom", "user-01"),
    # Added so two departments are actually big enough to compare against.
    # "How you compare" withholds a team average below five people other than
    # the viewer, because at smaller sizes the team mean plus the viewer's own
    # figure gives an individual away. With only the fourteen personas above,
    # the biggest department held four active people, so the comparison the demo
    # exists to show was withheld for everyone who looked at it.
    #
    # Operations and Finance are deliberately over the line and Marketing,
    # Technology, People and Legal deliberately under it: the withheld state is
    # part of what a demo should show, not a bug to seed around.
    ("user-14", "Yusuf Demir", "Operations Analyst", "Operations", "Wellington", "New Zealand", "user-02"),
    ("user-15", "Carys Llewellyn", "Process Improvement Lead", "Operations", "Melbourne", "Australia", "user-02"),
    ("user-16", "Thabo Molefe", "Service Delivery Manager", "Operations", "Brisbane", "Australia", "user-05"),
    ("user-17", "Ingrid Sørensen", "Logistics Coordinator", "Operations", "Wellington", "New Zealand", "user-05"),
    ("user-18", "Lucia Ferrari", "Commercial Analyst", "Finance", "Sydney", "Australia", "user-01"),
    ("user-19", "Owen Tibbett", "Payroll Manager", "Finance", "Manchester", "United Kingdom", "user-01"),
    ("user-20", "Anjali Kapoor", "Treasury Analyst", "Finance", "Melbourne", "Australia", "user-03"),
    ("user-21", "Mateo Silva", "Campaign Manager", "Marketing", "Brisbane", "Australia", "user-07"),
    ("user-22", "Fiona Achebe", "Talent Acquisition Lead", "People", "Dublin", "Ireland", "user-09"),
    ("user-23", "Petr Novak", "Platform Engineer", "Technology", "Melbourne", "Australia", "user-10"),
]

# Everyone except two — a directory with universal licensing tells a tenant
# nothing about who is missing one.
_UNLICENSED = {"user-08", "user-09"}

# The persona the local admin account is bound to while demo data is loaded, so
# the personal pages can be reached without an Entra sign-in. Chosen for having
# a manager, a team around them and a middling amount of activity.
DEMO_PERSONA_USER_ID = "user-02"

# The personas the prompt generator deliberately leaves alone: they hold a
# licence and have no activity at all, which is the row a tenant most wants to
# find on the Tenant users listing and would never appear if everybody here had
# prompts. Everyone else is active — selecting "the first twelve" stopped working
# once the directory grew past twelve, because the people who make the team
# comparisons possible would have had no prompts to compare.
_INACTIVE_PERSONAS = {"user-12", "user-13"}


def _active_persona_ids() -> list[str]:
    return [uid for uid, *_ in _PERSONAS if uid not in _INACTIVE_PERSONAS]


def _persona_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for uid, name, title, dept, office, country, manager in _PERSONAS:
        local = name.lower().replace(" ", ".").replace("'", "")
        rows.append(
            {
                "user_id": uid,
                "upn": f"{local}@{DOMAIN}",
                "email": f"{local}@{DOMAIN}",
                "display_name": name,
                "job_title": title,
                "company_name": COMPANY,
                "department": dept,
                "office_location": office,
                "country": country,
                "manager_id": manager,
                "account_enabled": True,
                "user_type": "Member",
                "has_copilot_license": uid not in _UNLICENSED,
            }
        )
    return rows


# How good each person is at prompting, as an offset on the 1-10 scale. Without
# this, every score is drawn from the same distribution, so with a few hundred
# prompts everybody averages about 5.5 — the coaching pages have nobody to coach,
# the briefing has no watch-outs, and the person picker is pointless. A real
# tenant has strong prompters and struggling ones, so the demo does too.
_SKILL: dict[str, int] = {
    "user-00": 2, "user-01": 1, "user-02": 0, "user-03": 3, "user-04": -1,
    "user-05": 1, "user-06": -3, "user-07": 2, "user-08": -2, "user-09": 0,
    "user-10": 1, "user-11": -3,
    # The later personas spread either side of the middle, so a team average is
    # not simply the viewer's own figure repeated.
    "user-14": -2, "user-15": 2, "user-16": 0, "user-17": -1, "user-18": 3,
    "user-19": -2, "user-20": 1, "user-21": -1, "user-22": 0, "user-23": 2,
}

# One lever is the organisation's weakest, so the briefing has something to say
# about where enablement would pay. People are worse at stating a goal than at
# anything else, which is also what the coaching copy assumes.
_LEVER_BIAS = {"goal": -1, "context": 0, "source": 0, "expectation": 1}


def _clamp(value: int) -> int:
    return max(1, min(10, value))


def _rand_gcse(skill: int) -> dict[str, int]:
    base = random.randint(3, 8) + skill
    return {
        lever: _clamp(base + _LEVER_BIAS[lever] + random.randint(-1, 1))
        for lever in ("goal", "context", "source", "expectation")
    }


# Marks a job_runs row as demo data, so clearing the demo removes exactly these
# rows and never a record of something that really ran.
_DEMO_RUN_MARK = "demo"


async def _delete_demo_job_runs(session) -> None:
    """Remove only the seeded runs, never a record of something that really ran.

    Matched in Python on the marker in ``stats`` rather than with a JSON
    containment operator, because this script has to work on SQLite as well as
    Postgres and the syntax for that differs between them.
    """
    rows = (await session.execute(select(JobRun))).scalars().all()
    for row in rows:
        if isinstance(row.stats, dict) and row.stats.get(_DEMO_RUN_MARK):
            await session.delete(row)


async def _seed_job_runs(session, today: date) -> int:
    """A fortnight of collection and analysis runs for Scan history.

    Including a failure and a run still in progress. A log where everything
    always succeeded teaches nobody what a failure looks like, and until this
    existed the in-progress indicator was mapped but had never been rendered
    anywhere.
    """
    # The day the nightly collection broke, far enough back that it is not the
    # newest row — a failure at the top of the list is easy; one buried in the
    # middle is what people actually have to spot.
    failed_day = 9
    runs: list[JobRun] = []

    def at(days_ago: int, hour: int, minute: int = 0) -> datetime:
        d = today - timedelta(days=days_ago)
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)

    for days_ago in range(13, -1, -1):
        started = at(days_ago, 2)
        if days_ago == failed_day:
            runs.append(
                JobRun(
                    job_name="scheduled",
                    started_at=started,
                    finished_at=started + timedelta(seconds=42),
                    status="failed",
                    stats={
                        _DEMO_RUN_MARK: True,
                        "error": (
                            "Microsoft Graph returned 429 (throttled) on "
                            "getCopilotUserInteractions; retries exhausted"
                        ),
                        "prompts": 0,
                    },
                )
            )
            continue
        runs.append(
            JobRun(
                job_name="scheduled",
                started_at=started,
                finished_at=started + timedelta(minutes=3, seconds=12),
                status="success",
                stats={
                    _DEMO_RUN_MARK: True,
                    "prompts": random.randint(60, 240),
                    "entra_users": len(_PERSONAS),
                    "licensed_users": len(_PERSONAS) - len(_UNLICENSED),
                    "copilot_skus": 2,
                },
            )
        )
        analysis_started = started + timedelta(minutes=10)
        runs.append(
            JobRun(
                job_name="scheduled-analysis",
                started_at=analysis_started,
                finished_at=analysis_started + timedelta(minutes=6, seconds=40),
                status="success",
                stats={
                    _DEMO_RUN_MARK: True,
                    "prompts": random.randint(50, 200),
                    "conversations": random.randint(8, 30),
                    "errors": 0,
                },
            )
        )

    # One historical backfill, which is where the older prompts came from. It
    # writes "completed" rather than "success" — the same outcome under a
    # different word, because a different module wrote the row.
    backfill_started = at(12, 21)
    runs.append(
        JobRun(
            job_name="backfill",
            started_at=backfill_started,
            finished_at=backfill_started + timedelta(hours=1, minutes=48),
            status="completed",
            stats={
                _DEMO_RUN_MARK: True,
                "users": len(_PERSONAS),
                "prompts": 1840,
                "lookback_days": 90,
                "cancelled": False,
            },
        )
    )

    # Somebody pressing Run now, and an analysis pass still going. The running
    # row has no finished_at, which is what makes the duration column show a dash
    # and the status show as in progress.
    manual_started = at(3, 14, 35)
    runs.append(
        JobRun(
            job_name="manual",
            started_at=manual_started,
            finished_at=manual_started + timedelta(minutes=2, seconds=51),
            status="success",
            stats={_DEMO_RUN_MARK: True, "prompts": 74, "entra_users": len(_PERSONAS)},
        )
    )
    runs.append(
        JobRun(
            job_name="manual-analysis",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=4),
            finished_at=None,
            status="running",
            stats={_DEMO_RUN_MARK: True, "prompts": 31, "conversations": 6},
        )
    )

    for r in runs:
        session.add(r)
    return len(runs)


async def seed(conversations: int, reset: bool) -> dict[str, int]:
    async with SessionLocal() as session:
        if reset:
            await session.execute(delete(PromptAnalysis))
            await session.execute(delete(ConversationAnalysis))
            await session.execute(delete(Prompt))
            await session.execute(delete(EntraUser))
            await session.execute(delete(LicensedUser))
            await _delete_demo_job_runs(session)
            await session.commit()

        for row in _persona_rows():
            await session.merge(EntraUser(**row))
            if row["has_copilot_license"]:
                await session.merge(LicensedUser(user_id=row["user_id"]))

        # Bind the local admin account to one of these people, so the personal
        # pages can be reached without an Entra sign-in. Without it, anyone
        # evaluating with demo data can never open the pages the README
        # advertises: has_personal_view needs a directory identity, and the
        # password admin has none.
        cfg = await session.get(AppConfig, 1)
        if cfg is None:
            cfg = AppConfig(id=1)
            session.add(cfg)
        cfg.demo_persona_user_id = DEMO_PERSONA_USER_ID

        today = date.today()
        active_ids = _active_persona_ids()
        n_prompts = 0
        for c in range(conversations):
            conv_id = f"demo-conv-{c:04d}"
            app = random.choice(APPS)
            cat = random.choice(CATEGORIES)
            day = today - timedelta(days=random.randint(0, 89))
            n = random.randint(1, 6)
            user_id = active_ids[c % len(active_ids)]
            skill = _SKILL.get(user_id, 0)
            scores: list[int] = []
            user_gen = 0
            for p in range(n):
                pid = f"{conv_id}-p{p}"
                suggested = random.random() < _SUGGESTED_SHARE
                if suggested:
                    text = random.choice(_SUGGESTED_PROMPTS)
                    is_user = False
                else:
                    text = random.choice(_SAMPLE_PROMPTS)
                    is_user = not (len(text) < 12 or text.isupper())
                user_gen += int(is_user)
                # A suggested prompt is somebody else's words, so it does not
                # show what this person can do: those score around the middle
                # whatever their own skill.
                q = _clamp(
                    random.randint(3, 8) + (0 if suggested else skill) + random.randint(-1, 1)
                )
                scores.append(q)
                gcse = _rand_gcse(0 if suggested else skill)
                name_conf = random.randint(1, 10)
                sens_conf = random.randint(1, 10)
                session.add(
                    Prompt(
                        prompt_id=pid,
                        user_id=user_id,
                        conversation_id=conv_id,
                        app_name=app,
                        prompt_date=day,
                        conversation_type="appchat" if app != "Copilot Chat" else "bizchat",
                        conversation_location=random.choice(CONV_LOCATIONS),
                        chat_type=random.choice(CHAT_TYPES),
                        prompt_text=text,
                        name_confidence=name_conf,
                        sensitive_confidence=sens_conf,
                        curse_confidence=random.randint(1, 3),
                        analysed=True,
                    )
                )
                session.add(
                    PromptAnalysis(
                        prompt_id=pid,
                        conversation_id=conv_id,
                        user_generated=is_user,
                        sentiment=random.choice(SENTIMENTS),
                        quality_score=q,
                        quality_rationale=(
                            "Detailed and specific with clear desired output."
                            if q >= 7
                            else "Vague or minimal; lacks context."
                        ),
                        category=random.choice(CATEGORIES),
                        gcse_goal=gcse["goal"],
                        gcse_context=gcse["context"],
                        gcse_source=gcse["source"],
                        gcse_expectation=gcse["expectation"],
                    )
                )
                n_prompts += 1

            avg_q = round(sum(scores) / len(scores), 1)
            conv_q = max(1, min(10, round(avg_q)))
            session.add(
                ConversationAnalysis(
                    conversation_id=conv_id,
                    sentiment=random.choice(SENTIMENTS),
                    avg_quality_score=avg_q,
                    conversation_quality_score=conv_q,
                    user_generated_ratio=round(100.0 * user_gen / n, 1),
                    theme=random.choice(_THEMES),
                    insight=random.choice(_INSIGHTS),
                    category=cat,
                    improvement=(
                        "A stronger initial prompt with explicit goal and context "
                        "would have reduced follow-ups."
                        if conv_q < 5
                        else None
                    ),
                    suggested_starter_prompt=(
                        "Summarise the attached Q3 report into five bullets for the "
                        "leadership team, focusing on revenue drivers and risks."
                        if conv_q < 5 and n > 1
                        else None
                    ),
                    prompt_count=n,
                )
            )
        job_runs = await _seed_job_runs(session, today)
        await session.commit()
    return {
        "conversations": conversations,
        "prompts": n_prompts,
        "users": len(_PERSONAS),
        "job_runs": job_runs,
    }


async def clear() -> dict[str, int]:
    """Remove all seeded prompt/analysis/directory data.

    Credentials and user accounts are never affected. The demo persona binding
    goes with the data: leaving it would hand the local admin a personal view
    over people who are no longer there.
    """
    async with SessionLocal() as session:
        await session.execute(delete(ConversationAnalysis))
        await session.execute(delete(PromptAnalysis))
        await session.execute(delete(Prompt))
        await session.execute(delete(EntraUser))
        await session.execute(delete(LicensedUser))
        await _delete_demo_job_runs(session)
        cfg = await session.get(AppConfig, 1)
        if cfg is not None:
            cfg.demo_persona_user_id = None
        await session.commit()
    return {"cleared": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo prompt-analysis data.")
    # 140, not 40: the directory is 22 active people now, and at 40
    # conversations most of them had one or two, which is too thin for a team
    # average to mean anything.
    parser.add_argument("--conversations", type=int, default=140)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--clear", action="store_true", help="Clear data and exit")
    args = parser.parse_args()
    # psycopg async needs a SelectorEventLoop on Windows (no-op elsewhere).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if args.clear:
        asyncio.run(clear())
        print("Demo data cleared.")
        return
    stats = asyncio.run(seed(args.conversations, args.reset))
    print(
        f"Seeded {stats['prompts']} prompts across {stats['conversations']} "
        f"conversations for {stats['users']} directory users, "
        f"and {stats['job_runs']} collection runs."
    )


if __name__ == "__main__":
    main()
