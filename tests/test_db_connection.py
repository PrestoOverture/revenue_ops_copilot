from collections.abc import AsyncIterator
import asyncpg
import pytest
import pytest_asyncio
from src.config import Settings
from src.db.connection import Database

# mark the tests as asyncio and use the module scope
pytestmark = pytest.mark.asyncio(loop_scope="module")

# ensure that the database is available for the tests
@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_database_available() -> AsyncIterator[None]:
    database_url = Settings().DATABASE_URL  # type: ignore[call-arg]

    connection: asyncpg.Connection | None = None
    try:
        connection = await asyncpg.connect(dsn=database_url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable for db connection tests: {exc}")
    else:
        await connection.close()

    yield

    await Database.disconnect()

# test that the connect method creates a pool
async def test_connect_creates_pool() -> None:
    await Database.disconnect()
    await Database.connect()
    assert Database.pool is not None

# test that the pool.acquire method returns a working connection
async def test_pool_acquire_returns_working_connection() -> None:
    if Database.pool is None:
        await Database.connect()

    assert Database.pool is not None
    async with Database.pool.acquire() as connection:
        value = await connection.fetchval("SELECT 1;")
    assert value == 1

# test that the disconnect method closes the pool and sets the pool to None
async def test_disconnect_closes_pool() -> None:
    await Database.connect()
    await Database.disconnect()
    assert Database.pool is None

# test that the connect method is idempotent and returns the same pool    
async def test_connect_twice_is_idempotent() -> None:
    await Database.disconnect()

    await Database.connect()
    first_pool = Database.pool

    await Database.connect()
    second_pool = Database.pool

    assert first_pool is not None
    assert first_pool is second_pool

# test that the disconnect method is idempotent
async def test_disconnect_twice_is_idempotent() -> None:
    await Database.disconnect()
    await Database.disconnect()
    assert Database.pool is None
