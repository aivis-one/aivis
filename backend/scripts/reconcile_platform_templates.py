#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Reconcile Platform Default Templates
#                     (Refactor 2 iter 2.3, R2 §4.9)
# =============================================================================
#
# Sweeps the platform-default templates inbox into company_document_templates
# rows with company_id IS NULL. Run by platform lawyers (or the install
# script as part of bootstrap) when the central fallback templates need
# to be refreshed.
#
# Single direction only (inbox -> DB), same reasoning as the per-company
# reconcile: a missing platform default is an infrastructure incident,
# not a soft-delete signal.
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
# VALIDATION + REPLACE SEMANTICS + CACHE INVALIDATION:
#   Identical to scripts/reconcile_templates.py -- the only differences
#   are the storage prefix, the company_id (NULL vs UUID), and the audit
#   event names. The logic is duplicated rather than extracted into a
#   shared library because the project keeps reconcile scripts as
#   single self-contained files (cf. scripts/reconcile_attachments.py),
#   and the duplication is contained at ~150 lines.
#
# CLI:
#   docker compose exec -T app python -m scripts.reconcile_platform_templates \
#       [--dry-run]
#
#   No company_id argument: there is exactly one platform default series
#   (company_id IS NULL).
#
# AUDIT:
#   System-actor entries (actor_type="system") with actor_id = the
#   platform user. Events:
#     platform.template_reconciled_created
#     platform.template_reconciled_archived_and_replaced
#
# COMMIT MODEL:
#   The script commits per-folder. A bad sidecar in folder A doesn't
#   roll back the successful activation of folder B.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

# Make `app.*` importable when this file is run as a standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from jinja2 import Environment, TemplateSyntaxError, meta as jinja_meta
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
    upload_object,
)
from app.modules.auth.service import get_platform_user_id
from app.modules.companies.constants import (
    TEMPLATE_ASSET_EXTENSION_TO_MIME,
    TEMPLATE_PLACEHOLDERS,
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.companies.schemas import TemplateInboxMetadata
from app.modules.companies.service import invalidate_template_html_cache

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants + presentation helpers
# ---------------------------------------------------------------------------


SIDECAR_NAME = "_meta.cbsmeta.json"
HTML_NAME = "template.html"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"

# Inbox / canonical prefix templates (R2 §4.9). Always include the
# trailing slash so concatenation with bare filenames is safe.
INBOX_PREFIX = "_platform/templates-inbox/"
CANONICAL_PREFIX_TEMPLATE = "_platform/templates/{kind}/{language}/"

# Matches asset_data_uri('<filename>') / asset_data_uri("<filename>"),
# capturing the bare filename. Identical to the per-company reconcile.
ASSET_DATA_URI_RE = re.compile(r"asset_data_uri\(\s*['\"]([^'\"]+)['\"]\s*\)")

# ANSI colours -- match scripts/reconcile_templates.py.
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
# Stats container
# ---------------------------------------------------------------------------


@dataclass
class ReconcileStats:
    """Tally returned by reconcile_platform_templates."""

    inspected: int = 0
    created: int = 0
    archived_and_replaced: int = 0
    skipped: int = 0
    skipped_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Inbox scanning
# ---------------------------------------------------------------------------


async def _list_inbox_folders() -> list[tuple[str, dict[str, str]]]:
    """List every <kind>__<lang>/ folder under the platform inbox."""
    keys = await list_objects(INBOX_PREFIX)

    folders: dict[str, dict[str, str]] = {}
    for key in keys:
        # _platform/templates-inbox/<folder>/<filename>
        relative = key[len(INBOX_PREFIX):]
        parts = relative.split("/", 1)
        if len(parts) != 2 or not parts[1]:
            continue
        folder_name, filename = parts
        folders.setdefault(folder_name, {})[filename] = key

    result: list[tuple[str, dict[str, str]]] = []
    for folder_name in sorted(folders.keys()):
        if "__" not in folder_name:
            warn(f"skipping inbox folder with no '__' separator: {folder_name}")
            continue
        result.append((folder_name, folders[folder_name]))
    return result


def _parse_folder_name(folder_name: str) -> tuple[str, str]:
    """Split `<kind>__<lang>` on the LAST `__` into (kind, language)."""
    head, _, tail = folder_name.rpartition("__")
    return head, tail


# ---------------------------------------------------------------------------
# Per-folder validation + activation
# ---------------------------------------------------------------------------


def _classify_folder_files(
    files: dict[str, str],
) -> tuple[str | None, str | None, dict[str, tuple[str, str]], list[str]]:
    """Same shape as reconcile_templates._classify_folder_files."""
    sidecar_key: str | None = None
    html_key: str | None = None
    assets: dict[str, tuple[str, str]] = {}
    stray: list[str] = []

    for filename, key in files.items():
        if filename == SIDECAR_NAME:
            sidecar_key = key
            continue
        if filename == HTML_NAME:
            html_key = key
            continue
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime = TEMPLATE_ASSET_EXTENSION_TO_MIME.get(ext)
        if mime is None:
            stray.append(filename)
            continue
        assets[filename] = (key, mime)
    return sidecar_key, html_key, assets, stray


def _validate_html_against_kind(
    html: str,
    kind: DocumentTemplateKind,
    asset_filenames: set[str],
) -> tuple[set[str], str | None]:
    """Run the §4.8 HTML validation gauntlet (placeholder whitelist +
    asset-reference resolution).
    """
    env = Environment()
    try:
        ast = env.parse(html)
    except TemplateSyntaxError as exc:
        return set(), f"jinja2 parse error: {exc.message} (line {exc.lineno})"

    used = jinja_meta.find_undeclared_variables(ast)
    allowed = TEMPLATE_PLACEHOLDERS[kind] | {"asset_data_uri"}
    unknown = used - allowed
    if unknown:
        return set(), f"undeclared template variables: {sorted(unknown)}"

    referenced = set(ASSET_DATA_URI_RE.findall(html))
    missing = referenced - asset_filenames
    if missing:
        return set(), (
            f"asset_data_uri references missing assets: {sorted(missing)} "
            f"(folder has: {sorted(asset_filenames)})"
        )
    return referenced, None


# ---------------------------------------------------------------------------
# Storage operations
# ---------------------------------------------------------------------------


async def _move_to_canonical(
    *,
    inbox_key: str,
    canonical_key: str,
    content_type: str,
) -> None:
    """Copy bytes from inbox to canonical, then delete the inbox object."""
    data = await get_object_bytes(inbox_key)
    await upload_object(canonical_key, data, content_type)
    await delete_object(inbox_key)


async def _archive_previous_active(
    session: AsyncSession,
    *,
    kind: DocumentTemplateKind,
    language: str,
) -> CompanyDocumentTemplate | None:
    """Flip the previous platform-default active row (if any) to archived."""
    stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    )
    result = await session.execute(stmt)
    previous = result.scalar_one_or_none()
    if previous is None:
        return None
    previous.status = TemplateStatus.ARCHIVED
    await session.flush()
    return previous


