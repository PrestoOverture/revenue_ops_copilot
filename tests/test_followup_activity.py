from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
import pytest
from temporalio.common import WorkflowIDReusePolicy
from temporalio.testing import ActivityEnvironment
from src.activities.followup import schedule_followup
from src.workflows.followup_workflow import FollowupWorkflow
from src.workflows.models import QualificationResult

# build mock pool and connection
def _build_pool_and_connection_mocks() -> tuple[MagicMock, MagicMock]:
    mock_conn = MagicMock()

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

# mock lead fixture
@pytest.fixture
def mock_lead() -> dict[str, object]:
    return {
        "id": UUID("00000000-0000-0000-0000-000000000123"),
        "tenant_id": UUID("00000000-0000-0000-0000-000000000001"),
        "external_lead_id": "hubspot-123",
        "email": "test@example.com",
        "name": "Test User",
        "company": "Test Corp",
        "source": "website",
        "raw_payload": {},
        "state": "SENT",
    }

# mock tenant config fixture
@pytest.fixture
def mock_tenant_config() -> dict[str, object]:
    return {
        "tenant_id": UUID("00000000-0000-0000-0000-000000000001"),
        "followup_delay_hours": 72,
        "max_touchpoints": 4,
        "approval_required": True,
        "followups_enabled": True,
    }

# sample qualification fixture
@pytest.fixture
def sample_qualification() -> QualificationResult:
    return QualificationResult(
        priority="P1",
        budget_range="mid_market",
        timeline="30_days",
        notes="Good fit.",
        routing="AUTO",
        policy_decision="ALLOW",
        model="gpt-4o-mini",
        prompt_version="qualify_v1.0",
        tokens_in=100,
        tokens_out=40,
        cost_usd=0.00015,
    )

# test schedule followup happy path
@pytest.mark.asyncio
async def test_schedule_followup_happy_path(
    mock_lead: dict[str, object],
    mock_tenant_config: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()

    with (
        patch("src.activities.followup.Database") as mock_database,
        patch(
            "src.activities.followup.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.followup.get_tenant_config",
            new_callable=AsyncMock,
            return_value=mock_tenant_config,
        ),
        patch(
            "src.activities.followup.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
        patch(
            "src.activities.followup.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="test-queue"),
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        result = await environment.run(
            schedule_followup, str(lead_id), 1, sample_qualification
        )

    expected_workflow_id = (
        f"followup:{mock_lead['tenant_id']}:{mock_lead['external_lead_id']}:1"
    )
    assert result == expected_workflow_id

    workflow_call = mock_client.start_workflow.await_args
    assert workflow_call is not None
    assert workflow_call.args[0] == FollowupWorkflow.run
    workflow_input = workflow_call.args[1]
    assert workflow_input.max_touchpoints == 4
    assert workflow_call.kwargs["id"] == expected_workflow_id
    assert workflow_call.kwargs["task_queue"] == "test-queue"
    assert workflow_call.kwargs["start_delay"] == timedelta(hours=72)
    assert (
        workflow_call.kwargs["id_reuse_policy"]
        == WorkflowIDReusePolicy.REJECT_DUPLICATE
    )

# test schedule followup default config
@pytest.mark.asyncio
async def test_schedule_followup_default_config(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()

    with (
        patch("src.activities.followup.Database") as mock_database,
        patch(
            "src.activities.followup.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.followup.get_tenant_config",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.activities.followup.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
        patch(
            "src.activities.followup.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="test-queue"),
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        await environment.run(schedule_followup, str(lead_id), 1, sample_qualification)

    workflow_call = mock_client.start_workflow.await_args
    assert workflow_call is not None
    workflow_input = workflow_call.args[1]
    assert workflow_input.max_touchpoints == 3
    assert workflow_call.kwargs["start_delay"] == timedelta(hours=48)

# test schedule followup workflow id format
@pytest.mark.asyncio
async def test_schedule_followup_workflow_id_format(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()
    mock_client = MagicMock()
    mock_client.start_workflow = AsyncMock()

    with (
        patch("src.activities.followup.Database") as mock_database,
        patch(
            "src.activities.followup.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.followup.get_tenant_config",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.activities.followup.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
        patch(
            "src.activities.followup.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="test-queue"),
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        result = await environment.run(
            schedule_followup, str(lead_id), 3, sample_qualification
        )

    expected_workflow_id = (
        f"followup:{mock_lead['tenant_id']}:{mock_lead['external_lead_id']}:3"
    )
    assert result == expected_workflow_id

# test schedule followup lead not found
@pytest.mark.asyncio
async def test_schedule_followup_lead_not_found(
    sample_qualification: QualificationResult,
) -> None:
    lead_id = UUID("77777777-7777-7777-7777-777777777777")
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.followup.Database") as mock_database,
        patch(
            "src.activities.followup.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.activities.followup.get_tenant_config",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.followup.get_temporal_client",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.followup.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="test-queue"),
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        with pytest.raises(ValueError, match=str(lead_id)):
            await environment.run(
                schedule_followup, str(lead_id), 1, sample_qualification
            )
