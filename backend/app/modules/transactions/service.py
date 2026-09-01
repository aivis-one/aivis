# =============================================================================
# AIVIS.ONE Backend -- Transaction Service (Sprint 6.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   record_transaction()  -- write immutable event log entry
#   list_transactions()   -- paginated + filtered history for a user
#   get_transaction()     -- single event by id with user_id guard
#
# RECORD:
#   Called from other services in the same DB session. Pure write,
#   no commit (P-01). Caller is responsible for providing correct
#   type, amount, reference, and details.
#
# FILTERS:
#   - type: exact match or prefix (e.g. "withdrawal:" for all withdrawal events)
#   - date_from / date_to: inclusive range on created_at
#   - amount_min / amount_max: absolute value filter on amount_cents
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
#
# EXPORT (TASK-39 item 2):
#   export_transactions_csv() reuses list_transactions() with the SAME
#   filters the screen uses, so a downloaded statement matches whatever
#   the user was looking at. It does NOT reuse pagination -- an export
#   has no page control, so it fetches up to EXPORT_MAX_ROWS rows in one
#   shot (list_transactions's COUNT query is unaffected by LIMIT, so the
#   row-cap check below sees the true total even when it exceeds the
#   fetched page).
#
#   COLUMNS ARE DELIBERATELY NARROW: Date, Type, Amount, Currency,
#   Reference Type, Reference ID. amount_cents is CENTS -- emitted as a
#   decimal amount (2 dp) via Decimal quantize, never raw cents.
#   `details` (free-form JSONB with internal fields) and `user_id` are
#   NEVER emitted -- same leak class as the company audit feed fix.
#
#   CSV FORMULA INJECTION: every emitted cell goes through
#   _sanitize_csv_cell() BEFORE csv.writer sees it. csv.writer's own
#   quoting stops delimiter/quote breakage, not formula interpretation
#   -- a cell starting with =, +, -, @, tab or CR still opens as a live
#   formula in Excel/Sheets/LibreOffice regardless of how csv.writer
#   quoted it. See _sanitize_csv_cell's docstring for the mitigation.
# =============================================================================

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.transactions.constants import EXPORT_MAX_ROWS
from app.modules.transactions.models import Transaction

logger = structlog.get_logger()

# Leading characters that Excel / Google Sheets / LibreOffice interpret
# as the start of a formula when a CSV cell opens with them. Tab and CR
# are included per the OWASP CSV-injection guidance (a leading tab/CR
# can also trigger formula evaluation in some spreadsheet parsers).
_FORMULA_LEAD_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_cell(value: str) -> str:
    """Neutralise CSV formula injection for one cell.

    A cell whose value starts with =, +, -, @, tab or CR is read as a
    FORMULA by Excel/Sheets/LibreOffice when the file is opened, not as
    literal text -- csv.writer's quoting (which guards against
    delimiter/quote breakage) does nothing to stop this. Prefixing a
    leading apostrophe is the standard mitigation: every mainstream
    spreadsheet app renders an apostrophe-led cell as literal text
    instead of evaluating it.

    Applied to every DB-SOURCED cell, rather than to the columns that
    happen to look risky: guessing which column can never carry a
    hostile value is the expensive mistake, and the guard costs nothing.

    TWO CLAIMS THAT USED TO STAND HERE WERE WRONG, and both are removed
    rather than softened:

    - `type` and `reference_type` were described as having "no DB-level
      enum constraint". They do -- ck_transactions_type and
      ck_transactions_reference_type each list their legal values. The
      guard is still right to run over them (a constraint can be
      dropped, and this function does not get to assume it will not),
      but the stated reason was false.
    - A negative amount was described as getting the apostrophe prefix
      as "an accepted trade-off". It does not: _transaction_csv_row
      exempts the amount column deliberately, with its own reasoning at
      the call site, precisely so the column stays numeric.
    """
    if value and value[0] in _FORMULA_LEAD_CHARS:
        return "'" + value
    return value


def _transaction_csv_row(txn: Transaction) -> list[str]:
    """Map one Transaction to its sanitized CSV row.

    Column order: Date, Type, Amount, Currency, Reference Type,
    Reference ID. `details` and `user_id` are never included -- see
    module header.
    """
    amount = (Decimal(txn.amount_cents) / Decimal(100)).quantize(Decimal("0.01"))

    # THE AMOUNT COLUMN IS DELIBERATELY NOT SANITISED, and this is the
    # difference between a statement you can use and one you cannot.
    # Negative amounts are pervasive here -- installment tranches,
    # reversals, purchases and commission debits all record a negative
    # amount_cents -- so most real exports carry many rows starting with
    # "-". Running those through _sanitize_csv_cell() prefixes an
    # apostrophe, which every spreadsheet reads as "force this cell to
    # TEXT": the column stops being numeric and the user can no longer
    # SUM or chart their own statement, which is the main reason to
    # export one at all.
    # It is safe to exempt because this cell is not data we received --
    # we BUILD it, one line above, as str() of a quantised Decimal. The
    # only characters it can contain are digits, "-" and ".", so it
    # cannot express a formula. "-" leads the OWASP list because a
    # FREE-TEXT field may start "-1+cmd|...", not because a real
    # negative number is dangerous.
    # Every other column stays sanitised: they are DB-sourced strings.
    date_cell, currency_cell = txn.created_at.isoformat(), txn.currency
    ref_id_cell = str(txn.reference_id) if txn.reference_id else ""
    return [
        _sanitize_csv_cell(date_cell),
        _sanitize_csv_cell(txn.type),
        str(amount),
        _sanitize_csv_cell(currency_cell),
        _sanitize_csv_cell(txn.reference_type or ""),
        _sanitize_csv_cell(ref_id_cell),
    ]