async def _activate_folder(
    session: AsyncSession,
    *,
    folder_name: str,
    files: dict[str, str],
    platform_user_id: UUID,
    dry_run: bool,
) -> tuple[str, str | None]:
    """Validate + activate one platform-default inbox folder.

    Returns (status, reason); status is "created" / "archived_and_replaced"
    / "skipped".
    """
    sidecar_key, html_key, assets, stray = _classify_folder_files(files)
    if sidecar_key is None:
        return "skipped", f"missing {SIDECAR_NAME}"
    if html_key is None:
        return "skipped", f"missing {HTML_NAME}"
    if stray:
        return "skipped", f"stray files in folder: {sorted(stray)}"

    try:
        sidecar_bytes = await get_object_bytes(sidecar_key)
        metadata = TemplateInboxMetadata.model_validate_json(sidecar_bytes)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return "skipped", f"invalid sidecar: {exc}"

    folder_kind, folder_lang = _parse_folder_name(folder_name)
    if folder_kind != metadata.kind:
        return "skipped", (
            f"folder kind {folder_kind!r} != sidecar kind "
            f"{metadata.kind!r}"
        )
    if folder_lang != metadata.language:
        return "skipped", (
            f"folder language {folder_lang!r} != sidecar language "
            f"{metadata.language!r}"
        )

    try:
        html_bytes = await get_object_bytes(html_key)
        html = html_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return "skipped", f"{HTML_NAME} is not valid utf-8: {exc}"

    asset_filenames = set(assets.keys())
    _, html_error = _validate_html_against_kind(
        html, metadata.kind, asset_filenames
    )
    if html_error is not None:
        return "skipped", html_error

    if dry_run:
        return "created", None  # the CLI distinguishes new vs replace by
                                # peeking the previous-active separately;
                                # for dry-run we report as "created" --
                                # exact previous-row peek would add a
                                # read for marginal benefit.

    previous = await _archive_previous_active(
        session,
        kind=metadata.kind,
        language=metadata.language,
    )
    new_version = (previous.version + 1) if previous is not None else 1

    canonical_prefix = CANONICAL_PREFIX_TEMPLATE.format(
        kind=metadata.kind,
        language=metadata.language,
    )

    await _move_to_canonical(
        inbox_key=html_key,
        canonical_key=canonical_prefix + HTML_NAME,
        content_type=HTML_CONTENT_TYPE,
    )
    for filename, (asset_key, mime) in assets.items():
        await _move_to_canonical(
            inbox_key=asset_key,
            canonical_key=canonical_prefix + filename,
            content_type=mime,
        )
    await delete_object(sidecar_key)

    new_row = CompanyDocumentTemplate(
        company_id=None,
        kind=metadata.kind,
        language=metadata.language,
        version=new_version,
        title=metadata.title,
        storage_prefix=canonical_prefix,
        asset_files=sorted(asset_filenames),
        status=TemplateStatus.ACTIVE,
        created_by=None,
    )
    session.add(new_row)
    await session.flush()

    if previous is None:
        event = "platform.template_reconciled_created"
        audit_data = {
            "kind": str(metadata.kind),
            "language": metadata.language,
            "version": new_version,
            "storage_prefix": canonical_prefix,
            "asset_files": sorted(asset_filenames),
        }
        outcome = "created"
    else:
        event = "platform.template_reconciled_archived_and_replaced"
        audit_data = {
            "kind": str(metadata.kind),
            "language": metadata.language,
            "old_template_id": str(previous.id),
            "old_version": previous.version,
            "new_version": new_version,
            "storage_prefix": canonical_prefix,
            "asset_files": sorted(asset_filenames),
        }
        outcome = "archived_and_replaced"

    await record_audit(
        session=session,
        event=event,
        actor_id=platform_user_id,
        actor_type="system",
        target_type="platform_template",
        target_id=new_row.id,
        data=audit_data,
    )

    await invalidate_template_html_cache(canonical_prefix)
    return outcome, None


