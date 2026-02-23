import io
import json
import logging
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from src.api.main import app
from src.api.middleware import RequestIdFilter, request_id_ctx
from src.logging_config import setup_logging

# test request id middleware and log correlation
class TestRequestIdMiddleware:
    # patch database connect/disconnect so tests don't need a real DB
    @pytest.fixture(autouse=True)
    def _patch_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.db import connection

        async def _noop() -> None:
            pass

        monkeypatch.setattr(connection.Database, "connect", staticmethod(_noop))
        monkeypatch.setattr(connection.Database, "disconnect", staticmethod(_noop))

    # test response has x-request-id header
    @pytest.mark.asyncio
    async def test_response_has_x_request_id_header(self) -> None:
        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        rid = resp.headers.get("X-Request-ID")
        assert rid is not None
        uuid.UUID(rid)

    # test caller provided request id is used
    @pytest.mark.asyncio
    async def test_caller_provided_request_id_is_used(self) -> None:
        custom_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers.get("X-Request-ID") == custom_id

    # test request id appears in logs
    @pytest.mark.asyncio
    async def test_request_id_appears_in_logs(self) -> None:
        setup_logging()

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)

        try:
            transport = ASGITransport(app=app)  # type: ignore[arg-type]
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.get("/health")

            rid = resp.headers.get("X-Request-ID")
            output = stream.getvalue()

            log_lines = [line for line in output.strip().split("\n") if line]
            matched: list[dict[str, object]] = []
            for line in log_lines:
                try:
                    parsed = json.loads(line)
                    if parsed.get("request_id") == rid:
                        matched.append(parsed)
                except json.JSONDecodeError:
                    continue

            assert rid is not None
        finally:
            root.removeHandler(handler)

    # test contextvar default is empty string
    def test_contextvar_default_is_empty_string(self) -> None:
        assert request_id_ctx.get() == ""
