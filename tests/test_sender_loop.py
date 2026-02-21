from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from src.workers.sender import OutboxRecord, dispatch, process_record, run_sender

# build outbox record for testing
def _build_outbox_record(
    *,
    record_type: str = "SEND_EMAIL",
    attempts: int = 0,
    max_attempts: int = 5,
) -> OutboxRecord:
    now = datetime.now(timezone.utc)
    return OutboxRecord(
        id=uuid4(),
        tenant_id=uuid4(),
        lead_id=uuid4(),
        type=record_type,
        idempotency_key=f"key-{uuid4()}",
        payload={"email": "lead@example.com", "subject": "hello", "body": "<p>body</p>"},
        status="PENDING",
        attempts=attempts,
        max_attempts=max_attempts,
        last_error=None,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
        sent_at=None,
    )

# test dispatch routes email successfully
@pytest.mark.asyncio
async def test_dispatch_routes_email() -> None:
    record = _build_outbox_record(record_type="SEND_EMAIL")
    with patch(
        "src.workers.senders.email.send_email",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send_email:
        result = await dispatch(record)

    assert result is True
    mock_send_email.assert_awaited_once_with(record)

# test dispatch routes crm successfully
@pytest.mark.asyncio
async def test_dispatch_routes_crm() -> None:
    record = _build_outbox_record(record_type="CRM_UPSERT")
    with patch(
        "src.workers.senders.crm.send_crm_upsert",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send_crm:
        result = await dispatch(record)

    assert result is True
    mock_send_crm.assert_awaited_once_with(record)

# test dispatch unknown type returns false
@pytest.mark.asyncio
async def test_dispatch_unknown_type_returns_false() -> None:
    record = _build_outbox_record(record_type="UNKNOWN")
    result = await dispatch(record)
    assert result is False

# test process record success marks sent
@pytest.mark.asyncio
async def test_process_record_success_marks_sent() -> None:
    record = _build_outbox_record()
    call_order: list[str] = []

    async def mock_mark_processing(_: object) -> None:
        call_order.append("processing")

    async def mock_dispatch(_: object) -> bool:
        call_order.append("dispatch")
        return True

    async def mock_mark_sent(_: object) -> None:
        call_order.append("sent")

    with (
        patch("src.workers.sender.mark_outbox_processing", new_callable=AsyncMock, side_effect=mock_mark_processing) as mock_processing,
        patch("src.workers.sender.dispatch", new_callable=AsyncMock, side_effect=mock_dispatch) as mock_dispatch_fn,
        patch("src.workers.sender.mark_outbox_sent", new_callable=AsyncMock, side_effect=mock_mark_sent) as mock_mark_sent_fn,
    ):
        await process_record(record)

    mock_processing.assert_awaited_once_with(record.id)
    mock_dispatch_fn.assert_awaited_once_with(record)
    mock_mark_sent_fn.assert_awaited_once_with(record.id)
    assert call_order == ["processing", "dispatch", "sent"]

# test process record failure marks retry
@pytest.mark.asyncio
async def test_process_record_failure_marks_retry() -> None:
    record = _build_outbox_record(attempts=0, max_attempts=5)

    with (
        patch("src.workers.sender.mark_outbox_processing", new_callable=AsyncMock) as mock_processing,
        patch("src.workers.sender.dispatch", new_callable=AsyncMock, return_value=False),
        patch("src.workers.sender.mark_outbox_failed", new_callable=AsyncMock) as mock_mark_failed,
    ):
        await process_record(record)

    mock_processing.assert_awaited_once_with(record.id)
    mock_mark_failed.assert_awaited_once_with(
        record.id,
        "Dispatch returned failure",
        1,
    )

# test process record failure marks permanently failed
@pytest.mark.asyncio
async def test_process_record_failure_marks_permanently_failed() -> None:
    record = _build_outbox_record(attempts=4, max_attempts=5)

    with (
        patch("src.workers.sender.mark_outbox_processing", new_callable=AsyncMock) as mock_processing,
        patch("src.workers.sender.dispatch", new_callable=AsyncMock, return_value=False),
        patch(
            "src.workers.sender.mark_outbox_permanently_failed",
            new_callable=AsyncMock,
        ) as mock_permanent_fail,
    ):
        await process_record(record)

    mock_processing.assert_awaited_once_with(record.id)
    mock_permanent_fail.assert_awaited_once_with(
        record.id,
        "Dispatch returned failure",
        5,
    )

# test process record exception marks retry
@pytest.mark.asyncio
async def test_process_record_exception_marks_retry() -> None:
    record = _build_outbox_record()
    with (
        patch("src.workers.sender.mark_outbox_processing", new_callable=AsyncMock) as mock_processing,
        patch(
            "src.workers.sender.dispatch",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
        patch("src.workers.sender.mark_outbox_failed", new_callable=AsyncMock) as mock_mark_failed,
    ):
        await process_record(record)

    mock_processing.assert_awaited_once_with(record.id)
    mark_failed_call = mock_mark_failed.await_args
    assert mark_failed_call is not None
    assert mark_failed_call.args[0] == record.id
    assert "boom" in mark_failed_call.args[1]
    assert mark_failed_call.args[2] == 1

# test run sender polls and shuts down
@pytest.mark.asyncio
async def test_run_sender_polls_and_shuts_down() -> None:
    class FakeEvent:
        def __init__(self) -> None:
            self._is_set = False

        def is_set(self) -> bool:
            return self._is_set

        def set(self) -> None:
            self._is_set = True

    fake_event = FakeEvent()
    call_order: list[str] = []

    async def fake_recover() -> int:
        call_order.append("recover")
        return 0

    async def fake_poll() -> list[OutboxRecord]:
        call_order.append("poll")
        return []

    async def fake_sleep(_: int) -> None:
        call_order.append("sleep")
        fake_event.set()

    mock_loop = MagicMock()

    with (
        patch("src.workers.sender.Database.connect", new_callable=AsyncMock) as mock_connect,
        patch("src.workers.sender.Database.disconnect", new_callable=AsyncMock) as mock_disconnect,
        patch("src.workers.sender.recover_stuck_entries", new_callable=AsyncMock, side_effect=fake_recover) as mock_recover,
        patch("src.workers.sender.poll_outbox", new_callable=AsyncMock, side_effect=fake_poll) as mock_poll_outbox,
        patch("src.workers.sender.asyncio.Event", return_value=fake_event),
        patch("src.workers.sender.asyncio.get_running_loop", return_value=mock_loop),
        patch("src.workers.sender.asyncio.sleep", new_callable=AsyncMock, side_effect=fake_sleep),
    ):
        await run_sender()

    mock_connect.assert_awaited_once()
    mock_recover.assert_awaited_once()
    mock_poll_outbox.assert_awaited_once()
    mock_disconnect.assert_awaited_once()
    assert call_order.index("recover") < call_order.index("poll")
