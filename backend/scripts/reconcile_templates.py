#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Reconcile Per-Company Document Templates
#                     (Refactor 2 iter 2.3, R2 §4.8)
# =============================================================================
#
# Sweeps the per-company templates inbox into the company_document_templates
# table. Single direction only: inbox -> DB. There is no "broken-direction"
# pass for templates -- a missing template.html in MinIO is an
# infrastructure incident, not a soft-delete signal, and the 4-stage
# fallback (R2 §4.7) already masks per-company misses with the platform
# default. Catch broken inventories with a separate health-check task,
# not by quietly archiving production rows.
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
# Folder name format: `<kind>__<lang>` with a DOUBLE underscore as the
# separator. Single underscores are legal inside the kind portion (e.g.
# `purchase_agreement__de`), so we split on the LAST `__` only.
#
# CANONICAL LAYOUT (where the reconcile moves files to, R2 §2.2):
#   companies/<company_id>/templates/<kind>/<lang>/
#       template.html
#       <asset>.png / .jpg / .jpeg
#
# The companion `_meta.cbsmeta.json` is NOT moved to the canonical path
# -- the metadata is captured in the DB row and the JSON is deleted from
# MinIO at the end of a successful reconcile.
#
# VALIDATION (a single failed check skips the folder; subsequent folders
# are unaffected):
#   1. _meta.cbsmeta.json must exist, parse as JSON, and validate against
#      TemplateInboxMetadata (kind / language / title / status).
#   2. The kind / language fields in the metadata must match the folder
#      name (catches drift between filename and contents).
#   3. template.html must exist and parse via jinja2.Environment.parse
#      without raising TemplateSyntaxError.
#   4. Every undeclared variable in the parsed AST must be either a
#      key in TEMPLATE_PLACEHOLDERS[kind] or the literal string
#      `asset_data_uri` (the registered Jinja global).
#   5. Every asset_data_uri('<filename>') reference inside the HTML
#      must resolve to a file actually present in the same folder
#      with a whitelisted extension (PNG / JPEG).
#   6. The folder must contain ONLY: template.html, _meta.cbsmeta.json,
#      and asset files with whitelisted extensions. Stray files block
#      activation -- they're either typos or attempted exfiltration.
#
# REPLACE SEMANTICS (R2 §4.8):
#   For each (company_id, kind, language) triple, exactly one row is
#   `active`. When a new template comes in:
#     - existing active row (if any) -> archived
#     - new row created with version = previous.version + 1
#                     status   = active
#                     asset_files populated from the inbox folder
#   When NO previous row exists, the new row gets version = 1.
#
# CACHE INVALIDATION (R2 §4.10):
#   On successful upload-and-replace, we drop the Redis HTML cache for
#   the canonical storage_prefix so the next render hits MinIO once and
#   re-warms the cache.
#
# CLI:
#   docker compose exec -T app python -m scripts.reconcile_templates \
#       <company_id> [--dry-run]
#
#   --all is intentionally NOT supported here. Per-company templates are
#   uploaded individually; "reconcile every company in one shot" is not a
#   real operational scenario, and adding it would mask per-company
#   failures in a single bulk pass. Add it when there's a use case.
#
# AUDIT:
#   System-actor entries (actor_type="system") with actor_id = the
#   platform user. Events:
#     company.template_reconciled_created
#     company.template_reconciled_archived_and_replaced
#
# COMMIT MODEL:
#   The script commits per-folder. A bad sidecar in folder A doesn't
#   roll back the successful activation of folder B. Each folder's
#   commit covers: archive of the old active row + insert of the new
#   row + every per-folder audit event.
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
from sqlalchemy import func, select
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
from app.modules.companies.models import (
    CompanyDocumentTemplate,
    CompanyProfile,
)
from app.modules.companies.schemas import TemplateInboxMetadata
from app.modules.companies.service import invalidate_template_html_cache

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants + presentation helpers
# ---------------------------------------------------------------------------


SIDECAR_NAME = "_meta.cbsmeta.json"
HTML_NAME = "template.html"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"

# Inbox / canonical prefix templates. Always include the trailing slash
# so concatenation with bare filenames is safe.
INBOX_PREFIX_TEMPLATE = "companies/{company_id}/templates-inbox/"
CANONICAL_PREFIX_TEMPLATE = "companies/{company_id}/templates/{kind}/{language}/"

