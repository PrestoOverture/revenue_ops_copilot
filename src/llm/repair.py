import json
import logging
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)
REPAIR_MODEL = "gpt-4o-mini"


# repair a JSON payload using the LLM and return the repaired JSON or None if the repair fails
async def repair_json(
    llm_client: LLMClient,  # LLM client to use for the repair
    invalid_json: str,  # JSON payload to repair
    schema: dict,  # JSON schema to repair the JSON payload to
) -> dict | None:  # repaired JSON payload or None if the repair fails
    logger.info(
        "repair_json_attempt_started",
        extra={
            "model": REPAIR_MODEL,
            "invalid_json_length": len(invalid_json),
            "schema_keys": sorted(schema.keys()),
        },
    )

    messages = _build_repair_messages(invalid_json=invalid_json, schema=schema)

    try:
        response = await llm_client.chat_completion(
            model=REPAIR_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.warning(
            "repair_json_llm_call_failed",
            extra={"model": REPAIR_MODEL, "error_type": type(exc).__name__},
            exc_info=exc,
        )
        return None

    content = response["content"]
    if not isinstance(content, str):
        logger.warning(
            "repair_json_response_content_invalid",
            extra={"model": REPAIR_MODEL, "content_type": type(content).__name__},
        )
        return None

    try:
        repaired = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning(
            "repair_json_parse_failed",
            extra={"model": REPAIR_MODEL, "error_type": type(exc).__name__},
            exc_info=exc,
        )
        return None

    if not isinstance(repaired, dict):
        logger.warning(
            "repair_json_result_not_object",
            extra={"model": REPAIR_MODEL, "parsed_type": type(repaired).__name__},
        )
        return None

    logger.info(
        "repair_json_attempt_succeeded",
        extra={"model": REPAIR_MODEL, "repaired_keys": sorted(repaired.keys())},
    )
    return repaired


# build the messages for the repair prompt
def _build_repair_messages(invalid_json: str, schema: dict) -> list[dict[str, str]]:
    schema_json = json.dumps(schema, ensure_ascii=True, sort_keys=True)
    return [
        {
            "role": "system",
            "content": (
                "You repair invalid JSON. Return only valid JSON that conforms to "
                "the provided JSON schema."
            ),
        },
        {
            "role": "user",
            "content": (
                "Fix the JSON below to conform to the schema.\n\n"
                f"Schema:\n{schema_json}\n\n"
                f"Invalid JSON:\n{invalid_json}"
            ),
        },
    ]
