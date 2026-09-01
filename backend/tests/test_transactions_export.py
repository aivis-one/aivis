# =============================================================================
# AIVIS.ONE Backend -- Transaction Export Tests (TASK-39 item 2)
# =============================================================================
#
# Tests cover:
#   1: Export returns CSV -- correct headers, content-type, filename
#   2: Amounts are decimal (2dp), not raw cents -- and details/user_id
#      columns are never emitted
#   3: Caller only ever gets their OWN rows, even when another user has
#      matching transactions
#   4: CSV formula-injection guard -- a hostile value cannot come back
#      as a live formula (leading char neutralised). Asserted against
#      _sanitize_csv_cell directly: see that test's docstring for why it
#      can no longer be driven through the API
#   5: Row-cap boundary -- exceeding EXPORT_MAX_ROWS returns 400, not a
#      silently truncated file (EXPORT_MAX_ROWS patched down via
#      monkeypatch so the test does not need to insert thousands of rows)
#   6: Filters (type prefix + amount_min/amount_max) are honoured, same
#      as the list endpoint
#   7: Rate limiting -- the (max+1)th call in the window gets 429
#
# ISOLATION (shared test DB): every test creates its own user via
# register_user() (UUID-suffixed email), and the export endpoint scopes
# every query to the caller's user_id -- so a fresh user's export
# contains that test's rows and nothing else.
#
# WHY NOT A PER-TEST TYPE MARKER. These tests used to mint a unique
# `exporttest_<hex>` prefix and write it into transactions.type. That
# column carries a CHECK constraint listing the fifteen legal transaction
# types (added in migration 0012, rebuilt in 0036), so every one of those
# INSERTs was refused by the database and the whole file had never
# passed. The types below are real members of TransactionType; isolation
# comes from the fresh user, which is stronger anyway -- it is what the
# endpoint actually enforces.
# =============================================================================

import csv
import io
import uuid
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.transactions.constants import TransactionType
from app.modules.transactions.service import _sanitize_csv_cell, record_transaction
from app.modules.users.models import User
from tests.helpers import auth_headers, register_user


async def _register(client: AsyncClient) -> tuple[UUID, str]:
    """Register a fresh user, return (user_id, session_token)."""
    data = await register_user(client)
    return UUID(data["user"]["id"]), data["session_token"]


# Real transaction types, used instead of the synthetic marker these
# tests used to mint. Both are legal values of the ck_transactions_type
# CHECK constraint; a credit and a debit, so the decimal/sign assertions
# below still have both signs to work with.
_T_CREDIT = TransactionType.DEPOSIT_RECEIVED.value
_T_DEBIT = TransactionType.PURCHASE_COMPLETED.value
_T_SMALL = TransactionType.INSTALLMENT_TRANCHE_PAID.value


def _parse_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


