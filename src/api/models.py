from typing import Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator

# webhook payload schema
class WebhookPayload(BaseModel):
    tenant_id: UUID
    external_lead_id: str
    dedupe_key: str
    event_type: str = "lead.created"
    email: EmailStr
    name: str | None = None
    company: str | None = None
    source: str | None = None

    # validate external lead id
    @field_validator("external_lead_id", mode="before")
    @classmethod
    def validate_external_lead_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_lead_id must not be empty")
        return normalized

    # validate dedupe key
    @field_validator("dedupe_key", mode="before")
    @classmethod
    def validate_dedupe_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("dedupe_key must not be empty")
        return normalized

# webhook response schema
class WebhookResponse(BaseModel):
    workflow_id: str
    status: str

# approval request schema
class ApprovalRequest(BaseModel):
    action: Literal["approve", "cancel"]

# lead status response schema
class LeadStatusResponse(BaseModel):
    lead_id: UUID
    tenant_id: UUID
    external_lead_id: str
    email: str
    state: str
    priority: str | None = None
    budget_range: str | None = None
    timeline: str | None = None
    routing: str | None = None
    touchpoint_count: int = 0
    created_at: str
    updated_at: str
