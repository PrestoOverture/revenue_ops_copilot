import logging
from typing import Any, cast

import openai

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, max_retries=0)

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        response_format: dict | None = None,
    ) -> dict[str, str | int]:
        request_payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if response_format is not None:
            request_payload["response_format"] = response_format

        logger.info(
            "llm_chat_completion_started",
            extra={
                "model": model,
                "message_count": len(messages),
                "has_response_format": response_format is not None,
            },
        )
        response = await self._client.chat.completions.create(**request_payload)
        content = cast(str, response.choices[0].message.content)
        usage = cast(openai.types.CompletionUsage, response.usage)
        tokens_in = usage.prompt_tokens
        tokens_out = usage.completion_tokens
        logger.info(
            "llm_chat_completion_succeeded",
            extra={
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            },
        )

        return {
            "content": content,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
