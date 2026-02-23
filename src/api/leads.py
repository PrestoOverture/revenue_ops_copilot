import logging
from typing import Any, cast
from uuid import UUID
from fastapi import APIRouter, HTTPException
import temporalio.client as temporal_client
from temporalio.service import RPCError, RPCStatusCode
from src.api.models import ApprovalRequest, LeadStatusResponse
from src.db.connection import Database
from src.db.queries import get_lead_by_id
from src.workflows.client import get_temporal_client
from src.workflows.lead_workflow import LeadWorkflow

logger = logging.getLogger(__name__)
router = APIRouter()
TemporalWorkflowNotFoundError = cast(
    type[Exception],
    getattr(temporal_client, "WorkflowNotFoundError", Exception),
)


# signal a lead workflow
@router.post("/leads/{lead_id}/signal")
async def signal_lead_workflow(lead_id: UUID, body: ApprovalRequest) -> dict[str, str]:
    try:
        # get database pool
        pool = Database.pool
        if pool is None:
            raise RuntimeError("Database pool is not initialized")

        # acquire database connection
        lead: dict[str, Any] | None
        async with pool.acquire() as conn:
            lead = await get_lead_by_id(conn, lead_id)

        # check if lead exists
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        # build workflow id
        workflow_id = f"lead:{lead['tenant_id']}:{lead['external_lead_id']}"
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)

        try:
            # signal workflow
            if body.action == "approve":
                await handle.signal(LeadWorkflow.approve)
            else:
                await handle.signal(LeadWorkflow.cancel)
        except TemporalWorkflowNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found or already completed",
            ) from None
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise HTTPException(
                    status_code=404,
                    detail="Workflow not found or already completed",
                ) from None
            raise

        logger.info(
            "Lead signal sent lead_id=%s workflow_id=%s action=%s",
            lead_id,
            workflow_id,
            body.action,
        )
        return {
            "lead_id": str(lead_id),
            "workflow_id": workflow_id,
            "action": body.action,
            "status": "signal_sent",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "lead_signal_failed lead_id=%s action=%s", lead_id, body.action
        )
        raise HTTPException(status_code=500, detail="Internal server error") from None


# get a lead status
@router.get("/leads/{lead_id}")
async def get_lead_status(lead_id: UUID) -> LeadStatusResponse:
    try:
        pool = Database.pool
        if pool is None:
            raise RuntimeError("Database pool is not initialized")

        lead: dict[str, Any] | None
        async with pool.acquire() as conn:
            lead = await get_lead_by_id(conn, lead_id)

        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        response = LeadStatusResponse(
            lead_id=lead["id"],
            tenant_id=lead["tenant_id"],
            external_lead_id=lead["external_lead_id"],
            email=lead["email"],
            state=lead["state"],
            priority=lead.get("priority"),
            budget_range=lead.get("budget_range"),
            timeline=lead.get("timeline"),
            routing=lead.get("routing"),
            touchpoint_count=lead.get("touchpoint_count", 0),
            created_at=lead["created_at"].isoformat(),
            updated_at=lead["updated_at"].isoformat(),
        )
        logger.info("Lead status queried lead_id=%s", lead_id)
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("lead_status_query_failed lead_id=%s", lead_id)
        raise HTTPException(status_code=500, detail="Internal server error") from None
