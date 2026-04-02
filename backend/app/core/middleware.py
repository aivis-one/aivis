# =============================================================================
# CBSHOME Backend -- ASGI Middleware
# =============================================================================
#
# Pure ASGI -- no BaseHTTPMiddleware wrapper. This guarantees that
# structlog contextvars work reliably without TaskGroup isolation
# issues that BaseHTTPMiddleware can introduce.
#
# TRACE ID:
#   Every HTTP request gets a trace_id:
#     - From X-Trace-ID header (if provided by client/load balancer)
#     - Or auto-generated uuid4
#   The trace_id is:
#     1. Bound to structlog contextvars -> appears in every log line
#     2. Returned in X-Trace-ID response header -> client can correlate
#     3. Available via contextvars for AuditLog (Sprint 0.5+)
#
# AVATAR SESSION:
#   If the Redis session contains avatar_session_id, it is read and
#   bound to structlog contextvars. Every log line in avatar mode
#   is automatically annotated without changes in business logic.
#   Populated by start_avatar() in Sprint 3.2.
#
# SECURITY:
#   Client-provided trace_id is validated against a safe character set.
#   Values > 36 chars or with unsafe chars are replaced with fresh uuid4.
#   Prevents log injection and AuditLog pollution (trace_id is String(36)).
# =============================================================================

import re
from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

# Safe character set: UUIDs, custom IDs like "svc.req.123".
# Rejects spaces, newlines, unicode, quotes, slashes.
_TRACE_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

logger = structlog.get_logger()


class TraceIdMiddleware:
    """Attach trace_id (and avatar_session_id if present) to every request.

    Pure ASGI implementation -- operates on scope/receive/send directly.
    Non-HTTP scopes (lifespan, websocket) pass through unchanged.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # --- Extract trace_id from X-Trace-ID header ---
        headers = dict(scope.get("headers", []))
        raw_trace = headers.get(b"x-trace-id", b"").decode("latin-1", errors="replace")

        if raw_trace and len(raw_trace) <= 36 and _TRACE_ID_RE.match(raw_trace):
            trace_id = raw_trace
        else:
            trace_id = str(uuid4())

        # --- Bind to structlog contextvars ---
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        # --- Avatar session id (Sprint 3.2) ---
        # TraceIdMiddleware reads avatar_session_id from Redis session
        # and binds it to contextvars so every log line in avatar mode
        # is annotated automatically. Implementation added in Sprint 3.2
        # when auth session parsing is available.
        # avatar_session_id = _extract_avatar_session_id(headers)
        # if avatar_session_id:
        #     structlog.contextvars.bind_contextvars(
        #         avatar_session_id=avatar_session_id
        #     )

        # --- Inject X-Trace-ID into response headers ---
        async def send_with_trace(message: dict) -> None:  # type: ignore[type-arg]
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list.append(
                    (b"x-trace-id", trace_id.encode())
                )
                message = {**message, "headers": headers_list}
            await send(message)

        await self.app(scope, receive, send_with_trace)
