"""Azure OpenAI analysis layer.

Wraps the chat-completions API to turn a Copilot **conversation** (its ordered
prompts) into structured quality / GCSE / sentiment / category scores plus
name / sensitive-info / curse-word confidences.

Design notes
------------
* **Model-agnostic.** The deployment name is configuration, not code. The
  default is ``gpt-5.4-mini`` (a current, GA Azure OpenAI model at time of
  writing); swap it for any deployment (e.g. ``gpt-5.6-terra`` for higher
  accuracy, ``gpt-5.4-nano`` for lowest cost) in Settings without a code change.
* **Structured Outputs.** Responses are constrained with a JSON schema
  (``response_format`` = ``json_schema``) so parsing never depends on the model
  "remembering" to avoid markdown. If the configured model/api-version does not
  support ``json_schema``, we fall back to ``json_object`` + tolerant parsing.
* **Pluggable + two modes.** ``analysis_mode="combined"`` (default) does one
  call per conversation returning everything. ``analysis_mode="split"`` runs the
  analyser once per conversation and the sensitivity prompt once per prompt,
  matching the original solution (useful to route sensitivity elsewhere).
* **Provider seam.** Everything goes through :class:`AnalysisProvider`; the
  concrete :class:`AzureOpenAIProvider` can be replaced (tests inject a fake, and
  an OpenAI-compatible or Azure AI Language PII provider could slot in later).

The credentials and model come from the ``app_config`` row (endpoint +
deployment + api-version + Fernet-encrypted key), entered in the admin UI — they
are never baked into the image.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from shared.analysis_prompts import (
    ANALYSER_ONLY_SYSTEM_PROMPT,
    COMBINED_SYSTEM_PROMPT,
    COMBINED_USER_TEMPLATE,
    PROMPT_CATEGORIES,
    SENSITIVITY_SYSTEM_PROMPT,
    SENSITIVITY_USER_TEMPLATE,
    SENTIMENTS,
)

logger = logging.getLogger("shared.llm")

DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_API_VERSION = "2025-01-01-preview"


class LLMError(RuntimeError):
    """Raised when the analysis model cannot be reached or returns garbage."""


# --------------------------------------------------------------------------
# JSON schemas (Structured Outputs)
# --------------------------------------------------------------------------
def _gcse_schema() -> dict[str, Any]:
    lever = {"type": "integer", "minimum": 1, "maximum": 10}
    return {
        "type": "object",
        "properties": {
            "goal": lever,
            "context": lever,
            "source": lever,
            "expectation": lever,
        },
        "required": ["goal", "context", "source", "expectation"],
        "additionalProperties": False,
    }


def _prompt_item_schema(*, with_sensitivity: bool) -> dict[str, Any]:
    conf = {"type": "integer", "minimum": 1, "maximum": 10}
    props: dict[str, Any] = {
        "rowId": {"type": "string"},
        "userGenerated": {"type": "boolean"},
        "promptSentiment": {"type": "string", "enum": SENTIMENTS},
        "qualityScore": {"type": "integer", "minimum": 1, "maximum": 10},
        "qualityRationale": {"type": "string"},
        "promptCategory": {"type": "string", "enum": PROMPT_CATEGORIES},
        "gcseScores": _gcse_schema(),
    }
    required = list(props.keys())
    if with_sensitivity:
        props["nameConfidence"] = conf
        props["sensitiveInfoConfidence"] = conf
        props["curseWordConfidence"] = conf
        required += ["nameConfidence", "sensitiveInfoConfidence", "curseWordConfidence"]
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _conversation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "conversationSentiment": {"type": "string", "enum": SENTIMENTS},
            "averageQualityScore": {"type": "number"},
            "conversationQualityScore": {"type": "integer", "minimum": 1, "maximum": 10},
            "userGeneratedRatio": {"type": "integer", "minimum": 0, "maximum": 100},
            "conversationTheme": {"type": "string"},
            "conversationInsight": {"type": "string"},
            "conversationCategory": {"type": "string", "enum": PROMPT_CATEGORIES},
            "conversationImprovement": {"type": "string"},
            "suggestedStarterPrompt": {"type": "string"},
        },
        "required": [
            "conversationSentiment",
            "averageQualityScore",
            "conversationQualityScore",
            "userGeneratedRatio",
            "conversationTheme",
            "conversationInsight",
            "conversationCategory",
            "conversationImprovement",
            "suggestedStarterPrompt",
        ],
        "additionalProperties": False,
    }


def conversation_analysis_schema(*, with_sensitivity: bool) -> dict[str, Any]:
    """Top-level schema returned by the analyser call."""
    return {
        "type": "object",
        "properties": {
            "prompts": {
                "type": "array",
                "items": _prompt_item_schema(with_sensitivity=with_sensitivity),
            },
            "conversation": _conversation_schema(),
        },
        "required": ["prompts", "conversation"],
        "additionalProperties": False,
    }


def sensitivity_schema() -> dict[str, Any]:
    conf = {"type": "integer", "minimum": 1, "maximum": 10}
    return {
        "type": "object",
        "properties": {
            "nameConfidence": conf,
            "sensitiveInfoConfidence": conf,
            "curseWordConfidence": conf,
        },
        "required": ["nameConfidence", "sensitiveInfoConfidence", "curseWordConfidence"],
        "additionalProperties": False,
    }


# --------------------------------------------------------------------------
# Provider interface
# --------------------------------------------------------------------------
class AnalysisProvider(Protocol):
    """Minimal seam the engine depends on (real Azure OpenAI, or a test fake)."""

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        """Return a parsed JSON object honouring ``schema``."""
        ...


class AzureOpenAIProvider:
    """Concrete provider backed by the ``openai`` SDK's ``AsyncAzureOpenAI``."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = DEFAULT_API_VERSION,
    ) -> None:
        if not (endpoint and api_key and deployment):
            raise LLMError("Azure OpenAI endpoint, key and deployment are required.")
        # Imported lazily so the package is only needed where analysis runs.
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "The 'openai' package is required for analysis. Install it "
                "(it is in the project dependencies)."
            ) from exc

        self._deployment = deployment
        self._client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # Prefer strict Structured Outputs; fall back to json_object if the
        # model/api-version rejects json_schema.
        try:
            resp = await self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": schema,
                        "strict": True,
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001 - broad on purpose, then retry
            logger.warning(
                "json_schema response_format failed (%s); retrying as json_object", exc
            )
            resp = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system + "\nReturn ONLY valid JSON."},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )

        content = (resp.choices[0].message.content or "").strip()
        return _loads(content)


