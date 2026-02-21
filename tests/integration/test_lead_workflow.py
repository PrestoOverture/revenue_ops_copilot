import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4
import asyncpg
import httpx
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from src.activities.draft import draft_email
from src.activities.outbox import write_outbox_crm, write_outbox_email
from src.activities.qualify import qualify_lead
from src.api.main import app
from src.db.connection import Database
from src.db.queries import get_lead_by_id, insert_event, insert_lead
from src.workflows.lead_workflow import LeadWorkflow
from src.workflows.models import (
    LeadWorkflowInput,
    LeadWorkflowResult,
    QualificationResult,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# mock qualify lead response
def _mock_qualify_response() -> str:
    return json.dumps(
        {
            "priority": "P1",
            "budget_range": "mid_market",
            "timeline": "30_days",
            "notes": "Integration test qualification",
            "routing": "AUTO",
            "policy_decision": "ALLOW",
        }
    )

# mock draft email response for integration test
def _mock_draft_response() -> str:
    return json.dumps(
        {
            "subject": "Integration test subject",
            "body": "Integration test email body",
            "tone": "professional",
        }
    )

# mock schedule followup activity
@activity.defn(name="schedule_followup")
async def mock_schedule_followup(
    lead_id: str,
    touchpoint: int,
    qualification: QualificationResult,
) -> str:
    return f"followup:mock:{lead_id}:{touchpoint}"

# wait for workflow state to reach expected state
async def _wait_for_state(
    handle: Any,
    expected_state: str,
    max_iterations: int = 200,
) -> None:
    for _ in range(max_iterations):
        state = await handle.query(LeadWorkflow.get_state)
        if state == expected_state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Workflow did not reach state {expected_state}")

# test happy path lead workflow completes successfully
async def test_happy_path_lead_workflow(
    db_pool: asyncpg.Pool,
    temporal_env: WorkflowEnvironment,
) -> None:
    tenant_id = uuid4()
    external_lead_id = f"inttest-{uuid4()}"
    lead_id: UUID | None = None

    assert Database.pool is db_pool

    call_count = 0

    async def mock_chat_completion(
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, str | int]:
        nonlocal call_count
        del model, messages, kwargs
        call_count += 1
        content = (
            _mock_qualify_response() if call_count == 1 else _mock_draft_response()
        )
        return {"content": content, "tokens_in": 100, "tokens_out": 50}

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                event_id = await insert_event(
                    conn=conn,
                    tenant_id=tenant_id,
                    dedupe_key=f"dedupe-{external_lead_id}",
                    event_type="lead.created",
                    payload={"source": "integration_test"},
                )
                lead_id = await insert_lead(
                    conn=conn,
                    tenant_id=tenant_id,
                    external_lead_id=external_lead_id,
                    email="test@example.com",
                    name="Test Lead",
                    company="TestCorp",
                    source="web",
                    raw_payload={"source": "integration_test"},
                )
                assert isinstance(event_id, UUID)

        with patch(
            "src.llm.client.LLMClient.chat_completion",
            new_callable=AsyncMock,
            side_effect=mock_chat_completion,
        ):
            task_queue = f"test-queue-{uuid4()}"
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[LeadWorkflow],
                activities=[
                    qualify_lead,
                    draft_email,
                    write_outbox_email,
                    write_outbox_crm,
                    mock_schedule_followup,
                ],
            ):
                workflow_id = f"lead:{tenant_id}:{external_lead_id}"
                handle = await temporal_env.client.start_workflow(
                    LeadWorkflow.run,
                    LeadWorkflowInput(
                        lead_id=str(lead_id),
                        tenant_id=str(tenant_id),
                        external_lead_id=external_lead_id,
                        approval_required=False,
                        followups_enabled=True,
                    ),
                    id=workflow_id,
                    task_queue=task_queue,
                )
                result = await handle.result()

        assert call_count == 2
        assert isinstance(result, LeadWorkflowResult)
        assert result.status == "COMPLETED"

        assert lead_id is not None
        async with db_pool.acquire() as conn:
            lead = await get_lead_by_id(conn, lead_id)
            assert lead is not None
            assert lead["priority"] == "P1"
            assert lead["budget_range"] == "mid_market"
            assert lead["routing"] == "AUTO"
            assert lead["state"] in ("QUALIFIED", "DRAFTED")

            outbox_rows = await conn.fetch(
                "SELECT * FROM outbox WHERE lead_id = $1 ORDER BY type",
                lead_id,
            )
            assert len(outbox_rows) == 2
            types = {row["type"] for row in outbox_rows}
            assert types == {"SEND_EMAIL", "CRM_UPSERT"}
            for row in outbox_rows:
                assert row["status"] == "PENDING"

            run_rows = await conn.fetch(
                "SELECT * FROM runs WHERE lead_id = $1 ORDER BY step",
                lead_id,
            )
            assert len(run_rows) == 2
            steps = {row["step"] for row in run_rows}
            assert steps == {"qualify", "draft"}
            for row in run_rows:
                assert row["model"] is not None
                assert row["prompt_version"] is not None
                assert row["tokens_in"] is not None
                assert row["tokens_out"] is not None
                assert row["cost_usd"] is not None
                assert row["status"] == "OK"
                assert row["repair_attempted"] is False
                assert row["fallback_used"] is None
    finally:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                if lead_id is not None:
                    await conn.execute("DELETE FROM outbox WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM runs WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM lead_state WHERE id = $1", lead_id)
                await conn.execute("DELETE FROM events WHERE tenant_id = $1", tenant_id)

