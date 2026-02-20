import json
import pytest
from pydantic import ValidationError
from src.llm.prompts.draft import DraftOutput, build_draft_prompt, parse_draft_response

# test that the build_draft_prompt function builds a prompt with a system and user message
def test_build_draft_prompt_contains_lead_and_qualification_context() -> None:
    lead_data = {
        "email": "prospect@example.com",
        "name": "Alex Kim",
        "company": "Orbit Labs",
        "source": "inbound",
    }
    qualification = {
        "priority": "P1",
        "budget_range": "mid_market",
        "timeline": "30_days",
        "notes": "Interested in implementation this quarter.",
    }

    messages = build_draft_prompt(lead_data=lead_data, qualification=qualification)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "prospect@example.com" in messages[1]["content"]
    assert "Orbit Labs" in messages[1]["content"]
    assert "P1" in messages[1]["content"]
    assert "mid_market" in messages[1]["content"]
    assert "30_days" in messages[1]["content"]
    assert "Interested in implementation this quarter." in messages[1]["content"]

# test that the parse_draft_response function parses a valid JSON response
def test_parse_draft_response_valid_json() -> None:
    response = json.dumps(
        {
            "subject": "Quick follow-up on your inquiry",
            "body": "Hi Alex,\n\nThanks for reaching out. Happy to connect.",
            "tone": "professional",
        }
    )

    parsed = parse_draft_response(response)

    assert isinstance(parsed, DraftOutput)
    assert parsed.subject == "Quick follow-up on your inquiry"
    assert parsed.body == "Hi Alex,\n\nThanks for reaching out. Happy to connect."
    assert parsed.tone == "professional"

# test that the parse_draft_response function raises a ValidationError if the subject is empty
def test_parse_draft_response_empty_subject_raises_validation_error() -> None:
    response = json.dumps(
        {
            "subject": "",
            "body": "Hello there",
            "tone": "friendly",
        }
    )

    with pytest.raises(ValidationError):
        parse_draft_response(response)

# test that the parse_draft_response function raises a ValidationError if the body is empty
def test_parse_draft_response_empty_body_raises_validation_error() -> None:
    response = json.dumps(
        {
            "subject": "Hello there",
            "body": "",
            "tone": "friendly",
        }
    )

    with pytest.raises(ValidationError):
        parse_draft_response(response)

# test that the parse_draft_response function raises a JSONDecodeError if the response is not valid JSON
def test_parse_draft_response_invalid_json_raises_json_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_draft_response("not valid json")
