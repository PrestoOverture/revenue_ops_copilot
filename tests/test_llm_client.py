import json

import httpx
import openai
import pytest
import respx

from src.llm.client import LLMClient


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_happy_path() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-test-1",
                "object": "chat.completion",
                "created": 1_707_000_000,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Qualified lead"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 35,
                    "total_tokens": 155,
                },
            },
        )
    )
    client = LLMClient(api_key="test-api-key")

    response = await client.chat_completion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Qualify this lead"}],
    )

    assert route.called
    assert response == {
        "content": "Qualified lead",
        "tokens_in": 120,
        "tokens_out": 35,
    }


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_with_response_format() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-test-2",
                "object": "chat.completion",
                "created": 1_707_000_000,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": '{"priority":"P1","routing":"AUTO"}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 22,
                    "total_tokens": 102,
                },
            },
        )
    )
    client = LLMClient(api_key="test-api-key")

    response = await client.chat_completion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Return JSON"}],
        response_format={"type": "json_object"},
    )

    assert route.called
    request_payload = json.loads(route.calls[0].request.content.decode("utf-8"))
    assert request_payload["response_format"] == {"type": "json_object"}
    assert response == {
        "content": '{"priority":"P1","routing":"AUTO"}',
        "tokens_in": 80,
        "tokens_out": 22,
    }


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_rate_limit_error_propagates() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            429,
            json={
                "error": {
                    "message": "Rate limit exceeded",
                    "type": "rate_limit_error",
                    "param": None,
                    "code": "rate_limit_exceeded",
                }
            },
        )
    )
    client = LLMClient(api_key="test-api-key")

    with pytest.raises(openai.RateLimitError):
        await client.chat_completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Qualify this lead"}],
        )


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_timeout_error_propagates() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=httpx.ReadTimeout("Request timed out")
    )
    client = LLMClient(api_key="test-api-key")

    with pytest.raises(openai.APITimeoutError):
        await client.chat_completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Qualify this lead"}],
        )
