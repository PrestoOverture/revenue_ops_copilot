import json
import logging
import time
from decimal import Decimal
from uuid import UUID
from pydantic import ValidationError
from temporalio import activity
from src.config import Settings
from src.db.connection import Database
from src.db.queries import get_lead_by_id, insert_run, update_lead_state
from src.llm.client import LLMClient
from src.llm.pricing import calculate_cost
from src.llm.prompts.draft import (
    PROMPT_VERSION,
    DraftOutput,
    build_draft_prompt,
    parse_draft_response,
)
from src.llm.repair import repair_json
from src.templates.fallback import render_fallback_template
from src.workflows.models import DraftResult, QualificationResult

logger = logging.getLogger(__name__)
DRAFT_MODEL = "gpt-4o"

# draft an email for the lead using parse -> repair -> fallback handling
@activity.defn
async def draft_email(lead_id: str, qualification: QualificationResult) -> DraftResult:
    logger.info("draft_email_started", extra={"lead_id": lead_id})

    settings = Settings()  # type: ignore[call-arg]
    llm_client = LLMClient(api_key=settings.OPENAI_API_KEY)
    lead_id_uuid = UUID(lead_id)
    pool = Database.pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.acquire() as conn:
        lead = await get_lead_by_id(conn, lead_id_uuid)
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        async with conn.transaction():
            await update_lead_state(conn, lead_id_uuid, "DRAFTING")

        messages = build_draft_prompt(dict(lead), qualification.model_dump())
        start_time = time.monotonic()
        llm_response = await llm_client.chat_completion(
            model=DRAFT_MODEL,
            messages=messages,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        tokens_in = int(llm_response["tokens_in"])
        tokens_out = int(llm_response["tokens_out"])
        content = str(llm_response["content"])
        logger.info(
            "draft_email_llm_completed",
            extra={
                "lead_id": lead_id,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
            },
        )

        repair_attempted = False
        fallback_used: str | None = None
        schema_valid = True

        try:
            draft = parse_draft_response(content)
        except (json.JSONDecodeError, ValidationError):
            schema_valid = False
            repair_attempted = True
            logger.info("draft_email_repair_attempt", extra={"lead_id": lead_id})
            repaired_payload = await repair_json(
                llm_client=llm_client,
                invalid_json=content,
                schema=DraftOutput.model_json_schema(),
            )
            if repaired_payload is not None:
                try:
                    draft = DraftOutput(**repaired_payload)
                    schema_valid = True
                except ValidationError:
                    fallback_used = "TEMPLATE"
                    context = {
                        "name": lead.get("name", "there"),
                        "company": lead.get("company", "your company"),
                    }
                    draft = render_fallback_template("initial_outreach", context)
            else:
                fallback_used = "TEMPLATE"
                context = {
                    "name": lead.get("name", "there"),
                    "company": lead.get("company", "your company"),
                }
                draft = render_fallback_template("initial_outreach", context)

            if fallback_used is not None:
                logger.warning(
                    "draft_email_fallback_used",
                    extra={
                        "lead_id": lead_id,
                        "fallback_used": fallback_used,
                    },
                )

        cost: Decimal = calculate_cost(DRAFT_MODEL, tokens_in, tokens_out)
        run_status = "FALLBACK" if fallback_used is not None else "OK"

        async with conn.transaction():
            await insert_run(
                conn=conn,
                tenant_id=lead["tenant_id"],
                lead_id=lead_id_uuid,
                step="draft",
                status=run_status,
                latency_ms=latency_ms,
                model=DRAFT_MODEL,
                prompt_version=PROMPT_VERSION,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                schema_valid=schema_valid,
                repair_attempted=repair_attempted,
                fallback_used=fallback_used,
            )
            await update_lead_state(conn, lead_id_uuid, "DRAFTED")

    logger.info(
        "draft_email_completed",
        extra={
            "lead_id": lead_id,
            "repair_attempted": repair_attempted,
            "fallback_used": fallback_used,
            "schema_valid": schema_valid,
        },
    )
    return DraftResult(
        subject=draft.subject,
        body=draft.body,
        tone=draft.tone,
        model=DRAFT_MODEL,
        prompt_version=PROMPT_VERSION,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=float(cost),
        repair_attempted=repair_attempted,
        fallback_used=fallback_used,
    )
