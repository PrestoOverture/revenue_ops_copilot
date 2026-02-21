from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import httpx
import pytest
from src.workers.sender import OutboxRecord
from src.workers.senders.crm import HUBSPOT_CONTACTS_URL, send_crm_upsert

# build outbox record for testing
def _build_outbox_record(payload: dict[str, object]) -> OutboxRecord:
    now = datetime.now(timezone.utc)
    return OutboxRecord(
        id=uuid4(),
        tenant_id=uuid4(),
        lead_id=uuid4(),
        type="CRM_UPSERT",
        idempotency_key=f"crm-upsert-{uuid4()}",
        payload=payload,
        status="PENDING",
        attempts=0,
        max_attempts=5,
        last_error=None,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
        sent_at=None,
    )

# build async client context manager
def _build_async_client_cm(
    *,
    post_response: httpx.Response | None = None,
    patch_response: httpx.Response | None = None,
    post_side_effect: Exception | None = None,
) -> tuple[MagicMock, MagicMock]:
    mock_client = MagicMock()
    if post_side_effect is not None:
        mock_client.post = AsyncMock(side_effect=post_side_effect)
    else:
        assert post_response is not None
        mock_client.post = AsyncMock(return_value=post_response)

    if patch_response is not None:
        mock_client.patch = AsyncMock(return_value=patch_response)
    else:
        mock_client.patch = AsyncMock()

    async_client_cm = MagicMock()
    async_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    async_client_cm.__aexit__ = AsyncMock(return_value=None)
    return async_client_cm, mock_client

# test send crm upsert success
@pytest.mark.asyncio
async def test_send_crm_upsert_success() -> None:
    record = _build_outbox_record({"email": "lead@example.com"})
    async_client_cm, _ = _build_async_client_cm(post_response=httpx.Response(status_code=201))

    with (
        patch(
            "src.workers.senders.crm.Settings",
            return_value=SimpleNamespace(HUBSPOT_API_KEY="pat-test"),
        ),
        patch("src.workers.senders.crm.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_crm_upsert(record)

    assert result is True

# test send crm upsert api failure
@pytest.mark.asyncio
async def test_send_crm_upsert_api_failure() -> None:
    record = _build_outbox_record({"email": "lead@example.com"})
    async_client_cm, _ = _build_async_client_cm(
        post_response=httpx.Response(status_code=400, text='{"message":"invalid request"}'),
    )

    with (
        patch(
            "src.workers.senders.crm.Settings",
            return_value=SimpleNamespace(HUBSPOT_API_KEY="pat-test"),
        ),
        patch("src.workers.senders.crm.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_crm_upsert(record)

    assert result is False

# test send crm upsert network error
@pytest.mark.asyncio
async def test_send_crm_upsert_network_error() -> None:
    record = _build_outbox_record({"email": "lead@example.com"})
    request = httpx.Request("POST", HUBSPOT_CONTACTS_URL)
    async_client_cm, _ = _build_async_client_cm(
        post_side_effect=httpx.ConnectError("connection failed", request=request),
    )

    with (
        patch(
            "src.workers.senders.crm.Settings",
            return_value=SimpleNamespace(HUBSPOT_API_KEY="pat-test"),
        ),
        patch("src.workers.senders.crm.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_crm_upsert(record)

    assert result is False

# test send crm upsert conflict then update
@pytest.mark.asyncio
async def test_send_crm_upsert_conflict_then_update() -> None:
    record = _build_outbox_record({"email": "lead@example.com", "name": "Jane Doe"})
    async_client_cm, mock_client = _build_async_client_cm(
        post_response=httpx.Response(
            status_code=409,
            json={
                "message": "Contact already exists. Existing ID: 12345",
                "category": "CONFLICT",
            },
        ),
        patch_response=httpx.Response(status_code=200),
    )

    with (
        patch(
            "src.workers.senders.crm.Settings",
            return_value=SimpleNamespace(HUBSPOT_API_KEY="pat-test"),
        ),
        patch("src.workers.senders.crm.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_crm_upsert(record)

    assert result is True
    patch_call = mock_client.patch.await_args
    assert patch_call is not None
    assert patch_call.args[0] == f"{HUBSPOT_CONTACTS_URL}/12345"

# test send crm upsert property mapping
@pytest.mark.asyncio
async def test_send_crm_upsert_property_mapping() -> None:
    payload = {
        "email": "lead@example.com",
        "name": "Jane Doe",
        "company": "Acme",
        "source": "website",
        "priority": "P1",
    }
    record = _build_outbox_record(payload)
    async_client_cm, mock_client = _build_async_client_cm(post_response=httpx.Response(status_code=201))

    with (
        patch(
            "src.workers.senders.crm.Settings",
            return_value=SimpleNamespace(HUBSPOT_API_KEY="pat-test"),
        ),
        patch("src.workers.senders.crm.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_crm_upsert(record)

    assert result is True
    post_call = mock_client.post.await_args
    assert post_call is not None
    assert post_call.kwargs["json"]["properties"] == {
        "email": "lead@example.com",
        "firstname": "Jane",
        "lastname": "Doe",
        "company": "Acme",
        "lead_source": "website",
        "hs_lead_status": "P1",
    }

# test send crm upsert optional fields omitted
@pytest.mark.asyncio
async def test_send_crm_upsert_optional_fields_omitted() -> None:
    record = _build_outbox_record({"email": "lead@example.com"})
    async_client_cm, mock_client = _build_async_client_cm(post_response=httpx.Response(status_code=201))

    with (
        patch(
            "src.workers.senders.crm.Settings",
            return_value=SimpleNamespace(HUBSPOT_API_KEY="pat-test"),
        ),
        patch("src.workers.senders.crm.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_crm_upsert(record)

    assert result is True
    post_call = mock_client.post.await_args
    assert post_call is not None
    assert post_call.kwargs["json"]["properties"] == {"email": "lead@example.com"}