# Matches asset_data_uri('<filename>') / asset_data_uri("<filename>") with
# optional whitespace inside the parens. Captures the bare filename so
# reconcile can verify each reference resolves to a file in the folder.
#
# LIMITATION (QC-NEW-03): only string-literal calls are validated. A call
# like `{% set f = 'logo.png' %}{{ asset_data_uri(f) }}` won't be caught
# by this regex; the template will activate, then fall through to a
# runtime BadRequestError inside make_asset_data_uri_func when the
# render attempts to resolve `f` against asset_files. In production all
# legitimate templates use literal filenames (R2 §4.4), so this is an
# accepted trade-off rather than a full Jinja2 AST walker.
ASSET_DATA_URI_RE = re.compile(r"asset_data_uri\(\s*['\"]([^'\"]+)['\"]\s*\)")

# ANSI colours -- match scripts/reconcile_attachments.py.
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
# Stats container
# ---------------------------------------------------------------------------


@dataclass
class ReconcileStats:
    """Tally returned by reconcile_company_templates so callers (CLI summary,
    tests) can assert what happened.

    Fields:
      inspected             -- number of <kind>__<lang>/ folders found.
      created               -- new active row inserted (no previous active).
      created_draft         -- new draft row inserted. Drafts do NOT archive
                                the previous active and are not visible to
                                find_active_template; activation comes from
                                a subsequent reconcile pass with status=active
                                in the sidecar.
      archived_and_replaced -- previous active row archived, new active
                                inserted with version+1.
      skipped               -- folder failed validation. See skipped_reasons
                                for human-readable explanations.
    """

    inspected: int = 0
    created: int = 0
    created_draft: int = 0
    archived_and_replaced: int = 0
    skipped: int = 0
    skipped_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Inbox scanning
# ---------------------------------------------------------------------------


async def _list_inbox_folders(
    company_id: UUID,
) -> list[tuple[str, dict[str, str]]]:
    """List every <kind>__<lang>/ folder under the company's templates
    inbox.

    Returns a list of (folder_name, files) tuples where `files` maps
    bare filenames to full MinIO keys. Sorted by folder name for
    deterministic CLI output.

    Folders without a `__` in the name are skipped with a WARN -- they
    can't be reconciled because we don't know which (kind, language)
    they belong to. Skipping is silent in stats (we never touched any
    DB rows), only the warning surfaces.
    """
    prefix = INBOX_PREFIX_TEMPLATE.format(company_id=company_id)
    keys = await list_objects(prefix)

    folders: dict[str, dict[str, str]] = {}
    for key in keys:
        # Each key looks like
        #   companies/<id>/templates-inbox/<folder>/<filename>
        # We strip the prefix, then split into folder + filename. Anything
        # at depth != 2 below the inbox prefix is ignored (defensive --
        # MinIO doesn't have real folders, only flat keys).
        relative = key[len(prefix):]
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
    """Split `<kind>__<lang>` on the LAST `__` into (kind, language).

    Single underscores INSIDE kind (purchase_agreement, ...) are legal,
    so we use rpartition to take the trailing chunk as the language.
    """
    head, sep, tail = folder_name.rpartition("__")
    return head, tail


# ---------------------------------------------------------------------------
# Per-folder validation + activation
#
# NOTE (QC-NEW-02): the helpers in this section + the next one
# (_classify_folder_files / _validate_html_against_kind /
# _move_to_canonical / _archive_previous_active / _get_max_version_for_pair)
# are duplicated verbatim in reconcile_platform_templates.py. Logic
# changes here MUST be mirrored there or the two reconcile flows
# diverge silently.
# ---------------------------------------------------------------------------


