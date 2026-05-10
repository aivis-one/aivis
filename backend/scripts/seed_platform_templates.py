#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Seed Platform Default Templates
#                     (Refactor 2 iter 2.3, R2 §4.9 + §1.4)
# =============================================================================
#
# Idempotent installer: for every (kind, language) pair, ensure exactly
# one `active` row with company_id IS NULL exists in
# `company_document_templates`. The row points at MinIO under
# `_platform/templates/<kind>/<lang>/` and lists the standard asset
# triple (logo.png, signature.png, stamp.png).
#
# This script ONLY creates DB rows. The actual HTML + asset bytes are
# uploaded to MinIO separately by `mc cp` in install_cbshome.sh. Order
# matters at install time:
#
#     1. mc cp -r backend/scripts/templates/_default/ \
#                local/cbshome-attachments/_platform/templates/
#     2. python -m scripts.seed_platform_templates
#
# If you run this BEFORE the mc cp step, the rows still get created
# correctly -- but the renderer will 500 on lookup because get_object_bytes
# can't find the HTML (R2 §4.7). Re-run the mc cp step and any cached
# HTML will be invalidated automatically by the next reconcile pass.
#
# IDEMPOTENCY:
#   For each (kind, language) we look up an existing row with
#   company_id IS NULL AND status='active'. If one exists, we skip.
#   If not, we INSERT (version=1, status='active', created_by=NULL).
#   Repeated runs are no-ops once every pair has its row.
#
# UPDATING PLATFORM DEFAULTS LATER:
#   Use `cbshome storage reconcile-platform-templates` (R2 §4.9). That
#   flow archives the old `active` row, creates a new one with version+1,
#   and invalidates the Redis HTML cache. This script is install-only.
#
# CLI:
#   docker compose exec -T app python -m scripts.seed_platform_templates [--dry-run]
#
# AUDIT:
#   System-actor entries (actor_type="system") with actor_id = the
#   platform user. One audit row per CREATE event:
#       platform.template_seeded
#   Skips do not write audit rows -- subsequent runs would otherwise
#   spam the audit log with no information content.
#
# COMMIT MODEL:
#   One COMMIT at the end of a successful run. Failures abort the whole
#   pass; on retry the idempotent lookup finds whatever was committed by
#   an earlier successful run and skips those pairs.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# Make `app.*` importable when this file is run as a standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import select
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
# Must match the files actually present under `backend/scripts/templates/
# _default/<kind>/<lang>/`.
ASSET_FILES: list[str] = ["logo.png", "signature.png", "stamp.png"]


# ---------------------------------------------------------------------------
# Presentation helpers (mirrors style of scripts/reconcile_attachments.py)
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

    Mirrors the convention used by reconcile_platform_templates.py so
    direct seed inserts and inbox-driven inserts produce identical
    storage_prefix strings.
    """
    return f"_platform/templates/{kind}/{language}/"


def _build_title(kind: str, language: str) -> str:
    """Human-readable title for staff inspection (R2 §4.2).

    Templates uploaded by lawyers later will set their own title via the
    cbsmeta.json sidecar. The seed-time title is just a sane default.
    """
    return f"Platform default: {kind} ({language})"


async def _row_exists(
    session: AsyncSession,
    kind: str,
    language: str,
) -> CompanyDocumentTemplate | None:
    """Look up the existing active platform-default row for one
    (kind, language), if any.

    Idempotency hinges on this query: the seed has already done its
    job iff an active row with company_id IS NULL exists for the pair.
    Drafts / archived rows do NOT count -- if some operator manually
    archived an active row, the next seed run treats the pair as
    uncovered and creates a new active.
    """
    stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def seed_platform_templates(
    session: AsyncSession,
    *,
    dry_run: bool = False,
) -> SeedStats:
    """Ensure one active platform-default row per (kind, language) pair.

    Args:
        session: Async DB session. The caller is responsible for the
            commit (the CLI commits once at the end; tests usually run
            inside their own transaction and discard).
        dry_run: When True, log intended actions without inserting.
            The audit row is also skipped in dry-run.

    Returns:
        SeedStats with inspected / created / skipped counts.
    """
    stats = SeedStats()

    # platform_user_id is required for the system audit attribution.
    # Calling it before the loop fails fast if the platform user doesn't
    # exist yet -- which would mean install order is wrong (cbshome seed
    # must run before this script; see install_cbshome.sh).
    platform_user_id = await get_platform_user_id(session)

    for kind in DocumentTemplateKind:
        for language in LANGUAGES:
            stats.inspected += 1

            existing = await _row_exists(session, kind, language)
            if existing is not None:
                log(
                    f"skip: {kind}/{language} "
                    f"(already active, version={existing.version}, id={existing.id})"
                )
                stats.skipped += 1
                continue

            if dry_run:
                log(f"would create: {kind}/{language}")
                stats.created += 1
                continue

            row = CompanyDocumentTemplate(
                company_id=None,
                kind=kind,
                language=language,
                version=1,
                title=_build_title(kind, language),
                storage_prefix=_build_storage_prefix(kind, language),
                # Copy the list so each row gets its own asset_files
                # rather than sharing a reference to the module-level
                # constant. JSONB column rebinds on commit anyway, but
                # the explicit copy keeps things readable.
                asset_files=list(ASSET_FILES),
                status=TemplateStatus.ACTIVE,
                created_by=None,
            )
            session.add(row)
            await session.flush()

            await record_audit(
                session=session,
                event="platform.template_seeded",
                actor_id=platform_user_id,
                actor_type="system",
                target_type="platform_template",
                target_id=row.id,
                data={
                    "kind": str(kind),
                    "language": language,
                    "version": row.version,
                    "storage_prefix": row.storage_prefix,
                    "asset_files": list(ASSET_FILES),
                },
            )

            log(f"created: {kind}/{language} (id={row.id})")
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
            "company_document_templates (R2 §4.9)."
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
