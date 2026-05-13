#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Seed Platform Default Templates
#                     (iter 2.5 mini-fix #3 rewrite)
# =============================================================================
#
# Idempotent installer: for every (kind, language) pair, ensure exactly
# one `active` row with company_id IS NULL exists in
# `company_document_templates`. The row points at MinIO under
# `_platform/templates/<kind>/<lang>/` and lists the standard asset
# triple (logo.png, signature.png, stamp.png).
#
# WHAT CHANGED IN iter 2.5 mini-fix #3:
#   The previous version hardcoded version=1 on every fresh insert.
#   When a test (or any other path) had left the pair with only archived
#   rows in the DB, the next seed run hit UniqueConstraint on
#   (company_id, kind, language, version)=NULL/.../.../1 and the entire
#   seed transaction died. The pair stayed broken on every subsequent
#   `cbshome update`.
#
#   This version computes new_version = max(version)+1 across all
#   statuses (R2 §4.8 BUG-NEW-01 pattern). When the table is empty for
#   the pair, max=0 and we still write version=1. When the pair has
#   only archived rows, we write at max+1 -- the seed self-heals.
#
#   Audit row distinguishes the two paths via the `data` payload:
#     recovered_from_archived = False  -- fresh seed, no prior rows.
#     recovered_from_archived = True   -- recovery: write version > 1,
#                                          max_archived_version included
#                                          for ops visibility.
#   Same event name (`platform.template_seeded`) so existing event-name
#   filters in audit dashboards keep working.
#
# IDEMPOTENCY:
#   For each (kind, language) we look up an existing row with
#   company_id IS NULL AND status='active'. If one exists, we skip
#   without writing an audit row (subsequent runs would otherwise spam
#   the log with no information content). If not, we INSERT a new
#   active at version = max(version across all statuses)+1.
#
# UPDATING PLATFORM DEFAULTS LATER:
#   Use `cbshome storage reconcile-platform-templates` (R2 §4.9). That
#   flow archives the old `active` row, creates a new one with
#   version+1, and invalidates the Redis HTML cache. This script is
#   install-time only.
#
# CLI:
#   docker compose exec -T app python -m scripts.seed_platform_templates [--dry-run]
#
# AUDIT:
#   System-actor entries (actor_type="system") with actor_id = the
#   platform user. Event: `platform.template_seeded`.
#   Skips do not write audit rows.
#
# COMMIT MODEL:
#   One COMMIT at the end of a successful run (in the CLI wrapper).
#   The library function never commits -- tests pass their own session
#   and rely on conftest rollback to discard everything.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make `app.*` importable when this file is run as a standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.modules.auth.service import get_platform_user_id
from app.modules.companies.constants import (
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate

logger = structlog.get_logger()


# Languages the platform supports. Must stay in sync with TemplateLanguage
# in app/modules/companies/schemas.py.
LANGUAGES: tuple[str, ...] = ("en", "ru", "de", "ar")

# Standard asset triple every platform default template references.
# Must match the files actually present under
# `backend/scripts/templates/_default/<kind>/<lang>/` so the renderer's
# make_asset_data_uri_func can resolve them.
ASSET_FILES: list[str] = ["logo.png", "signature.png", "stamp.png"]


# ---------------------------------------------------------------------------
# Presentation helpers (match scripts/reconcile_attachments.py style)
# ---------------------------------------------------------------------------

G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[SEED-TPL]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


# ---------------------------------------------------------------------------
# Stats container
# ---------------------------------------------------------------------------


@dataclass
class SeedStats:
    """Tally returned by seed_platform_templates() so the CLI can print
    a one-line summary and the test suite can assert on counts."""

    inspected: int = 0
    created: int = 0
    skipped: int = 0


# ---------------------------------------------------------------------------
# Core seed logic
# ---------------------------------------------------------------------------


def _build_storage_prefix(kind: str, language: str) -> str:
    """Canonical platform-default MinIO prefix for one (kind, language).

    Mirrors the convention used by _template_reconcile_core.platform_scope
    so seed inserts and reconcile inserts produce identical
    storage_prefix strings.
    """
    return f"_platform/templates/{kind}/{language}/"


def _build_title(kind: str, language: str) -> str:
    """Human-readable title for staff inspection (R2 §4.2).

    Lawyers' uploads override this via the cbsmeta.json sidecar; the
    seed-time title is just a sane default.
    """
    return f"Platform default: {kind} ({language})"


async def _find_active_row(
    session: AsyncSession,
    kind: str,
    language: str,
) -> CompanyDocumentTemplate | None:
    """Find the existing active platform-default row for one
    (kind, language) pair. Returns None if there isn't one.

    Idempotency hinges on this query: the seed considers the pair
    "already done" iff an active row with company_id IS NULL exists for
    it. Drafts and archived rows do not count -- if some operator (or
    test) flipped the active row to archived, the next seed run treats
    the pair as uncovered and creates a fresh active.
    """
    stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_max_version(
    session: AsyncSession,
    kind: str,
    language: str,
) -> int:
    """Return max(version) across ALL statuses for (NULL, kind, language).

    Returns 0 when no rows exist so the caller writes version=1 on a
    truly fresh install.

    Why all statuses, not just active:
      - The UNIQUE constraint on (company_id, kind, language, version)
        uses NULLS NOT DISTINCT and matches across status, so version
        collisions happen against draft and archived rows too.
      - If a pair has archived v1 with no active row (broken state left
        by a test or an aborted reconcile), inserting another v1 would
        fail with IntegrityError. Picking max+1 self-heals -- writes
        v2 active and the seed transaction survives.
    """
    stmt = select(func.max(CompanyDocumentTemplate.version)).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
    )
    result = await session.execute(stmt)
    return result.scalar() or 0


