from uuid import uuid4
import pytest
from pydantic import ValidationError
from src.api.models import ApprovalRequest, WebhookPayload, WebhookResponse

# test valid webhook payload
def test_valid_webhook_payload() -> None:
    payload = WebhookPayload(
        tenant_id=uuid4(),
        external_lead_id="lead-123",
        dedupe_key="dedupe-123",
        email="alice@example.com",
        name="Alice",
        company="Acme",
        source="web",
    )
    assert payload.email == "alice@example.com"

# test webhook payload missing email fails validation
def test_webhook_payload_missing_email_fails() -> None:
    with pytest.raises(ValidationError):
        WebhookPayload(
            tenant_id=uuid4(),
            external_lead_id="lead-123",
            dedupe_key="dedupe-123",
        )


# test webhook payload invalid email fails validation
def test_webhook_payload_invalid_email_fails() -> None:
    with pytest.raises(ValidationError):
        WebhookPayload(
            tenant_id=uuid4(),
            external_lead_id="lead-123",
            dedupe_key="dedupe-123",
            email="not-an-email",
        )


# test webhook payload empty external lead id fails validation
def test_webhook_payload_empty_external_lead_id_fails() -> None:
    with pytest.raises(ValidationError):
        WebhookPayload(
            tenant_id=uuid4(),
            external_lead_id="",
            dedupe_key="dedupe-123",
            email="alice@example.com",
        )


# test webhook payload empty dedupe key fails validation
def test_webhook_payload_empty_dedupe_key_fails() -> None:
    with pytest.raises(ValidationError):
        WebhookPayload(
            tenant_id=uuid4(),
            external_lead_id="lead-123",
            dedupe_key="  ",
            email="alice@example.com",
        )


# test valid approval request approve
def test_approval_request_valid_approve() -> None:
    approval = ApprovalRequest(action="approve")
    assert approval.action == "approve"


# test valid approval request cancel
def test_approval_request_valid_cancel() -> None:
    approval = ApprovalRequest(action="cancel")
    assert approval.action == "cancel"


# test invalid approval request action fails validation
def test_approval_request_invalid_action_fails() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest(action="reject")


# test webhook response serialization
def test_webhook_response_serialization() -> None:
    response = WebhookResponse(
        workflow_id="lead:00000000-0000-0000-0000-000000000001:lead-123",
        status="accepted",
    )
    assert response.model_dump() == {
        "workflow_id": "lead:00000000-0000-0000-0000-000000000001:lead-123",
        "status": "accepted",
    }
