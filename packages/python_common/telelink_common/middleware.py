"""Request correlation via pure ASGI middleware (safe for streaming responses)."""

import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from telelink_common.logging import request_id_context

logger = logging.getLogger("telelink.request")
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp, service: str) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("x-request-id", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        started = perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["x-request-id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            try:
                # Log the route template, never query strings or IDs in raw paths.
                route = getattr(scope.get("route"), "path", "<unmatched>")
                logger.info(
                    "http_request",
                    extra={
                        "service": self.service,
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": route,
                        "status_code": status_code,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    },
                )
            finally:
                request_id_context.reset(token)
