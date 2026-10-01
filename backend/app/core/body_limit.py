# =============================================================================
# AIVIS.ONE Backend -- Per-endpoint request body limit (H29 P-61)
# =============================================================================
#
# Every endpoint that accepts files declares how large its WHOLE request may
# be, and a request above that is answered 413 before the application reads
# or parses a byte of it.
#
# WHERE THE LIMIT COMES FROM. Not a second literal: an endpoint declares how
# many files it takes and the per-file limit its service already enforces,
#
#     @upload_body_limit(files=3, per_file_bytes=KYC_MAX_DOCUMENT_BYTES)
#
# and the request limit is files * per_file_bytes + MULTIPART_OVERHEAD_BYTES.
# A per-file limit therefore lives in exactly one place, and the request limit
# moves with it. The per-file checks in the services stay what they were: a
# request inside its limit can still carry one file over its own cap, and
# that file gets the service's specific, readable error.
#
# WHY A PURE ASGI MIDDLEWARE AND NOT A DEPENDENCY. FastAPI reads and parses a
# multipart body BEFORE it solves dependencies, so nothing declared on a route
# can refuse earlier than the full parse. A middleware runs before FastAPI is
# entered at all.
#
# THE TWO WAYS A BODY ARRIVES, both handled:
#   Content-Length above the limit -> 413 at once; the application is never
#     called and the body is never read.
#   anything else -> the bytes are counted as they are received, and the
#     request is cut off the moment the count passes the limit: 413 is sent
#     from here, the application is told the client went away, and whatever
#     it tries to answer after that is dropped. The count runs whether or not
#     Content-Length was given: the server never delivers more than a
#     declared length, so for an honest declaration the count simply never
#     fires, and a body framed some other way cannot hide behind a small
#     declared one.
#   Malformed Content-Length forms never reach this code. Measured on this
#   stack (uvicorn[standard] -> httptools, as the image runs it): duplicate
#   headers equal or not, non-digits, negative, empty, "+N", "N, N", and
#   Content-Length together with chunked are all refused 400 by the server
#   before any application code runs. So the header is read as one decimal
#   integer and nothing else is handled.
#
# WHY THE COUNT IS NOT AN EXCEPTION. An exception raised from receive()
# while FastAPI parses the form is caught by FastAPI's own `except Exception`
# around the parse and turned into 400 "There was an error parsing the body"
# -- the oversized request would be reported as malformed.
#
# ORDER IN main.py. Registered BEFORE CORSMiddleware, which makes it the inner
# of the two: the 413 passes back out through CORS and carries its headers, so
# a browser sees a 413 and not an opaque network failure.
#
# ┌─ KNOWN CEILING ──────────────────────────────────────────────────────────
# │ (1) MECHANICS: the host nginx accepts up to 100M on ANY API path before
# │     this application sees the request. The API server block
# │     (scripts/aivis-manage.sh, render_nginx_api) sets
# │     client_max_body_size 100M at SERVER level and has no
# │     proxy_request_buffering off -- the tree's only occurrence of that
# │     directive is in the storage block -- so nginx reads every request
# │     body to the end before it opens the connection to the app. A 413
# │     from here saves the parse, the spool to disk and the service work;
# │     it does not save the transfer, and it cannot make a request that
# │     nginx accepts cheaper to receive. For the four attachment endpoints
# │     the per-file limit is the same 100MB, so their 413 from here is
# │     unreachable behind nginx and stands as defence in depth.
# │ (2) STATUS: acknowledged by design.
# │ (3) REFERENCE: P-61.
# │ (4) UNCONSERVATION TRIGGER: `aivis nginx render` stops overwriting the
# │     SSL configuration that certbot writes into the rendered files.
# │ (5) SHAPE OF THE FIX: give each upload path its own location in
# │     render_nginx_api with its own client_max_body_size, equal to the
# │     limit declared here, and repeat the proxy_set_header block into it.
# │     One place only -- install_aivis.sh renders through the same
# │     function and carries no template of its own.
# │ (6) REJECTED, AND WHY: editing the nginx template now -- re-rendering
# │     drops https on the box. A route dependency instead of this
# │     middleware -- FastAPI parses the body before dependencies run, so
# │     it would refuse after the full parse, not before it.
# └──────────────────────────────────────────────────────────────────────────
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

