import logging
from uuid import UUID
from temporalio import activity
from src.db.connection import Database
from src.db.queries import get_lead_by_id, insert_outbox
from src.workflows.models import DraftResult, QualificationResult

logger = logging.getLogger(__name__)

# write an email to the outbox
@activity.defn
async def write_outbox_email(lead_id: str, draft: DraftResult, touchpoint: int) -> str:
    logger.info(
        "write_outbox_email_started",
        extra={"lead_id": lead_id, "type": "SEND_EMAIL", "touchpoint": touchpoint},
    )

    lead_id_uuid = UUID(lead_id)
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        lead = await get_lead_by_id(conn, lead_id_uuid)
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        payload = {
            "subject": draft.subject,
            "body": draft.body,
            "tone": draft.tone,
            "to_email": lead["email"],
            "to_name": lead.get("name"),
        }
        idempotency_key = f"{lead_id}:email:{touchpoint}"

        async with conn.transaction():
            outbox_id = await insert_outbox(
                conn=conn,
                tenant_id=lead["tenant_id"],
                lead_id=lead_id_uuid,
                type="SEND_EMAIL",
                idempotency_key=idempotency_key,
                payload=payload,
            )

    logger.info(
        "write_outbox_email_completed",
        extra={
            "lead_id": lead_id,
            "type": "SEND_EMAIL",
            "outbox_id": str(outbox_id),
        },
    )
    return str(outbox_id)

# write a CRM_UPSERT intent to the outbox
@activity.defn
async def write_outbox_crm(lead_id: str, qualification: QualificationResult) -> str:
    logger.info(
        "write_outbox_crm_started",
        extra={"lead_id": lead_id, "type": "CRM_UPSERT"},
    )

    lead_id_uuid = UUID(lead_id)
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        lead = await get_lead_by_id(conn, lead_id_uuid)
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        payload = {
            "external_lead_id": lead["external_lead_id"],
            "email": lead["email"],
            "name": lead.get("name"),
            "company": lead.get("company"),
            "priority": qualification.priority,
            "budget_range": qualification.budget_range,
            "timeline": qualification.timeline,
            "routing": qualification.routing,
        }
        idempotency_key = f"{lead_id}:crm"

        async with conn.transaction():
            outbox_id = await insert_outbox(
                conn=conn,
                tenant_id=lead["tenant_id"],
                lead_id=lead_id_uuid,
                type="CRM_UPSERT",
                idempotency_key=idempotency_key,
                payload=payload,
            )

    logger.info(
        "write_outbox_crm_completed",
        extra={
            "lead_id": lead_id,
            "type": "CRM_UPSERT",
            "outbox_id": str(outbox_id),
        },
    )
    return str(outbox_id)
