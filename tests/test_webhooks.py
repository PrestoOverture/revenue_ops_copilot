from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from asyncpg.exceptions import UniqueViolationError
import httpx
import pytest
from src.api.main import app
from src.api.webhooks import WorkflowExecutionAlreadyStartedError

# build pool and connection mocks
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

# valid payload
def _valid_payload(tenant_id: str, external_lead_id: str) -> dict[str, str]:
    return {
        "tenant_id": tenant_id,
        "external_lead_id": external_lead_id,
        "dedupe_key": "dedupe-123",
        "event_type": "lead.created",
        "email": "alice@example.com",
        "name": "Alice",
        "company": "Acme",
        "source": "web",
    }

# test webhook lead accepted
@pytest.mark.asyncio
async def test_webhook_lead_accepted() -> None:
    tenant_id = str(uuid4())
    external_lead_id = "lead-123"
    workflow_id = f"lead:{tenant_id}:{external_lead_id}"
    event_id = uuid4()
    lead_id = uuid4()
    mock_pool, _ = _build_pool_and_connection_mocks()
    mock_temporal_client = MagicMock()
    mock_temporal_client.start_workflow = AsyncMock()

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
        patch("src.api.webhooks.Database") as mock_database,
        patch(
            "src.api.webhooks.insert_event",
            new_callable=AsyncMock,
            return_value=event_id,
        ) as mock_insert_event,
        patch(
            "src.api.webhooks.insert_lead",
            new_callable=AsyncMock,
            return_value=lead_id,
        ) as mock_insert_lead,
        patch(
            "src.api.webhooks.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_temporal_client,
        ),
        patch(
            "src.api.webhooks.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="lead-processing"),
        ),
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/webhooks/lead",
                json=_valid_payload(tenant_id, external_lead_id),
            )

    assert response.status_code == 200
    assert response.json() == {"workflow_id": workflow_id, "status": "accepted"}
    mock_insert_event.assert_awaited_once()
    mock_insert_lead.assert_awaited_once()
    mock_temporal_client.start_workflow.assert_awaited_once()

# test webhook lead duplicate event
@pytest.mark.asyncio
async def test_webhook_lead_duplicate_event() -> None:
    tenant_id = str(uuid4())
    external_lead_id = "lead-123"
    workflow_id = f"lead:{tenant_id}:{external_lead_id}"
    mock_pool, _ = _build_pool_and_connection_mocks()
    mock_temporal_client = MagicMock()
    mock_temporal_client.start_workflow = AsyncMock()

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
        patch("src.api.webhooks.Database") as mock_database,
        patch(
            "src.api.webhooks.insert_event",
            new_callable=AsyncMock,
            side_effect=UniqueViolationError("duplicate key"),
        ),
        patch("src.api.webhooks.insert_lead", new_callable=AsyncMock) as mock_insert_lead,
        patch(
            "src.api.webhooks.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_temporal_client,
        ) as mock_get_temporal_client,
        patch(
            "src.api.webhooks.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="lead-processing"),
        ),
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/webhooks/lead",
                json=_valid_payload(tenant_id, external_lead_id),
            )

    assert response.status_code == 200
    assert response.json() == {"workflow_id": workflow_id, "status": "duplicate"}
    mock_insert_lead.assert_not_awaited()
    mock_get_temporal_client.assert_not_awaited()
    mock_temporal_client.start_workflow.assert_not_awaited()

# test webhook lead duplicate workflow
@pytest.mark.asyncio
async def test_webhook_lead_duplicate_workflow() -> None:
    tenant_id = str(uuid4())
    external_lead_id = "lead-123"
    workflow_id = f"lead:{tenant_id}:{external_lead_id}"
    mock_pool, _ = _build_pool_and_connection_mocks()
    mock_temporal_client = MagicMock()
    mock_temporal_client.start_workflow = AsyncMock(
        side_effect=WorkflowExecutionAlreadyStartedError(
            workflow_id=workflow_id,
            workflow_type="LeadWorkflow",
        )
    )

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
        patch("src.api.webhooks.Database") as mock_database,
        patch(
            "src.api.webhooks.insert_event",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ),
        patch(
            "src.api.webhooks.insert_lead",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ),
        patch(
            "src.api.webhooks.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_temporal_client,
        ),
        patch(
            "src.api.webhooks.Settings",
            return_value=SimpleNamespace(TEMPORAL_TASK_QUEUE="lead-processing"),
        ),
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/webhooks/lead",
                json=_valid_payload(tenant_id, external_lead_id),
            )

    assert response.status_code == 200
    assert response.json() == {"workflow_id": workflow_id, "status": "duplicate"}

# test webhook lead invalid payload missing required fields
@pytest.mark.asyncio
async def test_webhook_lead_invalid_payload() -> None:
    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post("/webhooks/lead", json={})

    assert response.status_code == 422