def _loads(content: str) -> dict[str, Any]:
    """Parse a model response, tolerating stray markdown fences."""
    if content.startswith("```"):
        content = content.strip("`")
        # drop a leading "json" language tag if present
        newline = content.find("\n")
        if newline != -1 and content[:newline].strip().lower() in {"json", ""}:
            content = content[newline + 1 :]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model did not return valid JSON: {exc}") from exc


# --------------------------------------------------------------------------
# High-level analyser
# --------------------------------------------------------------------------
class ConversationAnalyser:
    """Runs the analysis prompts against a provider, in combined or split mode."""

    def __init__(
        self,
        provider: AnalysisProvider,
        *,
        analysis_mode: str = "combined",
    ) -> None:
        self._provider = provider
        self._mode = analysis_mode if analysis_mode in {"combined", "split"} else "combined"

    async def analyse(self, prompts: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyse one conversation.

        ``prompts`` is a list of ``{"rowId": str, "text": str}`` in order. Returns
        ``{"prompts": [...], "conversation": {...}}`` where each prompt entry
        includes the sensitivity confidences (in both modes).
        """
        if not prompts:
            raise LLMError("Cannot analyse an empty conversation.")
        if self._mode == "combined":
            return await self._analyse_combined(prompts)
        return await self._analyse_split(prompts)

    async def _analyse_combined(self, prompts: list[dict[str, Any]]) -> dict[str, Any]:
        user = COMBINED_USER_TEMPLATE.format(
            conversation_json=json.dumps(prompts, ensure_ascii=False, indent=2)
        )
        return await self._provider.complete_json(
            system=COMBINED_SYSTEM_PROMPT,
            user=user,
            schema=conversation_analysis_schema(with_sensitivity=True),
            schema_name="copilot_conversation_analysis",
        )

    async def _analyse_split(self, prompts: list[dict[str, Any]]) -> dict[str, Any]:
        # 1) analyser (quality/GCSE/sentiment/category) — one call per conversation
        user = COMBINED_USER_TEMPLATE.format(
            conversation_json=json.dumps(prompts, ensure_ascii=False, indent=2)
        )
        analysis = await self._provider.complete_json(
            system=ANALYSER_ONLY_SYSTEM_PROMPT,
            user=user,
            schema=conversation_analysis_schema(with_sensitivity=False),
            schema_name="copilot_conversation_analysis",
        )
        # 2) sensitivity — one call per prompt, merged back onto each entry
        by_row = {p["rowId"]: p for p in analysis.get("prompts", [])}
        for prompt in prompts:
            row_id = prompt["rowId"]
            sens = await self._provider.complete_json(
                system=SENSITIVITY_SYSTEM_PROMPT,
                user=SENSITIVITY_USER_TEMPLATE.format(prompt_text=prompt.get("text", "")),
                schema=sensitivity_schema(),
                schema_name="copilot_prompt_sensitivity",
            )
            target = by_row.get(row_id)
            if target is not None:
                target["nameConfidence"] = sens.get("nameConfidence")
                target["sensitiveInfoConfidence"] = sens.get("sensitiveInfoConfidence")
                target["curseWordConfidence"] = sens.get("curseWordConfidence")
        return analysis
