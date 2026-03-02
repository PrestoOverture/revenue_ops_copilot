import json
import pytest
from pydantic import ValidationError
from src.llm.prompts.qualify import (
    FALLBACK_QUALIFICATION,
    PROMPT_VERSION,
    QualificationOutput,
    build_qualify_prompt,
    parse_qualify_response,
)

# test that the build_qualify_prompt function builds a prompt with a system and user message
def test_build_qualify_prompt_contains_system_and_user_messages() -> None:
    lead_data = {
        "email": "buyer@example.com",
        "company": "Acme Corp",
        "source": "web_form",
        "raw_payload": {"employees": 350, "use_case": "automation"},
        "name": "Jamie Lee",
    }

    messages = build_qualify_prompt(lead_data)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "buyer@example.com" in messages[1]["content"]
    assert "Acme Corp" in messages[1]["content"]
    assert "web_form" in messages[1]["content"]
    assert "raw_payload" in messages[1]["content"]
    assert "Priority Tier Definitions" in messages[0]["content"]
    assert "Policy Decision Rules" in messages[0]["content"]
    assert "Routing Rules" in messages[0]["content"]
    assert "Timeline Inference Rules" in messages[0]["content"]


def test_qualify_prompt_version_is_v2() -> None:
    assert PROMPT_VERSION == "qualify_v2.0"


def test_user_prompt_contains_few_shot_examples() -> None:
    messages = build_qualify_prompt({"email": "test@example.com"})
    user_prompt = messages[1]["content"]

    assert "Example 1 (P0/ALLOW)" in user_prompt
    assert "Example 2 (P2/REQUIRE_REVIEW)" in user_prompt
    assert "Example 3 (P3/BLOCK)" in user_prompt


def test_user_prompt_does_not_include_conservative_bias_phrase() -> None:
    messages = build_qualify_prompt({"email": "test@example.com"})
    user_prompt = messages[1]["content"].lower()
    assert "choose policy_decision and routing conservatively" not in user_prompt

# test that the parse_qualify_response function parses a valid JSON response
def test_parse_qualify_response_valid_json() -> None:
    response_json = json.dumps(
        {
            "priority": "P1",
            "budget_range": "mid_market",
            "timeline": "30_days",
            "notes": "Strong buying signal.",
            "routing": "AUTO",
            "policy_decision": "ALLOW",
        }
    )

    parsed = parse_qualify_response(response_json)

    assert isinstance(parsed, QualificationOutput)
    assert parsed.priority == "P1"
    assert parsed.budget_range == "mid_market"
    assert parsed.timeline == "30_days"
    assert parsed.routing == "AUTO"
    assert parsed.policy_decision == "ALLOW"

# test that the parse_qualify_response function raises a JSONDecodeError if the response is not valid JSON
def test_parse_qualify_response_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_qualify_response("not a json document")

# test that the parse_qualify_response function raises a ValidationError if the response is not valid against the schema
def test_parse_qualify_response_invalid_schema_raises() -> None:
    invalid_schema_json = json.dumps(
        {
            "priority": "P9",
            "budget_range": "mid_market",
            "timeline": "30_days",
            "notes": "Invalid priority enum.",
            "routing": "AUTO",
            "policy_decision": "ALLOW",
        }
    )

    with pytest.raises(ValidationError):
        parse_qualify_response(invalid_schema_json)

# test that the fallback qualification defaults are set correctly
def test_fallback_qualification_defaults() -> None:
    assert FALLBACK_QUALIFICATION.priority == "P2"
    assert FALLBACK_QUALIFICATION.budget_range == "unknown"
    assert FALLBACK_QUALIFICATION.timeline == "exploratory"
    assert FALLBACK_QUALIFICATION.notes == "Fallback due to LLM failure"
    assert FALLBACK_QUALIFICATION.routing == "REQUIRE_REVIEW"
    assert FALLBACK_QUALIFICATION.policy_decision == "REQUIRE_REVIEW"
