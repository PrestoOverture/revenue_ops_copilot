import logging
from uuid import UUID
from src.db.connection import Database

logger = logging.getLogger(__name__)

BACKOFF_SCHEDULE: list[int] = [60, 300, 1800, 3600]
PROCESSING_TIMEOUT_MINUTES: int = 5

# calculate backoff seconds based on attempt
def calculate_backoff_seconds(attempt: int) -> int:
    return BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)]

# mark outbox as processing
async def mark_outbox_processing(record_id: UUID) -> None:
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    query = """
        UPDATE outbox
        SET status = 'PROCESSING', updated_at = now()
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(query, record_id)

    logger.info("outbox_marked_processing", extra={"outbox_id": str(record_id)})

# mark outbox as sent
async def mark_outbox_sent(record_id: UUID) -> None:
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    query = """
        UPDATE outbox
        SET status = 'SENT', sent_at = now(), updated_at = now()
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(query, record_id)

    logger.info("outbox_marked_sent", extra={"outbox_id": str(record_id)})

# mark outbox as failed and schedule retry
async def mark_outbox_failed(record_id: UUID, error: str, attempt: int) -> None:
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    next_attempt_seconds = calculate_backoff_seconds(attempt)
    query = """
        UPDATE outbox
        SET status = 'PENDING',
            last_error = $2,
            attempts = $3,
            next_attempt_at = now() + ($4 * interval '1 second'),
            updated_at = now()
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(query, record_id, error, attempt, next_attempt_seconds)

    logger.info(
        "outbox_retry_scheduled",
        extra={
            "outbox_id": str(record_id),
            "next_attempt_seconds": next_attempt_seconds,
            "attempt_number": attempt,
        },
    )

# mark outbox as permanently failed
async def mark_outbox_permanently_failed(
    record_id: UUID,
    error: str,
    attempt: int,
) -> None:
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    query = """
        UPDATE outbox
        SET status = 'FAILED',
            last_error = $2,
            attempts = $3,
            updated_at = now()
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(query, record_id, error, attempt)

    logger.error(
        "outbox_marked_permanently_failed",
        extra={"outbox_id": str(record_id), "attempts": attempt},
    )

# recover stuck entries
async def recover_stuck_entries() -> int:
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    query = """
        UPDATE outbox
        SET status = 'PENDING', updated_at = now()
        WHERE status = 'PROCESSING'
          AND updated_at < now() - ($1 * interval '1 minute')
        RETURNING id
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(query, PROCESSING_TIMEOUT_MINUTES)

    count = len(rows)
    if count > 0:
        logger.warning("outbox_stuck_entries_recovered", extra={"count": count})
    return count
