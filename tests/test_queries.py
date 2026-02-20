from decimal import Decimal
from uuid import UUID, uuid4
import asyncpg
import pytest
import pytest_asyncio
from src.config import Settings
from src.db.connection import Database
from src.db.queries import (
    get_active_prompt,
    get_fallback_template,
    get_lead_by_id,
    get_tenant_config,
    insert_event,
    insert_lead,
    insert_outbox,
    insert_run,
    update_lead_state,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")

# ensure that the database is available for the tests
@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="module")
async def ensure_database_available() -> None:
    database_url = Settings().DATABASE_URL  # type: ignore[call-arg]
    try:
        test_connection = await asyncpg.connect(dsn=database_url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable for query tests: {exc}")
    else:
        await test_connection.close()

    await Database.connect()
    yield
    await Database.disconnect()

# get a connection from the database pool
@pytest_asyncio.fixture(loop_scope="module")
async def conn() -> asyncpg.Connection:
    assert Database.pool is not None
    async with Database.pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            yield connection
        finally:
            await transaction.rollback()

# create a lead for the tests
async def _create_lead(conn: asyncpg.Connection, tenant_id: UUID, suffix: str) -> UUID:
    return await insert_lead(
        conn=conn,
        tenant_id=tenant_id,
        external_lead_id=f"ext-{suffix}",
        email=f"{suffix}@example.com",
        name="Lead Name",
        company="Acme",
        source="web",
        raw_payload={"source": "test"},
    )

# test that the insert_event function inserts an event into the events table
async def test_insert_event(conn: asyncpg.Connection) -> None:
    event_id = await insert_event(
        conn=conn,
        tenant_id=uuid4(),
        dedupe_key=f"dedupe-{uuid4()}",
        event_type="lead.created",
        payload={"hello": "world"},
    )
    assert isinstance(event_id, UUID)

# test that the insert_event function raises an exception if the event already exists
async def test_insert_event_duplicate(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    dedupe_key = f"dedupe-{uuid4()}"

    await insert_event(
        conn=conn,
        tenant_id=tenant_id,
        dedupe_key=dedupe_key,
        event_type="lead.created",
        payload={"value": 1},
    )

    with pytest.raises(asyncpg.UniqueViolationError):
        await insert_event(
            conn=conn,
            tenant_id=tenant_id,
            dedupe_key=dedupe_key,
            event_type="lead.created",
            payload={"value": 2},
        )

# test that the insert_lead function inserts a lead into the lead_state table
async def test_insert_lead(conn: asyncpg.Connection) -> None:
    lead_id = await _create_lead(conn, uuid4(), "insert-lead")
    assert isinstance(lead_id, UUID)

# test that the get_lead_by_id function gets a lead by id from the lead_state table
async def test_get_lead_by_id(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    lead_id = await _create_lead(conn, tenant_id, "get-lead")

    lead = await get_lead_by_id(conn, lead_id)

    assert lead is not None
    assert lead["id"] == lead_id
    assert lead["tenant_id"] == tenant_id
    assert lead["email"] == "get-lead@example.com"

# test that the get_lead_by_id function returns None if the lead is not found
async def test_get_lead_by_id_not_found(conn: asyncpg.Connection) -> None:
    lead = await get_lead_by_id(conn, uuid4())
    assert lead is None

# test that the update_lead_state function updates a lead in the lead_state table
async def test_update_lead_state(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    lead_id = await _create_lead(conn, tenant_id, "update-state")

    await update_lead_state(conn, lead_id, "QUALIFIED", priority="P1")
    lead = await get_lead_by_id(conn, lead_id)

    assert lead is not None
    assert lead["state"] == "QUALIFIED"
    assert lead["priority"] == "P1"

# test that the insert_outbox function inserts an outbox into the outbox table
async def test_insert_outbox(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    lead_id = await _create_lead(conn, tenant_id, "outbox")

    outbox_id = await insert_outbox(
        conn=conn,
        tenant_id=tenant_id,
        lead_id=lead_id,
        type="email",
        idempotency_key=f"idempotency-{uuid4()}",
        payload={"subject": "hello"},
    )
    assert isinstance(outbox_id, UUID)

# test that the insert_outbox function is idempotent
async def test_insert_outbox_idempotent(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    lead_id = await _create_lead(conn, tenant_id, "outbox-idempotent")
    idempotency_key = f"idempotency-{uuid4()}"

    first_outbox_id = await insert_outbox(
        conn=conn,
        tenant_id=tenant_id,
        lead_id=lead_id,
        type="email",
        idempotency_key=idempotency_key,
        payload={"subject": "hello"},
    )
    second_outbox_id = await insert_outbox(
        conn=conn,
        tenant_id=tenant_id,
        lead_id=lead_id,
        type="email",
        idempotency_key=idempotency_key,
        payload={"subject": "hello"},
    )

    assert first_outbox_id == second_outbox_id

# test that the insert_run function inserts a run into the runs table
async def test_insert_run(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    lead_id = await _create_lead(conn, tenant_id, "insert-run")

    run_id = await insert_run(
        conn=conn,
        tenant_id=tenant_id,
        lead_id=lead_id,
        step="qualify",
        status="SUCCESS",
        error=None,
        error_code=None,
        latency_ms=1200,
        model="gpt-4o-mini",
        prompt_version="qualify_v1.0",
        tokens_in=100,
        tokens_out=40,
        cost_usd=Decimal("0.000123"),
        schema_valid=True,
        repair_attempted=False,
        fallback_used=None,
        policy_decision="ALLOW",
        policy_reason="meets-policy",
    )
    assert isinstance(run_id, UUID)

# test that the get_tenant_config function gets the tenant config from the tenant_config table
async def test_get_tenant_config(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    await conn.execute(
        """
        INSERT INTO tenant_config (
            tenant_id, email_provider, llm_provider
        )
        VALUES ($1, $2, $3)
        """,
        tenant_id,
        "sendgrid",
        "openai",
    )

    config = await get_tenant_config(conn, tenant_id)
    assert config is not None
    assert config["tenant_id"] == tenant_id
    assert config["email_provider"] == "sendgrid"

# test that the get_tenant_config function returns None if the tenant config is not found
async def test_get_tenant_config_not_found(conn: asyncpg.Connection) -> None:
    config = await get_tenant_config(conn, uuid4())
    assert config is None

# test that the get_active_prompt function gets an active prompt from the prompts table
async def test_get_active_prompt(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    prompt_name = f"qualify-{uuid4()}"
    await conn.execute(
        """
        INSERT INTO prompts (
            tenant_id, name, version, system_prompt, user_template, model, is_active
        )
        VALUES ($1, $2, $3, $4, $5, $6, true)
        """,
        tenant_id,
        prompt_name,
        "v1.0",
        "system",
        "user",
        "gpt-4o-mini",
    )

    prompt = await get_active_prompt(conn, tenant_id, prompt_name)
    assert prompt is not None
    assert prompt["tenant_id"] == tenant_id
    assert prompt["name"] == prompt_name

# test that the get_active_prompt function falls back to the system prompt if the tenant prompt is not found
async def test_get_active_prompt_falls_back_to_system(conn: asyncpg.Connection) -> None:
    requesting_tenant_id = uuid4()
    prompt_name = f"draft-{uuid4()}"
    await conn.execute(
        """
        INSERT INTO prompts (
            tenant_id, name, version, system_prompt, user_template, model, is_active
        )
        VALUES (NULL, $1, $2, $3, $4, $5, true)
        """,
        prompt_name,
        "v1.0",
        "system-default",
        "user-default",
        "gpt-4o-mini",
    )

    prompt = await get_active_prompt(conn, requesting_tenant_id, prompt_name)
    assert prompt is not None
    assert prompt["tenant_id"] is None
    assert prompt["name"] == prompt_name

# test that the get_fallback_template function gets a fallback template from the email_templates table
async def test_get_fallback_template(conn: asyncpg.Connection) -> None:
    tenant_id = uuid4()
    template_name = f"initial-{uuid4()}"
    await conn.execute(
        """
        INSERT INTO email_templates (
            tenant_id, name, subject_template, body_template
        )
        VALUES ($1, $2, $3, $4)
        """,
        tenant_id,
        template_name,
        "Hello {{ name }}",
        "Body",
    )

    template = await get_fallback_template(conn, tenant_id, template_name)
    assert template is not None
    assert template["tenant_id"] == tenant_id
    assert template["name"] == template_name

# test that the get_fallback_template function returns None if the fallback template is not found
async def test_get_fallback_template_not_found(conn: asyncpg.Connection) -> None:
    template = await get_fallback_template(conn, uuid4(), f"missing-{uuid4()}")
    assert template is None
