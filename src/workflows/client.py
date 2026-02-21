import asyncio
import logging
from temporalio.client import Client

logger = logging.getLogger(__name__)

_client: Client | None = None
_lock = asyncio.Lock()

# get a connected Temporal client using an async-safe singleton
async def get_temporal_client() -> Client:
    global _client

    async with _lock:
        if _client is not None:
            return _client

        from src.config import Settings

        settings = Settings()  # type: ignore[call-arg]
        target_host = settings.TEMPORAL_ADDRESS
        namespace = settings.TEMPORAL_NAMESPACE

        try:
            _client = await Client.connect(
                target_host=target_host,
                namespace=namespace,
            )
        except Exception:
            logger.exception(
                "temporal_client_connection_failed address=%s namespace=%s",
                target_host,
                namespace,
                extra={
                    "target_host": target_host,
                    "namespace": namespace,
                },
            )
            raise

        return _client

# reset the Temporal client singleton. Intended for tests.
async def reset_client() -> None:
    global _client

    async with _lock:
        _client = None
