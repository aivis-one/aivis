# =============================================================================
# AIVIS.ONE Backend -- Agreement Snapshot Worker Tests (H34 P-122)
# =============================================================================
#
# Tests cover:
#   1: one row that cannot be snapshotted does not stop the pass -- for a
#      template that does not compile (unknown filter), a database error
#      while loading the row, and an exception nobody predicted. The bad
#      row is charged one attempt and audited; the row after it in the
#      SAME pass is snapshotted.
#   2: a row at the attempt ceiling is not selected at all.
#   3: a filled agreement_html is returned as-is, without touching storage.
#
# NO STORAGE. The template body and its asset helper are monkeypatched on
# agreement_service, the module that calls them, so the render runs for
# real (the real Jinja2 environment, the real context) on a body chosen
# here. Nothing in this file needs the storage stack.
#
# THE PASS IS PINNED TO THIS TEST'S ROWS. The worker takes the oldest
# eligible purchases, ordered by created_at, up to the batch size, from
# the whole database -- and on CI every purchase other tests made carries
# a seeded template and a NULL snapshot. So each test moves its own rows
# to a moment older than anything else in the database (and older than
# any earlier run of this file: the offset grows with the wall clock) and
# sets the batch size to exactly the rows it means the pass to take.
# Foreign rows are never selected, never rendered and never charged.
#
# Email prefix: none of its own -- register_user picks unique addresses.
# =============================================================================

import time
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from jinja2 import TemplateAssertionError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.companies.constants import TemplateStatus
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases import agreement_service, agreement_worker
from app.modules.purchases.agreement_service import (
    build_agreement_data_for_snapshot,
    render_agreement_html,
)
from app.modules.purchases.agreement_worker import run_agreement_snapshot_batch
from app.modules.purchases.models import Purchase
from tests.helpers import auth_headers, create_admin_user, register_user

_GOOD_BODY = "<p>Agreement for {{ investor_name }}, {{ units }} units.</p>"
# A filter that does not exist: a TemplateAssertionError when the body
# COMPILES (from_string) -- the exception the worker did not catch
# before H34, which rolled the whole pass back on every run.
_UNKNOWN_FILTER_BODY = "<p>{{ investor_name|no_such_filter }}</p>"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def _company_and_product(
    client: AsyncClient, admin_token: str
) -> tuple[dict, dict]:
    """One active company with its pool and one active product."""
    co = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"aw_co_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": "Snapshot Worker Co",
            "description": "Company for the agreement worker tests",
            "price_per_unit_cents": 10000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert co.status_code == 201, co.text
    company = co.json()
    pool = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool.status_code == 201, pool.text
    prod = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": "Snapshot Package",
            "package_size": 10,
        },
        headers=auth_headers(admin_token),
    )
    assert prod.status_code == 201, prod.text
    product = prod.json()
    for url, body in (
        (f"/api/v1/staff/companies/{company['id']}", {"status": "active"}),
        (f"/api/v1/staff/products/{product['id']}/status", {"status": "active"}),
    ):
        resp = await client.patch(url, json=body, headers=auth_headers(admin_token))
        assert resp.status_code == 200, resp.text
    return company, product


