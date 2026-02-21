import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
import pytest
from temporalio.testing import ActivityEnvironment
from src.activities.qualify import qualify_lead
from src.llm.prompts.qualify import FALLBACK_QUALIFICATION, PROMPT_VERSION
from src.workflows.models import QualificationResult

# build mock pool and connection
def _build_pool_and_connection_mocks() -> tuple[MagicMock, MagicMock]:
    mock_conn = MagicMock()

    transaction_cm = AsyncMock()
    transaction_cm.__aenter__.return_value = None
    transaction_cm.__aexit__.return_value = None
    mock_conn.transaction.return_value = transaction_cm

    acquire_cm = AsyncMock()
    acquire_cm.__aenter__.return_value = mock_conn
    acquire_cm.__aexit__.return_value = None

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acquire_cm
    return mock_pool, mock_conn

# mock lead fixture
@pytest.fixture
def mock_lead() -> dict[str, object]:
    return {
        "id": UUID("00000000-0000-0000-0000-000000000123"),
        "tenant_id": UUID("00000000-0000-0000-0000-000000000001"),
        "external_lead_id": "hubspot-123",
        "email": "test@example.com",
        "name": "Test User",
        "company": "Test Corp",
        "source": "website",
        "raw_payload": {},
        "state": "PENDING",
    }

# test qualify lead happy path
@pytest.mark.asyncio
async def test_qualify_lead_happy_path(mock_lead: dict[str, object]) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, mock_conn = _build_pool_and_connection_mocks()
    llm_content = {
        "priority": "P1",
        "budget_range": "mid_market",
        "timeline": "30_days",
        "notes": "High intent and active evaluation.",
        "routing": "AUTO",
        "policy_decision": "ALLOW",
    }

    with (
        patch("src.activities.qualify.Database") as mock_database,
        patch(
            "src.activities.qualify.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.qualify.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.qualify.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.qualify.update_lead_state",
            new_callable=AsyncMock,
        ) as mock_update_lead_state,
        patch(
            "src.activities.qualify.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": json.dumps(llm_content),
                "tokens_in": 120,
                "tokens_out": 40,
            }
        )
        environment = ActivityEnvironment()
        result = await environment.run(qualify_lead, str(lead_id))

    assert isinstance(result, QualificationResult)
    assert result.priority == "P1"
    assert result.budget_range == "mid_market"
    assert result.repair_attempted is False
    assert result.fallback_used is None
    assert result.model == "gpt-4o-mini"
    mock_update_lead_state.assert_any_await(mock_conn, lead_id, "QUALIFYING")
    mock_update_lead_state.assert_any_await(
        mock_conn,
        lead_id,
        "QUALIFIED",
        priority="P1",
        budget_range="mid_market",
        timeline="30_days",
        qualification_notes="High intent and active evaluation.",
        routing="AUTO",
    )

    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["step"] == "qualify"
    assert insert_run_kwargs["status"] == "OK"
    assert insert_run_kwargs["schema_valid"] is True

# test qualify lead repair success
@pytest.mark.asyncio
async def test_qualify_lead_repair_success(mock_lead: dict[str, object]) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()
    repaired_output = {
        "priority": "P0",
        "budget_range": "enterprise",
        "timeline": "immediate",
        "notes": "Repair succeeded with complete qualification fields.",
        "routing": "AUTO",
        "policy_decision": "ALLOW",
    }

    with (
        patch("src.activities.qualify.Database") as mock_database,
        patch(
            "src.activities.qualify.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.qualify.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.qualify.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.qualify.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.qualify.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
        patch(
            "src.activities.qualify.repair_json",
            new_callable=AsyncMock,
            return_value=repaired_output,
        ) as mock_repair_json,
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": "not json at all",
                "tokens_in": 75,
                "tokens_out": 30,
            }
        )
        environment = ActivityEnvironment()
        result = await environment.run(qualify_lead, str(lead_id))

    assert result.repair_attempted is True
    assert result.fallback_used is None
    mock_repair_json.assert_awaited_once()
    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["repair_attempted"] is True
    assert insert_run_kwargs["schema_valid"] is True

# test qualify lead fallback
@pytest.mark.asyncio
async def test_qualify_lead_fallback(mock_lead: dict[str, object]) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.qualify.Database") as mock_database,
        patch(
            "src.activities.qualify.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.qualify.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.qualify.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.qualify.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.qualify.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
        patch(
            "src.activities.qualify.repair_json",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": "invalid payload",
                "tokens_in": 80,
                "tokens_out": 20,
            }
        )
        environment = ActivityEnvironment()
        result = await environment.run(qualify_lead, str(lead_id))

    assert result.priority == FALLBACK_QUALIFICATION.priority
    assert result.routing == FALLBACK_QUALIFICATION.routing
    assert result.repair_attempted is True
    assert result.fallback_used == "DEFAULTS"
    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["repair_attempted"] is True
    assert insert_run_kwargs["fallback_used"] == "DEFAULTS"
    assert insert_run_kwargs["status"] == "FALLBACK"

# test qualify lead run record telemetry
@pytest.mark.asyncio
async def test_qualify_lead_run_record_telemetry(mock_lead: dict[str, object]) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()
    llm_content = {
        "priority": "P1",
        "budget_range": "smb",
        "timeline": "90_days",
        "notes": "Qualified SMB lead with medium urgency.",
        "routing": "REQUIRE_REVIEW",
        "policy_decision": "REQUIRE_REVIEW",
    }

    with (
        patch("src.activities.qualify.Database") as mock_database,
        patch(
            "src.activities.qualify.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.qualify.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.qualify.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.qualify.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.qualify.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": json.dumps(llm_content),
                "tokens_in": 100,
                "tokens_out": 50,
            }
        )
        environment = ActivityEnvironment()
        await environment.run(qualify_lead, str(lead_id))

    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["model"] == "gpt-4o-mini"
    assert insert_run_kwargs["prompt_version"] == PROMPT_VERSION
    assert insert_run_kwargs["tokens_in"] == 100
    assert insert_run_kwargs["tokens_out"] == 50
    assert isinstance(insert_run_kwargs["cost_usd"], Decimal)
    assert insert_run_kwargs["cost_usd"] > Decimal("0")
    assert isinstance(insert_run_kwargs["latency_ms"], int)
    assert insert_run_kwargs["latency_ms"] >= 0

# test qualify lead not found
@pytest.mark.asyncio
async def test_qualify_lead_not_found(mock_lead: dict[str, object]) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.qualify.Database") as mock_database,
        patch(
            "src.activities.qualify.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.qualify.LLMClient"),
        patch(
            "src.activities.qualify.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.activities.qualify.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.qualify.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        with pytest.raises(ValueError, match=str(lead_id)):
            await environment.run(qualify_lead, str(lead_id))
