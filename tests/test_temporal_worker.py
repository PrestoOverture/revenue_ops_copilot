from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.activities.followup import schedule_followup
from src.activities.draft import draft_email
from src.activities.outbox import write_outbox_crm, write_outbox_email
from src.activities.qualify import qualify_lead
from src.workers.temporal_worker import run_worker
from src.workflows.followup_workflow import FollowupWorkflow
from src.workflows.lead_workflow import LeadWorkflow

# test run worker connects db and temporal
@pytest.mark.asyncio
async def test_run_worker_connects_db_and_temporal() -> None:
    mock_client = MagicMock()
    mock_worker_instance = MagicMock()
    mock_worker_instance.__aenter__ = AsyncMock(return_value=mock_worker_instance)
    mock_worker_instance.__aexit__ = AsyncMock(return_value=None)
    ready_event = asyncio_event_mock()
    mock_loop = MagicMock()

    with (
        patch(
            "src.workers.temporal_worker.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="test-queue"),
        ),
        patch("src.workers.temporal_worker.Database") as mock_database,
        patch(
            "src.workers.temporal_worker.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_get_client,
        patch("src.workers.temporal_worker.Worker") as mock_worker_cls,
        patch("src.workers.temporal_worker.asyncio.Event", return_value=ready_event),
        patch(
            "src.workers.temporal_worker.asyncio.get_running_loop",
            return_value=mock_loop,
        ),
    ):
        mock_database.connect = AsyncMock()
        mock_database.disconnect = AsyncMock()
        mock_worker_cls.return_value = mock_worker_instance

        await run_worker()

    mock_database.connect.assert_awaited_once()
    mock_get_client.assert_awaited_once()
    mock_database.disconnect.assert_awaited_once()

# test run worker creates worker with correct config
@pytest.mark.asyncio
async def test_run_worker_creates_worker_with_correct_config() -> None:
    mock_client = MagicMock()
    mock_worker_instance = MagicMock()
    mock_worker_instance.__aenter__ = AsyncMock(return_value=mock_worker_instance)
    mock_worker_instance.__aexit__ = AsyncMock(return_value=None)
    ready_event = asyncio_event_mock()
    mock_loop = MagicMock()

    with (
        patch(
            "src.workers.temporal_worker.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="test-queue"),
        ),
        patch("src.workers.temporal_worker.Database") as mock_database,
        patch(
            "src.workers.temporal_worker.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
        patch("src.workers.temporal_worker.Worker") as mock_worker_cls,
        patch("src.workers.temporal_worker.asyncio.Event", return_value=ready_event),
        patch(
            "src.workers.temporal_worker.asyncio.get_running_loop",
            return_value=mock_loop,
        ),
    ):
        mock_database.connect = AsyncMock()
        mock_database.disconnect = AsyncMock()
        mock_worker_cls.return_value = mock_worker_instance

        await run_worker()

    assert mock_worker_cls.call_count == 1
    call = mock_worker_cls.call_args
    assert call is not None
    assert call.args[0] is mock_client
    assert call.kwargs["task_queue"] == "test-queue"
    assert call.kwargs["workflows"] == [LeadWorkflow, FollowupWorkflow]
    assert call.kwargs["activities"] == [
        qualify_lead,
        draft_email,
        write_outbox_email,
        write_outbox_crm,
        schedule_followup,
    ]

# test run worker disconnects db on error
@pytest.mark.asyncio
async def test_run_worker_disconnects_db_on_error() -> None:
    with (
        patch(
            "src.workers.temporal_worker.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="test-queue"),
        ),
        patch("src.workers.temporal_worker.Database") as mock_database,
        patch(
            "src.workers.temporal_worker.get_temporal_client",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection refused"),
        ) as mock_get_client,
        patch("src.workers.temporal_worker.Worker") as mock_worker_cls,
    ):
        mock_database.connect = AsyncMock()
        mock_database.disconnect = AsyncMock()

        with pytest.raises(RuntimeError, match="Connection refused"):
            await run_worker()

    mock_database.connect.assert_awaited_once()
    mock_get_client.assert_awaited_once()
    mock_database.disconnect.assert_awaited_once()
    assert mock_worker_cls.call_count == 0

# mock asyncio event
def asyncio_event_mock() -> MagicMock:
    event = MagicMock()
    event.wait = AsyncMock(return_value=None)
    event.set = MagicMock()
    return event
