# =============================================================================
# AIVIS.ONE Backend -- who the operator is looking at (T-75)
# =============================================================================
#
# The operator's queue is comms' answer with one product key added to
# every row it can: `client_profile`. What is pinned here:
#
#   1. a row whose thread this product knows carries the person's name;
#   2. a row it does not know carries NO profile key -- and the list
#      still comes back;
#   3. an empty or half-empty profile produces null fields, never the
#      string "None" and never an empty name where an identifier is
#      expected;
#   4. the number of database statements does not grow with the number
#      of rows.
#
# POINT 4 IS COUNTED, NOT EYEBALLED, and the counter below is NEW
# MACHINERY in this suite -- nothing in tests/ measured statements before
# this file. It is a `before_cursor_execute` listener on the engine, the
# standard way, and it is here rather than in conftest because exactly
# one file needs it; a shared fixture nobody else uses would be a
# fixture that drifts.
#
# WHY THE ENRICHMENT IS TESTED AT THE SERVICE LEVEL, mostly. The
# function takes a page dict and a session and returns the page: driving
# comms to produce that dict would add a third fake comms to this suite
# for nothing, and the two that exist are deliberately per-surface (see
# the header of test_support_staff.py). One HTTP test covers the wiring
# the service level cannot see -- that the route hands the service a
# session at all -- and it fakes the single comms call with a canned
# page rather than a fake service.
# =============================================================================

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_engine
from app.modules.support import service as support_service
from app.modules.support.models import SupportThread
from app.modules.support.service import attach_client_profiles
from app.modules.users.models import User
from tests.helpers import auth_headers, create_staff_user, register_user

pytestmark = pytest.mark.asyncio

_STAFF_BASE = "/api/v1/staff/support/threads"


# ---------------------------------------------------------------------------
# Counting statements
# ---------------------------------------------------------------------------


