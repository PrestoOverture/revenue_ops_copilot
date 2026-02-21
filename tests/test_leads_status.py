from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import httpx
import pytest
from src.api.main import app

# build pool and connection mocks
def _build_pool_and_connection_mocks() -> tuple[MagicMock, MagicMock]:
    mock_conn = MagicMock()

    acquire_cm = AsyncMock()
    acquire_cm.__aenter__.return_value = mock_conn
    acquire_cm.__aexit__.return_value = None

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acquire_cm

    return mock_pool, mock_conn

# test get lead status success
@pytest.mark.asyncio
async def test_get_lead_status_success() -> None:
    lead_id = uuid4()
    tenant_id = uuid4()
    now = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    mock_pool, mock_conn = _build_pool_and_connection_mocks()

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
                "external_lead_id": "lead-123",
                "email": "alice@example.com",
                "state": "QUALIFIED",
                "priority": "P1",
                "budget_range": "mid_market",
                "timeline": "30_days",
                "routing": "AUTO",
                "touchpoint_count": 2,
                "created_at": now,
                "updated_at": now,
            },
        ) as mock_get_lead_by_id,
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/leads/{lead_id}")

    assert response.status_code == 200
    assert response.json() == {
        "lead_id": str(lead_id),
        "tenant_id": str(tenant_id),
        "external_lead_id": "lead-123",
        "email": "alice@example.com",
        "state": "QUALIFIED",
        "priority": "P1",
        "budget_range": "mid_market",
        "timeline": "30_days",
        "routing": "AUTO",
        "touchpoint_count": 2,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    mock_get_lead_by_id.assert_awaited_once_with(mock_conn, lead_id)

# test get lead status not found
@pytest.mark.asyncio
async def test_get_lead_status_not_found() -> None:
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
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/leads/{lead_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Lead not found"

# test get lead status optional fields null
@pytest.mark.asyncio
async def test_get_lead_status_optional_fields_null() -> None:
    lead_id = uuid4()
    tenant_id = uuid4()
    now = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    mock_pool, _ = _build_pool_and_connection_mocks()

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
                "external_lead_id": "lead-123",
                "email": "alice@example.com",
                "state": "PENDING",
                "priority": None,
                "budget_range": None,
                "timeline": None,
                "routing": None,
                "touchpoint_count": 0,
                "created_at": now,
                "updated_at": now,
            },
        ),
    ):
        mock_database.pool = mock_pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/leads/{lead_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["priority"] is None
    assert body["budget_range"] is None
    assert body["timeline"] is None
    assert body["routing"] is None

# test get lead status invalid uuid
@pytest.mark.asyncio
async def test_get_lead_status_invalid_uuid() -> None:
    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/leads/not-a-uuid")

    assert response.status_code == 422
