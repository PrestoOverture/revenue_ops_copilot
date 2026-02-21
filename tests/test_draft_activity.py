import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
import pytest
from temporalio.testing import ActivityEnvironment
from src.activities.draft import draft_email
from src.llm.prompts.draft import PROMPT_VERSION
from src.workflows.models import DraftResult, QualificationResult

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
        "state": "QUALIFIED",
    }

# sample qualification fixture
@pytest.fixture
def sample_qualification() -> QualificationResult:
    return QualificationResult(
        priority="P1",
        budget_range="mid_market",
        timeline="30_days",
        notes="Good fit.",
        routing="AUTO",
        policy_decision="ALLOW",
        model="gpt-4o-mini",
        prompt_version="qualify_v1.0",
        tokens_in=100,
        tokens_out=40,
        cost_usd=0.00015,
    )

# test draft email happy path
@pytest.mark.asyncio
async def test_draft_email_happy_path(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, mock_conn = _build_pool_and_connection_mocks()
    llm_content = {
        "subject": "Hello",
        "body": "Dear Test User, thanks for your interest.",
        "tone": "professional",
    }

    with (
        patch("src.activities.draft.Database") as mock_database,
        patch(
            "src.activities.draft.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.draft.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.draft.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.draft.update_lead_state",
            new_callable=AsyncMock,
        ) as mock_update_lead_state,
        patch(
            "src.activities.draft.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": json.dumps(llm_content),
                "tokens_in": 160,
                "tokens_out": 70,
            }
        )
        environment = ActivityEnvironment()
        result = await environment.run(draft_email, str(lead_id), sample_qualification)

    assert isinstance(result, DraftResult)
    assert result.subject == "Hello"
    assert result.body == "Dear Test User, thanks for your interest."
    assert result.tone == "professional"
    assert result.repair_attempted is False
    assert result.fallback_used is None
    assert result.model == "gpt-4o"
    mock_update_lead_state.assert_any_await(mock_conn, lead_id, "DRAFTING")
    mock_update_lead_state.assert_any_await(mock_conn, lead_id, "DRAFTED")

    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["step"] == "draft"
    assert insert_run_kwargs["status"] == "OK"
    assert insert_run_kwargs["schema_valid"] is True

# test draft email repair success
@pytest.mark.asyncio
async def test_draft_email_repair_success(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()
    repaired_output = {
        "subject": "Follow-up",
        "body": "Hi Test User, wanted to reconnect on your inquiry.",
        "tone": "friendly",
    }

    with (
        patch("src.activities.draft.Database") as mock_database,
        patch(
            "src.activities.draft.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.draft.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.draft.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.draft.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.draft.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
        patch(
            "src.activities.draft.repair_json",
            new_callable=AsyncMock,
            return_value=repaired_output,
        ),
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": "not valid json",
                "tokens_in": 120,
                "tokens_out": 60,
            }
        )
        environment = ActivityEnvironment()
        result = await environment.run(draft_email, str(lead_id), sample_qualification)

    assert result.repair_attempted is True
    assert result.fallback_used is None
    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["repair_attempted"] is True
    assert insert_run_kwargs["schema_valid"] is True

# test draft email fallback template
@pytest.mark.asyncio
async def test_draft_email_fallback_template(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.draft.Database") as mock_database,
        patch(
            "src.activities.draft.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.draft.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.draft.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.draft.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.draft.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
        patch(
            "src.activities.draft.repair_json",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": "invalid draft output",
                "tokens_in": 90,
                "tokens_out": 35,
            }
        )
        environment = ActivityEnvironment()
        result = await environment.run(draft_email, str(lead_id), sample_qualification)

    assert "Following up" in result.subject
    assert "Test User" in result.body
    assert "Test Corp" in result.body
    assert result.repair_attempted is True
    assert result.fallback_used == "TEMPLATE"
    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["fallback_used"] == "TEMPLATE"
    assert insert_run_kwargs["status"] == "FALLBACK"

# test draft email run record telemetry
@pytest.mark.asyncio
async def test_draft_email_run_record_telemetry(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()
    llm_content = {
        "subject": "Following up",
        "body": "Hi Test User, checking in on your current priorities.",
        "tone": "professional",
    }

    with (
        patch("src.activities.draft.Database") as mock_database,
        patch(
            "src.activities.draft.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.draft.LLMClient") as mock_llm_client_cls,
        patch(
            "src.activities.draft.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=mock_lead,
        ),
        patch(
            "src.activities.draft.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.draft.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ) as mock_insert_run,
    ):
        mock_database.pool = mock_pool
        mock_llm_client = mock_llm_client_cls.return_value
        mock_llm_client.chat_completion = AsyncMock(
            return_value={
                "content": json.dumps(llm_content),
                "tokens_in": 200,
                "tokens_out": 100,
            }
        )
        environment = ActivityEnvironment()
        await environment.run(draft_email, str(lead_id), sample_qualification)

    insert_run_call = mock_insert_run.await_args
    assert insert_run_call is not None
    insert_run_kwargs = insert_run_call.kwargs
    assert insert_run_kwargs["model"] == "gpt-4o"
    assert insert_run_kwargs["prompt_version"] == PROMPT_VERSION
    assert insert_run_kwargs["tokens_in"] == 200
    assert insert_run_kwargs["tokens_out"] == 100
    assert isinstance(insert_run_kwargs["cost_usd"], Decimal)
    assert insert_run_kwargs["cost_usd"] > Decimal("0")
    assert isinstance(insert_run_kwargs["latency_ms"], int)
    assert insert_run_kwargs["latency_ms"] >= 0

# test draft email lead not found
@pytest.mark.asyncio
async def test_draft_email_lead_not_found(
    mock_lead: dict[str, object],
    sample_qualification: QualificationResult,
) -> None:
    lead_id = mock_lead["id"]
    assert isinstance(lead_id, UUID)
    mock_pool, _ = _build_pool_and_connection_mocks()

    with (
        patch("src.activities.draft.Database") as mock_database,
        patch(
            "src.activities.draft.Settings",
            return_value=SimpleNamespace(OPENAI_API_KEY="test-key"),
        ),
        patch("src.activities.draft.LLMClient"),
        patch(
            "src.activities.draft.get_lead_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.activities.draft.update_lead_state",
            new_callable=AsyncMock,
        ),
        patch(
            "src.activities.draft.insert_run",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ),
    ):
        mock_database.pool = mock_pool
        environment = ActivityEnvironment()
        with pytest.raises(ValueError, match=str(lead_id)):
            await environment.run(draft_email, str(lead_id), sample_qualification)
