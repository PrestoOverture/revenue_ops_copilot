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
from src.llm.prompts.qualify import (
    FALLBACK_QUALIFICATION,
    PROMPT_VERSION,
    QualificationOutput,
    build_qualify_prompt,
    parse_qualify_response,
)
from src.llm.repair import repair_json
from src.workflows.models import QualificationResult

logger = logging.getLogger(__name__)
QUALIFY_MODEL = "gpt-4o-mini"


# qualify the lead
@activity.defn
async def qualify_lead(lead_id: str) -> QualificationResult:
    logger.info(
        "qualify_lead_started",
        extra={
            "lead_id": lead_id,
            "priority": None,
            "repair_attempted": False,
            "fallback_used": None,
        },
    )

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
            await update_lead_state(conn, lead_id_uuid, "QUALIFYING")

        messages = build_qualify_prompt(dict(lead))
        start_time = time.monotonic()
        llm_response = await llm_client.chat_completion(
            model=QUALIFY_MODEL,
            messages=messages,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        tokens_in = int(llm_response["tokens_in"])
        tokens_out = int(llm_response["tokens_out"])
        content = str(llm_response["content"])
        logger.info(
            "qualify_lead_llm_completed",
            extra={
                "lead_id": lead_id,
                "priority": None,
                "repair_attempted": False,
                "fallback_used": None,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
            },
        )

        repair_attempted = False
        fallback_used: str | None = None
        schema_valid = True

        try:
            qualification = parse_qualify_response(content)
        except (json.JSONDecodeError, ValidationError):
            schema_valid = False
            repair_attempted = True
            logger.info(
                "qualify_lead_repair_attempt",
                extra={
                    "lead_id": lead_id,
                    "priority": None,
                    "repair_attempted": True,
                    "fallback_used": None,
                },
            )
            repaired_payload = await repair_json(
                llm_client=llm_client,
                invalid_json=content,
                schema=QualificationOutput.model_json_schema(),
            )
            if repaired_payload is not None:
                try:
                    qualification = QualificationOutput(**repaired_payload)
                    schema_valid = True
                except ValidationError:
                    fallback_used = "DEFAULTS"
                    qualification = FALLBACK_QUALIFICATION
            else:
                fallback_used = "DEFAULTS"
                qualification = FALLBACK_QUALIFICATION

            if fallback_used is not None:
                logger.warning(
                    "qualify_lead_fallback_used",
                    extra={
                        "lead_id": lead_id,
                        "priority": qualification.priority,
                        "repair_attempted": repair_attempted,
                        "fallback_used": fallback_used,
                    },
                )

        cost: Decimal = calculate_cost(QUALIFY_MODEL, tokens_in, tokens_out)
        run_status = "FALLBACK" if fallback_used is not None else "OK"

        async with conn.transaction():
            await insert_run(
                conn=conn,
                tenant_id=lead["tenant_id"],
                lead_id=lead_id_uuid,
                step="qualify",
                status=run_status,
                latency_ms=latency_ms,
                model=QUALIFY_MODEL,
                prompt_version=PROMPT_VERSION,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                schema_valid=schema_valid,
                repair_attempted=repair_attempted,
                fallback_used=fallback_used,
                policy_decision=qualification.policy_decision,
                policy_reason=qualification.notes,
            )
            await update_lead_state(
                conn,
                lead_id_uuid,
                "QUALIFIED",
                priority=qualification.priority,
                budget_range=qualification.budget_range,
                timeline=qualification.timeline,
                qualification_notes=qualification.notes,
                routing=qualification.routing,
            )

    logger.info(
        "qualify_lead_completed",
        extra={
            "lead_id": lead_id,
            "priority": qualification.priority,
            "repair_attempted": repair_attempted,
            "fallback_used": fallback_used,
            "schema_valid": schema_valid,
        },
    )
    return QualificationResult(
        priority=qualification.priority,
        budget_range=qualification.budget_range,
        timeline=qualification.timeline,
        notes=qualification.notes,
        routing=qualification.routing,
        policy_decision=qualification.policy_decision,
        model=QUALIFY_MODEL,
        prompt_version=PROMPT_VERSION,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=float(cost),
        repair_attempted=repair_attempted,
        fallback_used=fallback_used,
    )
