import json

from pydantic import BaseModel, Field

PROMPT_VERSION = "draft_v1.0"


class DraftOutput(BaseModel):
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    tone: str


def build_draft_prompt(lead_data: dict, qualification: dict) -> list[dict[str, str]]:
    schema_json = json.dumps(
        DraftOutput.model_json_schema(),
        ensure_ascii=True,
        sort_keys=True,
    )
    lead_data_json = json.dumps(lead_data, ensure_ascii=True, sort_keys=True, default=str)
    qualification_context = {
        "priority": qualification.get("priority"),
        "budget_range": qualification.get("budget_range"),
        "timeline": qualification.get("timeline"),
        "notes": qualification.get("notes"),
    }
    qualification_json = json.dumps(
        qualification_context,
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )
    system_prompt = (
        f"You are a sales email drafting assistant. Prompt version: {PROMPT_VERSION}. "
        "Return only JSON and make it conform exactly to this schema: "
        f"{schema_json}"
    )
    user_prompt = (
        "Draft an outreach email using the lead context and qualification summary.\n\n"
        f"Lead data:\n{lead_data_json}\n\n"
        f"Qualification context:\n{qualification_json}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_draft_response(response: str) -> DraftOutput:
    parsed = json.loads(response)
    return DraftOutput(**parsed)