async def _template(
    db_session: AsyncSession, company_id: str
) -> tuple[UUID, str]:
    """A template ROW with a storage prefix of its own; returns (id,
    storage_prefix) as plain values, which outlive the session's
    expire_all(). Its body is never in storage: _patch_bodies decides
    what each prefix renders."""
    template = CompanyDocumentTemplate(
        company_id=UUID(company_id),
        kind="purchase_agreement",
        language="en",
        version=int(uuid.uuid4().hex[:7], 16),
        title="Snapshot worker test",
        storage_prefix=f"_test/agreement_worker/{uuid.uuid4().hex}/",
        asset_files=[],
        status=TemplateStatus.ACTIVE,
        created_by=None,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template.id, template.storage_prefix


async def _purchases(
    client: AsyncClient,
    db_session: AsyncSession,
    count: int,
) -> tuple[list[UUID], dict]:
    """`count` sale purchases by one investor, oldest first.

    Each sale is moved to a moment older than every other purchase in the
    database (see the module header), in the order returned, and its
    snapshot state is reset to "never tried".
    """
    _, admin_token = await create_admin_user(client, db_session)
    company, product = await _company_and_product(client, admin_token)

    data = await register_user(client)
    investor_id = UUID(data["user"]["id"])
    await record_active_ledger(
        db_session,
        user_id=investor_id,
        amount_cents=200_000 * count,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_aw_{uuid.uuid4().hex[:8]}",
    )
    await db_session.commit()

    sale_ids: list[UUID] = []
    for _ in range(count):
        resp = await client.post(
            f"/api/v1/products/{product['id']}/purchase",
            json={},
            headers=auth_headers(data["session_token"]),
        )
        assert resp.status_code == 201, resp.text
        sale_ids.append(
            UUID(next(p for p in resp.json() if p["legal_basis"] == "sale")["id"])
        )

    # Older than anything another test (or an earlier test of this file,
    # or an earlier run) created: the offset back from 2000-01-01 is the
    # wall clock in microseconds, so every later call lands earlier. This
    # call's own rows sit one microsecond apart -- far closer together
    # than two calls can ever be -- so no earlier test's leftover row can
    # fall between them and take a slot in the batch.
    base = datetime(2000, 1, 1, tzinfo=UTC) - timedelta(
        microseconds=time.time_ns() // 1000
    )
    for index, sale_id in enumerate(sale_ids):
        purchase = (
            await db_session.execute(select(Purchase).where(Purchase.id == sale_id))
        ).scalar_one()
        purchase.created_at = base + timedelta(microseconds=index)
        purchase.agreement_html = None
        purchase.agreement_snapshot_attempts = 0
    await db_session.commit()
    return sale_ids, company


async def _attach(
    db_session: AsyncSession, purchase_id: UUID, template_id: UUID
) -> None:
    await db_session.execute(
        text(
            "UPDATE purchases SET purchase_agreement_template_id = :t "
            "WHERE id = :p"
        ),
        {"t": str(template_id), "p": str(purchase_id)},
    )
    await db_session.commit()


async def _row(db_session: AsyncSession, purchase_id: UUID) -> Purchase:
    db_session.expire_all()
    return (
        await db_session.execute(select(Purchase).where(Purchase.id == purchase_id))
    ).scalar_one()


async def _failure_audits(db_session: AsyncSession, purchase_id: UUID) -> list[dict]:
    rows = await db_session.execute(
        text(
            "SELECT data FROM audit_log "
            "WHERE event = 'purchase.agreement_snapshot_failed' "
            "AND target_id = :p ORDER BY created_at"
        ),
        {"p": str(purchase_id)},
    )
    return [row[0] for row in rows]


def _patch_bodies(
    monkeypatch: pytest.MonkeyPatch, bodies: dict[str, str]
) -> list[str]:
    """Serve template bodies by storage prefix instead of from storage.

    Returns the list of prefixes the renderer asked for, so a test can
    prove storage was (or was not) reached. A prefix this test did not
    register fails loudly: the pass must never reach a foreign row.
    """
    asked: list[str] = []

    async def _body(storage_prefix: str) -> str:
        asked.append(storage_prefix)
        return bodies[storage_prefix]

    async def _assets(storage_prefix: str, asset_files: list[str]):  # type: ignore[no-untyped-def]
        def _uri(filename: str) -> str:
            raise AssertionError(f"no asset expected, got {filename}")

        return _uri

    monkeypatch.setattr(agreement_service, "get_template_html_cached", _body)
    monkeypatch.setattr(agreement_service, "make_asset_data_uri_func", _assets)
    return asked


# ---------------------------------------------------------------------------
# 1: one bad row does not stop the pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["unknown_filter", "database_error", "unexpected_exception"],
)
async def test_a_row_that_cannot_render_does_not_stop_the_pass(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """The bad row (oldest, first in the pass) is charged exactly one
    attempt, stays without a snapshot and gets one audit row; the row
    after it in the SAME pass is snapshotted.

    The three failures are the three ways the old loop broke:
      unknown_filter       -- TemplateAssertionError from compiling the
                              body; not in the old poison list, so it left
                              the loop and rolled back the pass, attempts
                              included, so the same row headed every pass.
      database_error       -- a statement failing inside the row's load:
                              without the savepoint the transaction is
                              aborted and the final commit loses every
                              row before it as well.
      unexpected_exception -- anything nobody listed.
    """
    (bad_id, good_id), company = await _purchases(client, db_session, 2)
    bad_template_id, bad_template_prefix = await _template(
        db_session, company["id"]
    )
    good_template_id, good_template_prefix = await _template(
        db_session, company["id"]
    )
    await _attach(db_session, bad_id, bad_template_id)
    await _attach(db_session, good_id, good_template_id)

    _patch_bodies(
        monkeypatch,
        {
            bad_template_prefix: (
                _UNKNOWN_FILTER_BODY if failure == "unknown_filter" else _GOOD_BODY
            ),
            good_template_prefix: _GOOD_BODY,
        },
    )
    if failure != "unknown_filter":
        real_build = agreement_worker.build_agreement_data_for_snapshot

        async def _build(purchase, session):  # type: ignore[no-untyped-def]
            if purchase.id == bad_id:
                if failure == "database_error":
                    await session.execute(text("SELECT 1 / 0"))
                raise RuntimeError("nobody predicted this")
            return await real_build(purchase, session)

        monkeypatch.setattr(
            agreement_worker, "build_agreement_data_for_snapshot", _build
        )
    monkeypatch.setattr(settings, "agreement_snapshot_worker_batch_size", 2)

    await run_agreement_snapshot_batch()

    bad = await _row(db_session, bad_id)
    assert bad.agreement_snapshot_attempts == 1
    assert bad.agreement_html is None
    assert await _failure_audits(db_session, bad_id) == [
        {
            "attempts": 1,
            "gave_up": False,
            "template_id": str(bad_template_id),
        }
    ]

    good = await _row(db_session, good_id)
    assert good.agreement_snapshot_attempts == 0
    assert good.agreement_html
    assert "units" in good.agreement_html
    assert await _failure_audits(db_session, good_id) == []


# ---------------------------------------------------------------------------
# 2: the attempt ceiling takes a row out of the selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_row_at_the_attempt_ceiling_is_not_selected(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A batch of ONE: the row at the ceiling is the oldest, so if it were
    still selectable it would take the only slot. Instead the next row is
    taken and snapshotted, and the ceiling row is left exactly as it was
    -- not rendered, not charged, not audited again.

    The pair of the ceiling: the same row one attempt below it is taken.
    """
    (capped_id, good_id), company = await _purchases(client, db_session, 2)
    capped_template_id, capped_template_prefix = await _template(
        db_session, company["id"]
    )
    good_template_id, good_template_prefix = await _template(
        db_session, company["id"]
    )
    await _attach(db_session, capped_id, capped_template_id)
    await _attach(db_session, good_id, good_template_id)
    ceiling = settings.agreement_snapshot_max_attempts
    await db_session.execute(
        text(
            "UPDATE purchases SET agreement_snapshot_attempts = :n WHERE id = :p"
        ),
        {"n": ceiling, "p": str(capped_id)},
    )
    await db_session.commit()

    asked = _patch_bodies(
        monkeypatch,
        {
            capped_template_prefix: _UNKNOWN_FILTER_BODY,
            good_template_prefix: _GOOD_BODY,
        },
    )
    monkeypatch.setattr(settings, "agreement_snapshot_worker_batch_size", 1)

    await run_agreement_snapshot_batch()

    assert asked == [good_template_prefix]
    capped = await _row(db_session, capped_id)
    assert capped.agreement_snapshot_attempts == ceiling
    assert capped.agreement_html is None
    assert await _failure_audits(db_session, capped_id) == []
    assert (await _row(db_session, good_id)).agreement_html

    # One below the ceiling: selectable again, charged, and now given up.
    await db_session.execute(
        text(
            "UPDATE purchases SET agreement_snapshot_attempts = :n WHERE id = :p"
        ),
        {"n": ceiling - 1, "p": str(capped_id)},
    )
    await db_session.commit()
    asked.clear()

    await run_agreement_snapshot_batch()

    assert asked == [capped_template_prefix]
    capped = await _row(db_session, capped_id)
    assert capped.agreement_snapshot_attempts == ceiling
    assert capped.agreement_html is None
    assert await _failure_audits(db_session, capped_id) == [
        {
            "attempts": ceiling,
            "gave_up": True,
            "template_id": str(capped_template_id),
        }
    ]


# ---------------------------------------------------------------------------
# 3: a snapshot is served as it is
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_filled_snapshot_is_returned_without_storage(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agreement_html, once written, is the document: returned byte for
    byte, with no template fetched and nothing rendered -- even though the
    template the row points at would no longer render at all.

    The pair: with the snapshot cleared, the same call does reach the
    template (and fails on it), so the first assertion is not vacuous.
    """
    (purchase_id,), company = await _purchases(client, db_session, 1)
    template_id, template_prefix = await _template(db_session, company["id"])
    await _attach(db_session, purchase_id, template_id)
    frozen = "<p>Signed on the day of purchase.</p>"
    await db_session.execute(
        text("UPDATE purchases SET agreement_html = :h WHERE id = :p"),
        {"h": frozen, "p": str(purchase_id)},
    )
    await db_session.commit()

    asked = _patch_bodies(
        monkeypatch, {template_prefix: _UNKNOWN_FILTER_BODY}
    )

    purchase = await _row(db_session, purchase_id)
    data = await build_agreement_data_for_snapshot(purchase, db_session)
    assert data is not None
    assert await render_agreement_html(data, db_session) == frozen
    assert asked == []

    purchase.agreement_html = None
    with pytest.raises(TemplateAssertionError):
        await render_agreement_html(data, db_session)
    assert asked == [template_prefix]
    await db_session.rollback()

    # The snapshot in the database is untouched by any of this.
    assert (await _row(db_session, purchase_id)).agreement_html == frozen
