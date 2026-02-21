from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
import pytest
from pydantic import ValidationError
from src.workers.sender import BATCH_SIZE, OutboxRecord, poll_outbox

# build pool and connection mocks
def _build_pool_and_connection_mocks(rows: list[dict[str, object]]) -> tuple[MagicMock, MagicMock]:
    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=rows)

    acquire_cm = AsyncMock()
    acquire_cm.__aenter__.return_value = mock_conn
    acquire_cm.__aexit__.return_value = None

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acquire_cm
    return mock_pool, mock_conn

# build outbox row
def _outbox_row(seed: int) -> dict[str, object]:
    base_time = datetime.now(timezone.utc) - timedelta(minutes=seed)
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "lead_id": uuid4(),
        "type": "SEND_EMAIL" if seed % 2 == 0 else "CRM_UPSERT",
        "idempotency_key": f"idempotency-{seed}",
        "payload": {"key": f"value-{seed}"},
        "status": "PENDING",
        "attempts": seed,
        "max_attempts": 5,
        "last_error": None,
        "next_attempt_at": base_time,
        "created_at": base_time - timedelta(minutes=5),
        "updated_at": base_time - timedelta(minutes=1),
        "sent_at": None,
    }

# test poll outbox returns pending records successfully
@pytest.mark.asyncio
async def test_poll_outbox_returns_pending_records() -> None:
    rows = [_outbox_row(0), _outbox_row(1)]
    mock_pool, _ = _build_pool_and_connection_mocks(rows)

    with patch("src.workers.sender.Database") as mock_database:
        mock_database.pool = mock_pool
        results = await poll_outbox()

    assert len(results) == 2
    assert all(isinstance(record, OutboxRecord) for record in results)
    assert results[0].id == rows[0]["id"]
    assert results[0].type == rows[0]["type"]
    assert results[0].payload == rows[0]["payload"]
    assert results[1].idempotency_key == rows[1]["idempotency_key"]
    assert results[1].lead_id == rows[1]["lead_id"]

# test poll outbox returns empty list when no pending records
@pytest.mark.asyncio
async def test_poll_outbox_returns_empty_list() -> None:
    mock_pool, _ = _build_pool_and_connection_mocks([])

    with patch("src.workers.sender.Database") as mock_database:
        mock_database.pool = mock_pool
        results = await poll_outbox()

    assert results == []

# test poll outbox respects batch size
@pytest.mark.asyncio
async def test_poll_outbox_respects_batch_size() -> None:
    rows = [_outbox_row(2)]
    mock_pool, mock_conn = _build_pool_and_connection_mocks(rows)

    with patch("src.workers.sender.Database") as mock_database:
        mock_database.pool = mock_pool
        await poll_outbox()

    fetch_call = mock_conn.fetch.await_args
    assert fetch_call is not None
    assert fetch_call.args[1] == BATCH_SIZE

# test outbox record model validation
def test_outbox_record_model_validation() -> None:
    valid_data = _outbox_row(3)
    model = OutboxRecord.model_validate(valid_data)
    assert isinstance(model.id, UUID)

    invalid_data = dict(valid_data)
    invalid_data.pop("tenant_id")
    with pytest.raises(ValidationError):
        OutboxRecord.model_validate(invalid_data)
