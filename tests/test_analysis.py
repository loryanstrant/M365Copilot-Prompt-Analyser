"""Tests for the LLM analysis layer (no network — a fake provider is injected)."""
from __future__ import annotations

import pytest

from shared.llm import (
    ConversationAnalyser,
    conversation_analysis_schema,
    sensitivity_schema,
)
from worker import analysis as wa
from worker.transforms import clean_prompt_text, extract_prompt_text


def _analysis_result(row_ids: list[str], *, with_sensitivity: bool = True) -> dict:
    prompts = []
    for rid in row_ids:
        item = {
            "rowId": rid,
            "userGenerated": True,
            "promptSentiment": "neutral",
            "qualityScore": 7,
            "qualityRationale": "clear intent",
            "promptCategory": "summarise",
            "gcseScores": {"goal": 8, "context": 6, "source": 5, "expectation": 7},
        }
        if with_sensitivity:
            item |= {
                "nameConfidence": 2,
                "sensitiveInfoConfidence": 3,
                "curseWordConfidence": 1,
            }
        prompts.append(item)
    return {
        "prompts": prompts,
        "conversation": {
            "conversationSentiment": "neutral",
            "averageQualityScore": 7.0,
            "conversationQualityScore": 7,
            "userGeneratedRatio": 100,
            "conversationTheme": "theme",
            "conversationInsight": "insight",
            "conversationCategory": "summarise",
            "conversationImprovement": "",
            "suggestedStarterPrompt": "",
        },
    }


class FakeProvider:
    """Records calls and returns canned, schema-shaped payloads."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete_json(self, *, system, user, schema, schema_name):
        self.calls.append(schema_name)
        if schema_name == "copilot_prompt_sensitivity":
            return {
                "nameConfidence": 4,
                "sensitiveInfoConfidence": 5,
                "curseWordConfidence": 1,
            }
        # analyser (combined or analyser-only): infer row ids from the schema arity
        with_sens = "nameConfidence" in str(schema)
        return _analysis_result(["p1", "p2"], with_sensitivity=with_sens)


# --- prompt-text cleaning ------------------------------------------------
def test_clean_prompt_text_strips_html_and_attachments() -> None:
    raw = "<p>Summarise&nbsp;this <attachment id='x'>FILE</attachment> please</p>"
    assert clean_prompt_text(raw, "html") == "Summarise this please"


def test_clean_prompt_text_plain_passthrough() -> None:
    assert clean_prompt_text("  Draft an email  ", "text") == "Draft an email"


def test_clean_prompt_text_empty() -> None:
    assert clean_prompt_text("", "text") is None
    assert clean_prompt_text(None, None) is None


def test_extract_prompt_text_from_body() -> None:
    raw = {"body": {"content": "<b>Hello</b>", "contentType": "html"}}
    assert extract_prompt_text(raw) == "Hello"


# --- analyser (combined) -------------------------------------------------
@pytest.mark.asyncio
async def test_combined_mode_single_call() -> None:
    provider = FakeProvider()
    analyser = ConversationAnalyser(provider, analysis_mode="combined")
    out = await analyser.analyse(
        [{"rowId": "p1", "text": "a"}, {"rowId": "p2", "text": "b"}]
    )
    assert provider.calls == ["copilot_conversation_analysis"]  # exactly one call
    assert len(out["prompts"]) == 2
    assert out["prompts"][0]["nameConfidence"] == 2


# --- analyser (split) ----------------------------------------------------
@pytest.mark.asyncio
async def test_split_mode_merges_sensitivity_per_prompt() -> None:
    provider = FakeProvider()
    analyser = ConversationAnalyser(provider, analysis_mode="split")
    out = await analyser.analyse(
        [{"rowId": "p1", "text": "a"}, {"rowId": "p2", "text": "b"}]
    )
    # 1 analyser call + 1 sensitivity call per prompt
    assert provider.calls.count("copilot_conversation_analysis") == 1
    assert provider.calls.count("copilot_prompt_sensitivity") == 2
    # sensitivity values came from the per-prompt call, not the analyser
    assert out["prompts"][0]["sensitiveInfoConfidence"] == 5


@pytest.mark.asyncio
async def test_empty_conversation_raises() -> None:
    with pytest.raises(Exception):
        await ConversationAnalyser(FakeProvider()).analyse([])


# --- DB mapping ----------------------------------------------------------
class _FakePrompt:
    def __init__(self, pid: str, conv: str) -> None:
        self.prompt_id = pid
        self.conversation_id = conv
        self.prompt_text = "x"
        self.prompt_date = None


def test_persist_rows_maps_scores_and_confidences() -> None:
    prompts = [_FakePrompt("p1", "c1"), _FakePrompt("p2", "c1")]
    result = _analysis_result(["p1", "p2"])
    pa_rows, ca_row, updates = wa._persist_rows("c1", prompts, result)

    assert {r["prompt_id"] for r in pa_rows} == {"p1", "p2"}
    assert pa_rows[0]["quality_score"] == 7
    assert pa_rows[0]["gcse_goal"] == 8
    assert ca_row["conversation_id"] == "c1"
    assert ca_row["conversation_quality_score"] == 7
    assert ca_row["prompt_count"] == 2
    assert updates["p1"]["analysed"] is True
    assert updates["p1"]["sensitive_confidence"] == 3


def test_persist_rows_ratio_coercion() -> None:
    prompts = [_FakePrompt("p1", "c1")]
    result = _analysis_result(["p1"])
    result["conversation"]["userGeneratedRatio"] = "80%"
    _, ca_row, _ = wa._persist_rows("c1", prompts, result)
    assert ca_row["user_generated_ratio"] == 80.0


def test_schemas_are_serialisable() -> None:
    import json

    json.dumps(conversation_analysis_schema(with_sensitivity=True))
    json.dumps(conversation_analysis_schema(with_sensitivity=False))
    json.dumps(sensitivity_schema())