# test idempotency duplicate webhook returns duplicate
async def test_idempotency_duplicate_webhook(
    db_pool: asyncpg.Pool,
    temporal_env: WorkflowEnvironment,
) -> None:
    tenant_id = uuid4()
    external_lead_id = f"inttest-idempotency-{uuid4()}"
    dedupe_key = f"dedupe-idempotency-{uuid4()}"
    workflow_id = f"lead:{tenant_id}:{external_lead_id}"

    payload = {
        "tenant_id": str(tenant_id),
        "external_lead_id": external_lead_id,
        "dedupe_key": dedupe_key,
        "event_type": "lead.created",
        "email": "idempotency@example.com",
        "name": "Idempotency Test",
        "company": "TestCorp",
        "source": "web",
    }

    assert Database.pool is db_pool

    try:
        with (
            patch("src.api.main.Database.connect", new_callable=AsyncMock),
            patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
            patch(
                "src.api.webhooks.get_temporal_client",
                new_callable=AsyncMock,
                return_value=temporal_env.client,
            ),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                response_1 = await client.post("/webhooks/lead", json=payload)
                assert response_1.status_code == 200
                data_1 = response_1.json()
                assert data_1["status"] == "accepted"
                assert data_1["workflow_id"] == workflow_id

                response_2 = await client.post("/webhooks/lead", json=payload)
                assert response_2.status_code == 200
                data_2 = response_2.json()
                assert data_2["status"] == "duplicate"
                assert data_2["workflow_id"] == workflow_id

        async with db_pool.acquire() as conn:
            lead_rows = await conn.fetch(
                """
                SELECT *
                FROM lead_state
                WHERE tenant_id = $1 AND external_lead_id = $2
                """,
                tenant_id,
                external_lead_id,
            )
            assert len(lead_rows) == 1

            event_rows = await conn.fetch(
                """
                SELECT *
                FROM events
                WHERE tenant_id = $1 AND dedupe_key = $2
                """,
                tenant_id,
                dedupe_key,
            )
            assert len(event_rows) == 1
    finally:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                lead_row = await conn.fetchrow(
                    """
                    SELECT id
                    FROM lead_state
                    WHERE tenant_id = $1 AND external_lead_id = $2
                    """,
                    tenant_id,
                    external_lead_id,
                )
                if lead_row is not None:
                    lead_id = lead_row["id"]
                    await conn.execute("DELETE FROM outbox WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM runs WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM lead_state WHERE id = $1", lead_id)
                await conn.execute("DELETE FROM events WHERE tenant_id = $1", tenant_id)

# test approval required workflow completes successfully
async def test_approval_required_approve(
    db_pool: asyncpg.Pool,
    temporal_env: WorkflowEnvironment,
) -> None:
    tenant_id = uuid4()
    external_lead_id = f"inttest-approve-{uuid4()}"
    lead_id: UUID | None = None

    assert Database.pool is db_pool

    call_count = 0

    async def mock_chat_completion(
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, str | int]:
        nonlocal call_count
        del model, messages, kwargs
        call_count += 1
        content = (
            _mock_qualify_response() if call_count == 1 else _mock_draft_response()
        )
        return {"content": content, "tokens_in": 100, "tokens_out": 50}

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                event_id = await insert_event(
                    conn=conn,
                    tenant_id=tenant_id,
                    dedupe_key=f"dedupe-{external_lead_id}",
                    event_type="lead.created",
                    payload={"source": "integration_test"},
                )
                lead_id = await insert_lead(
                    conn=conn,
                    tenant_id=tenant_id,
                    external_lead_id=external_lead_id,
                    email="test-approve@example.com",
                    name="Test Approve Lead",
                    company="TestCorp",
                    source="web",
                    raw_payload={"source": "integration_test"},
                )
                assert isinstance(event_id, UUID)

        with patch(
            "src.llm.client.LLMClient.chat_completion",
            new_callable=AsyncMock,
            side_effect=mock_chat_completion,
        ):
            task_queue = f"test-queue-{uuid4()}"
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[LeadWorkflow],
                activities=[
                    qualify_lead,
                    draft_email,
                    write_outbox_email,
                    write_outbox_crm,
                    mock_schedule_followup,
                ],
            ):
                workflow_id = f"lead:{tenant_id}:{external_lead_id}"
                handle = await temporal_env.client.start_workflow(
                    LeadWorkflow.run,
                    LeadWorkflowInput(
                        lead_id=str(lead_id),
                        tenant_id=str(tenant_id),
                        external_lead_id=external_lead_id,
                        approval_required=True,
                        followups_enabled=True,
                    ),
                    id=workflow_id,
                    task_queue=task_queue,
                )
                await _wait_for_state(handle, "AWAITING_APPROVAL")
                await handle.signal(LeadWorkflow.approve)
                result = await handle.result()

        assert call_count == 2
        assert isinstance(result, LeadWorkflowResult)
        assert result.status == "COMPLETED"

        assert lead_id is not None
        async with db_pool.acquire() as conn:
            lead = await get_lead_by_id(conn, lead_id)
            assert lead is not None
            assert lead["priority"] == "P1"
            assert lead["budget_range"] == "mid_market"
            assert lead["routing"] == "AUTO"
            assert lead["state"] in ("QUALIFIED", "DRAFTED")

            outbox_rows = await conn.fetch(
                "SELECT * FROM outbox WHERE lead_id = $1 ORDER BY type",
                lead_id,
            )
            assert len(outbox_rows) == 2
            types = {row["type"] for row in outbox_rows}
            assert types == {"SEND_EMAIL", "CRM_UPSERT"}
            for row in outbox_rows:
                assert row["status"] == "PENDING"

            run_rows = await conn.fetch(
                "SELECT * FROM runs WHERE lead_id = $1 ORDER BY step",
                lead_id,
            )
            assert len(run_rows) == 2
            steps = {row["step"] for row in run_rows}
            assert steps == {"qualify", "draft"}
            for row in run_rows:
                assert row["model"] is not None
                assert row["prompt_version"] is not None
                assert row["tokens_in"] is not None
                assert row["tokens_out"] is not None
                assert row["cost_usd"] is not None
                assert row["status"] == "OK"
                assert row["repair_attempted"] is False
                assert row["fallback_used"] is None
    finally:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                if lead_id is not None:
                    await conn.execute("DELETE FROM outbox WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM runs WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM lead_state WHERE id = $1", lead_id)
                await conn.execute("DELETE FROM events WHERE tenant_id = $1", tenant_id)

