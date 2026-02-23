import asyncio
import logging
import signal
from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel
from src.db.connection import Database
from src.db.outbox_queries import (
    mark_outbox_failed,
    mark_outbox_permanently_failed,
    mark_outbox_processing,
    mark_outbox_sent,
    recover_stuck_entries,
)
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)

BATCH_SIZE: int = 50
POLL_INTERVAL_SECONDS: int = 5


# outbox record model
class OutboxRecord(BaseModel):
    id: UUID
    tenant_id: UUID
    lead_id: UUID
    type: str
    idempotency_key: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    next_attempt_at: datetime
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None


# poll outbox for pending records and return records
async def poll_outbox() -> list[OutboxRecord]:
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    query = """
        SELECT id, tenant_id, lead_id, type, idempotency_key, payload,
               status, attempts, max_attempts, last_error,
               next_attempt_at, created_at, updated_at, sent_at
        FROM outbox
        WHERE status = 'PENDING' AND next_attempt_at <= now()
        ORDER BY next_attempt_at ASC
        LIMIT $1
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, BATCH_SIZE)

    records = [OutboxRecord.model_validate(dict(row)) for row in rows]
    logger.info(
        "sender_polled_outbox",
        extra={
            "record_count": len(records),
            "outbox_id": None,
            "type": None,
            "status": "PENDING",
        },
    )
    return records


# dispatch record to appropriate sender and return success
async def dispatch(record: OutboxRecord) -> bool:
    if record.type == "SEND_EMAIL":
        from src.workers.senders.email import send_email

        return await send_email(record)
    if record.type == "CRM_UPSERT":
        from src.workers.senders.crm import send_crm_upsert

        return await send_crm_upsert(record)

    logger.error(
        "outbox_unknown_type",
        extra={
            "outbox_id": str(record.id),
            "type": record.type,
            "status": record.status,
        },
    )
    return False


# process outbox record and mark as sent or failed
async def process_record(record: OutboxRecord) -> None:
    try:
        await mark_outbox_processing(record.id)
        dispatch_succeeded = await dispatch(record)
        if dispatch_succeeded:
            await mark_outbox_sent(record.id)
            return

        new_attempt = record.attempts + 1
        if new_attempt >= record.max_attempts:
            await mark_outbox_permanently_failed(
                record.id,
                "Dispatch returned failure",
                new_attempt,
            )
            return
        await mark_outbox_failed(record.id, "Dispatch returned failure", new_attempt)
    except Exception as exc:
        logger.error(
            "outbox_process_error",
            extra={
                "outbox_id": str(record.id),
                "type": record.type,
                "status": record.status,
                "error": str(exc),
            },
        )
        new_attempt = record.attempts + 1
        if new_attempt >= record.max_attempts:
            await mark_outbox_permanently_failed(record.id, str(exc), new_attempt)
            return
        await mark_outbox_failed(record.id, str(exc), new_attempt)


# run sender worker and handle shutdown signals
async def run_sender() -> None:
    setup_logging()
    await Database.connect()
    logger.info(
        "sender_worker_started",
        extra={"outbox_id": None, "type": None, "status": "STARTED"},
    )
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _handle_shutdown_signal(signal_name: str) -> None:
        logger.info(
            "sender_worker_shutdown_signal_received",
            extra={
                "signal": signal_name,
                "outbox_id": None,
                "type": None,
                "status": "SHUTDOWN_SIGNAL",
            },
        )
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_shutdown_signal, sig.name)
        except (NotImplementedError, RuntimeError, ValueError):
            logger.warning(
                "sender_worker_signal_handler_unavailable",
                extra={
                    "signal": sig.name,
                    "outbox_id": None,
                    "type": None,
                    "status": "SIGNAL_HANDLER_UNAVAILABLE",
                },
            )

    try:
        while not shutdown_event.is_set():
            try:
                await recover_stuck_entries()
                records = await poll_outbox()
                for record in records:
                    await process_record(record)
            except Exception as exc:
                logger.error(
                    "sender_worker_loop_error",
                    extra={
                        "error": str(exc),
                        "outbox_id": None,
                        "type": None,
                        "status": "LOOP_ERROR",
                    },
                )

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await Database.disconnect()
        logger.info(
            "sender_worker_stopped",
            extra={"outbox_id": None, "type": None, "status": "STOPPED"},
        )


if __name__ == "__main__":
    asyncio.run(run_sender())
