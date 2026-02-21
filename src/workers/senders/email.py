import logging
from typing import Any
import httpx
from src.config import Settings
from src.workers.sender import OutboxRecord

logger = logging.getLogger(__name__)

SENDGRID_MAIL_SEND_URL = "https://api.sendgrid.com/v3/mail/send"
SENDGRID_TIMEOUT_SECONDS = 30.0

# send email to SendGrid and return success 
async def send_email(record: OutboxRecord) -> bool:
    payload: dict[str, Any] = record.payload
    to_address = payload.get("to") or payload.get("to_email")
    subject = payload.get("subject")
    body = payload.get("body")

    settings = Settings()  # type: ignore[call-arg]
    from_email = payload.get("from_email") or settings.EMAIL_FROM

    request_body = {
        "personalizations": [{"to": [{"email": to_address}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/html", "value": body}],
    }
    headers = {
        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=SENDGRID_TIMEOUT_SECONDS) as client:
            response = await client.post(
                SENDGRID_MAIL_SEND_URL,
                headers=headers,
                json=request_body,
            )
        if 200 <= response.status_code <= 299:
            logger.info(
                "email_sent",
                extra={"outbox_id": str(record.id), "to": to_address},
            )
            return True

        logger.error(
            "email_send_failed",
            extra={
                "outbox_id": str(record.id),
                "status_code": response.status_code,
                "response_body": response.text,
            },
        )
        return False
    except httpx.HTTPError as exc:
        logger.error(
            "email_send_error",
            extra={"outbox_id": str(record.id), "error": str(exc)},
        )
        return False
    except Exception as exc:  # defensive guard for non-http errors
        logger.error(
            "email_send_error",
            extra={"outbox_id": str(record.id), "error": str(exc)},
        )
        return False
