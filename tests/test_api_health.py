from unittest.mock import AsyncMock, patch
import httpx
import pytest
from src.api.main import app

# test health returns 200
@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

# test health response content type
@pytest.mark.asyncio
async def test_health_response_content_type() -> None:
    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health")

    assert response.headers["content-type"] == "application/json"

# test openapi docs available at /docs
@pytest.mark.asyncio
async def test_openapi_docs_available() -> None:
    with (
        patch("src.api.main.Database.connect", new_callable=AsyncMock),
        patch("src.api.main.Database.disconnect", new_callable=AsyncMock),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/docs")

    assert response.status_code == 200