@pytest.mark.asyncio
async def test_export_headers_and_metadata(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /transactions/export -- 200, text/csv, Content-Disposition
    attachment filename, and a header row with exactly the 6 documented
    columns (no details, no user_id).
    """
    user_id, token = await _register(client)

    await record_transaction(
        db_session,
        user_id=user_id,
        type=_T_CREDIT,
        amount_cents=1234,
        reference_id=uuid.uuid4(),
        reference_type="payment",
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions/export",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")

    disposition = resp.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert ".csv" in disposition

    rows = _parse_csv(resp.text)
    header = rows[0]
    assert header == [
        "Date",
        "Type",
        "Amount",
        "Currency",
        "Reference Type",
        "Reference ID",
    ]
    assert "details" not in [h.lower() for h in header]
    assert "user_id" not in [h.lower() for h in header]
    assert len(header) == 6


@pytest.mark.asyncio
async def test_export_amounts_are_decimal_not_cents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """amount_cents=10050 (a positive credit) and amount_cents=-2500 (a
    debit) must render as "100.50" and "-25.00" -- 2dp decimals, never
    the raw integer cents value "10050"/"-2500".
    """
    user_id, token = await _register(client)
    await record_transaction(
        db_session,
        user_id=user_id,
        type=_T_CREDIT,
        amount_cents=10050,
        currency="USD",
    )
    await record_transaction(
        db_session,
        user_id=user_id,
        type=_T_DEBIT,
        amount_cents=-2500,
        currency="USD",
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions/export",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.text)
    data_rows = rows[1:]
    assert len(data_rows) == 2

    amounts_by_type = {r[1]: r[2] for r in data_rows}
    assert amounts_by_type[_T_CREDIT] == "100.50"
    # THE DEBIT MUST STAY A NUMBER, apostrophe-free. The formula guard
    # deliberately does NOT touch the amount column: a leading "-" would
    # otherwise be escaped, every spreadsheet would read the cell as
    # TEXT, and the user could no longer SUM their own statement --
    # which is most of the point of exporting one. Negative amounts are
    # not exotic here (installment tranches, reversals, purchases and
    # commission debits all record them), so this would hit almost every
    # real export. Safe to exempt because service.py BUILDS this cell
    # from a quantised Decimal -- digits, "-" and "." only, incapable of
    # expressing a formula. See _transaction_csv_row's comment.
    assert amounts_by_type[_T_DEBIT] == "-25.00"
    assert not amounts_by_type[_T_DEBIT].startswith("'")
    # Never the raw cents value ("10050"/"2500" would appear literally).
    assert "10050" not in amounts_by_type[_T_CREDIT]
    assert "2500" not in amounts_by_type[_T_DEBIT]
    # The column is genuinely arithmetic: both cells parse as Decimals
    # and sum. A regression to apostrophe-escaping fails right here.
    total = sum(Decimal(v) for v in amounts_by_type.values())
    assert total == Decimal("75.50")


@pytest.mark.asyncio
async def test_export_only_returns_callers_own_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User B's transaction of the SAME type must never appear
    in User A's export -- list_transactions()'s user_id scope is the
    only thing standing between this and a cross-account data leak.
    """
    user_a_id, token_a = await _register(client)
    user_b_id, _token_b = await _register(client)

    ref_a = uuid.uuid4()
    ref_b = uuid.uuid4()

    await record_transaction(
        db_session,
        user_id=user_a_id,
        type=_T_CREDIT,
        amount_cents=111,
        reference_id=ref_a,
        reference_type="payment",
    )
    await record_transaction(
        db_session,
        user_id=user_b_id,
        type=_T_CREDIT,
        amount_cents=222,
        reference_id=ref_b,
        reference_type="payment",
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions/export",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.text)
    data_rows = rows[1:]

    reference_ids = {r[5] for r in data_rows}
    assert str(ref_a) in reference_ids
    assert str(ref_b) not in reference_ids
    assert len(data_rows) == 1


def test_export_formula_injection_guard() -> None:
    """Every hostile leading character is neutered before a cell is
    written -- proof the file cannot re-open as a live formula in
    Excel/Sheets/LibreOffice.

    WHY THIS IS NO LONGER DRIVEN THROUGH THE API. The previous version
    stored "=cmd|' /C calc'!A0" in transactions.reference_type and read
    it back out of the exported CSV, on the stated grounds that `type`
    and `reference_type` are "plain String columns with no DB-level enum
    constraint". They are not: ck_transactions_type and
    ck_transactions_reference_type each list their legal values, so the
    hostile row could never be inserted and the test could never run.

    The old assertion was right about WHAT must happen and wrong about
    HOW to reach it. Asserting on _sanitize_csv_cell directly keeps the
    guarantee and drops the unreachable set-up -- a test that builds a
    state the schema forbids proves nothing about the export.

    The API-level half of this guarantee is covered by
    test_export_amounts_are_decimal_not_cents, which asserts a real
    exported row is NOT apostrophe-prefixed in the amount column.
    """
    hostile = "=cmd|' /C calc'!A0"

    # MUST-FIRE CONTROL: the payload really does lead with a formula
    # character, so a passing assertion below is not vacuous.
    assert hostile.startswith("=")

    neutered = _sanitize_csv_cell(hostile)
    assert not neutered.startswith("=")
    assert neutered.startswith("'=")
    assert neutered == "'" + hostile

    # The whole OWASP lead set, not just "=" -- a guard that caught only
    # the first character would pass a one-payload test and still ship
    # every other vector.
    for lead in ("=", "+", "-", "@", "\t", "\r"):
        assert _sanitize_csv_cell(lead + "danger") == "'" + lead + "danger", lead

    # A value that does NOT lead with one of them must pass through
    # untouched: a guard that prefixed everything would also pass the
    # assertions above.
    assert _sanitize_csv_cell("deposit:received") == "deposit:received"
    assert _sanitize_csv_cell("") == ""


@pytest.mark.asyncio
async def test_export_row_cap_boundary(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exceeding EXPORT_MAX_ROWS returns an explicit 400 (never a
    silently truncated file). EXPORT_MAX_ROWS is patched down to 3 for
    this test so it does not need to insert thousands of rows against
    the shared test DB.
    """
    monkeypatch.setattr("app.modules.transactions.service.EXPORT_MAX_ROWS", 3)

    user_id, token = await _register(client)
    for _ in range(4):  # one more than the patched cap
        await record_transaction(
            db_session,
            user_id=user_id,
            type=_T_CREDIT,
            amount_cents=100,
        )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions/export",
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    # Global AivisError handler -> {"error": code, "message": message}.
    # Assert the SENTENCE, not the bare digits -- "4" and "3" would
    # match almost any wording, including one that had stopped naming
    # the count and the cap at all.
    assert "4 transactions" in body["message"], body["message"]
    assert "3-row" in body["message"], body["message"]


@pytest.mark.asyncio
async def test_export_row_cap_not_tripped_under_the_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sibling to the boundary test above -- exactly AT the cap still
    succeeds (the check is `total > EXPORT_MAX_ROWS`, not `>=`)."""
    monkeypatch.setattr("app.modules.transactions.service.EXPORT_MAX_ROWS", 3)

    user_id, token = await _register(client)
    for _ in range(3):  # exactly the patched cap
        await record_transaction(
            db_session,
            user_id=user_id,
            type=_T_CREDIT,
            amount_cents=100,
        )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions/export",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.text)
    assert len(rows) - 1 == 3  # header + 3 data rows


@pytest.mark.asyncio
async def test_export_filters_are_honoured(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """amount_min/amount_max narrow the export the same way they narrow
    GET /transactions -- mirrors list_transactions()'s absolute-value
    filter on amount_cents.
    """
    user_id, token = await _register(client)
    await record_transaction(
        db_session, user_id=user_id, type=_T_SMALL, amount_cents=50
    )
    await record_transaction(
        db_session, user_id=user_id, type=_T_CREDIT, amount_cents=500
    )
    await record_transaction(
        db_session, user_id=user_id, type=_T_DEBIT, amount_cents=-5000
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions/export?amount_min=100&amount_max=1000",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.text)
    data_rows = rows[1:]
    types = {r[1] for r in data_rows}
    assert types == {_T_CREDIT}


@pytest.mark.asyncio
async def test_export_is_rate_limited(client: AsyncClient) -> None:
    """The (max+1)th export call within the window gets 429.

    Uses the SHARED default cap (settings.auth_rate_limit_max_requests /
    auth_rate_limit_window_seconds), read from settings rather than
    hardcoded, per this endpoint's docstring (transactions/router.py) --
    no override args are passed to check_rate_limit(), so whatever
    settings says IS the live limit. Keyed by user.id (not IP), so this
    test's own fresh user is naturally isolated from every other rate-
    limit test in the suite -- no clear_rate_limit fixture entry needed
    (same reasoning as auth/router.py's totp_setup precedent).
    """
    _user_id, token = await _register(client)
    limit = settings.auth_rate_limit_max_requests

    for _ in range(limit):
        resp = await client.get(
            "/api/v1/transactions/export", headers=auth_headers(token)
        )
        assert resp.status_code == 200, resp.text

    limited_resp = await client.get(
        "/api/v1/transactions/export", headers=auth_headers(token)
    )
    assert limited_resp.status_code == 429


@pytest.mark.asyncio
async def test_sanitize_csv_cell_control() -> None:
    """MUST-FIRE CONTROL for _sanitize_csv_cell in isolation: a benign
    value must pass through UNCHANGED (proves the guard is not
    over-eager and mangling ordinary data), while every documented
    formula-injection lead character is neutered. If this control ever
    fails to distinguish the two cases, the guard itself is broken.
    """
    from app.modules.transactions.service import _sanitize_csv_cell

    # Benign values pass through byte-for-byte.
    assert _sanitize_csv_cell("deposit:received") == "deposit:received"
    assert _sanitize_csv_cell("100.50") == "100.50"
    assert _sanitize_csv_cell("") == ""

    # Every documented lead character gets neutered.
    for lead in ("=", "+", "-", "@", "\t", "\r"):
        hostile = f"{lead}cmd|'/C calc'!A0"
        sanitized = _sanitize_csv_cell(hostile)
        assert sanitized == "'" + hostile
        assert sanitized[0] == "'"
        # No `or lead == "'"` escape hatch here: none of the six lead
        # characters IS an apostrophe, so that disjunct could only ever
        # weaken the assertion, never satisfy it.
        assert not sanitized.startswith(lead)

    # CONTROL, negative side: a value that does NOT start with a lead
    # character must NOT be prefixed -- if this failed, it would prove
    # the assertions above were vacuously true (guard mangling
    # everything) rather than actually discriminating.
    assert not _sanitize_csv_cell("safe_value").startswith("'")