# test approval required workflow cancelled
async def test_approval_required_cancel(
    db_pool: asyncpg.Pool,
    temporal_env: WorkflowEnvironment,
) -> None:
    tenant_id = uuid4()
    external_lead_id = f"inttest-cancel-{uuid4()}"
    lead_id: UUID | None = None

    assert Database.pool is db_pool

    call_count = 0

    async def mock_chat_completion(
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, str | int]:
        nonlocal call_count
        del model, messages, kwargs
        call_count += 1
        content = (
            _mock_qualify_response() if call_count == 1 else _mock_draft_response()
        )
        return {"content": content, "tokens_in": 100, "tokens_out": 50}

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                event_id = await insert_event(
                    conn=conn,
                    tenant_id=tenant_id,
                    dedupe_key=f"dedupe-{external_lead_id}",
                    event_type="lead.created",
                    payload={"source": "integration_test"},
                )
                lead_id = await insert_lead(
                    conn=conn,
                    tenant_id=tenant_id,
                    external_lead_id=external_lead_id,
                    email="test-cancel@example.com",
                    name="Test Cancel Lead",
                    company="TestCorp",
                    source="web",
                    raw_payload={"source": "integration_test"},
                )
                assert isinstance(event_id, UUID)

        with patch(
            "src.llm.client.LLMClient.chat_completion",
            new_callable=AsyncMock,
            side_effect=mock_chat_completion,
        ):
            task_queue = f"test-queue-{uuid4()}"
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[LeadWorkflow],
                activities=[
                    qualify_lead,
                    draft_email,
                    write_outbox_email,
                    write_outbox_crm,
                    mock_schedule_followup,
                ],
            ):
                workflow_id = f"lead:{tenant_id}:{external_lead_id}"
                handle = await temporal_env.client.start_workflow(
                    LeadWorkflow.run,
                    LeadWorkflowInput(
                        lead_id=str(lead_id),
                        tenant_id=str(tenant_id),
                        external_lead_id=external_lead_id,
                        approval_required=True,
                        followups_enabled=True,
                    ),
                    id=workflow_id,
                    task_queue=task_queue,
                )
                await _wait_for_state(handle, "AWAITING_APPROVAL")
                await handle.signal(LeadWorkflow.cancel)
                result = await handle.result()

        assert call_count == 2
        assert isinstance(result, LeadWorkflowResult)
        assert result.status == "CANCELLED"

        assert lead_id is not None
        async with db_pool.acquire() as conn:
            lead = await get_lead_by_id(conn, lead_id)
            assert lead is not None
            assert lead["priority"] == "P1"
            assert lead["budget_range"] == "mid_market"
            assert lead["routing"] == "AUTO"
            assert lead["state"] == "DRAFTED"

            outbox_rows = await conn.fetch(
                "SELECT * FROM outbox WHERE lead_id = $1 ORDER BY type",
                lead_id,
            )
            assert len(outbox_rows) == 0

            run_rows = await conn.fetch(
                "SELECT * FROM runs WHERE lead_id = $1 ORDER BY step",
                lead_id,
            )
            assert len(run_rows) == 2
            steps = {row["step"] for row in run_rows}
            assert steps == {"qualify", "draft"}
            for row in run_rows:
                assert row["model"] is not None
                assert row["prompt_version"] is not None
                assert row["tokens_in"] is not None
                assert row["tokens_out"] is not None
                assert row["cost_usd"] is not None
                assert row["status"] == "OK"
                assert row["repair_attempted"] is False
                assert row["fallback_used"] is None
    finally:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                if lead_id is not None:
                    await conn.execute("DELETE FROM outbox WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM runs WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM lead_state WHERE id = $1", lead_id)
                await conn.execute("DELETE FROM events WHERE tenant_id = $1", tenant_id)

