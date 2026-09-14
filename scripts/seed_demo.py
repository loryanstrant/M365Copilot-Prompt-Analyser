"""Seed synthetic demo data so the dashboards render without live Graph/AOAI.

Generates a realistic spread of prompts, per-prompt analysis and per-conversation
analysis directly into the database — no Microsoft Graph or Azure OpenAI calls.
Use it to explore the UI locally or in a demo environment.

Run inside the container / venv::

    python -m scripts.seed_demo            # ~40 conversations
    python -m scripts.seed_demo --conversations 100 --reset

``--reset`` clears the prompts/analysis tables first. This only ever touches the
three analysis tables; it never writes credentials or user accounts.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import date, timedelta

from sqlalchemy import delete

from shared.db import SessionLocal
from shared.models import ConversationAnalysis, Prompt, PromptAnalysis

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


def _rand_gcse() -> dict[str, int]:
    base = random.randint(3, 9)
    return {lever: max(1, min(10, base + random.randint(-2, 2))) for lever in
            ("goal", "context", "source", "expectation")}


async def seed(conversations: int, reset: bool) -> dict[str, int]:
    async with SessionLocal() as session:
        if reset:
            await session.execute(delete(PromptAnalysis))
            await session.execute(delete(ConversationAnalysis))
            await session.execute(delete(Prompt))
            await session.commit()

        today = date.today()
        n_prompts = 0
        for c in range(conversations):
            conv_id = f"demo-conv-{c:04d}"
            app = random.choice(APPS)
            cat = random.choice(CATEGORIES)
            day = today - timedelta(days=random.randint(0, 89))
            n = random.randint(1, 6)
            scores: list[int] = []
            user_gen = 0
            for p in range(n):
                pid = f"{conv_id}-p{p}"
                text = random.choice(_SAMPLE_PROMPTS)
                is_user = not (len(text) < 12 or text.isupper())
                user_gen += int(is_user)
                q = random.randint(1, 10)
                scores.append(q)
                gcse = _rand_gcse()
                name_conf = random.randint(1, 10)
                sens_conf = random.randint(1, 10)
                session.add(
                    Prompt(
                        prompt_id=pid,
                        user_id=f"user-{c % 12:02d}",
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
        await session.commit()
    return {"conversations": conversations, "prompts": n_prompts}


async def clear() -> dict[str, int]:
    """Remove all seeded prompt/analysis data.

    Only touches the three analysis tables — credentials (``app_config``) and
    user accounts (``app_users``) are never affected.
    """
    async with SessionLocal() as session:
        await session.execute(delete(ConversationAnalysis))
        await session.execute(delete(PromptAnalysis))
        await session.execute(delete(Prompt))
        await session.commit()
    return {"cleared": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo prompt-analysis data.")
    parser.add_argument("--conversations", type=int, default=40)
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
    print(f"Seeded {stats['prompts']} prompts across {stats['conversations']} conversations.")


if __name__ == "__main__":
    main()
