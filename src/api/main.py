from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from src.api.leads import router as leads_router
from src.api.middleware import RequestIdMiddleware
from src.api.webhooks import router as webhooks_router
from src.db.connection import Database
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


# lifespan callback
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    await Database.connect()
    logger.info("Database pool connected")
    yield
    await Database.disconnect()
    logger.info("Database pool disconnected")


# create FastAPI app
app = FastAPI(
    title="Revenue Ops Copilot",
    lifespan=lifespan,
)
app.add_middleware(RequestIdMiddleware)
app.include_router(leads_router)
app.include_router(webhooks_router)


# health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