# ---------------------------------------------------------------------------
# Top-level reconcile
# ---------------------------------------------------------------------------


async def reconcile_platform_templates(
    session: AsyncSession,
    *,
    dry_run: bool = False,
) -> ReconcileStats:
    """Reconcile every inbox folder under _platform/templates-inbox/.

    Commits per folder so a partial failure leaves earlier successes
    in place.
    """
    stats = ReconcileStats()
    folders = await _list_inbox_folders()
    stats.inspected = len(folders)
    if not folders:
        return stats

    platform_user_id = await get_platform_user_id(session)

    for folder_name, files in folders:
        try:
            outcome, reason = await _activate_folder(
                session,
                folder_name=folder_name,
                files=files,
                platform_user_id=platform_user_id,
                dry_run=dry_run,
            )
        except Exception as exc:
            await session.rollback()
            err(f"{folder_name}: unhandled error: {exc}")
            stats.skipped += 1
            stats.skipped_reasons.append(f"{folder_name}: unhandled error: {exc}")
            continue

        if outcome == "skipped":
            await session.rollback()
            warn(f"{folder_name}: skipped: {reason}")
            stats.skipped += 1
            stats.skipped_reasons.append(f"{folder_name}: {reason}")
            continue

        if dry_run:
            log(f"{folder_name}: would activate ({outcome})")
            if outcome == "created":
                stats.created += 1
            else:
                stats.archived_and_replaced += 1
            continue

        await session.commit()
        if outcome == "created":
            log(f"{folder_name}: created")
            stats.created += 1
        else:
            log(f"{folder_name}: archived_and_replaced")
            stats.archived_and_replaced += 1

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reconcile_platform_templates",
        description=(
            "Sync _platform/templates-inbox/ into company_document_templates "
            "rows with company_id IS NULL (R2 §4.9)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inbox folders without writing.",
    )
    return parser


async def _run_cli(*, dry_run: bool) -> int:
    setup_logging()
    session_factory = get_session_factory()

    try:
        async with session_factory() as session:
            stats = await reconcile_platform_templates(session, dry_run=dry_run)

        log(
            f"done: inspected={stats.inspected} "
            f"created={stats.created} "
            f"archived_and_replaced={stats.archived_and_replaced} "
            f"skipped={stats.skipped}"
            + (" (dry-run)" if dry_run else "")
        )
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
