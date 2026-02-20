from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest

from src.llm.client import LLMClient
from src.llm.repair import repair_json


@pytest.mark.asyncio
async def test_repair_json_successful_repair() -> None:
    schema = {"type": "object", "properties": {"priority": {"type": "string"}}}
    repaired_payload = {"priority": "P1", "routing": "AUTO"}

    with patch.object(LLMClient, "chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "content": '{"priority":"P1","routing":"AUTO"}',
            "tokens_in": 10,
            "tokens_out": 5,
        }
        llm_client = LLMClient(api_key="test-api-key")

        result = await repair_json(
            llm_client=llm_client,
            invalid_json='{"priority":"P1"',
            schema=schema,
        )

        assert result == repaired_payload
        mock_chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_json_invalid_repair_returns_none() -> None:
    schema = {"type": "object", "properties": {"priority": {"type": "string"}}}

    with patch.object(LLMClient, "chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "content": "this is not valid json",
            "tokens_in": 12,
            "tokens_out": 4,
        }
        llm_client = LLMClient(api_key="test-api-key")

        result = await repair_json(
            llm_client=llm_client,
            invalid_json='{"priority":"P1"',
            schema=schema,
        )

        assert result is None
        mock_chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_json_llm_error_returns_none() -> None:
    schema = {"type": "object"}
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

    with patch.object(LLMClient, "chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = openai.APIError("LLM unavailable", request=request, body=None)
        llm_client = LLMClient(api_key="test-api-key")

        result = await repair_json(
            llm_client=llm_client,
            invalid_json='{"priority":"P1"',
            schema=schema,
        )

        assert result is None
        mock_chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_json_truncated_input_still_attempts_repair() -> None:
    truncated_input = '{"priority":"P1","notes":"needs fol'
    schema = {
        "type": "object",
        "properties": {
            "priority": {"type": "string"},
            "notes": {"type": "string"},
        },
    }

    with patch.object(LLMClient, "chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "content": '{"priority":"P1","notes":"needs follow up"}',
            "tokens_in": 20,
            "tokens_out": 8,
        }
        llm_client = LLMClient(api_key="test-api-key")

        result = await repair_json(
            llm_client=llm_client,
            invalid_json=truncated_input,
            schema=schema,
        )

        assert result == {"priority": "P1", "notes": "needs follow up"}
        mock_chat.assert_awaited_once()
        call_kwargs = mock_chat.await_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert truncated_input in call_kwargs["messages"][1]["content"]
