from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from src.db.outbox_queries import (
    calculate_backoff_seconds,
    mark_outbox_failed,
    mark_outbox_permanently_failed,
    mark_outbox_processing,
    mark_outbox_sent,
    recover_stuck_entries,
)

# build pool and connection mocks
def _build_pool_and_connection_mocks() -> tuple[MagicMock, MagicMock]:
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(return_value="UPDATE 1")
    mock_conn.fetch = AsyncMock(return_value=[])

    transaction_cm = AsyncMock()
    transaction_cm.__aenter__.return_value = None
    transaction_cm.__aexit__.return_value = None
    mock_conn.transaction.return_value = transaction_cm

    acquire_cm = AsyncMock()
    acquire_cm.__aenter__.return_value = mock_conn
    acquire_cm.__aexit__.return_value = None

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acquire_cm
    return mock_pool, mock_conn

# test calculate backoff seconds returns correct values
def test_calculate_backoff_seconds() -> None:
    assert calculate_backoff_seconds(0) == 60
    assert calculate_backoff_seconds(1) == 300
    assert calculate_backoff_seconds(3) == 3600
    assert calculate_backoff_seconds(99) == 3600

# test mark outbox processing updates record
@pytest.mark.asyncio
async def test_mark_outbox_processing() -> None:
    record_id = uuid4()
    mock_pool, mock_conn = _build_pool_and_connection_mocks()

    with patch("src.db.outbox_queries.Database") as mock_database:
        mock_database.pool = mock_pool
        await mark_outbox_processing(record_id)

    execute_call = mock_conn.execute.await_args
    assert execute_call is not None
    assert "status = 'PROCESSING'" in execute_call.args[0]
    assert execute_call.args[1] == record_id
    mock_conn.transaction.assert_called_once()

# test mark outbox sent updates record
@pytest.mark.asyncio
async def test_mark_outbox_sent() -> None:
    record_id = uuid4()
    mock_pool, mock_conn = _build_pool_and_connection_mocks()

    with patch("src.db.outbox_queries.Database") as mock_database:
        mock_database.pool = mock_pool
        await mark_outbox_sent(record_id)

    execute_call = mock_conn.execute.await_args
    assert execute_call is not None
    assert "status = 'SENT'" in execute_call.args[0]
    assert "sent_at = now()" in execute_call.args[0]
    assert execute_call.args[1] == record_id


@pytest.mark.asyncio
async def test_mark_outbox_failed_schedules_retry() -> None:
    record_id = uuid4()
    mock_pool, mock_conn = _build_pool_and_connection_mocks()

    with patch("src.db.outbox_queries.Database") as mock_database:
        mock_database.pool = mock_pool
        await mark_outbox_failed(record_id, "timeout", 2)

    execute_call = mock_conn.execute.await_args
    assert execute_call is not None
    assert "status = 'PENDING'" in execute_call.args[0]
    assert "next_attempt_at" in execute_call.args[0]
    assert execute_call.args[1] == record_id
    assert execute_call.args[2] == "timeout"
    assert execute_call.args[3] == 2
    assert execute_call.args[4] == 1800

# test mark outbox permanently failed updates record
@pytest.mark.asyncio
async def test_mark_outbox_permanently_failed() -> None:
    record_id = uuid4()
    mock_pool, mock_conn = _build_pool_and_connection_mocks()

    with patch("src.db.outbox_queries.Database") as mock_database:
        mock_database.pool = mock_pool
        await mark_outbox_permanently_failed(record_id, "permanent error", 5)

    execute_call = mock_conn.execute.await_args
    assert execute_call is not None
    assert "status = 'FAILED'" in execute_call.args[0]
    assert execute_call.args[1] == record_id
    assert execute_call.args[2] == "permanent error"
    assert execute_call.args[3] == 5

# test recover stuck entries with stuck records
@pytest.mark.asyncio
async def test_recover_stuck_entries_with_stuck_records() -> None:
    mock_pool, mock_conn = _build_pool_and_connection_mocks()
    mock_conn.fetch = AsyncMock(
        return_value=[{"id": uuid4()}, {"id": uuid4()}, {"id": uuid4()}]
    )

    with patch("src.db.outbox_queries.Database") as mock_database:
        mock_database.pool = mock_pool
        count = await recover_stuck_entries()

    assert count == 3
    fetch_call = mock_conn.fetch.await_args
    assert fetch_call is not None
    assert "status = 'PROCESSING'" in fetch_call.args[0]
    assert "interval '1 minute'" in fetch_call.args[0]

# test recover stuck entries with no stuck records
@pytest.mark.asyncio
async def test_recover_stuck_entries_with_no_stuck_records() -> None:
    mock_pool, _ = _build_pool_and_connection_mocks()

    with patch("src.db.outbox_queries.Database") as mock_database:
        mock_database.pool = mock_pool
        count = await recover_stuck_entries()

    assert count == 0
