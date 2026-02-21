import pytest
from pydantic import ValidationError
from src.workflows.models import (
    DraftResult,
    FollowupWorkflowInput,
    FollowupWorkflowResult,
    LeadWorkflowInput,
    LeadWorkflowResult,
    QualificationResult,
)

# test lead workflow input serialization
def test_lead_workflow_input_serialization() -> None:
    original = LeadWorkflowInput(
        lead_id="550e8400-e29b-41d4-a716-446655440000",
        tenant_id="550e8400-e29b-41d4-a716-446655440001",
        external_lead_id="hubspot-123",
        approval_required=False,
        followups_enabled=False,
    )

    serialized = original.model_dump_json()
    deserialized = LeadWorkflowInput.model_validate_json(serialized)

    assert deserialized == original

# test lead workflow input defaults
def test_lead_workflow_input_defaults() -> None:
    payload = LeadWorkflowInput(
        lead_id="550e8400-e29b-41d4-a716-446655440000",
        tenant_id="550e8400-e29b-41d4-a716-446655440001",
        external_lead_id="salesforce-456",
    )

    assert payload.approval_required is True
    assert payload.followups_enabled is True

# test lead workflow result serialization
def test_lead_workflow_result_serialization() -> None:
    success_result = LeadWorkflowResult(status="COMPLETED")
    success_roundtrip = LeadWorkflowResult.model_validate_json(
        success_result.model_dump_json()
    )
    assert success_roundtrip == success_result

    failed_result = LeadWorkflowResult(status="FAILED", error="Something went wrong")
    failed_roundtrip = LeadWorkflowResult.model_validate_json(
        failed_result.model_dump_json()
    )
    assert failed_roundtrip == failed_result

# test lead workflow result error default
def test_lead_workflow_result_error_default() -> None:
    result = LeadWorkflowResult(status="COMPLETED")
    assert result.error is None

# test qualification result serialization
def test_qualification_result_serialization() -> None:
    original = QualificationResult(
        priority="P0",
        budget_range="enterprise",
        timeline="immediate",
        notes="Budget approved and ready to buy this quarter.",
        routing="AUTO",
        policy_decision="ALLOW",
        model="gpt-4o-mini",
        prompt_version="qualify_v1.0",
        tokens_in=120,
        tokens_out=40,
        cost_usd=0.00015,
        repair_attempted=True,
        fallback_used="DEFAULTS",
    )

    serialized = original.model_dump_json()
    deserialized = QualificationResult.model_validate_json(serialized)

    assert deserialized == original

# test qualification result defaults
def test_qualification_result_defaults() -> None:
    result = QualificationResult(
        priority="P2",
        budget_range="unknown",
        timeline="exploratory",
        notes="Limited details; needs manual qualification.",
        routing="REQUIRE_REVIEW",
        policy_decision="REQUIRE_REVIEW",
        model="gpt-4o-mini",
        prompt_version="qualify_v1.0",
        tokens_in=80,
        tokens_out=22,
        cost_usd=0.00005,
    )

    assert result.repair_attempted is False
    assert result.fallback_used is None

# test draft result serialization
def test_draft_result_serialization() -> None:
    original = DraftResult(
        subject="Following up on your request",
        body="Hi there, I wanted to follow up on your recent inquiry.",
        tone="professional",
        model="gpt-4o",
        prompt_version="draft_v1.0",
        tokens_in=250,
        tokens_out=90,
        cost_usd=0.00125,
        repair_attempted=True,
        fallback_used="TEMPLATE",
    )

    serialized = original.model_dump_json()
    deserialized = DraftResult.model_validate_json(serialized)

    assert deserialized == original

# test draft result defaults
def test_draft_result_defaults() -> None:
    result = DraftResult(
        subject="Following up",
        body="Hi there, checking in on your timeline.",
        tone="friendly",
        model="gpt-4o",
        prompt_version="draft_v1.0",
        tokens_in=140,
        tokens_out=55,
        cost_usd=0.0009,
    )

    assert result.repair_attempted is False
    assert result.fallback_used is None

# test required fields validation
def test_required_fields_validation() -> None:
    with pytest.raises(ValidationError):
        LeadWorkflowInput.model_validate(
            {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440001",
                "external_lead_id": "missing-lead-id",
            }
        )

    with pytest.raises(ValidationError):
        QualificationResult.model_validate(
            {
                "priority": "P1",
                "budget_range": "mid_market",
                "timeline": "30_days",
                "notes": "Good fit but missing budget details.",
                "routing": "AUTO",
                "policy_decision": "ALLOW",
                "prompt_version": "qualify_v1.0",
                "tokens_in": 100,
                "tokens_out": 35,
                "cost_usd": 0.00012,
            }
        )

    with pytest.raises(ValidationError):
        DraftResult.model_validate(
            {
                "body": "Missing subject line in this payload.",
                "tone": "direct",
                "model": "gpt-4o",
                "prompt_version": "draft_v1.0",
                "tokens_in": 160,
                "tokens_out": 60,
                "cost_usd": 0.001,
            }
        )

# test followup workflow input serialization
def test_followup_workflow_input_serialization() -> None:
    original = FollowupWorkflowInput(
        lead_id="550e8400-e29b-41d4-a716-446655440000",
        tenant_id="550e8400-e29b-41d4-a716-446655440001",
        external_lead_id="hubspot-123",
        touchpoint=2,
        max_touchpoints=4,
        qualification=QualificationResult(
            priority="P1",
            budget_range="mid_market",
            timeline="30_days",
            notes="Good fit.",
            routing="AUTO",
            policy_decision="ALLOW",
            model="gpt-4o-mini",
            prompt_version="qualify_v1.0",
            tokens_in=100,
            tokens_out=40,
            cost_usd=0.00015,
        ),
    )

    serialized = original.model_dump_json()
    deserialized = FollowupWorkflowInput.model_validate_json(serialized)

    assert deserialized == original

# test followup workflow input defaults
def test_followup_workflow_input_defaults() -> None:
    payload = FollowupWorkflowInput(
        lead_id="550e8400-e29b-41d4-a716-446655440000",
        tenant_id="550e8400-e29b-41d4-a716-446655440001",
        external_lead_id="hubspot-123",
        touchpoint=1,
        qualification=QualificationResult(
            priority="P1",
            budget_range="mid_market",
            timeline="30_days",
            notes="Good fit.",
            routing="AUTO",
            policy_decision="ALLOW",
            model="gpt-4o-mini",
            prompt_version="qualify_v1.0",
            tokens_in=100,
            tokens_out=40,
            cost_usd=0.00015,
        ),
    )

    assert payload.max_touchpoints == 3

# test followup workflow result serialization
def test_followup_workflow_result_serialization() -> None:
    original = FollowupWorkflowResult(
        status="COMPLETED",
        touchpoint=2,
        error=None,
    )

    serialized = original.model_dump_json()
    deserialized = FollowupWorkflowResult.model_validate_json(serialized)

    assert deserialized == original
