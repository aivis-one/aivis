# =============================================================================
# AIVIS.ONE Backend -- per-endpoint request body limit (H29 P-61)
# =============================================================================
#
# WHAT THIS GUARDS. app/core/body_limit.py answers 413 to an upload request
# above its endpoint's declared limit before the application reads the body.
# Four groups of assertions:
#
#   THE TABLE -- exactly the seven upload endpoints carry a limit, each equal
#     to files * per-file limit + overhead computed from the SAME constants
#     the services check; and EVERY endpoint taking an UploadFile has one.
#     The second is the class guard: a new upload endpoint without a limit
#     fails here, not in production.
#   DECLARED LENGTH -- above the limit -> 413 with neither the application
#     nor receive() ever called; at the limit and at zero -> passed through.
#   COUNTED LENGTH -- a body without Content-Length is cut off at the limit:
#     one 413, the application told the client left, its own answer dropped.
#   THROUGH THE REAL APP -- an anonymous oversized upload gets 413, not 401,
#     which proves the refusal comes before auth, parsing and routing; the
#     413 carries CORS headers, which proves the middleware sits inside CORS.
#
# Malformed Content-Length forms are not tested here because they cannot
# reach this code: the server (uvicorn + httptools) refuses them with 400
# first -- measured, recorded in body_limit.py's header.
# =============================================================================

from __future__ import annotations

import typing
from uuid import uuid4

import pytest
from fastapi import UploadFile
from httpx import AsyncClient

from app.core.body_limit import (
    MULTIPART_OVERHEAD_BYTES,
    RequestBodyLimitMiddleware,
    _flatten,
    declared_limits,
    upload_body_limit,
)
from app.core.config import settings
from app.main import app
from app.modules.companies.constants import ROADMAP_COVER_MAX_BYTES
from app.modules.kyc.constants import KYC_MAX_DOCUMENT_BYTES

MiB = 1024 * 1024

EXPECTED = {
    ("POST", "/api/v1/kyc/submit"): 3 * KYC_MAX_DOCUMENT_BYTES,
    ("PUT", "/api/v1/staff/companies/{company_id}/roadmap/{item_id}/cover"): ROADMAP_COVER_MAX_BYTES,
    ("PUT", "/api/v1/company/roadmap/{item_id}/cover"): ROADMAP_COVER_MAX_BYTES,
    ("POST", "/api/v1/company/attachments"): settings.minio_max_file_size_bytes,
    ("PATCH", "/api/v1/company/attachments/{attachment_id}/replace"): settings.minio_max_file_size_bytes,
    ("POST", "/api/v1/staff/companies/{company_id}/attachments"): settings.minio_max_file_size_bytes,
    (
        "PATCH",
        "/api/v1/staff/companies/{company_id}/attachments/{attachment_id}/replace",
    ): settings.minio_max_file_size_bytes,
}

COVER_PATH = f"/api/v1/company/roadmap/{uuid4()}/cover"
COVER_LIMIT = ROADMAP_COVER_MAX_BYTES + MULTIPART_OVERHEAD_BYTES


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


def _table() -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for route, limit in declared_limits(app.router.routes):
        for method in route.methods:
            key = (method, route.path)
            assert key not in out, f"{key} carries a limit twice"
            out[key] = limit
    return out


def test_exactly_the_seven_upload_endpoints_carry_a_limit() -> None:
    """EMPTINESS: the table is not empty, and it is exactly these seven --
    each limit derived from the per-file constant the service enforces."""
    table = _table()
    assert len(table) == 7
    assert table == {
        key: per_file + MULTIPART_OVERHEAD_BYTES for key, per_file in EXPECTED.items()
    }


def _takes_upload(endpoint: typing.Any) -> bool:
    hints = typing.get_type_hints(endpoint)
    return any(
        hint is UploadFile or UploadFile in typing.get_args(hint)
        for hint in hints.values()
    )


def test_every_endpoint_that_takes_a_file_has_a_limit() -> None:
    """SHORTAGE, AS A CLASS: any endpoint with an UploadFile parameter -- today
    or added later -- without a declared limit fails here. Paired: the scan
    finds upload endpoints at all (it is not vacuously true)."""
    uploads = [
        route
        for route in _flatten(app.router.routes)
        if getattr(route, "endpoint", None) is not None and _takes_upload(route.endpoint)
    ]
    assert len(uploads) == 7
    limited = {id(route) for route, _ in declared_limits(app.router.routes)}
    missing = [route.path for route in uploads if id(route) not in limited]
    assert missing == []


def test_a_limit_declared_twice_is_refused() -> None:
    """REPETITION: a second declaration on one endpoint fails at import time
    instead of the last one silently winning."""

    @upload_body_limit(files=1, per_file_bytes=1)
    async def endpoint() -> None: ...

    with pytest.raises(RuntimeError, match="twice"):
        upload_body_limit(files=2, per_file_bytes=1)(endpoint)


# ---------------------------------------------------------------------------
# The middleware on its own, with a spy behind it
# ---------------------------------------------------------------------------


class _Spy:
    def __init__(self, reply: bool = True) -> None:
        self.called = False
        self.received: list[dict] = []
        self.reply = reply

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        self.called = True
        while True:
            message = await receive()
            self.received.append(message)
            if message["type"] == "http.disconnect" or not message.get("more_body"):
                break
        if self.reply:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})


