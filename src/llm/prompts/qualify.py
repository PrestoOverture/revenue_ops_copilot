import json
from typing import Literal
from pydantic import BaseModel

PROMPT_VERSION = "qualify_v2.0"

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
        f"You are a lead qualification assistant. Prompt version: {PROMPT_VERSION}.\n\n"
        "Return only JSON and make it conform exactly to this schema:\n"
        f"{schema_json}\n\n"
        "Priority Tier Definitions:\n"
        "P0 - Enterprise, High Intent:\n"
        "- C-suite or VP titles (CTO, VP Engineering, CIO, VP Product, VP Operations)\n"
        "- Business email domain (not gmail/yahoo/hotmail/outlook)\n"
        "- High-intent source: demo_request, pricing_page, enterprise_inquiry\n"
        "- Budget: enterprise. Timeline: immediate or 30_days.\n\n"
        "P1 - Mid-Market, Moderate Intent:\n"
        "- Director or Manager titles\n"
        "- Business email domain\n"
        "- Moderate-intent source: webinar, whitepaper_download, contact_form\n"
        "- Budget: mid_market. Timeline: 30_days or 90_days.\n\n"
        "P2 - SMB or Exploratory:\n"
        "- Real company name but smaller or unclear size\n"
        "- Lower-intent source: blog_post, organic_search, or unclear\n"
        "- Budget: smb or unknown. Timeline: 90_days or exploratory.\n\n"
        "P3 - Individual, Not Qualified:\n"
        "- No real company (Self-Employed, Freelance, N/A, Independent, Student, "
        "Solo Founder, Personal, Side Hustle, TBD, or empty)\n"
        "- Personal email domain (gmail, yahoo, hotmail, outlook, proton, icloud)\n"
        "- Budget: unknown. Timeline: exploratory.\n\n"
        "Policy Decision Rules:\n"
        "ALLOW - Confident qualification:\n"
        "- Priority is P0 or P1, and no red flags\n"
        "- Priority is P2 with clear budget (smb), real company name, and business email domain\n\n"
        "BLOCK - Reject outright:\n"
        "- Obvious spam (bot-like name, random/nonsense email domain)\n"
        "- Known competitor signals (company name contains \"competitor\")\n"
        "- Blocked/disposable email domains (e.g., mailinator, guerrillamail, temp-mail)\n"
        "- Do not use BLOCK for personal/free email domains alone\n\n"
        "REQUIRE_REVIEW - Human review needed:\n"
        "- Priority is P2 or P3 (unless P2 qualifies for ALLOW above)\n"
        "- Mixed signals (enterprise source but personal email, or vice versa)\n"
        "- Uncertain or ambiguous data\n"
        "- IMPORTANT: P3 leads with personal email domains (gmail, yahoo, etc.) are NOT spam. "
        "They are individuals who need review, not blocking.\n\n"
        "Policy precedence:\n"
        "- BLOCK only when explicit BLOCK signals are present\n"
        "- If not explicit BLOCK and there is uncertainty, use REQUIRE_REVIEW\n"
        "- Personal/free email without spam or competitor signal should usually be REQUIRE_REVIEW\n\n"
        "Routing Rules:\n"
        "- AUTO when policy_decision is ALLOW\n"
        "- REQUIRE_REVIEW when policy_decision is BLOCK or REQUIRE_REVIEW\n\n"
        "Timeline Inference Rules:\n"
        "- immediate: demo_request or pricing_page from enterprise/mid_market leads\n"
        "- 30_days: enterprise_inquiry, or webinar/whitepaper from mid_market leads\n"
        "- 90_days: contact_form, webinar, or whitepaper from SMB leads\n"
        "- exploratory: blog_post, organic_search, or no clear intent signal\n\n"
        "If signals conflict, prioritize safety and policy rules while still applying tier definitions."
    )
    user_prompt = (
        "Qualify the lead using the following lead_state data.\n\n"
        "Few-shot examples (synthetic):\n"
        "Example 1 (P0/ALLOW)\n"
        "Input: {\"name\":\"Dana Patel\",\"title\":\"VP Engineering\",\"email\":\"dana@megacorp.com\","
        "\"company\":\"MegaCorp\",\"source\":\"demo_request\"}\n"
        "Output: {\"priority\":\"P0\",\"budget_range\":\"enterprise\",\"timeline\":\"immediate\","
        "\"notes\":\"Enterprise VP requested demo with high intent.\",\"routing\":\"AUTO\","
        "\"policy_decision\":\"ALLOW\"}\n\n"
        "Example 2 (P2/REQUIRE_REVIEW)\n"
        "Input: {\"name\":\"Chris\",\"title\":\"Consultant\",\"email\":\"chris@unknown-startup.co\","
        "\"company\":\"Unknown Startup\",\"source\":\"blog_post\"}\n"
        "Output: {\"priority\":\"P2\",\"budget_range\":\"unknown\",\"timeline\":\"exploratory\","
        "\"notes\":\"Low intent source and limited company clarity.\",\"routing\":\"REQUIRE_REVIEW\","
        "\"policy_decision\":\"REQUIRE_REVIEW\"}\n\n"
        "Example 3 (P3/BLOCK)\n"
        "Input: {\"name\":\"asdf123\",\"title\":\"N/A\",\"email\":\"bot@zxqv-random.biz\","
        "\"company\":\"\",\"source\":\"contact_form\"}\n"
        "Output: {\"priority\":\"P3\",\"budget_range\":\"unknown\",\"timeline\":\"exploratory\","
        "\"notes\":\"Bot-like signal with suspicious disposable-like domain.\",\"routing\":\"REQUIRE_REVIEW\","
        "\"policy_decision\":\"BLOCK\"}\n\n"
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
