import logging
import asyncpg  # type: ignore[import-untyped]
from src.config import Settings

logger = logging.getLogger(__name__)

# manages the database connection pool
class Database:
    pool: asyncpg.Pool | None = None

    # connect to the database and create a pool
    @classmethod
    async def connect(cls) -> None:
        if cls.pool is not None:
            logger.warning("Database pool already connected")
            return

        database_url = Settings().DATABASE_URL  # type: ignore[call-arg]
        cls.pool = await asyncpg.create_pool(dsn=database_url)
        logger.info("Database pool connected")

    # disconnect from the database and close the pool
    @classmethod
    async def disconnect(cls) -> None:
        if cls.pool is None:
            return

        await cls.pool.close()
        cls.pool = None
        logger.info("Database pool disconnected")
