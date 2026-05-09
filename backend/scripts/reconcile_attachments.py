#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Reconcile Company Attachments
#                     (Refactor 2 iter 2.2, batch E1)
# =============================================================================
#
# Two-direction reconciliation between MinIO and the company_attachments
# table. R2 §3.7.
#
# ORPHANS (MinIO -> DB):
#   For every object under   companies/<company_id>/inbox/<filename>
#   that has a sibling       companies/<company_id>/inbox/<filename>.cbsmeta.json
#   parse the sidecar (AttachmentInboxMetadata), then:
#     - exact match in DB on (company_id, title, category, language,
#       is_deleted=False)  -> REPLACE the existing attachment's bytes
#                             (storage_key, original_filename, mime_type,
#                              file_size_bytes get refreshed; metadata
#                              stays as it was in DB);
#     - no match           -> CREATE a new attachment with the parsed
#                             metadata, bytes uploaded to the canonical
#                             attachments/<attachment_id>/<filename> path;
#     - >1 match           -> SKIP with warning (ambiguity).
#   On success: the inbox file and its sidecar are deleted.
#
# BROKEN (DB -> MinIO):
#   For every non-deleted CompanyAttachment whose storage_key no longer
#   exists in the bucket, soft-delete the row (is_deleted=True).
#
# CLI:
#   docker compose exec -T app python -m scripts.reconcile_attachments \
#       <company_id> [--dry-run] [--orphans-only] [--broken-only]
#   docker compose exec -T app python -m scripts.reconcile_attachments \
#       --all       [--dry-run] [--orphans-only] [--broken-only]
#
#   <company_id> and --all are mutually exclusive; exactly one is required.
#
# AUDIT:
#   System-actor entries (actor_type="system") with actor_id = the
#   platform user. Events:
#     company.attachment_reconciled_created
#     company.attachment_reconciled_replaced
#     company.attachment_reconciled_soft_deleted
#
# COMMIT MODEL:
#   The script commits per-attachment in the orphans loop so a partial
#   failure leaves the rest reconciled. The broken loop commits at the
#   end -- soft-delete is cheap and idempotent so a retry will finish
#   the job anyway.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