CSV_EXPORT_HEADER: list[str] = [
    "Date",
    "Type",
    "Amount",
    "Currency",
    "Reference Type",
    "Reference ID",
]


async def record_transaction(
    session: AsyncSession,
    *,
    user_id: UUID,
    type: str,
    amount_cents: int,
    reference_id: UUID | None = None,
    reference_type: str | None = None,
    details: dict[str, Any] | None = None,
    currency: str = "USD",
) -> Transaction:
    """Write an immutable event log entry.

    Pure write -- called from other services in the same session.

    Args:
        session: Active DB session. Caller manages commit (P-01).
        user_id: User who owns this event in their history.
        type: Event type from TransactionType enum.
        amount_cents: Operation amount (positive=in, negative=out).
        reference_id: ID of the source entity (payment, purchase, etc.).
        reference_type: Type of the source entity.
        details: Type-specific metadata JSONB for frontend display.
        currency: Currency code (default USD).

    Returns:
        The created Transaction entry (flushed, not committed).
    """
    entry = Transaction(
        user_id=user_id,
        type=type,
        amount_cents=amount_cents,
        currency=currency,
        reference_id=reference_id,
        reference_type=reference_type,
        details=details,
    )
    session.add(entry)
    await session.flush()

    logger.info(
        "transaction_recorded",
        transaction_id=str(entry.id),
        user_id=str(user_id),
        type=type,
        amount_cents=amount_cents,
        reference_type=reference_type,
    )

    return entry


async def list_transactions(
    user_id: UUID,
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    type_filter: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
) -> tuple[list[Transaction], int]:
    """Get paginated and filtered transaction history for a user.

    Filters:
        type_filter: Exact match or prefix with ":" (e.g. "withdrawal:").
        date_from: Inclusive lower bound on created_at.
        date_to: Inclusive upper bound on created_at.
        amount_min: Minimum absolute amount_cents.
        amount_max: Maximum absolute amount_cents.

    Returns:
        (transactions, total_count) tuple.
    """
    # Base filter.
    conditions = [Transaction.user_id == user_id]

    # Type filter: prefix match if ends with ":", exact otherwise.
    if type_filter:
        if type_filter.endswith(":"):
            conditions.append(Transaction.type.startswith(type_filter))
        else:
            conditions.append(Transaction.type == type_filter)

    # Date range.
    if date_from:
        conditions.append(Transaction.created_at >= date_from)
    if date_to:
        conditions.append(Transaction.created_at <= date_to)

    # Amount range (absolute value).
    if amount_min is not None:
        conditions.append(func.abs(Transaction.amount_cents) >= amount_min)
    if amount_max is not None:
        conditions.append(func.abs(Transaction.amount_cents) <= amount_max)

    # Count.
    count_stmt = (
        select(func.count())
        .select_from(Transaction)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Items.
    stmt = (
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def get_transaction(
    transaction_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> Transaction:
    """Load a single transaction by ID with user ownership guard.

    Args:
        transaction_id: Transaction UUID.
        user_id: Authenticated user ID (ownership check).
        session: Active DB session.

    Returns:
        Transaction entry.

    Raises:
        NotFoundError: Transaction not found or belongs to another user.
    """
    stmt = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    )
    result = await session.execute(stmt)
    txn = result.scalar_one_or_none()

    if txn is None:
        raise NotFoundError("Transaction not found")

    return txn


async def export_transactions_csv(
    user_id: UUID,
    session: AsyncSession,
    *,
    type_filter: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
) -> str:
    """Build a CSV statement of the user's own transaction history.

    Reuses list_transactions() with the SAME filters the caller passed
    (mirrors the screen), fetching up to EXPORT_MAX_ROWS rows in a
    single unpaginated call -- an export has no page control. Ownership
    is enforced the same way as every other call into
    list_transactions(): user_id scopes the query, there is no
    parameter by which a caller can request another user's rows.

    Row cap: list_transactions()'s COUNT query is independent of its
    LIMIT, so `total` here is the TRUE number of matching rows even
    when it exceeds EXPORT_MAX_ROWS. If it does, this raises
    BadRequestError (400) naming the actual count instead of silently
    truncating the file -- the caller must narrow date_from/date_to or
    the type filter and retry. The query itself is still bounded (LIMIT
    EXPORT_MAX_ROWS) regardless of outcome, so this never holds an
    unbounded result set in memory.

    Returns:
        CSV text (header row + one row per transaction, newest first --
        same ordering as list_transactions()). Every cell has been
        through _sanitize_csv_cell() to neutralise formula injection.

    Raises:
        BadRequestError: More than EXPORT_MAX_ROWS rows match the filters.
    """
    items, total = await list_transactions(
        user_id,
        session,
        page=1,
        per_page=EXPORT_MAX_ROWS,
        type_filter=type_filter,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
    )

    if total > EXPORT_MAX_ROWS:
        raise BadRequestError(
            message=(
                f"{total} transactions match these filters, which exceeds "
                f"the {EXPORT_MAX_ROWS}-row export limit. Narrow the date "
                "range or type filter and try again."
            ),
            code="export_row_limit_exceeded",
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_EXPORT_HEADER)
    for txn in items:
        writer.writerow(_transaction_csv_row(txn))

    logger.info(
        "transactions_exported",
        user_id=str(user_id),
        row_count=len(items),
    )

    return buffer.getvalue()
