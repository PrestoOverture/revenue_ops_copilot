from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
import pytest
from temporalio.testing import ActivityEnvironment
from src.activities.outbox import write_outbox_crm, write_outbox_email
from src.workflows.models import DraftResult, QualificationResult

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
        "state": "DRAFTED",
    }

# sample draft fixture
@pytest.fixture
def sample_draft() -> DraftResult:
    return DraftResult(
        subject="Following up on your inquiry",
        body="Hi Test User, thanks for reaching out.",
        tone="professional",
        model="gpt-4o",
        prompt_version="draft_v1.0",
        tokens_in=200,
        tokens_out=90,
        cost_usd=0.00125,
    )


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

# test write outbox email happy path
@pytest.mark.asyncio
async def test_write_outbox_email_happy_path(
    mock_lead: dict[str, object],
    sample_draft: DraftResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    outbox_uuid = UUID("11111111-1111-1111-1111-111111111111")
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.outbox.Database") as mock_database,
        patch(
            "src.activities.outbox.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.outbox.insert_outbox",
            new_callable=AsyncMock,
            return_value=outbox_uuid,
        ) as mock_insert_outbox,
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        result = await environment.run(
            write_outbox_email, str(lead_id), sample_draft, 0
        )

    assert result == str(outbox_uuid)
    insert_call = mock_insert_outbox.await_args
    assert insert_call is not None
    insert_kwargs = insert_call.kwargs
    assert insert_kwargs["type"] == "SEND_EMAIL"
    assert insert_kwargs["idempotency_key"] == f"{lead_id}:email:0"
    assert insert_kwargs["tenant_id"] == mock_lead["tenant_id"]
    assert insert_kwargs["lead_id"] == lead_id
    payload = insert_kwargs["payload"]
    assert payload["subject"] == sample_draft.subject
    assert payload["body"] == sample_draft.body
    assert payload["tone"] == sample_draft.tone
    assert payload["to_email"] == mock_lead["email"]
    assert payload["to_name"] == mock_lead["name"]

# test write outbox email idempotency key includes touchpoint
@pytest.mark.asyncio
async def test_write_outbox_email_idempotency_key_includes_touchpoint(
    mock_lead: dict[str, object],
    sample_draft: DraftResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    outbox_uuid = UUID("22222222-2222-2222-2222-222222222222")
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.outbox.Database") as mock_database,
        patch(
            "src.activities.outbox.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.outbox.insert_outbox",
            new_callable=AsyncMock,
            return_value=outbox_uuid,
        ) as mock_insert_outbox,
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        await environment.run(write_outbox_email, str(lead_id), sample_draft, 2)

    insert_call = mock_insert_outbox.await_args
    assert insert_call is not None
    insert_kwargs = insert_call.kwargs
    assert insert_kwargs["idempotency_key"] == f"{lead_id}:email:2"

# test write outbox crm happy path
@pytest.mark.asyncio
async def test_write_outbox_crm_happy_path(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    outbox_uuid = UUID("33333333-3333-3333-3333-333333333333")
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.outbox.Database") as mock_database,
        patch(
            "src.activities.outbox.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.outbox.insert_outbox",
            new_callable=AsyncMock,
            return_value=outbox_uuid,
        ) as mock_insert_outbox,
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        result = await environment.run(
            write_outbox_crm, str(lead_id), sample_qualification
        )

    assert result == str(outbox_uuid)
    insert_call = mock_insert_outbox.await_args
    assert insert_call is not None
    insert_kwargs = insert_call.kwargs
    assert insert_kwargs["type"] == "CRM_UPSERT"
    assert insert_kwargs["idempotency_key"] == f"{lead_id}:crm"
    assert insert_kwargs["tenant_id"] == mock_lead["tenant_id"]
    assert insert_kwargs["lead_id"] == lead_id
    payload = insert_kwargs["payload"]
    assert payload["external_lead_id"] == mock_lead["external_lead_id"]
    assert payload["email"] == mock_lead["email"]
    assert payload["name"] == mock_lead["name"]
    assert payload["company"] == mock_lead["company"]
    assert payload["priority"] == sample_qualification.priority
    assert payload["budget_range"] == sample_qualification.budget_range
    assert payload["timeline"] == sample_qualification.timeline
    assert payload["routing"] == sample_qualification.routing

# test write outbox email lead not found
@pytest.mark.asyncio
async def test_write_outbox_email_lead_not_found(sample_draft: DraftResult) -> None:
    lead_id = UUID("44444444-4444-4444-4444-444444444444")
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.outbox.Database") as mock_database,
        patch(
            "src.activities.outbox.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.activities.outbox.insert_outbox",
            new_callable=AsyncMock,
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        with pytest.raises(ValueError, match=str(lead_id)):
            await environment.run(write_outbox_email, str(lead_id), sample_draft, 0)

# test write outbox crm lead not found
@pytest.mark.asyncio
async def test_write_outbox_crm_lead_not_found(
    sample_qualification: QualificationResult,
) -> None:
    lead_id = UUID("55555555-5555-5555-5555-555555555555")
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.outbox.Database") as mock_database,
        patch(
            "src.activities.outbox.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.activities.outbox.insert_outbox",
            new_callable=AsyncMock,
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        with pytest.raises(ValueError, match=str(lead_id)):
            await environment.run(write_outbox_crm, str(lead_id), sample_qualification)

# test write outbox email pool not initialized
@pytest.mark.asyncio
async def test_write_outbox_email_pool_not_initialized(
    sample_draft: DraftResult,
) -> None:
    lead_id = UUID("66666666-6666-6666-6666-666666666666")

    with patch("src.activities.outbox.Database") as mock_database:
        mock_database.pool = None
        environment = ActivityEnvironment()
        with pytest.raises(RuntimeError):
            await environment.run(write_outbox_email, str(lead_id), sample_draft, 0)
