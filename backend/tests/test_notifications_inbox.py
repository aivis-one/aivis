# =============================================================================
# AIVIS.ONE Backend -- Notifications inbox: the bell (Phase 6)
# =============================================================================
#
# Mirrors test_support_threads.py's shape: comms is faked at the module
# boundary (app.core.comms.httpx), the fake answers exactly the surface
# this module uses, and a call to a path nobody implemented fails the
# test rather than falling through to a plausible default.
#
# What is pinned here:
#   1. the trust model -- there is no recipient/user id field anywhere
#      on this wire, so there is nothing for a caller to override, and
#      the id comms receives is always the session's;
#   2. the four verbs answer with typed, comms-shaped payloads;
#   3. comms being unreachable while configured is a clean AivisError
#      (502/504), never a 500 and never a fabricated zero;
#   4. comms not being configured on this box degrades to an honestly
#      empty inbox instead of erroring on every request.
# =============================================================================

from typing import Any
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient

from app.core import comms as comms_module
from app.core.config import settings
from tests.helpers import auth_headers, register_user

_URL = "http://comms.test"
_TOKEN = "phase6-service-token"


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


class _FakeComms:
    """An in-memory comms answering only the inbox surface."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.items: dict[str, list[dict[str, Any]]] = {}
        self.unread: dict[str, int] = {}
        self.read_ids: dict[str, set[str]] = {}
        # Armed by a test to break the next non-recipient call. An
        # exception instance is raised from the wire; an int is
        # answered as that status.
        self.fail_with: Any = None
        # Overrides the /unread-count (and page) response body outright,
        # for the malformed-payload test.
        self.raw_page: Any = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self

        class _FakeClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def __aenter__(self) -> "_FakeClient":
                return self

            async def __aexit__(self, *exc_info: Any) -> bool:
                return False

            async def request(
                self,
                method: str,
                url: str,
                params: dict | None = None,
                json: dict | None = None,
                headers: dict | None = None,
            ) -> _FakeResponse:
                return fake.handle(method, url, params, json, headers)

        monkeypatch.setattr(comms_module.httpx, "AsyncClient", _FakeClient)

    def handle(
        self,
        method: str,
        url: str,
        params: dict | None,
        json: dict | None,
        headers: dict | None,
    ) -> _FakeResponse:
        path = url[len(_URL) :]
        self.calls.append(
            {"method": method, "path": path, "params": params, "json": json}
        )

        # The recipient upsert (registration, PUT .../recipients/{id})
        # is deliberately NOT broken by fail_with -- same reasoning as
        # test_support_threads.py. Distinguished from the inbox paths
        # (.../recipients/{id}/inbox...) by the absence of "/inbox".
        if path.startswith("/api/v1/recipients/") and "/inbox" not in path:
            return _FakeResponse(200, {})

        if isinstance(self.fail_with, Exception):
            raise self.fail_with
        if isinstance(self.fail_with, int):
            return _FakeResponse(self.fail_with, {"detail": "comms said no"})

        recipient_id = self._recipient_from(path)

        if path.endswith("/inbox"):
            if self.raw_page is not None:
                return _FakeResponse(200, self.raw_page)
            rows = self.items.get(recipient_id, [])
            return _FakeResponse(
                200,
                {
                    "items": rows,
                    "next_cursor": None,
                    "unread": self.unread.get(recipient_id, 0),
                },
            )

        if path.endswith("/inbox/unread-count"):
            return _FakeResponse(
                200, {"unread": self.unread.get(recipient_id, 0)}
            )

        if path.endswith("/inbox/read-all"):
            self.unread[recipient_id] = 0
            for row in self.items.get(recipient_id, []):
                row["read_at"] = "2026-01-01T00:00:00+00:00"
            return _FakeResponse(200, {"unread": 0})

        if path.endswith("/read") and "/inbox/" in path:
            delivery_id = path.rsplit("/", 2)[1]
            rows = self.items.get(recipient_id, [])
            match = next((r for r in rows if r["id"] == delivery_id), None)
            if match is None:
                return _FakeResponse(404, {"detail": "delivery not found"})
            if match["read_at"] is None:
                match["read_at"] = "2026-01-01T00:00:00+00:00"
                self.unread[recipient_id] = max(
                    0, self.unread.get(recipient_id, 0) - 1
                )
            return _FakeResponse(
                200, {"unread": self.unread.get(recipient_id, 0)}
            )

        raise AssertionError(f"fake comms has no route for {method} {path}")

    @staticmethod
    def _recipient_from(path: str) -> str:
        # /api/v1/recipients/{id}/inbox...
        parts = path.split("/")
        return parts[4]

    def seed_item(
        self, recipient_id: str, *, item_id: str | None = None, **overrides: Any
    ) -> dict[str, Any]:
        row = {
            "id": item_id or str(uuid4()),
            "type": "withdrawal.completed",
            "title": "Withdrawal completed",
            "body": "Your withdrawal has been processed.",
            "action_data": None,
            "priority": 0,
            "sent_at": "2026-01-01T00:00:00+00:00",
            "read_at": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        row.update(overrides)
        self.items.setdefault(recipient_id, []).append(row)
        self.unread[recipient_id] = self.unread.get(recipient_id, 0) + (
            1 if row["read_at"] is None else 0
        )
        return row


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> _FakeComms:
    monkeypatch.setattr(settings, "comms_api_url", _URL)
    monkeypatch.setattr(settings, "comms_service_token", _TOKEN)
    fake = _FakeComms()
    fake.install(monkeypatch)
    return fake


async def _registered(client: AsyncClient) -> tuple[dict[str, str], str]:
    body = await register_user(client)
    return auth_headers(body["session_token"]), body["user"]["id"]


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_the_callers_own_items_and_badge(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_item(user_id, title="Withdrawal completed")
    comms.seed_item(user_id, title="KYC approved")

    response = await client.get("/api/v1/notifications", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 2
    assert body["unread"] == 2
    assert body["next_cursor"] is None
    assert body["items"][0]["action_data"] is None


@pytest.mark.asyncio
async def test_unread_count_alone(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_item(user_id)
    comms.seed_item(user_id)

    response = await client.get(
        "/api/v1/notifications/unread-count", headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"unread": 2}


@pytest.mark.asyncio
async def test_mark_one_read_decrements_the_badge(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, user_id = await _registered(client)
    item = comms.seed_item(user_id)
    comms.seed_item(user_id)

    response = await client.post(
        f"/api/v1/notifications/{item['id']}/read", headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"unread": 1}


@pytest.mark.asyncio
async def test_mark_one_read_is_idempotent(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, user_id = await _registered(client)
    item = comms.seed_item(user_id)

    first = await client.post(
        f"/api/v1/notifications/{item['id']}/read", headers=headers
    )
    second = await client.post(
        f"/api/v1/notifications/{item['id']}/read", headers=headers
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"unread": 0}


@pytest.mark.asyncio
async def test_mark_unknown_delivery_read_is_404(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, _ = await _registered(client)

    response = await client.post(
        f"/api/v1/notifications/{uuid4()}/read", headers=headers
    )

    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_mark_all_read_zeroes_the_badge(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_item(user_id)
    comms.seed_item(user_id)

    response = await client.post(
        "/api/v1/notifications/read-all", headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"unread": 0}


# ---------------------------------------------------------------------------
# 2. Trust model: no recipient/user id is ever accepted from the wire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_session_is_the_only_source_of_the_recipient_id(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """The id comms sees is the session's, always -- there is no field
    on any of these four routes a client could use to name someone
    else's inbox."""
    headers, user_id = await _registered(client)
    comms.seed_item(user_id)

    await client.get("/api/v1/notifications", headers=headers)
    await client.get("/api/v1/notifications/unread-count", headers=headers)
    await client.post("/api/v1/notifications/read-all", headers=headers)

    inbox_calls = [c for c in comms.calls if c["path"].endswith("/inbox")]
    assert inbox_calls, "expected at least one inbox call"
    for call in inbox_calls:
        assert f"/recipients/{user_id}/inbox" in call["path"]


