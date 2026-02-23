import asyncio
import logging
import signal
from temporalio.worker import Worker
from src.activities.followup import schedule_followup
from src.activities.draft import draft_email
from src.activities.outbox import write_outbox_crm, write_outbox_email
from src.activities.qualify import qualify_lead
from src.config import Settings
from src.db.connection import Database
from src.logging_config import setup_logging
from src.workflows.client import get_temporal_client
from src.workflows.followup_workflow import FollowupWorkflow
from src.workflows.lead_workflow import LeadWorkflow

# run the temporal worker
async def run_worker() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    settings = Settings()  # type: ignore[call-arg]

    try:
        await Database.connect()
        client = await get_temporal_client()
        shutdown_event = asyncio.Event()

        loop = asyncio.get_running_loop()

        def _handle_shutdown_signal(signal_name: str) -> None:
            logger.info(
                "temporal_worker_shutdown_signal_received",
                extra={"signal": signal_name},
            )
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_shutdown_signal, sig.name)
            except (NotImplementedError, RuntimeError, ValueError):
                logger.warning(
                    "temporal_worker_signal_handler_unavailable",
                    extra={"signal": sig.name},
                )

        worker = Worker(
            client,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
            workflows=[LeadWorkflow, FollowupWorkflow],
            activities=[
                qualify_lead,
                draft_email,
                write_outbox_email,
                write_outbox_crm,
                schedule_followup,
            ],
        )
        logger.info(
            "temporal_worker_starting",
            extra={
                "task_queue": settings.TEMPORAL_TASK_QUEUE,
                "workflows": ["LeadWorkflow", "FollowupWorkflow"],
                "activities": [
                    "qualify_lead",
                    "draft_email",
                    "write_outbox_email",
                    "write_outbox_crm",
                    "schedule_followup",
                ],
            },
        )

        async with worker:
            logger.info(
                "temporal_worker_started",
                extra={"task_queue": settings.TEMPORAL_TASK_QUEUE},
            )
            await shutdown_event.wait()
            logger.info("temporal_worker_shutting_down")
    finally:
        await Database.disconnect()
        logger.info("temporal_worker_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(run_worker())
