import asyncio
from typing import Any
from uuid import uuid4
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from src.workflows.followup_workflow import FollowupWorkflow
from src.workflows.models import (
    DraftResult,
    FollowupWorkflowInput,
    FollowupWorkflowResult,
    QualificationResult,
)

# mock draft email activity
@activity.defn(name="draft_email")
async def mock_draft_email(
    lead_id: str, qualification: QualificationResult
) -> DraftResult:
    return DraftResult(
        subject="Following up",
        body="Hi, checking in on your evaluation.",
        tone="professional",
        model="gpt-4o",
        prompt_version="draft_v1.0",
        tokens_in=150,
        tokens_out=70,
        cost_usd=0.00095,
    )

# mock draft email activity with slow response
@activity.defn(name="draft_email")
async def mock_draft_email_slow(
    lead_id: str, qualification: QualificationResult
) -> DraftResult:
    await asyncio.sleep(0.2)
    return await mock_draft_email(lead_id, qualification)

# mock write outbox email activity
@activity.defn(name="write_outbox_email")
async def mock_write_outbox_email(
    lead_id: str, draft: DraftResult, touchpoint: int
) -> str:
    return "outbox-followup-id"

# mock schedule followup activity
@activity.defn(name="schedule_followup")
async def mock_schedule_followup(
    lead_id: str,
    touchpoint: int,
    qualification: QualificationResult,
) -> str:
    return f"followup:mock:{lead_id}:{touchpoint}"

# build followup input
def _build_followup_input(
    *, touchpoint: int, max_touchpoints: int = 3
) -> FollowupWorkflowInput:
    return FollowupWorkflowInput(
        lead_id="00000000-0000-0000-0000-000000000123",
        tenant_id="00000000-0000-0000-0000-000000000001",
        external_lead_id="hubspot-123",
        touchpoint=touchpoint,
        max_touchpoints=max_touchpoints,
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

# start time skipping or skip
async def _start_time_skipping_or_skip() -> WorkflowEnvironment:
    try:
        return await WorkflowEnvironment.start_time_skipping()
    except RuntimeError as exc:
        if "Failed starting test server" in str(exc):
            pytest.skip("Temporal test server download unavailable in this environment")
        raise

# wait for state
async def _wait_for_state(handle: Any, expected_state: str) -> None:
    for _ in range(200):
        state = await handle.query(FollowupWorkflow.get_state)
        if state == expected_state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Workflow did not reach state {expected_state}")

# workflow id
def _workflow_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"

# test followup workflow happy path
@pytest.mark.asyncio
async def test_followup_workflow_happy_path() -> None:
    input_data = _build_followup_input(touchpoint=1, max_touchpoints=3)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[FollowupWorkflow],
            activities=[
                mock_draft_email,
                mock_write_outbox_email,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                FollowupWorkflow.run,
                input_data,
                id=_workflow_id("followup-happy"),
                task_queue="test-queue",
            )
            result = await handle.result()

    assert isinstance(result, FollowupWorkflowResult)
    assert result.status == "COMPLETED"
    assert result.touchpoint == 1

# test followup workflow cancel
@pytest.mark.asyncio
async def test_followup_workflow_cancel() -> None:
    input_data = _build_followup_input(touchpoint=1, max_touchpoints=3)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[FollowupWorkflow],
            activities=[
                mock_draft_email_slow,
                mock_write_outbox_email,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                FollowupWorkflow.run,
                input_data,
                id=_workflow_id("followup-cancel"),
                task_queue="test-queue",
            )
            await _wait_for_state(handle, "DRAFTING")
            await handle.signal(FollowupWorkflow.cancel)
            result = await handle.result()

    assert result.status == "CANCELLED"
    assert result.touchpoint == input_data.touchpoint

# test followup workflow at max touchpoints
@pytest.mark.asyncio
async def test_followup_workflow_at_max_touchpoints() -> None:
    input_data = _build_followup_input(touchpoint=3, max_touchpoints=3)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[FollowupWorkflow],
            activities=[
                mock_draft_email,
                mock_write_outbox_email,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                FollowupWorkflow.run,
                input_data,
                id=_workflow_id("followup-at-max"),
                task_queue="test-queue",
            )
            result = await handle.result()

    assert result.status == "COMPLETED"
    assert result.touchpoint == 3

# test followup workflow state transitions
@pytest.mark.asyncio
async def test_followup_workflow_state_transitions() -> None:
    input_data = _build_followup_input(touchpoint=1, max_touchpoints=3)

    async with await _start_time_skipping_or_skip() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[FollowupWorkflow],
            activities=[
                mock_draft_email,
                mock_write_outbox_email,
                mock_schedule_followup,
            ],
        ):
            handle = await env.client.start_workflow(
                FollowupWorkflow.run,
                input_data,
                id=_workflow_id("followup-state"),
                task_queue="test-queue",
            )
            await handle.result()
            final_state = await handle.query(FollowupWorkflow.get_state)

    assert final_state == "COMPLETED"
