"""LLM analysis stage.

Runs *after* ingest. Finds prompts that have been captured but not yet analysed,
groups them into their conversations, sends each conversation to the analysis
model (see :mod:`shared.llm`), and persists:

* ``prompt_analysis``       - one row per prompt (quality / GCSE / sentiment / category)
* ``conversation_analysis`` - one row per conversation (theme / insight / overall score...)
* ``prompts``               - marked ``analysed=True`` with sensitivity confidences filled in

The whole thing is idempotent and incremental: only ``analysed = False`` prompts
are picked up, and a conversation is (re)analysed as a unit so its aggregate
scores stay consistent. Conversations are processed with bounded concurrency.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.crypto import decrypt
from shared.llm import (
    AzureOpenAIProvider,
    ConversationAnalyser,
    DEFAULT_MODEL,
    LLMError,
)
from shared.models import (
    AppConfig,
    ConversationAnalysis,
    JobRun,
    Prompt,
    PromptAnalysis,
)
from shared.upsert import bulk_upsert

logger = logging.getLogger("worker.analysis")

SessionFactory = Callable[[], AsyncSession]

# Conversations analysed per single-prompt fallback bucket. Prompts with no
# conversation_id are analysed one-per-"conversation" keyed by their own id.
_PROMPT_ANALYSIS_KEYS = [
    "conversation_id",
    "user_generated",
    "sentiment",
    "quality_score",
    "quality_rationale",
    "category",
    "gcse_goal",
    "gcse_context",
    "gcse_source",
    "gcse_expectation",
]
_CONVERSATION_ANALYSIS_KEYS = [
    "sentiment",
    "avg_quality_score",
    "conversation_quality_score",
    "user_generated_ratio",
    "theme",
    "insight",
    "category",
    "improvement",
    "suggested_starter_prompt",
    "prompt_count",
]


class AnalysisError(RuntimeError):
    """Raised when analysis cannot run (e.g. Azure OpenAI not configured)."""


def build_analyser(config: AppConfig) -> ConversationAnalyser:
    """Construct a :class:`ConversationAnalyser` from stored (encrypted) creds."""
    if not (config.aoai_endpoint and config.aoai_key_encrypted):
        raise AnalysisError("Azure OpenAI is not configured.")
    key = decrypt(config.aoai_key_encrypted)
    # NB: ``config.aoai_api_version`` is deliberately ignored — the v1 API
    # surface takes no api-version. The column is kept only so existing rows
    # need no migration.
    provider = AzureOpenAIProvider(
        endpoint=config.aoai_endpoint,
        api_key=key,
        deployment=config.aoai_deployment or DEFAULT_MODEL,
    )
    return ConversationAnalyser(
        provider, analysis_mode=config.analysis_mode or "combined"
    )


async def _load_unanalysed(session: AsyncSession) -> dict[str, list[Prompt]]:
    """Return unanalysed prompts (with text) grouped by conversation key."""
    rows = (
        await session.execute(
            select(Prompt)
            .where(Prompt.analysed.is_(False))
            .where(Prompt.prompt_text.is_not(None))
            .order_by(Prompt.conversation_id, Prompt.prompt_date, Prompt.prompt_id)
        )
    ).scalars().all()
    groups: dict[str, list[Prompt]] = {}
    for row in rows:
        key = row.conversation_id or row.prompt_id
        groups.setdefault(key, []).append(row)
    return groups


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return None


def _as_ratio(value: Any) -> float | None:
    """Coerce ``"80%"`` / ``80`` / ``0.8`` into a 0-100 float."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().rstrip("%")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _persist_rows(
    conversation_key: str,
    prompts: list[Prompt],
    result: dict[str, Any],
) -> tuple[list[dict], dict | None, dict[str, dict]]:
    """Map an LLM result onto DB rows. Pure (no I/O) so it is easy to test.

    Returns ``(prompt_analysis_rows, conversation_analysis_row, prompt_updates)``
    where ``prompt_updates`` maps prompt_id -> {analysed, confidences}.
    """
    text_ids = {p.prompt_id for p in prompts}
    conv_id = prompts[0].conversation_id if prompts else None

    pa_rows: list[dict] = []
    prompt_updates: dict[str, dict] = {}
    for item in result.get("prompts", []):
        row_id = item.get("rowId")
        if row_id not in text_ids:
            continue
        gcse = item.get("gcseScores") or {}
        pa_rows.append(
            {
                "prompt_id": row_id,
                "conversation_id": conv_id,
                "user_generated": _as_bool(item.get("userGenerated")),
                "sentiment": item.get("promptSentiment"),
                "quality_score": item.get("qualityScore"),
                "quality_rationale": item.get("qualityRationale"),
                "category": item.get("promptCategory"),
                "gcse_goal": gcse.get("goal"),
                "gcse_context": gcse.get("context"),
                "gcse_source": gcse.get("source"),
                "gcse_expectation": gcse.get("expectation"),
            }
        )
        prompt_updates[row_id] = {
            "analysed": True,
            "name_confidence": item.get("nameConfidence"),
            "sensitive_confidence": item.get("sensitiveInfoConfidence"),
            "curse_confidence": item.get("curseWordConfidence"),
        }

    ca_row: dict | None = None
    if conv_id:
        conv = result.get("conversation") or {}
        ca_row = {
            "conversation_id": conv_id,
            "sentiment": conv.get("conversationSentiment"),
            "avg_quality_score": _as_ratio(conv.get("averageQualityScore")),
            "conversation_quality_score": conv.get("conversationQualityScore"),
            "user_generated_ratio": _as_ratio(conv.get("userGeneratedRatio")),
            "theme": conv.get("conversationTheme"),
            "insight": conv.get("conversationInsight"),
            "category": conv.get("conversationCategory"),
            "improvement": conv.get("conversationImprovement") or None,
            "suggested_starter_prompt": conv.get("suggestedStarterPrompt") or None,
            "prompt_count": len(prompts),
        }
    return pa_rows, ca_row, prompt_updates