@pytest.mark.asyncio
async def test_no_recipient_field_is_accepted_anywhere_on_the_wire(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """A body carrying a recipient/user id is simply not read: none of
    these endpoints declare a request body model at all, so FastAPI
    ignores anything sent (extra JSON on a bodyless POST does not 422
    here the way support's extra="forbid" models do -- there is no
    field to smuggle it through in the first place)."""
    headers, user_id = await _registered(client)
    other = str(uuid4())

    response = await client.post(
        "/api/v1/notifications/read-all",
        headers=headers,
        json={"recipient_id": other, "user_id": other},
    )

    assert response.status_code == 200, response.text
    call = comms.calls[-1]
    assert f"/recipients/{user_id}/inbox/read-all" in call["path"]
    assert other not in call["path"]


@pytest.mark.asyncio
async def test_a_foreign_recipient_id_cannot_be_smuggled_via_path(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """The only path parameter on this router is a delivery id, never a
    recipient id -- confirmed by asserting the route table itself
    carries no such parameter."""
    from app.main import app

    for route in app.routes:
        if getattr(route, "path", "").startswith("/api/v1/notifications"):
            assert "recipient" not in route.path
            assert "user_id" not in route.path


@pytest.mark.asyncio
async def test_notifications_require_a_session(client: AsyncClient) -> None:
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# 3. comms unreachable while configured: a clean AivisError, never a lie
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_down_on_list_is_a_clean_refusal(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, _ = await _registered(client)
    comms.fail_with = httpx.ConnectError("comms is down")

    response = await client.get("/api/v1/notifications", headers=headers)

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_unavailable"


@pytest.mark.asyncio
async def test_comms_timeout_on_unread_count_is_504_not_a_crash(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, _ = await _registered(client)
    comms.fail_with = httpx.ReadTimeout("timed out")

    response = await client.get(
        "/api/v1/notifications/unread-count", headers=headers
    )

    assert response.status_code == 504, response.text
    assert response.json()["error"] == "comms_timeout"


@pytest.mark.asyncio
async def test_a_malformed_comms_page_is_a_refusal_not_a_crash(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """comms' answer is input too: a page missing required fields must
    not become a pydantic ValidationError leaking out as a 500."""
    headers, _ = await _registered(client)
    comms.raw_page = {"items": [{"id": "not-a-uuid"}]}

    response = await client.get("/api/v1/notifications", headers=headers)

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_unavailable"


# ---------------------------------------------------------------------------
# 4. comms not configured on this box: an honestly empty inbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_not_configured_degrades_to_an_empty_inbox(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No comms address at all -- a supported box state (local dev, CI)
    -- answers as an honestly empty bell rather than a 502 on every
    page load. Registration itself must also not depend on comms being
    configured here, so this test does not use the `comms` fixture."""
    monkeypatch.setattr(settings, "comms_api_url", "")

    body = await register_user(client)
    headers = auth_headers(body["session_token"])

    page = await client.get("/api/v1/notifications", headers=headers)
    unread = await client.get(
        "/api/v1/notifications/unread-count", headers=headers
    )
    read_all = await client.post(
        "/api/v1/notifications/read-all", headers=headers
    )
    read_one = await client.post(
        f"/api/v1/notifications/{uuid4()}/read", headers=headers
    )

    assert page.status_code == 200, page.text
    assert page.json() == {"items": [], "next_cursor": None, "unread": 0}
    assert unread.status_code == 200
    assert unread.json() == {"unread": 0}
    assert read_all.status_code == 200
    assert read_all.json() == {"unread": 0}
    assert read_one.status_code == 200
    assert read_one.json() == {"unread": 0}