def _classify_folder_files(
    files: dict[str, str],
) -> tuple[str | None, str | None, dict[str, tuple[str, str]], list[str]]:
    """Walk one inbox folder's files and split them into named buckets.

    Returns a tuple:
      (sidecar_key, html_key, assets, stray)
        sidecar_key -- full MinIO key of _meta.cbsmeta.json, or None.
        html_key    -- full MinIO key of template.html, or None.
        assets      -- {filename: (key, mime_type)} for every recognised
                        asset (extension in TEMPLATE_ASSET_EXTENSION_TO_MIME).
        stray       -- filenames that don't fit any bucket (template would
                        be activated with stray garbage in its folder --
                        we treat that as a hard error).
    """
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
    """Run the §4.8 HTML validation gauntlet.

    Returns (referenced_assets, error_msg). On success error_msg is None
    and referenced_assets is the deduplicated set of bare filenames the
    template wants from asset_data_uri(...).
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
# Storage operations -- per-folder commit
# ---------------------------------------------------------------------------


async def _move_to_canonical(
    *,
    inbox_key: str,
    canonical_key: str,
    content_type: str,
) -> None:
    """Copy bytes from inbox_key to canonical_key, then delete the inbox
    object. MinIO has no native rename, so this is a read + write +
    delete sequence.
    """
    data = await get_object_bytes(inbox_key)
    await upload_object(canonical_key, data, content_type)
    await delete_object(inbox_key)


async def _archive_previous_active(
    session: AsyncSession,
    *,
    company_id: UUID,
    kind: DocumentTemplateKind,
    language: str,
) -> CompanyDocumentTemplate | None:
    """Flip the existing active row (if any) to archived and return it.

    The caller uses the return value for the audit row. Version computation
    has moved to _get_max_version_for_pair (BUG-NEW-01 fix): with drafts in
    the picture, version+1 off the previous active collides with whatever
    drafts already sit at higher versions for the same (kind, language).

    QC-NEW-01: with_for_update() takes a row-level lock so two concurrent
    reconcile invocations can't both read the same active row, both
    flip it to archived, both insert version=N+1 and one of them blow up
    on the UniqueConstraint with no rollback.
    """
    stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.company_id == company_id,
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    ).with_for_update()
    result = await session.execute(stmt)
    previous = result.scalar_one_or_none()
    if previous is None:
        return None
    previous.status = TemplateStatus.ARCHIVED
    await session.flush()
    return previous


async def _get_max_version_for_pair(
    session: AsyncSession,
    *,
    company_id: UUID,
    kind: DocumentTemplateKind | str,
    language: str,
) -> int:
    """Return max(version) for (company_id, kind, language) across all
    statuses. Returns 0 when no rows exist so the caller inserts version=1.

    Why max-of-everything rather than `previous.version + 1`: drafts and
    historical archived rows can sit alongside the current active. With
    R2 §4.8 draft support (BUG-NEW-01 fix), a freshly-uploaded draft
    can be at version=2 while the active is at version=1; the next
    active reconcile must land on version=3, not version=2.
    """
    stmt = select(func.max(CompanyDocumentTemplate.version)).where(
        CompanyDocumentTemplate.company_id == company_id,
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
    )
    result = await session.execute(stmt)
    return result.scalar() or 0


async def _activate_folder(
    session: AsyncSession,
    *,
    company_id: UUID,
    folder_name: str,
    files: dict[str, str],
    platform_user_id: UUID,
    dry_run: bool,
) -> tuple[str, str | None]:
    """Validate + activate-or-stage one inbox folder.

    Returns (status, reason) where status is one of:
      "created"               -- new active inserted, no previous active.
      "archived_and_replaced" -- previous active archived, new active
                                  inserted with bumped version.
      "created_draft"         -- new draft inserted (sidecar status=draft).
                                  No archive, no cache invalidation -- the
                                  draft is not visible to find_active_template.
      "skipped"               -- validation failed; reason is human-readable.
    """
    # Step 1: classify folder contents.
    sidecar_key, html_key, assets, stray = _classify_folder_files(files)
    if sidecar_key is None:
        return "skipped", f"missing {SIDECAR_NAME}"
    if html_key is None:
        return "skipped", f"missing {HTML_NAME}"
    if stray:
        return "skipped", f"stray files in folder: {sorted(stray)}"

    # Step 2: parse + validate sidecar.
    try:
        sidecar_bytes = await get_object_bytes(sidecar_key)
        metadata = TemplateInboxMetadata.model_validate_json(sidecar_bytes)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return "skipped", f"invalid sidecar: {exc}"

    # Step 3: cross-check folder name vs sidecar.
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

    # Step 4: parse + validate HTML.
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

    # The sidecar status drives the rest of the flow:
    #   "active" -> archive previous active (if any), insert new active.
    #   "draft"  -> insert draft alongside; do NOT touch any active row.
    sidecar_active = metadata.status == "active"

    # Validation passed. In dry-run we report the outcome the real run
    # WOULD reach without touching DB or MinIO. BUG-NEW-02: previous
    # tautology always returned "created"; we now peek the existing
    # active to choose between "created" and "archived_and_replaced".
    if dry_run:
        if not sidecar_active:
            return "created_draft", None
        peek_stmt = select(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.company_id == company_id,
            CompanyDocumentTemplate.kind == metadata.kind,
            CompanyDocumentTemplate.language == metadata.language,
            CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
        )
        peek_existing = (await session.execute(peek_stmt)).scalar_one_or_none()
        return (
            "archived_and_replaced" if peek_existing is not None else "created",
            None,
        )

    # Step 5: pick the version off the full series, not just the active
    # row. BUG-NEW-01 fix: drafts and historical archived rows can
    # already occupy version slots; we always insert at max+1.
    max_version = await _get_max_version_for_pair(
        session,
        company_id=company_id,
        kind=metadata.kind,
        language=metadata.language,
    )
    new_version = max_version + 1

    # Step 6: archive previous active iff the new row will be active.
    # Drafts must NOT archive the previous active -- the operator wants
    # to stage a candidate without taking production offline.
    previous: CompanyDocumentTemplate | None = None
    if sidecar_active:
        previous = await _archive_previous_active(
            session,
            company_id=company_id,
            kind=metadata.kind,
            language=metadata.language,
        )

    canonical_prefix = CANONICAL_PREFIX_TEMPLATE.format(
        company_id=company_id,
        kind=metadata.kind,
        language=metadata.language,
    )

    # Step 7: move files. template.html first so a partial failure leaves
    # a usable previous-active intact (we already flipped it to archived,
    # but the canonical bytes haven't been touched yet -- a re-run will
    # find the previous-archived row and increment from there).
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
    # Sidecar metadata is captured in the DB row; we drop it from MinIO.
    await delete_object(sidecar_key)

    # Step 8: insert new row. BUG-NEW-03 fix: created_by is the platform
    # user (system actor) rather than NULL -- audit attribution lives on
    # actor_id, but created_by is the persistent author pointer on the
    # row itself; both should reflect "system".
    new_row_status = (
        TemplateStatus.ACTIVE if sidecar_active else TemplateStatus.DRAFT
    )
    new_row = CompanyDocumentTemplate(
        company_id=company_id,
        kind=metadata.kind,
        language=metadata.language,
        version=new_version,
        title=metadata.title,
        storage_prefix=canonical_prefix,
        asset_files=sorted(asset_filenames),
        status=new_row_status,
        created_by=platform_user_id,
    )
    session.add(new_row)
    await session.flush()

    # Step 9: audit + cache invalidation. Cache only matters for active
    # rows -- find_active_template never touches drafts, so a stale
    # template_html:* entry for a draft prefix can't surface to a render.
    if not sidecar_active:
        event = "company.template_reconciled_draft_created"
        audit_data = {
            "company_id": str(company_id),
            "kind": str(metadata.kind),
            "language": metadata.language,
            "version": new_version,
            "storage_prefix": canonical_prefix,
            "asset_files": sorted(asset_filenames),
        }
        outcome = "created_draft"
    elif previous is None:
        event = "company.template_reconciled_created"
        audit_data = {
            "company_id": str(company_id),
            "kind": str(metadata.kind),
            "language": metadata.language,
            "version": new_version,
            "storage_prefix": canonical_prefix,
            "asset_files": sorted(asset_filenames),
        }
        outcome = "created"
    else:
        event = "company.template_reconciled_archived_and_replaced"
        audit_data = {
            "company_id": str(company_id),
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
        target_type="template",
        target_id=new_row.id,
        data=audit_data,
    )

    if sidecar_active:
        await invalidate_template_html_cache(canonical_prefix)
    return outcome, None


# ---------------------------------------------------------------------------
# Top-level reconcile
# ---------------------------------------------------------------------------


async def reconcile_company_templates(
    session: AsyncSession,
    company_id: UUID,
    *,
    dry_run: bool = False,
) -> ReconcileStats:
    """Reconcile every inbox folder for one company. Commits per folder
    so a partial failure leaves earlier successes in place.
    """
    stats = ReconcileStats()
    folders = await _list_inbox_folders(company_id)
    stats.inspected = len(folders)
    if not folders:
        return stats

    platform_user_id = await get_platform_user_id(session)

    for folder_name, files in folders:
        try:
            outcome, reason = await _activate_folder(
                session,
                company_id=company_id,
                folder_name=folder_name,
                files=files,
                platform_user_id=platform_user_id,
                dry_run=dry_run,
            )
        except Exception as exc:
            # Hard errors during MinIO ops or DB flushes -- roll back so a
            # partially-archived previous row doesn't get committed.
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
            # No commit; no DB changes were made.
            if outcome == "created":
                stats.created += 1
            elif outcome == "created_draft":
                stats.created_draft += 1
            else:
                stats.archived_and_replaced += 1
            continue

        await session.commit()
        if outcome == "created":
            log(f"{folder_name}: created")
            stats.created += 1
        elif outcome == "created_draft":
            log(f"{folder_name}: created_draft")
            stats.created_draft += 1
        else:
            log(f"{folder_name}: archived_and_replaced")
            stats.archived_and_replaced += 1

    return stats


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
    """Cheap sanity check: bail early if the UUID isn't a real company."""
    stmt = select(CompanyProfile.id).where(CompanyProfile.id == company_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _run_cli(*, company_id: UUID, dry_run: bool) -> int:
    setup_logging()
    session_factory = get_session_factory()

    try:
        async with session_factory() as session:
            if not await _verify_company_exists(session, company_id):
                err(f"company {company_id} not found")
                return 2

            stats = await reconcile_company_templates(
                session, company_id, dry_run=dry_run
            )

        log(
            f"done: inspected={stats.inspected} "
            f"created={stats.created} "
            f"created_draft={stats.created_draft} "
            f"archived_and_replaced={stats.archived_and_replaced} "
            f"skipped={stats.skipped}"
            + (" (dry-run)" if dry_run else "")
        )
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
