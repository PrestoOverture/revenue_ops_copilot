import logging
from uuid import UUID
import asyncpg  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException
from temporalio.common import WorkflowIDReusePolicy
try:
    from temporalio.client import WorkflowExecutionAlreadyStartedError
except ImportError:  # temporalio<1.23 compatibility
    from temporalio.exceptions import (
        WorkflowAlreadyStartedError as WorkflowExecutionAlreadyStartedError,
    )
from src.api.models import WebhookPayload, WebhookResponse
from src.config import Settings
from src.db.connection import Database
from src.db.queries import insert_event, insert_lead
from src.workflows.client import get_temporal_client
from src.workflows.lead_workflow import LeadWorkflow
from src.workflows.models import LeadWorkflowInput

logger = logging.getLogger(__name__)
router = APIRouter()

# ingest a lead webhook
@router.post("/webhooks/lead")
async def ingest_lead_webhook(payload: WebhookPayload) -> WebhookResponse:
    # build workflow id
    workflow_id = f"lead:{payload.tenant_id}:{payload.external_lead_id}"
    payload_dict = payload.model_dump(mode="json")

    # log webhook received
    logger.info(
        "Lead webhook received tenant_id=%s external_lead_id=%s",
        payload.tenant_id,
        payload.external_lead_id,
    )

    try:
        # get database pool
        pool = Database.pool
        if pool is None:
            raise RuntimeError("Database pool is not initialized")

        # acquire database connection
        lead_id: UUID
        async with pool.acquire() as conn:
            async with conn.transaction():
                try:
                    await insert_event(
                        conn=conn,
                        tenant_id=payload.tenant_id,
                        dedupe_key=payload.dedupe_key,
                        event_type=payload.event_type,
                        payload=payload_dict,
                    )
                except asyncpg.UniqueViolationError:
                    logger.info(
                        "Duplicate lead detected tenant_id=%s external_lead_id=%s",
                        payload.tenant_id,
                        payload.external_lead_id,
                    )
                    return WebhookResponse(workflow_id=workflow_id, status="duplicate")

                lead_id = await insert_lead(
                    conn=conn,
                    tenant_id=payload.tenant_id,
                    external_lead_id=payload.external_lead_id,
                    email=str(payload.email),
                    name=payload.name,
                    company=payload.company,
                    source=payload.source,
                    raw_payload=payload_dict,
                )

        client = await get_temporal_client()
        settings = Settings()  # type: ignore[call-arg]

        try:
            await client.start_workflow(
                LeadWorkflow.run,
                LeadWorkflowInput(
                    lead_id=str(lead_id),
                    tenant_id=str(payload.tenant_id),
                    external_lead_id=payload.external_lead_id,
                    approval_required=True,
                    followups_enabled=True,
                ),
                id=workflow_id,
                task_queue=settings.TEMPORAL_TASK_QUEUE,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except WorkflowExecutionAlreadyStartedError:
            logger.info(
                "Duplicate lead detected tenant_id=%s external_lead_id=%s",
                payload.tenant_id,
                payload.external_lead_id,
            )
            return WebhookResponse(workflow_id=workflow_id, status="duplicate")

        logger.info(
            "Workflow started tenant_id=%s external_lead_id=%s workflow_id=%s",
            payload.tenant_id,
            payload.external_lead_id,
            workflow_id,
        )
        return WebhookResponse(workflow_id=workflow_id, status="accepted")
    except Exception:
        logger.exception(
            "lead_webhook_ingestion_failed tenant_id=%s external_lead_id=%s",
            payload.tenant_id,
            payload.external_lead_id,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from None
