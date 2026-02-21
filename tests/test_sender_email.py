from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import httpx
import pytest
from src.workers.sender import OutboxRecord
from src.workers.senders.email import SENDGRID_MAIL_SEND_URL, send_email

# build outbox record for testing
def _build_outbox_record(payload: dict[str, object]) -> OutboxRecord:
    now = datetime.now(timezone.utc)
    return OutboxRecord(
        id=uuid4(),
        tenant_id=uuid4(),
        lead_id=uuid4(),
        type="SEND_EMAIL",
        idempotency_key=f"send-email-{uuid4()}",
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
    response: httpx.Response | None = None,
    side_effect: Exception | None = None,
) -> tuple[MagicMock, MagicMock]:
    mock_client = MagicMock()
    if side_effect is not None:
        mock_client.post = AsyncMock(side_effect=side_effect)
    else:
        assert response is not None
        mock_client.post = AsyncMock(return_value=response)

    async_client_cm = MagicMock()
    async_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    async_client_cm.__aexit__ = AsyncMock(return_value=None)
    return async_client_cm, mock_client

# test send email success
@pytest.mark.asyncio
async def test_send_email_success() -> None:
    record = _build_outbox_record(
        {
            "to": "recipient@example.com",
            "subject": "Subject",
            "body": "<p>Hello</p>",
            "from_email": "sender@example.com",
        }
    )
    async_client_cm, _ = _build_async_client_cm(response=httpx.Response(status_code=202))

    with (
        patch(
            "src.workers.senders.email.Settings",
            return_value=SimpleNamespace(SENDGRID_API_KEY="SG.test", EMAIL_FROM="fallback@example.com"),
        ),
        patch("src.workers.senders.email.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_email(record)

    assert result is True

# test send email api failure
@pytest.mark.asyncio
async def test_send_email_api_failure() -> None:
    record = _build_outbox_record(
        {
            "to": "recipient@example.com",
            "subject": "Subject",
            "body": "<p>Hello</p>",
            "from_email": "sender@example.com",
        }
    )
    async_client_cm, _ = _build_async_client_cm(
        response=httpx.Response(status_code=400, text='{"errors":[{"message":"bad request"}]}'),
    )

    with (
        patch(
            "src.workers.senders.email.Settings",
            return_value=SimpleNamespace(SENDGRID_API_KEY="SG.test", EMAIL_FROM="fallback@example.com"),
        ),
        patch("src.workers.senders.email.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_email(record)

    assert result is False

# test send email network error
@pytest.mark.asyncio
async def test_send_email_network_error() -> None:
    record = _build_outbox_record(
        {
            "to": "recipient@example.com",
            "subject": "Subject",
            "body": "<p>Hello</p>",
            "from_email": "sender@example.com",
        }
    )
    request = httpx.Request("POST", SENDGRID_MAIL_SEND_URL)
    async_client_cm, _ = _build_async_client_cm(
        side_effect=httpx.ConnectError("connection failed", request=request),
    )

    with (
        patch(
            "src.workers.senders.email.Settings",
            return_value=SimpleNamespace(SENDGRID_API_KEY="SG.test", EMAIL_FROM="fallback@example.com"),
        ),
        patch("src.workers.senders.email.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_email(record)

    assert result is False

# test send email payload extraction
@pytest.mark.asyncio
async def test_send_email_payload_extraction() -> None:
    payload = {
        "to": "recipient@example.com",
        "subject": "Quarterly update",
        "body": "<p>Pipeline update</p>",
        "from_email": "sender@example.com",
    }
    record = _build_outbox_record(payload)
    async_client_cm, mock_client = _build_async_client_cm(response=httpx.Response(status_code=202))

    with (
        patch(
            "src.workers.senders.email.Settings",
            return_value=SimpleNamespace(SENDGRID_API_KEY="SG.test", EMAIL_FROM="fallback@example.com"),
        ),
        patch("src.workers.senders.email.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_email(record)

    assert result is True
    post_call = mock_client.post.await_args
    assert post_call is not None
    assert post_call.args[0] == SENDGRID_MAIL_SEND_URL
    assert post_call.kwargs["json"] == {
        "personalizations": [{"to": [{"email": payload["to"]}]}],
        "from": {"email": payload["from_email"]},
        "subject": payload["subject"],
        "content": [{"type": "text/html", "value": payload["body"]}],
    }

# test send email falls back to settings from email
@pytest.mark.asyncio
async def test_send_email_falls_back_to_settings_from_email() -> None:
    payload = {
        "to": "recipient@example.com",
        "subject": "Subject",
        "body": "<p>Hello</p>",
    }
    record = _build_outbox_record(payload)
    async_client_cm, mock_client = _build_async_client_cm(response=httpx.Response(status_code=202))

    with (
        patch(
            "src.workers.senders.email.Settings",
            return_value=SimpleNamespace(
                SENDGRID_API_KEY="SG.test",
                EMAIL_FROM="default-sender@example.com",
            ),
        ),
        patch("src.workers.senders.email.httpx.AsyncClient", return_value=async_client_cm),
    ):
        result = await send_email(record)

    assert result is True
    post_call = mock_client.post.await_args
    assert post_call is not None
    assert post_call.kwargs["json"]["from"]["email"] == "default-sender@example.com"
