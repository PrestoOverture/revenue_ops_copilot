import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID
import asyncpg  # type: ignore[import-untyped]
logger = logging.getLogger(__name__)

# allowed fields to update in the lead_state table
ALLOWED_LEAD_STATE_UPDATE_FIELDS = {
    "priority",
    "budget_range",
    "timeline",
    "qualification_notes",
    "routing",
    "touchpoint_count",
    "max_touchpoints",
    "next_followup_at",
    "name",
    "company",
    "source",
    "raw_payload",
    "email",
}

# insert an event into the events table
async def insert_event(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    dedupe_key: str,
    event_type: str,
    payload: dict[str, Any],
) -> UUID:
    payload_json = json.dumps(payload)
    query = """
        INSERT INTO events (tenant_id, dedupe_key, event_type, payload)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING id
    """
    event_id = await conn.fetchval(query, tenant_id, dedupe_key, event_type, payload_json)
    if event_id is None:
        raise RuntimeError("Failed to insert event")
    return event_id

# insert a lead into the lead_state table
async def insert_lead(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    external_lead_id: str,
    email: str,
    name: str | None,
    company: str | None,
    source: str | None,
    raw_payload: dict[str, Any] | None,
) -> UUID:
    raw_payload_json = json.dumps(raw_payload) if raw_payload is not None else None
    query = """
        INSERT INTO lead_state (
            tenant_id,
            external_lead_id,
            email,
            name,
            company,
            source,
            raw_payload
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING id
    """
    lead_id = await conn.fetchval(
        query,
        tenant_id,
        external_lead_id,
        email,
        name,
        company,
        source,
        raw_payload_json,
    )
    if lead_id is None:
        raise RuntimeError("Failed to insert lead")
    return lead_id

# get a lead by id from the lead_state table
async def get_lead_by_id(conn: asyncpg.Connection, lead_id: UUID) -> dict[str, Any] | None:
    query = "SELECT * FROM lead_state WHERE id = $1"
    row = await conn.fetchrow(query, lead_id)
    return dict(row) if row is not None else None


# update a lead in the lead_state table
async def update_lead_state(
    conn: asyncpg.Connection,
    lead_id: UUID,
    state: str,
    **fields: Any,
) -> None:
    values: list[Any] = [state]
    set_clauses: list[str] = ["state = $1", "updated_at = now()"]

    for field_name, field_value in fields.items():
        if field_name not in ALLOWED_LEAD_STATE_UPDATE_FIELDS:
            raise ValueError(f"Unsupported lead_state update field: {field_name}")

        if field_name == "raw_payload" and field_value is not None:
            field_value = json.dumps(field_value)
            set_clauses.append(f"{field_name} = ${len(values) + 1}::jsonb")
        else:
            set_clauses.append(f"{field_name} = ${len(values) + 1}")
        values.append(field_value)

    values.append(lead_id)
    query = f"UPDATE lead_state SET {', '.join(set_clauses)} WHERE id = ${len(values)}"
    await conn.execute(query, *values)

# insert an outbox into the outbox table
async def insert_outbox(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    lead_id: UUID,
    type: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> UUID:
    payload_json = json.dumps(payload)
    insert_query = """
        INSERT INTO outbox (
            tenant_id,
            lead_id,
            type,
            idempotency_key,
            payload
        )
        VALUES ($1, $2, $3, $4, $5::jsonb)
        ON CONFLICT (tenant_id, type, idempotency_key) DO NOTHING
        RETURNING id
    """
    outbox_id = await conn.fetchval(
        insert_query,
        tenant_id,
        lead_id,
        type,
        idempotency_key,
        payload_json,
    )
    if outbox_id is not None:
        return outbox_id

    select_query = """
        SELECT id
        FROM outbox
        WHERE tenant_id = $1 AND type = $2 AND idempotency_key = $3
    """
    existing_outbox_id = await conn.fetchval(select_query, tenant_id, type, idempotency_key)
    if existing_outbox_id is None:
        raise RuntimeError("Failed to insert or find existing outbox row")
    return existing_outbox_id

# insert a run into the runs table
async def insert_run(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    lead_id: UUID,
    step: str,
    status: str,
    error: str | None = None,
    error_code: str | None = None,
    latency_ms: int | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: Decimal | None = None,
    schema_valid: bool | None = None,
    repair_attempted: bool = False,
    fallback_used: str | None = None,
    policy_decision: str | None = None,
    policy_reason: str | None = None,
) -> UUID:
    query = """
        INSERT INTO runs (
            tenant_id,
            lead_id,
            step,
            status,
            error,
            error_code,
            latency_ms,
            model,
            prompt_version,
            tokens_in,
            tokens_out,
            cost_usd,
            schema_valid,
            repair_attempted,
            fallback_used,
            policy_decision,
            policy_reason
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
        )
        RETURNING id
    """
    run_id = await conn.fetchval(
        query,
        tenant_id,
        lead_id,
        step,
        status,
        error,
        error_code,
        latency_ms,
        model,
        prompt_version,
        tokens_in,
        tokens_out,
        cost_usd,
        schema_valid,
        repair_attempted,
        fallback_used,
        policy_decision,
        policy_reason,
    )
    if run_id is None:
        raise RuntimeError("Failed to insert run")
    return run_id

# get the tenant config from the tenant_config table
async def get_tenant_config(conn: asyncpg.Connection, tenant_id: UUID) -> dict[str, Any] | None:
    query = "SELECT * FROM tenant_config WHERE tenant_id = $1"
    row = await conn.fetchrow(query, tenant_id)
    return dict(row) if row is not None else None

# get an active prompt from the prompts table
async def get_active_prompt(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    name: str,
) -> dict[str, Any] | None:
    tenant_query = """
        SELECT *
        FROM prompts
        WHERE tenant_id = $1 AND name = $2 AND is_active = true
    """
    tenant_row = await conn.fetchrow(tenant_query, tenant_id, name)
    if tenant_row is not None:
        return dict(tenant_row)

    system_default_query = """
        SELECT *
        FROM prompts
        WHERE tenant_id IS NULL AND name = $1 AND is_active = true
    """
    system_default_row = await conn.fetchrow(system_default_query, name)
    return dict(system_default_row) if system_default_row is not None else None

# get a fallback template from the email_templates table
async def get_fallback_template(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    name: str,
) -> dict[str, Any] | None:
    query = """
        SELECT *
        FROM email_templates
        WHERE tenant_id = $1 AND name = $2
    """
    row = await conn.fetchrow(query, tenant_id, name)
    return dict(row) if row is not None else None
