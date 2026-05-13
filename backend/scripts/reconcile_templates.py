#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Reconcile Per-Company Document Templates
#                     (iter 2.5 mini-fix #3 rewrite, R2 §4.8)
# =============================================================================
#
# Sweeps one company's templates inbox into rows in
# `company_document_templates` with company_id == X.
#
# This file is the THIN CLI wrapper. All reconcile logic lives in
# scripts/_template_reconcile_core.py -- this script and the platform
# variant call into reconcile_with_scope() with a different scope.
#
# WHAT CHANGED IN iter 2.5 mini-fix #3:
#   - Logic moved to _template_reconcile_core (no duplication with the
#     platform reconcile script).
#   - reconcile_company_templates() NEVER calls session.commit() or
#     session.rollback() on the outer transaction. Each folder runs in
#     its own SAVEPOINT in the core; CLI wraps the pass in one outer
#     transaction and commits ONCE at the end.
#
# INBOX LAYOUT (R2 §4.8):
#   companies/<company_id>/templates-inbox/<kind>__<lang>/
#       template.html
#       _meta.cbsmeta.json
#       logo.png        (or .jpg / .jpeg)
#       signature.png
#       stamp.png
#       ...
#
# Folder name format: `<kind>__<lang>` (DOUBLE underscore separator).
# kinds may legally contain a single underscore (e.g. purchase_agreement);
# the core splits on the LAST `__` only.
#
# CANONICAL LAYOUT (R2 §2.2):
#   companies/<company_id>/templates/<kind>/<lang>/
#       template.html
#       <asset>.png / .jpg / .jpeg
#
# AUDIT EVENTS (system actor, actor_id = platform user):
#   company.template_reconciled_created
#   company.template_reconciled_created_draft
#   company.template_reconciled_archived_and_replaced
# The payload includes "company_id": str(uuid) so audit dashboards can
# filter per-company.
#
# CLI:
#   docker compose exec -T app python -m scripts.reconcile_templates \
#       <company_id> [--dry-run]
#
#   --all is intentionally NOT supported. Per-company templates are
#   uploaded one company at a time; bulk-reconcile would mask per-
#   company failures behind a single summary. Add when there's a real
#   use case.
#
# COMMIT MODEL (CLI):
#   One outer transaction per company per CLI invocation. Per-folder
#   SAVEPOINTs inside; one outer commit at the end.
#
# DEGRADATION ENVELOPE:
#   Same as the platform variant -- see reconcile_platform_templates.py
#   header.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Make `app.*` importable when this file is run as a standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.modules.companies.models import CompanyProfile
from scripts._template_reconcile_core import (
    ReconcileStats,
    company_scope,
    reconcile_with_scope,
)

logger = structlog.get_logger()


# Re-exported for tests that import these constants from the old
# monolithic file. Built from the scope factory so a rename only
# touches one place.
def _build_inbox_prefix_template() -> str:
    """Inbox prefix with `{company_id}` placeholder, kept for backward
    compatibility with tests/test_reconcile_templates.py.
    """
    return "companies/{company_id}/templates-inbox/"


def _build_canonical_prefix_template() -> str:
    return "companies/{company_id}/templates/{kind}/{language}/"


def _build_draft_prefix_template() -> str:
    return "companies/{company_id}/templates/{kind}/{language}/.draft-v{version}/"


INBOX_PREFIX_TEMPLATE: str = _build_inbox_prefix_template()
CANONICAL_PREFIX_TEMPLATE: str = _build_canonical_prefix_template()
DRAFT_PREFIX_TEMPLATE: str = _build_draft_prefix_template()


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[RECONCILE-TPL]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


# ---------------------------------------------------------------------------
# Library entry point
# ---------------------------------------------------------------------------


async def reconcile_company_templates(
    session: AsyncSession,
    company_id: UUID,
    *,
    dry_run: bool = False,
) -> ReconcileStats:
    """Reconcile every inbox folder under
    `companies/<company_id>/templates-inbox/`.

    Thin wrapper over reconcile_with_scope(company_scope(company_id)).
    See scripts/_template_reconcile_core for the per-folder semantics.

    DOES NOT commit or roll back the outer transaction. Caller owns it:
      - CLI opens a session, calls this, commits once at the end.
      - Tests call this from the conftest db_session; conftest rollback
        at teardown discards every per-folder SAVEPOINT release.

    Args:
        session: Active DB session. Caller manages the outer transaction.
        company_id: UUID of the company whose inbox to reconcile.
        dry_run: When True, report would-be outcomes without writing.

    Returns:
        ReconcileStats counters.
    """
    return await reconcile_with_scope(
        session, company_scope(company_id), dry_run=dry_run
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reconcile_templates",
        description=(
            "Sync companies/<id>/templates-inbox/ into "
            "company_document_templates rows (R2 §4.8)."
        ),
    )
    parser.add_argument(
        "company_id",
        type=UUID,
        help="UUID of the company to reconcile.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inbox folders without writing.",
    )
    return parser


async def _verify_company_exists(
    session: AsyncSession,
    company_id: UUID,
) -> bool:
    """Cheap sanity check before opening the outer transaction proper:
    bail with exit code 2 if the UUID doesn't match a real company.
    """
    stmt = select(CompanyProfile.id).where(CompanyProfile.id == company_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _run_cli(*, company_id: UUID, dry_run: bool) -> int:
    """CLI entry point. Returns the process exit code:
      0 -- success
      1 -- internal failure
      2 -- company not found
    """
    setup_logging()
    session_factory = get_session_factory()

    try:
        async with session_factory() as session:
            if not await _verify_company_exists(session, company_id):
                err(f"company {company_id} not found")
                return 2

            try:
                stats = await reconcile_company_templates(
                    session, company_id, dry_run=dry_run
                )
            except Exception:
                # Unhandled error inside the core loop -- discard every
                # savepoint release that already made it into the outer
                # transaction so the DB stays at its pre-pass state.
                await session.rollback()
                raise

            if not dry_run:
                await session.commit()
            else:
                await session.rollback()

        log(
            f"done: inspected={stats.inspected} "
            f"created={stats.created} "
            f"created_draft={stats.created_draft} "
            f"archived_and_replaced={stats.archived_and_replaced} "
            f"skipped={stats.skipped}"
            + (" (dry-run)" if dry_run else "")
        )
        for reason in stats.skipped_reasons:
            warn(reason)
        return 0
    except Exception:
        logger.exception("reconcile_templates_failed")
        err("reconcile failed; see traceback above")
        return 1
    finally:
        await dispose_engine()


def main() -> None:
    args = _build_parser().parse_args()
    exit_code = asyncio.run(
        _run_cli(company_id=args.company_id, dry_run=args.dry_run)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
