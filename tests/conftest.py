from collections.abc import AsyncIterator
import logging
import asyncpg
import pytest
import pytest_asyncio
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from src.config import Settings
from src.db.connection import Database

logger = logging.getLogger(__name__)

# create test settings fixture
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

# create database pool fixture
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_pool(test_settings: Settings) -> AsyncIterator[asyncpg.Pool]:
    try:
        test_connection = await asyncpg.connect(dsn=test_settings.DATABASE_URL)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable for integration tests: {exc}")
    else:
        await test_connection.close()

    await Database.connect()
    assert Database.pool is not None
    logger.info("Integration test database pool connected")

    try:
        yield Database.pool
    finally:
        await Database.disconnect()
        logger.info("Integration test database pool disconnected")

# create database connection fixture
@pytest_asyncio.fixture(loop_scope="session")
async def db_conn(db_pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    async with db_pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            yield connection
        finally:
            await transaction.rollback()

# create temporal environment fixture
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_env() -> AsyncIterator[WorkflowEnvironment]:
    try:
        env = await WorkflowEnvironment.start_time_skipping()
    except RuntimeError as exc:
        if "Failed starting test server" in str(exc):
            pytest.skip("Temporal test server unavailable")
        raise

    try:
        yield env
    finally:
        await env.shutdown()

# create temporal client fixture
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_client(temporal_env: WorkflowEnvironment) -> Client:
    return temporal_env.client
