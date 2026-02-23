import logging
from datetime import timedelta
from uuid import UUID
from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from src.config import Settings
from src.db.connection import Database
from src.db.queries import get_lead_by_id, get_tenant_config
from src.workflows.client import get_temporal_client
from src.workflows.models import FollowupWorkflowInput, QualificationResult

logger = logging.getLogger(__name__)


# schedule a followup for the lead
@activity.defn
async def schedule_followup(
    lead_id: str,
    touchpoint: int,
    qualification: QualificationResult,
) -> str:
    lead_id_uuid = UUID(lead_id)
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        lead = await get_lead_by_id(conn, lead_id_uuid)
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        tenant_config = await get_tenant_config(conn, lead["tenant_id"])
        delay_hours = 48
        max_touchpoints = 3
        if tenant_config is not None:
            followup_delay_hours = tenant_config.get("followup_delay_hours")
            tenant_max_touchpoints = tenant_config.get("max_touchpoints")
            if followup_delay_hours is not None:
                delay_hours = int(followup_delay_hours)
            if tenant_max_touchpoints is not None:
                max_touchpoints = int(tenant_max_touchpoints)

    workflow_id = (
        f"followup:{lead['tenant_id']}:{lead['external_lead_id']}:{touchpoint}"
    )
    workflow_input = FollowupWorkflowInput(
        lead_id=lead_id,
        tenant_id=str(lead["tenant_id"]),
        external_lead_id=lead["external_lead_id"],
        touchpoint=touchpoint,
        max_touchpoints=max_touchpoints,
        qualification=qualification,
    )

    settings = Settings()  # type: ignore[call-arg]
    from src.workflows.followup_workflow import FollowupWorkflow

    client: Client = await get_temporal_client()
    await client.start_workflow(
        FollowupWorkflow.run,
        workflow_input,
        id=workflow_id,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        start_delay=timedelta(hours=delay_hours),
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )

    logger.info(
        "schedule_followup_completed",
        extra={
            "lead_id": lead_id,
            "workflow_id": workflow_id,
            "delay_hours": delay_hours,
            "touchpoint": touchpoint,
        },
    )
    return workflow_id
