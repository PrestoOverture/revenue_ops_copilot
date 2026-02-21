from pydantic import BaseModel
from src.llm.prompts.draft import DraftOutput
from src.llm.prompts.qualify import QualificationOutput

# input schema for the lead workflow
class LeadWorkflowInput(BaseModel):
    lead_id: str
    tenant_id: str
    external_lead_id: str
    approval_required: bool = True
    followups_enabled: bool = True

# result schema for the lead workflow
class LeadWorkflowResult(BaseModel):
    status: str
    error: str | None = None

# result schema for the qualification activity
class QualificationResult(QualificationOutput):
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    repair_attempted: bool = False
    fallback_used: str | None = None

# result schema for the draft activity
class DraftResult(DraftOutput):
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    repair_attempted: bool = False
    fallback_used: str | None = None

# input schema for the followup workflow
class FollowupWorkflowInput(BaseModel):
    lead_id: str
    tenant_id: str
    external_lead_id: str
    touchpoint: int
    max_touchpoints: int = 3
    qualification: QualificationResult

# result schema for the followup workflow
class FollowupWorkflowResult(BaseModel):
    status: str
    touchpoint: int
    error: str | None = None
