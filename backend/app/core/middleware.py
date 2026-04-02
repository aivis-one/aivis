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
#   ip_address        -- real client IP from X-Real-IP (set by Nginx)
#   user_agent        -- User-Agent header (truncated to 500 chars)
#   avatar_session_id -- set in Sprint 3.2 when avatar mode is active
#
# IP ADDRESS STRATEGY:
#   Nginx sets X-Real-IP to $remote_addr (the actual connecting IP).
#   This cannot be spoofed by the client -- Nginx always overwrites it.
#   X-Forwarded-For is NOT used because clients can inject fake IPs
#   as the first element, polluting audit logs.
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

# Max length to store in structlog context (mirrors AuditLog.user_agent).
_USER_AGENT_MAX_LEN = 500

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
        # Use X-Real-IP set by Nginx ($remote_addr) -- cannot be spoofed by client.
        # Nginx config: proxy_set_header X-Real-IP $remote_addr;
        # Fallback to REMOTE_ADDR from ASGI scope for non-proxied requests (tests).
        real_ip = headers.get(b"x-real-ip", b"").decode("latin-1", errors="replace").strip()
        if real_ip:
            ip_address = real_ip
        else:
            client = scope.get("client")
            ip_address = client[0] if client else "unknown"

        # --- user_agent (truncated to match AuditLog column length) ---
        raw_ua = headers.get(b"user-agent", b"").decode("latin-1", errors="replace")
        user_agent = raw_ua[:_USER_AGENT_MAX_LEN] if raw_ua else ""

        # --- Bind all to structlog contextvars ---
        # These appear automatically in every log line for this request.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # --- avatar_session_id (Sprint 3.2) ---
        # TraceIdMiddleware reads avatar_session_id from Redis session
        # and binds it so every log line in avatar mode is annotated automatically.
        # Implemented in Sprint 3.2 when auth session parsing is available.

        # --- Inject X-Trace-ID into response headers ---
        async def send_with_trace(message: dict) -> None:  # type: ignore[type-arg]
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": headers_list}
            await send(message)

        await self.app(scope, receive, send_with_trace)
