# =============================================================================
# AIVIS.ONE Backend -- Notifications preferences: the settings screen
# (TASK-38 item 4)
# =============================================================================
#
# Mirrors test_notifications_inbox.py's shape: comms is faked at the
# module boundary (app.core.comms.httpx), the fake answers only the
# preferences surface this module uses, and a call to a path nobody
# implemented fails the test rather than falling through to a
# plausible default.
#
# What is pinned here, beyond the happy path:
#   1. the trust model -- there is no recipient/user id field anywhere
#      a client can set on this wire (PreferencesPatchIn's extra="forbid"
#      rejects an attempt to smuggle one before comms is ever called);
#   2. PATCH forwards partial category toggles and full schedule
#      replace/clear with the exact presence semantics comms requires
#      (omitted vs. explicit null);
#   3. the 404-no-recipient-row case: GET and PATCH both translate it
#      to the SAME clean CommsUnavailableError (502, comms_recipient_pending)
#      rather than GET fabricating a page PATCH could not honour --
#      see notifications/service.py's header for the full reasoning;
#   4. comms unconfigured on this box: GET degrades to an honest
#      default form, PATCH does not (nothing to persist to);
#   5. comms unreachable while configured is a clean AivisError, never
#      a 500 and never a fabricated answer.
# =============================================================================

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.core import comms as comms_module
from app.core.config import settings
from tests.helpers import auth_headers, register_user

_URL = "http://comms.test"
_TOKEN = "phase6-service-token"

