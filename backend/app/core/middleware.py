# =============================================================================
# CBSHOME Backend -- ASGI Middleware
# =============================================================================
#
# Pure ASGI -- no BaseHTTPMiddleware wrapper. This guarantees that
# structlog contextvars work reliably without TaskGroup isolation
# issues that BaseHTTPMiddleware can introduce.
#
# BINDS TO STRUCTLOG CONTEXTVARS (available in every log line):
#   trace_id          -- UUID, from X-Trace-ID header or auto-generated
#   ip_address        -- client IP (X-Forwarded-For or REMOTE_ADDR)
#   user_agent        -- User-Agent header
#   avatar_session_id -- set in Sprint 3.2 when avatar mode is active
#
# TRACE ID RULES:
#   - From X-Trace-ID header if: len <= 36 AND matches safe char set
#   - Otherwise: auto-generated uuid4
#   - Returned in X-Trace-ID response header for client correlation
#   - Written to AuditLog.trace_id (String(36)) via record_audit()
#
# SECURITY:
#   Safe char set prevents log injection and AuditLog.trace_id pollution.
#   Rejects spaces, newlines, unicode, quotes, slashes, etc.
# =============================================================================

import re
from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

# Safe characters: UUIDs, "svc.req.123", "my-trace-42".
# Rejects injection vectors: spaces, newlines, unicode, quotes, slashes.
_TRACE_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

logger = structlog.get_logger()


class TraceIdMiddleware:
    """Attach request context to every HTTP request via structlog contextvars.

    Pure ASGI -- operates on scope/receive/send directly.
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

        headers = dict(scope.get("headers", []))

        # --- trace_id ---
        raw_trace = headers.get(b"x-trace-id", b"").decode("latin-1", errors="replace")
        if raw_trace and len(raw_trace) <= 36 and _TRACE_ID_RE.match(raw_trace):
            trace_id = raw_trace
        else:
            trace_id = str(uuid4())

        # --- ip_address ---
        # Prefer X-Forwarded-For (set by Nginx proxy_set_header).
        # Fall back to REMOTE_ADDR from ASGI scope.
        forwarded_for = headers.get(b"x-forwarded-for", b"").decode("latin-1", errors="replace")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()
        else:
            client = scope.get("client")
            ip_address = client[0] if client else "unknown"

        # --- user_agent ---
        user_agent = headers.get(b"user-agent", b"").decode("latin-1", errors="replace")

        # --- Bind all to structlog contextvars ---
        # These appear automatically in every log line for this request.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # --- avatar_session_id (Sprint 3.2) ---
        # TraceIdMiddleware will read avatar_session_id from the Redis session
        # and bind it here so every log line in avatar mode is annotated.
        # Implementation added in Sprint 3.2 when auth session parsing is available.
        # Example:
        #   if avatar_session_id := _extract_avatar_session_id(headers):
        #       structlog.contextvars.bind_contextvars(
        #           avatar_session_id=avatar_session_id
        #       )

        # --- Inject X-Trace-ID into response headers ---
        async def send_with_trace(message: dict) -> None:  # type: ignore[type-arg]
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": headers_list}
            await send(message)

        await self.app(scope, receive, send_with_trace)