# Make `app.*` importable when this file is run as a standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.core.storage import (
    delete_object,
    get_object_bytes,
    list_objects,
    object_exists,
    upload_object,
)
from app.modules.auth.service import get_platform_user_id
from app.modules.companies.constants import ALLOWED_ATTACHMENT_MIME_TYPES
from app.modules.companies.models import CompanyAttachment, CompanyProfile
from app.modules.companies.schemas import AttachmentInboxMetadata
from app.modules.companies.service import (
    _build_storage_key,
    _shift_orders_to_make_room,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants + presentation helpers
# ---------------------------------------------------------------------------


SIDECAR_SUFFIX = ".cbsmeta.json"
INBOX_PREFIX_TEMPLATE = "companies/{company_id}/inbox/"

# ANSI colours, matching the other scripts in scripts/.
G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[RECONCILE]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


# ---------------------------------------------------------------------------
# Stats container
# ---------------------------------------------------------------------------


@dataclass
class ReconcileStats:
    """Tally returned by reconcile_orphans / reconcile_broken so callers
    (CLI summary, tests) can assert what happened."""

    inspected: int = 0
    created: int = 0
    replaced: int = 0
    soft_deleted: int = 0
    skipped: int = 0
    # Human-readable reasons -- not load-bearing, but useful for logs/tests.
    skipped_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guess_mime_type(filename: str) -> str | None:
    """Resolve MIME type by filename extension. Returns None if unknown.

    We intentionally use stdlib `mimetypes` rather than python-magic --
    the staff router already enforces the same whitelist on uploads, so
    misclassification at the inbox boundary just means staff fixes the
    extension or the sidecar JSON. Adding python-magic for one script
    is overkill.
    """
    guess, _ = mimetypes.guess_type(filename)
    return guess


async def _get_all_company_ids(session: AsyncSession) -> list[UUID]:
    """Return every CompanyProfile.id, regardless of status.

    Hidden / archived companies are still in scope: a company that just
    flipped to archived may still have inbox bytes that need either
    reconciling or sweeping.
    """
    stmt = select(CompanyProfile.id)
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def _list_inbox_pairs(
    company_id: UUID,
) -> list[tuple[str, str | None]]:
    """List inbox objects and pair each main file with its sidecar.

    Returns: list of (main_key, sidecar_key_or_None). Sidecar files
    themselves are NOT returned as main_keys.
    """
    prefix = INBOX_PREFIX_TEMPLATE.format(company_id=company_id)
    keys = await list_objects(prefix)

    main_keys = [k for k in keys if not k.endswith(SIDECAR_SUFFIX)]
    sidecar_set = {k for k in keys if k.endswith(SIDECAR_SUFFIX)}

    pairs: list[tuple[str, str | None]] = []
    for main_key in main_keys:
        sidecar_key = main_key + SIDECAR_SUFFIX
        pairs.append((main_key, sidecar_key if sidecar_key in sidecar_set else None))

    return pairs


async def _find_match(
    session: AsyncSession,
    company_id: UUID,
    metadata: AttachmentInboxMetadata,
) -> list[CompanyAttachment]:
    """Find non-deleted attachments matching (title, category, language).

    `language` is matched with IS NULL semantics when the metadata's
    language is None, since `column == NULL` is always false in SQL.
    """
    conditions = [
        CompanyAttachment.company_id == company_id,
        CompanyAttachment.is_deleted == False,  # noqa: E712
        CompanyAttachment.title == metadata.title,
        CompanyAttachment.category == metadata.category,
    ]
    if metadata.language is None:
        conditions.append(CompanyAttachment.language.is_(None))
    else:
        conditions.append(CompanyAttachment.language == metadata.language)

    stmt = select(CompanyAttachment).where(*conditions)
    return list((await session.execute(stmt)).scalars().all())


def _filename_from_key(key: str) -> str:
    """Last segment of a slash-separated key. MinIO keys are POSIX-style
    so a plain rsplit is safe."""
    return key.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Orphans direction (MinIO -> DB)
# ---------------------------------------------------------------------------


async def reconcile_orphans(
    session: AsyncSession,
    company_id: UUID,
    *,
    dry_run: bool = False,
) -> ReconcileStats:
    """Sweep companies/<company_id>/inbox/ into the attachments table.

    Each (main file + sidecar) pair becomes either a new attachment row
    or a replace of an existing one; on success the inbox files are
    deleted. Failures are logged and skipped -- they do not abort the
    whole pass.
    """
    stats = ReconcileStats()

    pairs = await _list_inbox_pairs(company_id)
    stats.inspected = len(pairs)

    if not pairs:
        return stats

    platform_user_id = await get_platform_user_id(session)

    for main_key, sidecar_key in pairs:
        filename = _filename_from_key(main_key)

        # --- Sidecar required ---
        if sidecar_key is None:
            reason = f"missing sidecar: {main_key}"
            warn(reason)
            stats.skipped += 1
            stats.skipped_reasons.append(reason)
            continue

        # --- Parse metadata ---
        try:
            sidecar_bytes = await get_object_bytes(sidecar_key)
            metadata = AttachmentInboxMetadata.model_validate_json(sidecar_bytes)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            reason = f"invalid sidecar {sidecar_key}: {exc}"
            warn(reason)
            stats.skipped += 1
            stats.skipped_reasons.append(reason)
            continue

        # --- Validate MIME by extension ---
        mime_type = _guess_mime_type(filename)
        if mime_type is None or mime_type not in ALLOWED_ATTACHMENT_MIME_TYPES:
            reason = f"unsupported MIME for {main_key} (guessed: {mime_type!r})"
            warn(reason)
            stats.skipped += 1
            stats.skipped_reasons.append(reason)
            continue

        # --- Fetch the actual bytes ---
        try:
            file_bytes = await get_object_bytes(main_key)
        except Exception as exc:
            reason = f"download failed for {main_key}: {exc}"
            err(reason)
            stats.skipped += 1
            stats.skipped_reasons.append(reason)
            continue

        # --- Resolve match (REPLACE) vs no-match (CREATE) ---
        matches = await _find_match(session, company_id, metadata)
        if len(matches) > 1:
            reason = (
                f"ambiguous match for {main_key}: "
                f"{len(matches)} attachments share (title, category, language)"
            )
            warn(reason)
            stats.skipped += 1
            stats.skipped_reasons.append(reason)
            continue

        if dry_run:
            log(
                f"[dry-run] would {'replace' if matches else 'create'} "
                f"from {main_key}"
            )
            if matches:
                stats.replaced += 1
            else:
                stats.created += 1
            continue

        if matches:
            await _replace_from_inbox(
                session,
                company_id=company_id,
                attachment=matches[0],
                file_bytes=file_bytes,
                original_filename=filename,
                content_type=mime_type,
                platform_user_id=platform_user_id,
                inbox_main_key=main_key,
                inbox_sidecar_key=sidecar_key,
            )
            stats.replaced += 1
        else:
            await _create_from_inbox(
                session,
                company_id=company_id,
                file_bytes=file_bytes,
                original_filename=filename,
                content_type=mime_type,
                metadata=metadata,
                platform_user_id=platform_user_id,
                inbox_main_key=main_key,
                inbox_sidecar_key=sidecar_key,
            )
            stats.created += 1

    return stats


async def _create_from_inbox(
    session: AsyncSession,
    *,
    company_id: UUID,
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    metadata: AttachmentInboxMetadata,
    platform_user_id: UUID,
    inbox_main_key: str,
    inbox_sidecar_key: str,
) -> None:
    """Insert a new CompanyAttachment from inbox bytes + metadata.

    Mirrors the relevant parts of companies.service.create_attachment but
    runs as actor_type="system" with the platform user as actor_id, so
    the audit trail makes the provenance obvious.
    """
    attachment_id = uuid4()
    storage_key = _build_storage_key(company_id, attachment_id, original_filename)

    await upload_object(storage_key, file_bytes, content_type)

    await _shift_orders_to_make_room(
        session, company_id, metadata.category, metadata.order
    )

    attachment = CompanyAttachment(
        id=attachment_id,
        company_id=company_id,
        category=metadata.category,
        language=metadata.language,
        title=metadata.title,
        description=metadata.description,
        storage_key=storage_key,
        original_filename=original_filename,
        mime_type=content_type,
        file_size_bytes=len(file_bytes),
        order=metadata.order,
        is_published=metadata.is_published,
        is_public=metadata.is_public,
        created_by=platform_user_id,
    )
    session.add(attachment)
    await session.flush()
    await session.refresh(attachment)

    await record_audit(
        session=session,
        event="company.attachment_reconciled_created",
        actor_id=platform_user_id,
        actor_type="system",
        target_type="attachment",
        target_id=attachment.id,
        data={
            "company_id": str(company_id),
            "category": metadata.category,
            "language": metadata.language,
            "mime_type": content_type,
            "file_size_bytes": len(file_bytes),
            "inbox_key": inbox_main_key,
        },
    )

    # Inbox cleanup happens in the same DB transaction window, so an
    # error mid-flight rolls back the row + leaves the inbox file for
    # the next reconcile. delete_object is idempotent on missing keys.
    await delete_object(inbox_main_key)
    await delete_object(inbox_sidecar_key)
    await session.commit()

    log(
        f"created attachment {attachment.id} "
        f"({len(file_bytes)} bytes, {content_type}) from {inbox_main_key}"
    )


async def _replace_from_inbox(
    session: AsyncSession,
    *,
    company_id: UUID,
    attachment: CompanyAttachment,
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    platform_user_id: UUID,
    inbox_main_key: str,
    inbox_sidecar_key: str,
) -> None:
    """Replace the bytes of an existing attachment with inbox bytes.

    Metadata fields (title / category / language / publish flags) stay
    as they were in DB -- the match key already pinned them; the inbox
    is the source of truth for bytes only.
    """
    new_storage_key = _build_storage_key(
        company_id, attachment.id, original_filename
    )
    old_storage_key = attachment.storage_key

    await upload_object(new_storage_key, file_bytes, content_type)
    if old_storage_key != new_storage_key:
        await delete_object(old_storage_key)

    attachment.storage_key = new_storage_key
    attachment.original_filename = original_filename
    attachment.mime_type = content_type
    attachment.file_size_bytes = len(file_bytes)

    await session.flush()
    await session.refresh(attachment)

    await record_audit(
        session=session,
        event="company.attachment_reconciled_replaced",
        actor_id=platform_user_id,
        actor_type="system",
        target_type="attachment",
        target_id=attachment.id,
        data={
            "company_id": str(company_id),
            "old_storage_key": old_storage_key,
            "new_storage_key": new_storage_key,
            "mime_type": content_type,
            "file_size_bytes": len(file_bytes),
            "inbox_key": inbox_main_key,
        },
    )

    await delete_object(inbox_main_key)
    await delete_object(inbox_sidecar_key)
    await session.commit()

    log(
        f"replaced attachment {attachment.id} "
        f"({len(file_bytes)} bytes, {content_type}) from {inbox_main_key}"
    )


# ---------------------------------------------------------------------------
# Broken direction (DB -> MinIO)
# ---------------------------------------------------------------------------


async def reconcile_broken(
    session: AsyncSession,
    company_id: UUID,
    *,
    dry_run: bool = False,
) -> ReconcileStats:
    """Soft-delete attachments whose MinIO object has gone missing.

    Already-soft-deleted rows are skipped (their object may already be
    gone after a hard-delete that was interrupted -- that's expected).
    """
    stats = ReconcileStats()

    stmt = select(CompanyAttachment).where(
        CompanyAttachment.company_id == company_id,
        CompanyAttachment.is_deleted == False,  # noqa: E712
    )
    rows = list((await session.execute(stmt)).scalars().all())
    stats.inspected = len(rows)

    if not rows:
        return stats

    platform_user_id = await get_platform_user_id(session)

    for attachment in rows:
        if await object_exists(attachment.storage_key):
            continue

        if dry_run:
            log(
                f"[dry-run] would soft-delete {attachment.id} "
                f"(missing object: {attachment.storage_key})"
            )
            stats.soft_deleted += 1
            continue

        attachment.is_deleted = True
        await session.flush()

        await record_audit(
            session=session,
            event="company.attachment_reconciled_soft_deleted",
            actor_id=platform_user_id,
            actor_type="system",
            target_type="attachment",
            target_id=attachment.id,
            data={
                "company_id": str(company_id),
                "storage_key": attachment.storage_key,
                "reason": "object_missing",
            },
        )
        stats.soft_deleted += 1

        log(
            f"soft-deleted {attachment.id} "
            f"(missing object: {attachment.storage_key})"
        )

    if not dry_run:
        await session.commit()

    return stats


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


async def reconcile(
    session: AsyncSession,
    company_ids: list[UUID],
    *,
    dry_run: bool,
    orphans_only: bool,
    broken_only: bool,
) -> tuple[ReconcileStats, ReconcileStats]:
    """Run both directions for every requested company.

    Returns the cumulative (orphans, broken) stats across all companies.
    """
    orphans_total = ReconcileStats()
    broken_total = ReconcileStats()

    for cid in company_ids:
        log(f"company {cid}")
        if not broken_only:
            stats = await reconcile_orphans(session, cid, dry_run=dry_run)
            orphans_total.inspected += stats.inspected
            orphans_total.created += stats.created
            orphans_total.replaced += stats.replaced
            orphans_total.skipped += stats.skipped
            orphans_total.skipped_reasons.extend(stats.skipped_reasons)
        if not orphans_only:
            stats = await reconcile_broken(session, cid, dry_run=dry_run)
            broken_total.inspected += stats.inspected
            broken_total.soft_deleted += stats.soft_deleted

    return orphans_total, broken_total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reconcile_attachments",
        description="Sync MinIO inbox into attachments / sweep broken records.",
    )
    parser.add_argument(
        "company_id",
        nargs="?",
        type=UUID,
        default=None,
        help="UUID of a single company to reconcile.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Reconcile every company in the database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log intended actions, write nothing.",
    )
    parser.add_argument(
        "--orphans-only",
        action="store_true",
        help="Skip the broken-direction sweep.",
    )
    parser.add_argument(
        "--broken-only",
        action="store_true",
        help="Skip the orphans-direction sweep.",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    setup_logging()
    factory = get_session_factory()

    async with factory() as session:
        try:
            if args.all:
                company_ids = await _get_all_company_ids(session)
            else:
                company_ids = [args.company_id]

            log(f"reconciling {len(company_ids)} company(ies)")

            orphans_total, broken_total = await reconcile(
                session,
                company_ids,
                dry_run=args.dry_run,
                orphans_only=args.orphans_only,
                broken_only=args.broken_only,
            )

            log("---- summary ----")
            log(
                f"orphans: inspected={orphans_total.inspected} "
                f"created={orphans_total.created} "
                f"replaced={orphans_total.replaced} "
                f"skipped={orphans_total.skipped}"
            )
            log(
                f"broken:  inspected={broken_total.inspected} "
                f"soft_deleted={broken_total.soft_deleted}"
            )
            return 0
        except Exception as exc:
            await session.rollback()
            err(f"Reconcile failed: {exc}")
            logger.exception("reconcile_failed")
            return 1
        finally:
            await dispose_engine()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Mutually exclusive: company_id XOR --all, exactly one required.
    no_company = args.company_id is None
    no_all = not args.all
    if no_company == no_all:
        parser.error("Specify either company_id or --all (exactly one).")

    if args.orphans_only and args.broken_only:
        parser.error("--orphans-only and --broken-only are mutually exclusive.")

    rc = asyncio.run(_async_main(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