async def seed_platform_templates(
    session: AsyncSession,
    *,
    dry_run: bool = False,
) -> SeedStats:
    """Ensure exactly one active platform-default row per (kind, language).

    Args:
        session: Async DB session. The caller is responsible for the
            commit (CLI commits once at the end; tests usually run
            inside their own transaction and rely on rollback at
            teardown).
        dry_run: When True, log intended actions without inserting.
            The audit row is also skipped in dry-run.

    Returns:
        SeedStats with inspected / created / skipped counters.
    """
    stats = SeedStats()

    # platform_user_id is required for the system-actor audit row.
    # Resolving it before the loop fails fast if the platform user does
    # not yet exist -- which would mean install order is wrong (the
    # `cbshome seed` step that creates the platform user must run
    # BEFORE this script; see install_cbshome.sh).
    platform_user_id = await get_platform_user_id(session)

    for kind in DocumentTemplateKind:
        for language in LANGUAGES:
            stats.inspected += 1

            existing = await _find_active_row(session, kind, language)
            if existing is not None:
                log(
                    f"skip: {kind}/{language} "
                    f"(already active, version={existing.version}, "
                    f"id={existing.id})"
                )
                stats.skipped += 1
                continue

            # No active row. We are about to insert one.
            # Pick version = max(version)+1 across all statuses so a
            # leftover archived row (from a test or aborted reconcile)
            # does not trip the UNIQUE constraint.
            max_version = await _get_max_version(session, kind, language)
            new_version = max_version + 1
            recovered = max_version > 0

            if dry_run:
                if recovered:
                    log(
                        f"would recover: {kind}/{language} v{new_version} "
                        f"(max archived={max_version})"
                    )
                else:
                    log(f"would create: {kind}/{language} v1")
                stats.created += 1
                continue

            row = CompanyDocumentTemplate(
                company_id=None,
                kind=kind,
                language=language,
                version=new_version,
                title=_build_title(kind, language),
                storage_prefix=_build_storage_prefix(kind, language),
                # Copy so each row gets its own asset_files list rather
                # than sharing a reference to the module-level constant.
                asset_files=list(ASSET_FILES),
                status=TemplateStatus.ACTIVE,
                # NULL: platform-default rows have no human author.
                # The system actor on the audit row carries the
                # attribution.
                created_by=None,
            )
            session.add(row)
            await session.flush()

            audit_data: dict[str, Any] = {
                "kind": str(kind),
                "language": language,
                "version": row.version,
                "storage_prefix": row.storage_prefix,
                "asset_files": list(ASSET_FILES),
                "recovered_from_archived": recovered,
            }
            if recovered:
                # Operational hint: how deep the archive went before we
                # patched over it. Helps Staff investigate when a pair
                # is repeatedly recovering.
                audit_data["max_archived_version"] = max_version

            await record_audit(
                session=session,
                event="platform.template_seeded",
                actor_id=platform_user_id,
                actor_type="system",
                target_type="platform_template",
                target_id=row.id,
                data=audit_data,
            )

            if recovered:
                log(
                    f"recovered: {kind}/{language} v{new_version} "
                    f"(max archived={max_version}, id={row.id})"
                )
            else:
                log(f"created: {kind}/{language} v1 (id={row.id})")
            stats.created += 1

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_platform_templates",
        description=(
            "Idempotently seed platform-default rows in "
            "company_document_templates (R2 §4.9). Self-heals when the "
            "pair was left with only archived rows by recovering at "
            "max(version)+1 active."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log intended actions without writing.",
    )
    return parser


async def _run_cli(*, dry_run: bool) -> int:
    """CLI entry point. Returns the exit code (0 success, 1 failure)."""
    setup_logging()
    session_factory = get_session_factory()

    try:
        async with session_factory() as session:
            stats = await seed_platform_templates(session, dry_run=dry_run)
            if not dry_run:
                await session.commit()

        log(
            f"done: inspected={stats.inspected} "
            f"created={stats.created} skipped={stats.skipped}"
            + (" (dry-run)" if dry_run else "")
        )
        return 0
    except Exception:
        logger.exception("seed_platform_templates_failed")
        err("seed failed; see traceback above")
        return 1
    finally:
        await dispose_engine()


def main() -> None:
    args = _build_parser().parse_args()
    exit_code = asyncio.run(_run_cli(dry_run=args.dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