_DEFAULT_CATEGORIES = (
    "agent_applications",
    "commissions",
    "deposits",
    "installments",
    "kyc",
    "payments",
    "purchases",
    "staff_messages",
    "support_messages",
    "withdrawals",
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


class _FakeCommsPrefs:
    """An in-memory comms answering only the preferences surface.

    self.recipients maps recipient_id -> the stored form. A recipient
    NOT in this dict answers 404 on both verbs -- modelling "comms has
    no row for this user yet" independently of whether the synchronous
    registration upsert (PUT /recipients/{id}, bypassed below) claimed
    success, exactly like the real trust boundary: a test seeds a
    recipient explicitly to opt into the synced state, rather than
    getting it for free from registration succeeding.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.recipients: dict[str, dict[str, Any]] = {}
        self.fail_with: Any = None
        # Overrides the GET response body outright, for the
        # malformed-payload test.
        self.raw_form: Any = None

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

        # Registration's synchronous recipient upsert (PUT
        # /api/v1/recipients/{id}, exactly -- no further segments).
        # Always answered 200 and deliberately does NOT seed
        # self.recipients: see the class docstring on why the two are
        # independent here.
        if (
            method == "PUT"
            and path.startswith("/api/v1/recipients/")
            and path.count("/") == 4
        ):
            return _FakeResponse(200, {})

        if not path.endswith("/preferences"):
            raise AssertionError(f"fake comms has no route for {method} {path}")

        if isinstance(self.fail_with, Exception):
            raise self.fail_with
        if isinstance(self.fail_with, int):
            return _FakeResponse(self.fail_with, {"detail": "comms said no"})

        recipient_id = path.split("/")[4]

        if recipient_id not in self.recipients:
            return _FakeResponse(
                404, {"detail": f"recipient {recipient_id} does not exist"}
            )

        if method == "GET":
            if self.raw_form is not None:
                return _FakeResponse(200, self.raw_form)
            return _FakeResponse(200, self.recipients[recipient_id])

        if method == "PATCH":
            form = self.recipients[recipient_id]
            body = json or {}
            if "categories" in body and body["categories"] is not None:
                form["categories"].update(body["categories"])
            if "schedule" in body:
                # Presence-sensitive: comms only overwrites the
                # schedule when the key is actually present, and an
                # explicit null clears it -- exactly what this branch
                # mirrors ("in body" catches both cases, "omitted"
                # never reaches here at all).
                form["schedule"] = body["schedule"]
            return _FakeResponse(200, form)

        raise AssertionError(f"fake comms has no route for {method} {path}")

    def seed_recipient(
        self, recipient_id: str, *, timezone: str = "Europe/Moscow"
    ) -> dict[str, Any]:
        form = {
            "categories": dict.fromkeys(_DEFAULT_CATEGORIES, True),
            "schedule": None,
            "timezone": timezone,
        }
        self.recipients[recipient_id] = form
        return form


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> _FakeCommsPrefs:
    monkeypatch.setattr(settings, "comms_api_url", _URL)
    monkeypatch.setattr(settings, "comms_service_token", _TOKEN)
    fake = _FakeCommsPrefs()
    fake.install(monkeypatch)
    return fake


async def _registered(client: AsyncClient) -> tuple[dict[str, str], str]:
    body = await register_user(client)
    return auth_headers(body["session_token"]), body["user"]["id"]


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_the_comms_shape(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    form = comms.seed_recipient(user_id)
    form["categories"]["kyc"] = False
    form["schedule"] = {"from": "22:00", "to": "07:00", "days": ["mon", "fri"]}

    response = await client.get(
        "/api/v1/notifications/preferences", headers=headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["categories"]["kyc"] is False
    assert body["categories"]["withdrawals"] is True
    assert body["schedule"] == {"from": "22:00", "to": "07:00", "days": ["mon", "fri"]}
    assert body["timezone"] == "Europe/Moscow"


@pytest.mark.asyncio
async def test_patch_forwards_partial_category_toggles(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"categories": {"kyc": False, "withdrawals": False}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["categories"]["kyc"] is False
    assert body["categories"]["withdrawals"] is False
    # Everything else untouched.
    assert body["categories"]["deposits"] is True

    # Only the listed toggles were forwarded -- not the whole map.
    call = comms.calls[-1]
    assert call["json"] == {"categories": {"kyc": False, "withdrawals": False}}


@pytest.mark.asyncio
async def test_patch_forwards_a_full_schedule_replace(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"schedule": {"from": "23:00", "to": "06:30", "days": ["sat", "sun"]}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schedule"] == {
        "from": "23:00",
        "to": "06:30",
        "days": ["sat", "sun"],
    }

    call = comms.calls[-1]
    assert call["json"] == {
        "schedule": {"from": "23:00", "to": "06:30", "days": ["sat", "sun"]}
    }


@pytest.mark.asyncio
async def test_patch_explicit_null_schedule_clears_it(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    form = comms.seed_recipient(user_id)
    form["schedule"] = {"from": "22:00", "to": "07:00", "days": ["mon"]}

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"schedule": None},
    )

    assert response.status_code == 200, response.text
    assert response.json()["schedule"] is None
    assert comms.calls[-1]["json"] == {"schedule": None}


@pytest.mark.asyncio
async def test_patch_omitted_schedule_key_is_never_forwarded(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    """Omitting `schedule` entirely must leave it untouched -- distinct
    from sending it as null. exclude_unset on PreferencesPatchIn is
    what makes the two distinguishable on the wire."""
    headers, user_id = await _registered(client)
    form = comms.seed_recipient(user_id)
    form["schedule"] = {"from": "22:00", "to": "07:00", "days": ["mon"]}

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"categories": {"kyc": False}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schedule"] == {"from": "22:00", "to": "07:00", "days": ["mon"]}

    call = comms.calls[-1]
    assert "schedule" not in call["json"]
    assert call["json"] == {"categories": {"kyc": False}}


# ---------------------------------------------------------------------------
# 2. Local validation: the read-only field and unknown keys never reach comms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_rejects_timezone_without_calling_comms(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)
    calls_before = len(comms.calls)

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"timezone": "UTC"},
    )

    assert response.status_code == 422, response.text
    # Rejected by PreferencesPatchIn's own extra="forbid" -- comms was
    # never even asked.
    assert len(comms.calls) == calls_before


# ---------------------------------------------------------------------------
# 3. Trust model: no recipient/user id is ever accepted from the wire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_session_is_the_only_source_of_the_recipient_id(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)

    await client.get("/api/v1/notifications/preferences", headers=headers)
    await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"categories": {"kyc": False}},
    )

    prefs_calls = [c for c in comms.calls if c["path"].endswith("/preferences")]
    assert prefs_calls, "expected at least one preferences call"
    for call in prefs_calls:
        assert f"/recipients/{user_id}/preferences" in call["path"]


@pytest.mark.asyncio
async def test_a_recipient_id_field_in_the_body_is_rejected_not_forwarded(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    """A client cannot smuggle a recipient/user id into the PATCH body:
    PreferencesPatchIn declares no such field, and extra="forbid" turns
    an attempt into a 422 instead of the extra key being silently
    dropped and the request forwarded anyway."""
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)
    other = "11111111-1111-1111-1111-111111111111"

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"categories": {"kyc": False}, "recipient_id": other, "user_id": other},
    )

    assert response.status_code == 422, response.text
    assert not any(other in c["path"] for c in comms.calls)


@pytest.mark.asyncio
async def test_no_recipient_or_user_path_parameter_exists_on_this_router(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/v1/notifications/preferences"):
            assert "recipient" not in path
            assert "user_id" not in path


@pytest.mark.asyncio
async def test_preferences_require_a_session(client: AsyncClient) -> None:
    get_response = await client.get("/api/v1/notifications/preferences")
    patch_response = await client.patch(
        "/api/v1/notifications/preferences", json={"categories": {"kyc": False}}
    )
    assert get_response.status_code == 401, get_response.text
    assert patch_response.status_code == 401, patch_response.text


# ---------------------------------------------------------------------------
# 4. The 404-no-recipient-row case: a clean, honest refusal on both verbs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_404_from_comms_is_a_clean_refusal_not_a_fabricated_page(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    """comms is configured and reachable but has no recipient row for
    this user (registration's synchronous upsert has not landed yet).
    Per notifications/service.py's header, this must NOT be answered
    with the "everything enabled" fallback GET uses for an unconfigured
    box -- that fallback is reserved for the permanent, box-wide case."""
    headers, _ = await _registered(client)
    # Deliberately not seeded -- this recipient has no row.

    response = await client.get(
        "/api/v1/notifications/preferences", headers=headers
    )

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_recipient_pending"


@pytest.mark.asyncio
async def test_patch_404_from_comms_is_the_same_clean_refusal(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, _ = await _registered(client)

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"categories": {"kyc": False}},
    )

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_recipient_pending"


# ---------------------------------------------------------------------------
# 5. comms unreachable while configured: a clean AivisError, never a lie
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_down_on_get_is_a_clean_refusal(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)
    comms.fail_with = httpx.ConnectError("comms is down")

    response = await client.get(
        "/api/v1/notifications/preferences", headers=headers
    )

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_unavailable"


@pytest.mark.asyncio
async def test_comms_timeout_on_patch_is_504_not_a_crash(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)
    comms.fail_with = httpx.ReadTimeout("timed out")

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"categories": {"kyc": False}},
    )

    assert response.status_code == 504, response.text
    assert response.json()["error"] == "comms_timeout"


@pytest.mark.asyncio
async def test_a_malformed_comms_form_is_a_refusal_not_a_crash(
    client: AsyncClient, comms: _FakeCommsPrefs
) -> None:
    headers, user_id = await _registered(client)
    comms.seed_recipient(user_id)
    comms.raw_form = {"categories": "not-a-dict"}

    response = await client.get(
        "/api/v1/notifications/preferences", headers=headers
    )

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_unavailable"


# ---------------------------------------------------------------------------
# 6. comms not configured on this box: GET degrades, PATCH does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_not_configured_get_degrades_to_a_default_form(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No comms address at all -- a supported, permanent box state
    (local dev, CI) -- answers as an honestly-default form (nothing
    muted, no quiet hours, no timezone) rather than a 502 on every
    settings-screen load. Registration itself must not depend on comms
    being configured, so this does not use the `comms` fixture."""
    monkeypatch.setattr(settings, "comms_api_url", "")

    body = await register_user(client)
    headers = auth_headers(body["session_token"])

    response = await client.get(
        "/api/v1/notifications/preferences", headers=headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schedule"] is None
    assert payload["timezone"] is None
    assert set(payload["categories"]) == set(_DEFAULT_CATEGORIES)
    assert all(payload["categories"].values())


@pytest.mark.asyncio
async def test_comms_not_configured_patch_does_not_degrade(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlike GET, PATCH has nothing to persist a "successful" write to
    on a box with no comms -- it must fail loudly (comms_request's
    default not-configured policy), not report a save that did not
    happen."""
    monkeypatch.setattr(settings, "comms_api_url", "")

    body = await register_user(client)
    headers = auth_headers(body["session_token"])

    response = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"categories": {"kyc": False}},
    )

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_unavailable"
