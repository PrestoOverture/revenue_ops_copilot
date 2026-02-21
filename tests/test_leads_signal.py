from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import httpx
import pytest
from temporalio.service import RPCError, RPCStatusCode
from src.api.main import app
from src.workflows.lead_workflow import LeadWorkflow

# build pool and connection mocks
def _build_pool_and_connection_mocks() -> tuple[MagicMock, MagicMock]:
    mock_conn = MagicMock()

    acquire_cm = AsyncMock()
    acquire_cm.__aenter__.return_value = mock_conn
    acquire_cm.__aexit__.return_value = None

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acquire_cm

    return mock_pool, mock_conn

# test signal approve success
@pytest.mark.asyncio
async def test_signal_approve_success() -> None:
    lead_id = uuid4()
    tenant_id = uuid4()
    external_lead_id = "lead-123"
    workflow_id = f"lead:{tenant_id}:{external_lead_id}"
    mock_pool, mock_conn = _build_pool_and_connection_mocks()

    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()

    mock_client = MagicMock()
    mock_client.get_workflow_handle.return_value = mock_handle

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
        patch("src.api.leads.Database") as mock_database,
        patch(
            "src.api.leads.get_lead_by_id",
            new_callable=AsyncMock,
            return_value={
                "id": lead_id,
                "tenant_id": tenant_id,
                "external_lead_id": external_lead_id,
            },
        ) as mock_get_lead_by_id,
        patch(
            "src.api.leads.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/leads/{lead_id}/signal",
                json={"action": "approve"},
            )

    assert response.status_code == 200
    assert response.json() == {
        "lead_id": str(lead_id),
        "workflow_id": workflow_id,
        "action": "approve",
        "status": "signal_sent",
    }
    mock_get_lead_by_id.assert_awaited_once_with(mock_conn, lead_id)
    mock_handle.signal.assert_awaited_once_with(LeadWorkflow.approve)

# test signal cancel success
@pytest.mark.asyncio
async def test_signal_cancel_success() -> None:
    lead_id = uuid4()
    tenant_id = uuid4()
    external_lead_id = "lead-123"
    workflow_id = f"lead:{tenant_id}:{external_lead_id}"
    mock_pool, _ = _build_pool_and_connection_mocks()

    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()

    mock_client = MagicMock()
    mock_client.get_workflow_handle.return_value = mock_handle

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
        patch("src.api.leads.Database") as mock_database,
        patch(
            "src.api.leads.get_lead_by_id",
            new_callable=AsyncMock,
            return_value={
                "id": lead_id,
                "tenant_id": tenant_id,
                "external_lead_id": external_lead_id,
            },
        ),
        patch(
            "src.api.leads.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/leads/{lead_id}/signal",
                json={"action": "cancel"},
            )

    assert response.status_code == 200
    assert response.json() == {
        "lead_id": str(lead_id),
        "workflow_id": workflow_id,
        "action": "cancel",
        "status": "signal_sent",
    }
    mock_handle.signal.assert_awaited_once_with(LeadWorkflow.cancel)

# test signal lead not found
@pytest.mark.asyncio
async def test_signal_lead_not_found() -> None:
    lead_id = uuid4()
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
        patch("src.api.leads.Database") as mock_database,
        patch(
            "src.api.leads.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("src.api.leads.get_temporal_client", new_callable=AsyncMock) as mock_client,
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/leads/{lead_id}/signal",
                json={"action": "approve"},
            )

    assert response.status_code == 404
    assert response.json()["detail"] == "Lead not found"
    mock_client.assert_not_awaited()

# test signal workflow not found
@pytest.mark.asyncio
async def test_signal_workflow_not_found() -> None:
    lead_id = uuid4()
    tenant_id = uuid4()
    external_lead_id = "lead-123"
    mock_pool, _ = _build_pool_and_connection_mocks()

    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock(
        side_effect=RPCError(
            message="workflow not found",
            status=RPCStatusCode.NOT_FOUND,
            raw_grpc_status=b"",
        )
    )
    mock_client = MagicMock()
    mock_client.get_workflow_handle.return_value = mock_handle

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
        patch("src.api.leads.Database") as mock_database,
        patch(
            "src.api.leads.get_lead_by_id",
            new_callable=AsyncMock,
            return_value={
                "id": lead_id,
                "tenant_id": tenant_id,
                "external_lead_id": external_lead_id,
            },
        ),
        patch(
            "src.api.leads.get_temporal_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ),
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/leads/{lead_id}/signal",
                json={"action": "approve"},
            )

    assert response.status_code == 404
    assert "Workflow not found" in response.json()["detail"]

# test signal invalid action
@pytest.mark.asyncio
async def test_signal_invalid_action() -> None:
    lead_id = uuid4()

    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/leads/{lead_id}/signal",
                json={"action": "reject"},
            )

    assert response.status_code == 422
