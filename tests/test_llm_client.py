"""Tests for the Azure OpenAI **v1** client construction.

The v1 surface (see the API version lifecycle doc) takes no ``api-version``
query parameter and no deployment name in the URL path — the deployment goes in
the request body as ``model``. These tests pin that wire shape, because that is
the part that broke when the dated surface was deprecated.
"""
from __future__ import annotations

import json

import httpx
import pytest

from shared.llm import AzureOpenAIProvider, LLMError, normalise_endpoint


@pytest.mark.parametrize(
    "given",
    [
        "https://my-resource.openai.azure.com",
        "https://my-resource.openai.azure.com/",
        "https://my-resource.openai.azure.com/openai",
        "https://my-resource.openai.azure.com/openai/",
        "https://my-resource.openai.azure.com/openai/v1",
        "https://my-resource.openai.azure.com/openai/v1/",
        "  https://my-resource.openai.azure.com/openai/v1/?api-version=2025-01-01-preview  ",
        "my-resource.openai.azure.com",
        # A full old-style request URL, pasted straight out of the portal.
        (
            "https://my-resource.openai.azure.com/openai/deployments/gpt-5.4-mini"
            "/chat/completions?api-version=2025-01-01-preview"
        ),
    ],
)
def test_normalise_endpoint_accepts_what_people_paste(given: str) -> None:
    assert normalise_endpoint(given) == "https://my-resource.openai.azure.com/openai/v1/"


def test_normalise_endpoint_handles_the_services_hostname() -> None:
    assert (
        normalise_endpoint("https://my-resource.services.ai.azure.com")
        == "https://my-resource.services.ai.azure.com/openai/v1/"
    )


def test_normalise_endpoint_rejects_empty() -> None:
    with pytest.raises(LLMError):
        normalise_endpoint("   ")


def test_provider_requires_endpoint_key_and_deployment() -> None:
    with pytest.raises(LLMError):
        AzureOpenAIProvider(endpoint="", api_key="k", deployment="d")


def test_provider_uses_the_plain_openai_client_on_the_v1_base_url() -> None:
    from openai import AsyncAzureOpenAI, AsyncOpenAI

    provider = AzureOpenAIProvider(
        endpoint="https://my-resource.openai.azure.com",
        api_key="secret",
        deployment="gpt-5.4-mini",
    )
    client = provider._client
    assert isinstance(client, AsyncOpenAI)
    assert not isinstance(client, AsyncAzureOpenAI)
    assert str(client.base_url) == "https://my-resource.openai.azure.com/openai/v1/"


async def test_request_path_carries_no_api_version_and_names_the_model() -> None:
    """Drive a real request through a stub transport and inspect the wire."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-5.4-mini",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"ok": true}'},
                    }
                ],
            },
        )

    provider = AzureOpenAIProvider(
        endpoint="https://my-resource.openai.azure.com",
        api_key="secret",
        deployment="gpt-5.4-mini",
    )
    provider._client = provider._client.with_options(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    out = await provider.complete_json(
        system="sys", user="usr", schema={"type": "object"}, schema_name="s"
    )

    assert out == {"ok": True}
    url = str(seen["url"])
    assert url == "https://my-resource.openai.azure.com/openai/v1/chat/completions"
    assert "api-version" not in url
    # The deployment travels in the body, not the path.
    assert "/deployments/" not in url
    assert seen["body"]["model"] == "gpt-5.4-mini"  # type: ignore[index]


async def test_falls_back_to_json_object_when_json_schema_is_rejected() -> None:
    """The pre-existing Structured Outputs fallback must survive the migration."""
    formats: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        fmt = body.get("response_format", {}).get("type")
        formats.append(fmt)
        if fmt == "json_schema":
            return httpx.Response(
                400, json={"error": {"message": "response_format not supported"}}
            )
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-5.4-mini",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"ok": 1}'},
                    }
                ],
            },
        )

    provider = AzureOpenAIProvider(
        endpoint="https://my-resource.openai.azure.com",
        api_key="secret",
        deployment="gpt-5.4-mini",
    )
    provider._client = provider._client.with_options(
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    out = await provider.complete_json(
        system="sys", user="usr", schema={"type": "object"}, schema_name="s"
    )

    assert out == {"ok": 1}
    assert formats == ["json_schema", "json_object"]
