import asyncio
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

# These imports are safe because Temporal resolves activity references at runtime.
# The workflow never calls these directly — it passes them to workflow.execute_activity().
with workflow.unsafe.imports_passed_through():
    from src.activities.followup import schedule_followup
    from src.activities.draft import draft_email
    from src.activities.outbox import write_outbox_crm, write_outbox_email
    from src.activities.qualify import qualify_lead
    from src.workflows.models import LeadWorkflowInput, LeadWorkflowResult

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["ValidationError", "PolicyBlockError"],
)

# workflow to lead a lead
# workflow_id format: lead:{tenant_id}:{external_lead_id}
@workflow.defn
class LeadWorkflow:
    # initialize the workflow
    def __init__(self) -> None:
        self._state = "PENDING"
        self._approved = False
        self._cancelled = False

    # run the workflow
    @workflow.run
    async def run(self, input: LeadWorkflowInput) -> LeadWorkflowResult:
        self._state = "QUALIFYING"
        qualification = await workflow.execute_activity(
            qualify_lead,
            args=[input.lead_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )
        self._state = "QUALIFIED"

        if qualification.routing == "REQUIRE_REVIEW":
            self._state = "AWAITING_APPROVAL"
            try:
                await workflow.wait_condition(
                    lambda: self._approved or self._cancelled,
                    timeout=timedelta(hours=24),
                )
            except asyncio.TimeoutError:
                self._state = "CANCELLED"
                return LeadWorkflowResult(
                    status="CANCELLED",
                    error="Approval timed out",
                )
            if self._cancelled:
                self._state = "CANCELLED"
                return LeadWorkflowResult(status="CANCELLED")

        self._state = "DRAFTING"
        draft = await workflow.execute_activity(
            draft_email,
            args=[input.lead_id, qualification],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=DEFAULT_RETRY,
        )
        self._state = "DRAFTED"

        if input.approval_required and not self._approved:
            self._state = "AWAITING_APPROVAL"
            try:
                await workflow.wait_condition(
                    lambda: self._approved or self._cancelled,
                    timeout=timedelta(hours=24),
                )
            except asyncio.TimeoutError:
                self._state = "CANCELLED"
                return LeadWorkflowResult(
                    status="CANCELLED",
                    error="Approval timed out",
                )
            if self._cancelled:
                self._state = "CANCELLED"
                return LeadWorkflowResult(status="CANCELLED")

        self._state = "SENDING"
        await workflow.execute_activity(
            write_outbox_email,
            args=[input.lead_id, draft, 0],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        self._state = "CRM_UPSERTING"
        await workflow.execute_activity(
            write_outbox_crm,
            args=[input.lead_id, qualification],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        if input.followups_enabled:
            self._state = "SCHEDULING_FOLLOWUP"
            await workflow.execute_activity(
                schedule_followup,
                args=[input.lead_id, 1, qualification],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY,
            )

        self._state = "COMPLETED"
        return LeadWorkflowResult(status="COMPLETED")

    @workflow.signal
    async def approve(self) -> None:
        self._approved = True

    @workflow.signal
    async def cancel(self) -> None:
        self._cancelled = True

    @workflow.query
    def get_state(self) -> str:
        return self._state
