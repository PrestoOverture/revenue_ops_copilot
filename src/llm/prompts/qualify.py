import json
from typing import Literal
from pydantic import BaseModel

PROMPT_VERSION = "qualify_v1.0"

# output schema for the qualification prompt
class QualificationOutput(BaseModel):
    priority: Literal["P0", "P1", "P2", "P3"]
    budget_range: Literal["enterprise", "mid_market", "smb", "unknown"]
    timeline: Literal["immediate", "30_days", "90_days", "exploratory"]
    notes: str
    routing: Literal["AUTO", "REQUIRE_REVIEW"]
    policy_decision: Literal["ALLOW", "BLOCK", "REQUIRE_REVIEW"]

# fallback qualification defaults
FALLBACK_QUALIFICATION = QualificationOutput(
    priority="P2",
    budget_range="unknown",
    timeline="exploratory",
    notes="Fallback due to LLM failure",
    routing="REQUIRE_REVIEW",
    policy_decision="REQUIRE_REVIEW",
)

# build the messages for the qualification prompt
def build_qualify_prompt(lead_data: dict) -> list[dict[str, str]]:
    schema_json = json.dumps(
        QualificationOutput.model_json_schema(),
        ensure_ascii=True,
        sort_keys=True,
    )
    lead_data_json = json.dumps(lead_data, ensure_ascii=True, sort_keys=True, default=str)
    system_prompt = (
        f"You are a lead qualification assistant. Prompt version: {PROMPT_VERSION}. "
        "Return only JSON and make it conform exactly to this schema: "
        f"{schema_json}"
    )
    user_prompt = (
        "Qualify the lead using the following lead_state data. "
        "Choose policy_decision and routing conservatively for uncertain inputs.\n\n"
        f"Lead data:\n{lead_data_json}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

# parse the response from the qualification prompt
def parse_qualify_response(response: str) -> QualificationOutput:
    parsed = json.loads(response)
    return QualificationOutput(**parsed)
