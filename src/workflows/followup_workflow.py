from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy
with workflow.unsafe.imports_passed_through():
    from src.activities.followup import schedule_followup
    from src.activities.draft import draft_email
    from src.activities.outbox import write_outbox_email
    from src.workflows.models import (
        DraftResult,
        FollowupWorkflowInput,
        FollowupWorkflowResult,
        QualificationResult,
    )

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["ValidationError", "PolicyBlockError"],
)

# workflow to follow up with a lead
# workflow_id format: followup:{tenant_id}:{external_lead_id}:{touchpoint}
@workflow.defn
class FollowupWorkflow:
    # initialize the workflow
    def __init__(self) -> None:
        self._state = "PENDING"
        self._cancelled = False

    # run the workflow
    @workflow.run
    async def run(self, input: FollowupWorkflowInput) -> FollowupWorkflowResult:
        if self._cancelled:
            return FollowupWorkflowResult(
                status="CANCELLED",
                touchpoint=input.touchpoint,
            )

        qualification: QualificationResult = input.qualification
        self._state = "DRAFTING"
        draft: DraftResult = await workflow.execute_activity(
            draft_email,
            args=[input.lead_id, qualification],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=DEFAULT_RETRY,
        )
        self._state = "DRAFTED"

        if self._cancelled:
            return FollowupWorkflowResult(
                status="CANCELLED",
                touchpoint=input.touchpoint,
            )

        self._state = "SENDING"
        await workflow.execute_activity(
            write_outbox_email,
            args=[input.lead_id, draft, input.touchpoint],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        if input.touchpoint < input.max_touchpoints:
            self._state = "SCHEDULING_NEXT"
            await workflow.execute_activity(
                schedule_followup,
                args=[input.lead_id, input.touchpoint + 1, input.qualification],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY,
            )

        self._state = "COMPLETED"
        return FollowupWorkflowResult(
            status="COMPLETED",
            touchpoint=input.touchpoint,
        )

    @workflow.signal
    async def cancel(self) -> None:
        self._cancelled = True

    @workflow.query
    def get_state(self) -> str:
        return self._state