F = TypeVar("F", bound=Callable[..., Any])

# Room for everything in a multipart request that is not file content: part
# boundaries and headers, and the non-file fields. The largest of those is
# the attachment metadata JSON -- title <= 500, description <= 5000,
# category <= 200 characters (AttachmentInboxMetadata), at most ~23 KB of
# UTF-8 -- so 64 KiB covers it with room to spare.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

LIMIT_ATTRIBUTE = "__request_body_limit__"


def upload_body_limit(*, files: int, per_file_bytes: int) -> Callable[[F], F]:
    """Declare an upload endpoint's request body limit.

    The limit is files * per_file_bytes + MULTIPART_OVERHEAD_BYTES. Declaring
    a limit twice on one endpoint is refused at import time rather than
    letting the last declaration win silently.
    """
    limit = files * per_file_bytes + MULTIPART_OVERHEAD_BYTES

    def mark(endpoint: F) -> F:
        if hasattr(endpoint, LIMIT_ATTRIBUTE):
            raise RuntimeError(
                f"{endpoint.__qualname__} declares a request body limit twice"
            )
        setattr(endpoint, LIMIT_ATTRIBUTE, limit)
        return endpoint

    return mark


def _flatten(routes: list[Any]) -> list[Any]:
    """Every concrete route, with included routers opened up.

    FastAPI (0.139, pinned <0.140) keeps each `app.include_router(...)` as a
    lazy wrapper that holds the APIRouter as `original_router`; the routes
    are not copied into the app's list. The wrapper's routes already carry
    their full path, because every router in this tree declares its prefix
    on itself and none is included under an extra prefix. If a FastAPI
    upgrade changes the wrapper, this returns no limited routes, and the
    test that pins the table to the seven upload endpoints fails -- the
    limit cannot disappear silently.
    """
    flat: list[Any] = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            flat.extend(_flatten(inner.routes))
        else:
            flat.append(route)
    return flat


def declared_limits(routes: list[Any]) -> list[tuple[Any, int]]:
    """(route, limit) for every route whose endpoint declares a limit."""
    return [
        (route, getattr(route.endpoint, LIMIT_ATTRIBUTE))
        for route in _flatten(routes)
        if hasattr(getattr(route, "endpoint", None), LIMIT_ATTRIBUTE)
    ]


async def _refuse(send: Send, limit: int) -> None:
    limit_mb = limit / (1024 * 1024)
    body = (
        '{"error":"request_too_large","message":'
        f'"The request is larger than this endpoint accepts ({limit_mb:.1f} MB)."}}'
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestBodyLimitMiddleware:
    """Refuse an upload request above its endpoint's declared limit with 413.

    Pure ASGI. Requests to endpoints without a declared limit pass through
    untouched -- no wrapper around receive or send.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._table: list[tuple[Any, int]] | None = None

    def _limit_for(self, scope: Scope) -> int | None:
        if self._table is None:
            # scope["app"] is set by Starlette before the middleware stack
            # runs; the route table is final by the first request.
            self._table = declared_limits(scope["app"].router.routes)
        for route, limit in self._table:
            match, _ = route.matches(scope)
            if match is Match.FULL:
                return limit
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = next(
            (v for k, v in scope["headers"] if k == b"content-length"), None
        )
        if declared is not None and int(declared) > limit:
            await _refuse(send, limit)
            return

        received = 0
        refused = False

        async def counting_receive() -> Message:
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    refused = True
                    await _refuse(send, limit)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not refused:
                await send(message)

        await self.app(scope, counting_receive, guarded_send)