class _StatementCounter:
    """Count SQL statements issued while the block is open.

    Counts EVERY statement, not just SELECTs against one table: the
    property under test is "the work does not grow with the page", and a
    per-row lookup would show up whatever it selected. A filter on the
    text would have to guess what the wrong implementation looks like.
    """

    def __init__(self) -> None:
        self.count = 0
        self._engine = get_engine().sync_engine

    def _on_execute(
        self,
        _conn: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        self.count += 1

    def __enter__(self) -> "_StatementCounter":
        event.listen(self._engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc: Any) -> None:
        event.remove(self._engine, "before_cursor_execute", self._on_execute)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _a_known_thread(
    client: AsyncClient,
    session: AsyncSession,
    *,
    profile: dict[str, Any] | None = None,
) -> tuple[UUID, UUID]:
    """One registered person plus the pointer row for their thread.

    Returns (comms thread id, client user id). A fresh user every time:
    support_threads.user_id is UNIQUE, one eternal conversation per
    person.
    """
    body = await register_user(client)
    user_id = UUID(body["user"]["id"])

    if profile is not None:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        user.set_jsonb("profile", profile)

    thread_id = uuid4()
    session.add(SupportThread(user_id=user_id, comms_thread_id=thread_id))
    await session.commit()
    return thread_id, user_id


def _page(*rows: dict[str, Any]) -> dict[str, Any]:
    """A page shaped the way comms answers the queue endpoint."""
    return {"threads": list(rows), "next_cursor": None}


# ---------------------------------------------------------------------------
# 1. The name arrives
# ---------------------------------------------------------------------------


async def test_a_known_thread_carries_the_persons_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    thread_id, client_id = await _a_known_thread(
        client,
        db_session,
        profile={"first_name": "Anna", "last_name": "Ivanova"},
    )

    page = await attach_client_profiles(
        db_session, _page({"id": str(thread_id), "client": str(client_id)})
    )

    profile = page["threads"][0]["client_profile"]
    assert profile["first_name"] == "Anna"
    assert profile["last_name"] == "Ivanova"
    assert profile["email"] is not None


async def test_the_queue_route_hands_the_service_a_session(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end, because the service level cannot see the wiring.

    list_operator_threads grew a session parameter for T-75 and the route
    grew the dependency that supplies it. Both halves are invisible from
    a service-level test, and a route still calling the old signature
    fails at import-time nowhere -- it fails on the first request.
    """
    _staff, token = await create_staff_user(client, db_session)
    thread_id, client_id = await _a_known_thread(
        client, db_session, profile={"first_name": "Pavel", "last_name": "Kim"}
    )

    async def _canned(
        _method: str, _path: str, **_kwargs: Any
    ) -> dict[str, Any]:
        return _page({"id": str(thread_id), "client": str(client_id)})

    monkeypatch.setattr(support_service, "comms_request", _canned)

    response = await client.get(_STAFF_BASE, headers=auth_headers(token))

    assert response.status_code == 200
    row = response.json()["threads"][0]
    assert row["client_profile"]["first_name"] == "Pavel"
    assert row["id"] == str(thread_id)


# ---------------------------------------------------------------------------
# 2. Rows this product does not know
# ---------------------------------------------------------------------------


async def test_a_thread_we_do_not_know_gets_no_key_and_breaks_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Absent, not null.

    A null profile would read as "this person exists and has no name",
    which is a different fact from "this thread is not one of ours". The
    view falls back to the client id either way, so the distinction costs
    nothing to keep and something to lose.
    """
    known, known_client = await _a_known_thread(
        client, db_session, profile={"first_name": "Vera", "last_name": "Sol"}
    )
    stranger = uuid4()

    page = await attach_client_profiles(
        db_session,
        _page(
            {"id": str(stranger), "client": str(uuid4())},
            {"id": str(known), "client": str(known_client)},
        ),
    )

    assert "client_profile" not in page["threads"][0]
    assert page["threads"][1]["client_profile"]["first_name"] == "Vera"


async def test_a_reply_without_threads_is_returned_untouched(
    db_session: AsyncSession,
) -> None:
    """The one place comms' answer is reshaped is the one place its
    shape has to be checked. An operator with an unenriched list can
    still work; an operator with a 500 cannot."""
    assert await attach_client_profiles(db_session, {}) == {}
    assert await attach_client_profiles(
        db_session, {"threads": None}
    ) == {"threads": None}


async def test_a_row_that_is_not_an_object_is_skipped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    known, known_client = await _a_known_thread(
        client, db_session, profile={"first_name": "Ines", "last_name": "Ru"}
    )

    page = await attach_client_profiles(
        db_session,
        {"threads": ["not-a-row", {"id": str(known), "client": str(known_client)}]},
    )

    assert page["threads"][0] == "not-a-row"
    assert page["threads"][1]["client_profile"]["first_name"] == "Ines"


async def test_a_row_whose_id_is_not_a_uuid_is_skipped(
    db_session: AsyncSession
) -> None:
    page = await attach_client_profiles(
        db_session, _page({"id": "nonsense", "client": str(uuid4())})
    )
    assert "client_profile" not in page["threads"][0]


# ---------------------------------------------------------------------------
# 3. Empty and half-empty profiles
# ---------------------------------------------------------------------------


async def test_an_empty_profile_yields_nulls_and_never_the_word_none(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The defect this guards is a string, not a crash.

    "None None" on screen comes from formatting a missing value instead
    of testing it, and it is indistinguishable from a real name until
    somebody reads it. The backend hands the pieces over as null and the
    view decides; what must never leave here is a filled-looking field.
    """
    thread_id, client_id = await _a_known_thread(
        client, db_session, profile={}
    )

    page = await attach_client_profiles(
        db_session, _page({"id": str(thread_id), "client": str(client_id)})
    )

    profile = page["threads"][0]["client_profile"]
    assert profile["first_name"] is None
    assert profile["last_name"] is None


async def test_blank_strings_are_reported_the_same_as_missing_keys(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`""` and an absent key are one state, not two.

    A blank string survives `.get()` and would render as a name of zero
    width -- a row with no visible client and no fallback either, which
    is worse than the uuid it replaced.
    """
    blank, blank_client = await _a_known_thread(
        client, db_session, profile={"first_name": "", "last_name": ""}
    )
    missing, missing_client = await _a_known_thread(
        client, db_session, profile={"country": "NL"}
    )

    page = await attach_client_profiles(
        db_session,
        _page(
            {"id": str(blank), "client": str(blank_client)},
            {"id": str(missing), "client": str(missing_client)},
        ),
    )

    blank_profile = page["threads"][0]["client_profile"]
    missing_profile = page["threads"][1]["client_profile"]
    assert blank_profile["first_name"] is missing_profile["first_name"] is None
    assert blank_profile["last_name"] is missing_profile["last_name"] is None


async def test_only_one_of_the_two_names_is_returned_as_it_is(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    thread_id, client_id = await _a_known_thread(
        client, db_session, profile={"first_name": "Cher"}
    )

    page = await attach_client_profiles(
        db_session, _page({"id": str(thread_id), "client": str(client_id)})
    )

    profile = page["threads"][0]["client_profile"]
    assert profile["first_name"] == "Cher"
    assert profile["last_name"] is None


# ---------------------------------------------------------------------------
# 4. One statement per page, counted
# ---------------------------------------------------------------------------


async def test_the_page_costs_one_statement_whatever_its_length(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The requirement item 1 states, measured rather than argued.

    Three rows and one row must cost the same, and that same must be
    one. A per-row implementation passes every other test in this file
    and fails only here -- which is the reason this file has a counter.
    """
    rows = []
    for name in ("Ann", "Bob", "Cid"):
        thread_id, client_id = await _a_known_thread(
            client, db_session, profile={"first_name": name}
        )
        rows.append({"id": str(thread_id), "client": str(client_id)})

    with _StatementCounter() as counter:
        await attach_client_profiles(db_session, _page(*rows))
    for_three = counter.count

    with _StatementCounter() as counter:
        await attach_client_profiles(db_session, _page(rows[0]))
    for_one = counter.count

    assert for_three == 1, f"three rows cost {for_three} statements"
    assert for_one == 1, f"one row cost {for_one} statements"


async def test_an_empty_page_costs_nothing_at_all(
    db_session: AsyncSession,
) -> None:
    """Zero, not one.

    An `IN ()` against an empty list is a round trip whose answer is
    known before it is asked, and the queue is empty far more often than
    it is full -- that is the normal state of a support channel that is
    keeping up.
    """
    with _StatementCounter() as counter:
        await attach_client_profiles(db_session, _page())

    assert counter.count == 0
