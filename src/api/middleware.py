import logging
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# context variable to store the request ID
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
# header name for the request ID
REQUEST_ID_HEADER = "X-Request-ID"

# logging filter that injects request_id into every log record
class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()  # type: ignore[attr-defined]
        return True

# middleware that assigns a unique request ID to each HTTP request
class RequestIdMiddleware(BaseHTTPMiddleware):
    # dispatch the request and assign the request ID to the response headers
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        rid = incoming_id if incoming_id else str(uuid.uuid4())

        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = rid
            return response
        finally:
            request_id_ctx.reset(token)