async def run_analysis(
    session_factory: SessionFactory,
    *,
    analyser: ConversationAnalyser | None = None,
    config: AppConfig | None = None,
    job_name: str = "analysis",
    max_conversations: int | None = None,
) -> dict[str, Any]:
    """Analyse all pending conversations and record the run in ``job_runs``."""
    async with session_factory() as session:
        if config is None:
            config = await session.get(AppConfig, 1)
            if config is None:
                raise AnalysisError("Azure OpenAI is not configured.")
        if analyser is None:
            analyser = build_analyser(config)

        groups = await _load_unanalysed(session)
        keys = list(groups.keys())
        if max_conversations:
            keys = keys[:max_conversations]

        job = JobRun(job_name=job_name, status="running")
        session.add(job)
        await session.flush()

        sem = asyncio.Semaphore(settings.analysis_concurrency)
        stats = {"conversations": 0, "prompts": 0, "errors": 0}

        async def analyse_one(key: str) -> dict[str, Any] | None:
            prompts = groups[key]
            payload = [
                {"rowId": p.prompt_id, "text": p.prompt_text or ""} for p in prompts
            ]
            async with sem:
                try:
                    result = await analyser.analyse(payload)
                except LLMError as exc:
                    logger.warning("Analysis failed for %s: %s", key, exc)
                    stats["errors"] += 1
                    return None
            return _persist_rows(key, prompts, result)  # type: ignore[return-value]

        try:
            results = await asyncio.gather(*(analyse_one(k) for k in keys))
            for packed in results:
                if not packed:
                    continue
                pa_rows, ca_row, prompt_updates = packed
                if pa_rows:
                    await bulk_upsert(
                        session,
                        PromptAnalysis,
                        pa_rows,
                        index_elements=["prompt_id"],
                        update_keys=_PROMPT_ANALYSIS_KEYS,
                    )
                if ca_row:
                    await bulk_upsert(
                        session,
                        ConversationAnalysis,
                        [ca_row],
                        index_elements=["conversation_id"],
                        update_keys=_CONVERSATION_ANALYSIS_KEYS,
                    )
                for pid, upd in prompt_updates.items():
                    await session.execute(
                        update(Prompt).where(Prompt.prompt_id == pid).values(**upd)
                    )
                    stats["prompts"] += 1
                stats["conversations"] += 1

            job.status = "success"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            logger.info("Analysis '%s' complete: %s", job_name, stats)
            return stats
        except Exception as exc:  # noqa: BLE001 - persisted for observability
            stats["error"] = str(exc)
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            logger.exception("Analysis '%s' failed", job_name)
            raise


async def test_aoai_connection(config: AppConfig) -> dict[str, Any]:
    """Validate Azure OpenAI config with a tiny analysis call. Never raises."""
    result: dict[str, Any] = {"ok": False, "detail": None}
    try:
        analyser = build_analyser(config)
    except AnalysisError as exc:
        result["detail"] = str(exc)
        return result
    try:
        out = await analyser.analyse(
            [{"rowId": "test", "text": "Summarise this document for me please."}]
        )
        result["ok"] = bool(out.get("prompts"))
        result["detail"] = "Model responded with a valid analysis."
    except Exception as exc:  # noqa: BLE001 - reported to caller
        result["detail"] = str(exc)
    return result