def _scope(method: str, path: str, content_length: int | None) -> dict:
    headers = [(b"content-type", b"multipart/form-data; boundary=x")]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "app": app,
    }


async def _run(scope: dict, chunks: list[bytes], spy: _Spy) -> tuple[list[dict], int]:
    sent: list[dict] = []
    pulled = 0

    async def receive() -> dict:
        nonlocal pulled
        pulled += 1
        if pulled > len(chunks):
            return {"type": "http.disconnect"}
        return {
            "type": "http.request",
            "body": chunks[pulled - 1],
            "more_body": pulled < len(chunks),
        }

    async def send(message: dict) -> None:
        sent.append(message)

    await RequestBodyLimitMiddleware(spy)(scope, receive, send)
    return sent, pulled


def _status(sent: list[dict]) -> list[int]:
    return [m["status"] for m in sent if m["type"] == "http.response.start"]


async def test_declared_length_over_the_limit_is_refused_unread() -> None:
    spy = _Spy()
    sent, pulled = await _run(_scope("PUT", COVER_PATH, COVER_LIMIT + 1), [b"x"], spy)
    assert _status(sent) == [413]
    assert spy.called is False
    assert pulled == 0
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert b'"error":"request_too_large"' in body


async def test_declared_length_at_the_limit_and_zero_pass() -> None:
    """The boundary belongs to the endpoint; EMPTINESS (length 0) is not this
    middleware's business -- FastAPI answers the missing file itself."""
    for length in (COVER_LIMIT, 0):
        spy = _Spy()
        sent, _ = await _run(_scope("PUT", COVER_PATH, length), [b""], spy)
        assert spy.called is True
        assert _status(sent) == [200]


async def test_undeclared_length_is_cut_off_at_the_limit() -> None:
    """SHORTAGE of the header: the body is counted. One 413 goes out, the
    application sees the client leave, and its own reply is dropped. The
    chunks after the limit are never pulled."""
    chunk = b"x" * MiB
    chunks = [chunk] * 20  # 20 MiB against a ~10 MiB limit
    spy = _Spy()
    sent, pulled = await _run(_scope("PUT", COVER_PATH, None), chunks, spy)
    assert _status(sent) == [413]
    assert spy.received[-1] == {"type": "http.disconnect"}
    assert pulled == COVER_LIMIT // MiB + 1 < len(chunks)


async def test_undeclared_length_inside_the_limit_passes() -> None:
    spy = _Spy()
    sent, _ = await _run(_scope("PUT", COVER_PATH, None), [b"x" * MiB] * 3, spy)
    assert _status(sent) == [200]
    assert all(m["type"] == "http.request" for m in spy.received)


async def test_other_routes_and_other_methods_are_not_touched() -> None:
    """A path without a limit, and the GET on a limited path, pass through
    with the ORIGINAL receive -- no wrapper, whatever the length."""
    huge = 10 * settings.minio_max_file_size_bytes
    for method, path in (
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/company/attachments"),
    ):
        spy = _Spy()
        sent, _ = await _run(_scope(method, path, huge), [b"{}"], spy)
        assert spy.called is True
        assert _status(sent) == [200]


async def test_non_http_scopes_pass_through() -> None:
    spy = _Spy(reply=False)
    reached: list[str] = []

    async def inner(scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        reached.append(scope["type"])

    await RequestBodyLimitMiddleware(inner)({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    assert reached == ["lifespan"]
    assert spy.called is False


# ---------------------------------------------------------------------------
# Through the real application
# ---------------------------------------------------------------------------


async def _chunked_multipart(file_bytes: int, size: int = MiB):
    """A well-formed multipart body, streamed without Content-Length.

    Well-formed on purpose: a junk body is refused by the multipart parser
    on its first chunk (400), long before any limit -- the test would then
    say nothing about the limit."""
    yield (
        b"--x\r\n"
        b'Content-Disposition: form-data; name="file"; filename="cover.png"\r\n'
        b"Content-Type: image/png\r\n\r\n"
    )
    sent = 0
    while sent < file_bytes:
        piece = min(size, file_bytes - sent)
        sent += piece
        yield b"x" * piece
    yield b"\r\n--x--\r\n"


async def test_oversized_anonymous_upload_gets_413_not_401(client: AsyncClient) -> None:
    """413 rather than 401: the refusal happens before authentication, form
    parsing and the endpoint -- nothing behind the middleware ran. And it
    carries the CORS header, so the middleware sits inside CORS."""
    resp = await client.put(
        COVER_PATH,
        content=_chunked_multipart(COVER_LIMIT + MiB),
        headers={
            "content-type": "multipart/form-data; boundary=x",
            "origin": "https://app.example.test",
        },
    )
    assert resp.status_code == 413
    assert resp.json()["error"] == "request_too_large"
    assert "access-control-allow-origin" in resp.headers


async def test_small_anonymous_upload_reaches_the_application(client: AsyncClient) -> None:
    """The pair: inside the limit the request is the application's, which
    answers an anonymous caller 401."""
    resp = await client.put(
        COVER_PATH,
        files={"file": ("cover.png", b"x" * MiB, "image/png")},
    )
    assert resp.status_code == 401
