import logging
import re
from typing import Any
import httpx
from src.config import Settings
from src.workers.sender import OutboxRecord

logger = logging.getLogger(__name__)

HUBSPOT_CONTACTS_URL = "https://api.hubapi.com/crm/v3/objects/contacts"
HUBSPOT_TIMEOUT_SECONDS = 30.0

# split name into first and last name
def _split_name(name: str) -> tuple[str, str]:
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])

# extract contact id from response
def _extract_contact_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None

    if not isinstance(body, dict):
        return None

    for key in ("id", "contactId", "contact_id"):
        value = body.get(key)
        if value is not None:
            return str(value)

    message = body.get("message")
    if isinstance(message, str):
        match = re.search(r"\b(\d{3,})\b", message)
        if match is not None:
            return match.group(1)

    return None

# build properties for CRM upsert
def _build_properties(payload: dict[str, Any]) -> dict[str, str]:
    email = payload.get("email")
    if not isinstance(email, str) or not email:
        return {}

    properties: dict[str, str] = {"email": email}

    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        firstname, lastname = _split_name(name.strip())
        properties["firstname"] = firstname
        properties["lastname"] = lastname

    company = payload.get("company")
    if isinstance(company, str) and company:
        properties["company"] = company

    source = payload.get("source")
    if isinstance(source, str) and source:
        properties["lead_source"] = source

    priority = payload.get("priority")
    if isinstance(priority, str) and priority:
        properties["hs_lead_status"] = priority

    return properties

# send CRM upsert to HubSpot and return success or failure
async def send_crm_upsert(record: OutboxRecord) -> bool:
    payload: dict[str, Any] = record.payload
    properties = _build_properties(payload)
    email = properties.get("email")
    if email is None:
        logger.error(
            "crm_upsert_error",
            extra={"outbox_id": str(record.id), "error": "Missing required email"},
        )
        return False

    headers = {
        "Authorization": f"Bearer {Settings().HUBSPOT_API_KEY}",  # type: ignore[call-arg]
        "Content-Type": "application/json",
    }
    request_body = {"properties": properties}

    try:
        async with httpx.AsyncClient(timeout=HUBSPOT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                HUBSPOT_CONTACTS_URL,
                headers=headers,
                json=request_body,
            )

            if 200 <= response.status_code <= 299:
                logger.info(
                    "crm_upsert_sent",
                    extra={"outbox_id": str(record.id), "email": email},
                )
                return True

            if response.status_code == 409:
                contact_id = _extract_contact_id(response)
                if contact_id is None:
                    logger.error(
                        "crm_upsert_failed",
                        extra={
                            "outbox_id": str(record.id),
                            "status_code": response.status_code,
                            "response_body": response.text,
                        },
                    )
                    return False

                patch_response = await client.patch(
                    f"{HUBSPOT_CONTACTS_URL}/{contact_id}",
                    headers=headers,
                    json=request_body,
                )
                if 200 <= patch_response.status_code <= 299:
                    logger.info(
                        "crm_upsert_updated_existing",
                        extra={
                            "outbox_id": str(record.id),
                            "email": email,
                            "contact_id": contact_id,
                        },
                    )
                    return True

                logger.error(
                    "crm_upsert_failed",
                    extra={
                        "outbox_id": str(record.id),
                        "status_code": patch_response.status_code,
                        "response_body": patch_response.text,
                    },
                )
                return False

            logger.error(
                "crm_upsert_failed",
                extra={
                    "outbox_id": str(record.id),
                    "status_code": response.status_code,
                    "response_body": response.text,
                },
            )
            return False
    except httpx.HTTPError as exc:
        logger.error(
            "crm_upsert_error",
            extra={"outbox_id": str(record.id), "error": str(exc)},
        )
        return False
    except Exception as exc:  # defensive guard for non-http errors
        logger.error(
            "crm_upsert_error",
            extra={"outbox_id": str(record.id), "error": str(exc)},
        )
        return False
