import asyncio
from typing import Any
from uuid import uuid4
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from src.workflows.lead_workflow import LeadWorkflow
from src.workflows.models import (
    DraftResult,
    LeadWorkflowInput,
    LeadWorkflowResult,
    QualificationResult,
)

# mock qualify lead activity
@activity.defn(name="qualify_lead")
async def mock_qualify_lead(lead_id: str) -> QualificationResult:
    return QualificationResult(
        priority="P1",
        budget_range="mid_market",
        timeline="30_days",
        notes="Test qualification.",
        routing="AUTO",
        policy_decision="ALLOW",
        model="gpt-4o-mini",
        prompt_version="qualify_v1.0",
        tokens_in=100,
        tokens_out=40,
        cost_usd=0.00015,
    )

# mock qualify lead activity with require review
@activity.defn(name="qualify_lead")
async def mock_qualify_lead_require_review(lead_id: str) -> QualificationResult:
    return QualificationResult(
        priority="P2",
        budget_range="unknown",
        timeline="exploratory",
        notes="Needs manual review.",
        routing="REQUIRE_REVIEW",
        policy_decision="REQUIRE_REVIEW",
        model="gpt-4o-mini",
        prompt_version="qualify_v1.0",
        tokens_in=80,
        tokens_out=30,
        cost_usd=0.00010,
    )

# mock draft email activity
@activity.defn(name="draft_email")
async def mock_draft_email(
    lead_id: str, qualification: QualificationResult
) -> DraftResult:
    return DraftResult(
        subject="Test Subject",
        body="Test Body",
        tone="professional",
        model="gpt-4o",
        prompt_version="draft_v1.0",
        tokens_in=200,
        tokens_out=90,
        cost_usd=0.00125,
    )

# mock write outbox email activity
@activity.defn(name="write_outbox_email")
async def mock_write_outbox_email(
    lead_id: str, draft: DraftResult, touchpoint: int
) -> str:
    return "outbox-email-id"

# mock write outbox crm activity
@activity.defn(name="write_outbox_crm")
async def mock_write_outbox_crm(
    lead_id: str, qualification: QualificationResult
) -> str:
    return "outbox-crm-id"

# mock schedule followup activity
@activity.defn(name="schedule_followup")
async def mock_schedule_followup(
    lead_id: str,
    touchpoint: int,
    qualification: QualificationResult,
) -> str:
    return f"followup:mock:{lead_id}:{touchpoint}"

# build input
def _build_input(*, approval_required: bool) -> LeadWorkflowInput:
    return LeadWorkflowInput(
        lead_id="00000000-0000-0000-0000-000000000123",
        tenant_id="00000000-0000-0000-0000-000000000001",
        external_lead_id="hubspot-123",
        approval_required=approval_required,
        followups_enabled=True,
    )

# wait for state
async def _wait_for_state(handle: Any, expected_state: str) -> None:
    for _ in range(200):
        state = await handle.query(LeadWorkflow.get_state)
        if state == expected_state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Workflow did not reach state {expected_state}")

# workflow id
def _workflow_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"

# start time skipping or skip
async def _start_time_skipping_or_skip() -> WorkflowEnvironment:
    try:
        return await WorkflowEnvironment.start_time_skipping()
    except RuntimeError as exc:
        if "Failed starting test server" in str(exc):
            pytest.skip("Temporal test server download unavailable in this environment")
        raise

# test workflow happy path
@pytest.mark.asyncio
async def test_workflow_happy_path() -> None:
    input_data = _build_input(approval_required=False)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[LeadWorkflow],
            activities=[
                mock_qualify_lead,
                mock_draft_email,
                mock_write_outbox_email,
                mock_write_outbox_crm,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                LeadWorkflow.run,
                input_data,
                id=_workflow_id("workflow-happy"),
                task_queue="test-queue",
            )
            result = await handle.result()

    assert isinstance(result, LeadWorkflowResult)
    assert result.status == "COMPLETED"
    state = await handle.query(LeadWorkflow.get_state)
    assert state == "COMPLETED"

# test workflow require review approve
@pytest.mark.asyncio
async def test_workflow_require_review_approve() -> None:
    input_data = _build_input(approval_required=False)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[LeadWorkflow],
            activities=[
                mock_qualify_lead_require_review,
                mock_draft_email,
                mock_write_outbox_email,
                mock_write_outbox_crm,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                LeadWorkflow.run,
                input_data,
                id=_workflow_id("workflow-review-approve"),
                task_queue="test-queue",
            )
            await _wait_for_state(handle, "AWAITING_APPROVAL")
            await handle.signal(LeadWorkflow.approve)
            result = await handle.result()

    assert result.status == "COMPLETED"

# test workflow require review cancel
@pytest.mark.asyncio
async def test_workflow_require_review_cancel() -> None:
    input_data = _build_input(approval_required=False)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[LeadWorkflow],
            activities=[
                mock_qualify_lead_require_review,
                mock_draft_email,
                mock_write_outbox_email,
                mock_write_outbox_crm,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                LeadWorkflow.run,
                input_data,
                id=_workflow_id("workflow-review-cancel"),
                task_queue="test-queue",
            )
            await _wait_for_state(handle, "AWAITING_APPROVAL")
            await handle.signal(LeadWorkflow.cancel)
            result = await handle.result()

    assert result.status == "CANCELLED"

# test workflow approval required gate
@pytest.mark.asyncio
async def test_workflow_approval_required_gate() -> None:
    input_data = _build_input(approval_required=True)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[LeadWorkflow],
            activities=[
                mock_qualify_lead,
                mock_draft_email,
                mock_write_outbox_email,
                mock_write_outbox_crm,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                LeadWorkflow.run,
                input_data,
                id=_workflow_id("workflow-approval-required"),
                task_queue="test-queue",
            )
            await _wait_for_state(handle, "AWAITING_APPROVAL")
            await handle.signal(LeadWorkflow.approve)
            result = await handle.result()

    assert result.status == "COMPLETED"

# test workflow cancel at approval gate
@pytest.mark.asyncio
async def test_workflow_cancel_at_approval_gate() -> None:
    input_data = _build_input(approval_required=True)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[LeadWorkflow],
            activities=[
                mock_qualify_lead,
                mock_draft_email,
                mock_write_outbox_email,
                mock_write_outbox_crm,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                LeadWorkflow.run,
                input_data,
                id=_workflow_id("workflow-approval-cancel"),
                task_queue="test-queue",
            )
            await _wait_for_state(handle, "AWAITING_APPROVAL")
            await handle.signal(LeadWorkflow.cancel)
            result = await handle.result()

    assert result.status == "CANCELLED"
