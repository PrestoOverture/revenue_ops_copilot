import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from src.workflows.client import get_temporal_client, reset_client

# reset temporal client singleton
@pytest_asyncio.fixture(autouse=True)
async def reset_temporal_client_singleton() -> None:
    await reset_client()
    yield
    await reset_client()

# test singleton returns same instance
@pytest.mark.asyncio
async def test_singleton_returns_same_instance() -> None:
    mock_client = MagicMock()
    settings = SimpleNamespace(
        TEMPORAL_ADDRESS="localhost:7233",
        TEMPORAL_NAMESPACE="default",
    )

    with (
        patch("src.config.Settings", return_value=settings),
        patch(
            "temporalio.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_connect,
    ):
        client_one = await get_temporal_client()
        client_two = await get_temporal_client()

    assert client_one is client_two
    mock_connect.assert_awaited_once()

# test reset client clears singleton
@pytest.mark.asyncio
async def test_reset_client_clears_singleton() -> None:
    settings = SimpleNamespace(
        TEMPORAL_ADDRESS="localhost:7233",
        TEMPORAL_NAMESPACE="default",
    )

    with (
        patch("src.config.Settings", return_value=settings),
        patch(
            "temporalio.client.Client.connect",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ) as mock_connect,
    ):
        await get_temporal_client()
        await reset_client()
        await get_temporal_client()

    assert mock_connect.await_count == 2

# test connection error logged and reraised
@pytest.mark.asyncio
async def test_connection_error_logged_and_reraised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = SimpleNamespace(
        TEMPORAL_ADDRESS="test-host:7233",
        TEMPORAL_NAMESPACE="test-ns",
    )

    with (
        patch("src.config.Settings", return_value=settings),
        patch(
            "temporalio.client.Client.connect",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection refused"),
        ),
    ):
        with caplog.at_level(logging.ERROR, logger="src.workflows.client"):
            with pytest.raises(RuntimeError, match="Connection refused"):
                await get_temporal_client()

    assert any(
        "temporal_client_connection_failed" in record.message
        and "test-host:7233" in record.message
        and "test-ns" in record.message
        for record in caplog.records
    )

# test reads settings correctly from namespace
@pytest.mark.asyncio
async def test_reads_settings_correctly() -> None:
    mock_client = MagicMock()
    settings = SimpleNamespace(
        TEMPORAL_ADDRESS="test-host:7233",
        TEMPORAL_NAMESPACE="test-ns",
    )

    with (
        patch("src.config.Settings", return_value=settings),
        patch(
            "temporalio.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_connect,
    ):
        client = await get_temporal_client()

    assert client is mock_client
    mock_connect.assert_awaited_once_with(
        target_host="test-host:7233",
        namespace="test-ns",
    )
