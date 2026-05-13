#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Reconcile Platform Default Templates
#                     (iter 2.5 mini-fix #3 rewrite, R2 §4.9)
# =============================================================================
#
# Sweeps the platform-default templates inbox into rows in
# `company_document_templates` with company_id IS NULL.
#
# This file is the THIN CLI wrapper. All reconcile logic lives in
# scripts/_template_reconcile_core.py -- both this script and the per-
# company variant call into reconcile_with_scope() with a different
# scope object.
#
# WHAT CHANGED IN iter 2.5 mini-fix #3:
#   - Logic moved to _template_reconcile_core (no more duplicated 150
#     lines with "MUST be mirrored" warnings).
#   - reconcile_platform_templates() NEVER calls session.commit() or
#     session.rollback() on the outer transaction. Each folder runs in
#     its own SAVEPOINT inside the core; this CLI wraps the whole pass
#     in a single outer transaction and commits it ONCE at the end.
#   - Tests that call this function from the conftest db_session no
#     longer leak archived rows into the live DB across pytest runs --
#     conftest rollback at teardown discards every savepoint release.
#
# INBOX LAYOUT (R2 §4.9):
#   _platform/templates-inbox/<kind>__<lang>/
#       template.html
#       _meta.cbsmeta.json
#       logo.png        (or .jpg / .jpeg)
#       signature.png
#       stamp.png
#
# CANONICAL LAYOUT:
#   _platform/templates/<kind>/<lang>/
#       template.html
#       <asset>.png / .jpg / .jpeg
#
# AUDIT EVENTS (system actor, actor_id = platform user):
#   platform.template_reconciled_created
#   platform.template_reconciled_created_draft
#   platform.template_reconciled_archived_and_replaced
#
# CLI:
#   docker compose exec -T app python -m scripts.reconcile_platform_templates [--dry-run]
#
# COMMIT MODEL (CLI):
#   One outer transaction wraps the whole pass. Per-folder SAVEPOINTs
#   release into it on success, roll back on skip / dry-run / error.
#   ONE outer commit at the end if every folder either succeeded or was
#   skipped cleanly. On an unhandled exception bubbling out of the
#   core loop, the outer transaction rolls back entirely (savepoint
#   releases included).
#
# DEGRADATION ENVELOPE (per ТЗ §4 пункт 4):
#   The invariant "archive previous active without replacement" can
#   NEVER be observed: archive + insert live in the same SAVEPOINT, so
#   they either both succeed (savepoint release) or both fail (savepoint
#   rollback). MinIO move runs AFTER the DB flush inside the savepoint;
#   if MinIO fails, savepoint rolls back the DB triple while files may
#   be partially moved -- acceptable per spec. If the OUTER commit
#   fails at the end of the pass, every savepoint release rolls back
#   but MinIO has already moved every successful folder's files; this
#   is the widest degradation possible and is allowed by spec.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make `app.*` importable when this file is run as a standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from scripts._template_reconcile_core import (
    ReconcileStats,
    platform_scope,
    reconcile_with_scope,
)

logger = structlog.get_logger()


# Re-exported for tests and CLI users who used to import these from the
# old monolithic file. Build them from platform_scope() so a future
# rename only happens in one place (the scope factory).
_PLATFORM_SCOPE = platform_scope()
INBOX_PREFIX: str = _PLATFORM_SCOPE.inbox_prefix
CANONICAL_PREFIX_TEMPLATE: str = _PLATFORM_SCOPE.canonical_template
DRAFT_PREFIX_TEMPLATE: str = _PLATFORM_SCOPE.draft_template


# ---------------------------------------------------------------------------
# Presentation helpers (match scripts/reconcile_attachments.py style)
# ---------------------------------------------------------------------------

G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[RECONCILE-PLATFORM-TPL]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


# ---------------------------------------------------------------------------
# Library entry point (called by CLI and by tests)
# ---------------------------------------------------------------------------


async def reconcile_platform_templates(
    session: AsyncSession,
    *,
    dry_run: bool = False,
) -> ReconcileStats:
    """Reconcile every inbox folder under `_platform/templates-inbox/`.

    Thin wrapper over reconcile_with_scope(platform_scope()). See
    scripts/_template_reconcile_core for the full per-folder semantics.

    DOES NOT commit or roll back the outer transaction. Caller owns it:
      - The CLI (_run_cli below) opens a session, calls this, commits
        once at the end of the pass.
      - Tests call this from the conftest db_session; conftest rollback
        at teardown discards every per-folder SAVEPOINT release.

    Args:
        session: Active DB session. Caller manages the outer transaction.
        dry_run: When True, report would-be outcomes without writing.

    Returns:
        ReconcileStats with inspected / created / created_draft /
        archived_and_replaced / skipped counters.
    """
    return await reconcile_with_scope(
        session, platform_scope(), dry_run=dry_run
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reconcile_platform_templates",
        description=(
            "Sync _platform/templates-inbox/ into "
            "company_document_templates rows with company_id IS NULL "
            "(R2 §4.9)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inbox folders without writing.",
    )
    return parser


async def _run_cli(*, dry_run: bool) -> int:
    """CLI entry point. Returns the process exit code (0 ok, 1 failure)."""
    setup_logging()
    session_factory = get_session_factory()

    try:
        # One session, one outer transaction for the whole pass. The
        # core opens a SAVEPOINT per folder inside this transaction.
        async with session_factory() as session:
            try:
                stats = await reconcile_platform_templates(
                    session, dry_run=dry_run
                )
            except Exception:
                # An unhandled error escaped the core loop entirely
                # (likely a get_platform_user_id failure, or an issue
                # listing the inbox prefix). Roll the outer transaction
                # back -- every successful savepoint release inside is
                # discarded so the DB stays in its pre-pass state.
                await session.rollback()
                raise

            if not dry_run:
                await session.commit()
            else:
                # Dry-run: nothing should have been persisted in the
                # outer transaction (every savepoint rolled back via the
                # core's sentinel), but rollback defensively.
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
        logger.exception("reconcile_platform_templates_failed")
        err("reconcile failed; see traceback above")
        return 1
    finally:
        await dispose_engine()


def main() -> None:
    args = _build_parser().parse_args()
    exit_code = asyncio.run(_run_cli(dry_run=args.dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