# test LLM failure triggers fallback workflow
async def test_llm_failure_triggers_fallback(
    db_pool: asyncpg.Pool,
    temporal_env: WorkflowEnvironment,
) -> None:
    tenant_id = uuid4()
    external_lead_id = f"inttest-fallback-{uuid4()}"
    lead_id: UUID | None = None

    assert Database.pool is db_pool

    call_count = 0

    async def mock_chat_completion(
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, str | int]:
        nonlocal call_count
        del model, messages, kwargs
        call_count += 1
        if call_count == 1:
            content = "NOT VALID JSON AT ALL"
        elif call_count == 2:
            content = "STILL NOT VALID JSON"
        else:
            content = _mock_draft_response()
        return {"content": content, "tokens_in": 80, "tokens_out": 40}

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                event_id = await insert_event(
                    conn=conn,
                    tenant_id=tenant_id,
                    dedupe_key=f"dedupe-{external_lead_id}",
                    event_type="lead.created",
                    payload={"source": "integration_test"},
                )
                lead_id = await insert_lead(
                    conn=conn,
                    tenant_id=tenant_id,
                    external_lead_id=external_lead_id,
                    email="test-fallback@example.com",
                    name="Test Fallback Lead",
                    company="TestCorp",
                    source="web",
                    raw_payload={"source": "integration_test"},
                )
                assert isinstance(event_id, UUID)

        with patch(
            "src.llm.client.LLMClient.chat_completion",
            new_callable=AsyncMock,
            side_effect=mock_chat_completion,
        ):
            task_queue = f"test-queue-{uuid4()}"
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[LeadWorkflow],
                activities=[
                    qualify_lead,
                    draft_email,
                    write_outbox_email,
                    write_outbox_crm,
                    mock_schedule_followup,
                ],
            ):
                workflow_id = f"lead:{tenant_id}:{external_lead_id}"
                handle = await temporal_env.client.start_workflow(
                    LeadWorkflow.run,
                    LeadWorkflowInput(
                        lead_id=str(lead_id),
                        tenant_id=str(tenant_id),
                        external_lead_id=external_lead_id,
                        approval_required=False,
                        followups_enabled=True,
                    ),
                    id=workflow_id,
                    task_queue=task_queue,
                )
                await _wait_for_state(handle, "AWAITING_APPROVAL")
                await handle.signal(LeadWorkflow.approve)
                result = await handle.result()

        assert call_count == 3
        assert isinstance(result, LeadWorkflowResult)
        assert result.status == "COMPLETED"

        assert lead_id is not None
        async with db_pool.acquire() as conn:
            lead = await get_lead_by_id(conn, lead_id)
            assert lead is not None
            assert lead["priority"] == "P2"
            assert lead["budget_range"] == "unknown"
            assert lead["routing"] == "REQUIRE_REVIEW"
            assert lead["qualification_notes"] == "Fallback due to LLM failure"

            outbox_rows = await conn.fetch(
                "SELECT * FROM outbox WHERE lead_id = $1 ORDER BY type",
                lead_id,
            )
            assert len(outbox_rows) == 2
            types = {row["type"] for row in outbox_rows}
            assert types == {"SEND_EMAIL", "CRM_UPSERT"}

            run_rows = await conn.fetch(
                "SELECT * FROM runs WHERE lead_id = $1 ORDER BY created_at",
                lead_id,
            )
            assert len(run_rows) == 2

            qualify_run = next(r for r in run_rows if r["step"] == "qualify")
            assert qualify_run["status"] == "FALLBACK"
            assert qualify_run["repair_attempted"] is True
            assert qualify_run["fallback_used"] == "DEFAULTS"
            assert qualify_run["model"] == "gpt-4o-mini"
            assert qualify_run["prompt_version"] is not None
            assert qualify_run["tokens_in"] is not None
            assert qualify_run["tokens_out"] is not None
            assert qualify_run["cost_usd"] is not None

            draft_run = next(r for r in run_rows if r["step"] == "draft")
            assert draft_run["status"] == "OK"
            assert draft_run["repair_attempted"] is False
            assert draft_run["fallback_used"] is None
            assert draft_run["model"] == "gpt-4o"
    finally:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                if lead_id is not None:
                    await conn.execute("DELETE FROM outbox WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM runs WHERE lead_id = $1", lead_id)
                    await conn.execute("DELETE FROM lead_state WHERE id = $1", lead_id)
                await conn.execute("DELETE FROM events WHERE tenant_id = $1", tenant_id)
