# =============================================================================
# CBSHOME Backend -- Template Reconcile Core
#                     (iter 2.5 mini-fix #3 -- shared core)
# =============================================================================
#
# Shared logic for the two reconcile entry points:
#   - scripts/reconcile_platform_templates.py  (platform scope, company_id IS NULL)
#   - scripts/reconcile_templates.py           (per-company scope, company_id == X)
#
# WHY EXTRACTED:
#   The two scripts used to duplicate ~150 lines verbatim with explicit
#   "MUST be mirrored" warnings. iter 2.5 mini-fix #3 reworks the per-
#   folder semantics; doing it twice in lock-step doubles the bug surface.
#   This module owns the logic; the script files are thin CLI wrappers
#   that pick a scope and call into here.
#
# CONTRACT (the part that matters for ТЗ §4):
#
# 1. Validation runs FIRST. Nothing is written to DB or MinIO until every
#    validation passes. A failed validation returns Outcome("skipped",
#    reason) with no side effects.
#
# 2. DB mutations (archive previous + insert new + audit) happen INSIDE
#    a SAVEPOINT (session.begin_nested()) opened by reconcile_with_scope.
#    They are flushed but NOT committed inside this module -- the caller
#    (CLI or test) owns the outer transaction.
#
# 3. MinIO mutations (move template.html, move assets, delete inbox
#    sidecar) happen AFTER the DB flush. If a MinIO call raises, the
#    savepoint rolls back the DB changes; MinIO may end up partially
#    moved -- ТЗ §4 explicitly allows this degradation, what it forbids
#    is archiving the previous active without a replacement, and that
#    can't happen because archive + insert live in the same savepoint.
#
# 4. Redis cache invalidation runs LAST and is wrapped in try/except --
#    a Redis outage cannot roll back a successful DB+MinIO reconcile.
#    The 5-minute TTL on the cache key is the correctness backstop.
#
# 5. reconcile_with_scope NEVER calls session.commit() or session.rollback()
#    on the outer transaction. Each folder is its own SAVEPOINT:
#      - clean success -> savepoint released into outer transaction.
#      - skipped / dry-run -> savepoint rolled back via internal sentinel.
#      - unhandled exception -> savepoint rolled back, recorded as skipped.
#    The OUTER commit lives on the caller (CLI does it once at the end
#    of the run; tests rely on conftest rollback to discard everything).
#
# TEST IMPLICATION:
#   Because this module never commits, tests calling reconcile_with_scope
#   (or its script-level wrappers) leave NO persistent state in the DB
#   after conftest teardown. This kills the Усилитель from iter 2.5
#   mini-fix #2 (archived rows accumulating in the live DB across pytest
#   runs of `cbshome update`).
# =============================================================================

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog
from jinja2 import Environment, TemplateSyntaxError, meta as jinja_meta
from pydantic import ValidationError
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.storage import (
    delete_object,
    get_object_bytes,
    list_objects,
    upload_object,
)
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
# Constants shared by both scopes
# ---------------------------------------------------------------------------

SIDECAR_NAME = "_meta.cbsmeta.json"
HTML_NAME = "template.html"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"

# Matches asset_data_uri('<filename>') / asset_data_uri("<filename>"),
# capturing the bare filename. Only literal-string calls are validated
# (R2 §4.8 QC-NEW-03). Set-and-call (`{% set f = 'logo.png' %}{{ asset_data_uri(f) }}`)
# slips through here and surfaces as a runtime BadRequestError inside
# make_asset_data_uri_func at render time.
ASSET_DATA_URI_RE = re.compile(r"asset_data_uri\(\s*['\"]([^'\"]+)['\"]\s*\)")


# ---------------------------------------------------------------------------
# Scope: platform vs per-company
# ---------------------------------------------------------------------------


@dataclass
class ReconcileScope:
    """Configuration that distinguishes platform-default reconcile from
    per-company reconcile.

    The two scopes differ only in:
      - which slice of company_document_templates they own
        (company_id IS NULL vs company_id == X)
      - which MinIO prefix they live under
      - which audit event names they emit
      - which created_by they stamp on a freshly inserted row

    Every other reconcile step is identical, which is why this module
    exists.
    """

    # MinIO inbox prefix (always ends with a slash).
    inbox_prefix: str

    # Canonical destination prefix template; placeholders `{kind}` and
    # `{language}` are substituted by format_canonical().
    canonical_template: str

    # Draft destination prefix template; placeholders `{kind}`,
    # `{language}`, and `{version}` are substituted by format_draft().
    draft_template: str

    # Value used for the company_id column on inserted rows.
    # None for the platform-default series.
    row_company_id: UUID | None

    # When True, freshly inserted rows get created_by = platform_user_id
    # (the per-company scope's audit attribution lands on a real user).
    # When False, created_by stays NULL (platform-default rows have no
    # human author -- the system actor on the audit row carries the
    # attribution).
    use_platform_user_id_as_created_by: bool

    # Audit event prefix, e.g. "platform.template_reconciled_" or
    # "company.template_reconciled_". audit_event() appends a suffix
    # ("created" / "created_draft" / "archived_and_replaced").
    audit_event_prefix: str

    # Audit `target_type` value: "platform_template" for platform scope,
    # "template" for per-company scope (matches the values established
    # in iter 2.3).
    audit_target_type: str

    # Extra fields merged into every audit `data` payload for this scope.
    # Per-company scope adds {"company_id": str(uuid)}; platform scope
    # leaves it empty.
    audit_extra_data: dict[str, Any] = field(default_factory=dict)

    def where_company_id_match(self) -> ColumnElement[bool]:
        """SQL predicate that scopes queries to this slice of the table.

        Returns the appropriate `company_id IS NULL` or `company_id == X`
        clause so the reconcile helpers can be shared.
        """
        if self.row_company_id is None:
            return CompanyDocumentTemplate.company_id.is_(None)
        return CompanyDocumentTemplate.company_id == self.row_company_id

    def format_canonical(self, *, kind: str, language: str) -> str:
        """Build the canonical (active) storage prefix for (kind, language)."""
        return self.canonical_template.format(kind=kind, language=language)

    def format_draft(self, *, kind: str, language: str, version: int) -> str:
        """Build the draft storage prefix for (kind, language, version)."""
        return self.draft_template.format(
            kind=kind, language=language, version=version
        )

    def audit_event(self, suffix: str) -> str:
        """Build the audit event name, e.g. `platform.template_reconciled_created`."""
        return f"{self.audit_event_prefix}{suffix}"

    def row_created_by(self, platform_user_id: UUID) -> UUID | None:
        """Return the value to stamp on CompanyDocumentTemplate.created_by
        for a row inserted by this scope.
        """
        return platform_user_id if self.use_platform_user_id_as_created_by else None


def platform_scope() -> ReconcileScope:
    """Scope object for the platform-default series (company_id IS NULL)."""
    return ReconcileScope(
        inbox_prefix="_platform/templates-inbox/",
        canonical_template="_platform/templates/{kind}/{language}/",
        draft_template="_platform/templates/{kind}/{language}/.draft-v{version}/",
        row_company_id=None,
        use_platform_user_id_as_created_by=False,
        audit_event_prefix="platform.template_reconciled_",
        audit_target_type="platform_template",
        audit_extra_data={},
    )


def company_scope(company_id: UUID) -> ReconcileScope:
    """Scope object for one company's per-company templates."""
    co_str = str(company_id)
    return ReconcileScope(
        inbox_prefix=f"companies/{co_str}/templates-inbox/",
        canonical_template=(
            f"companies/{co_str}/templates/{{kind}}/{{language}}/"
        ),
        draft_template=(
            f"companies/{co_str}/templates/{{kind}}/{{language}}/.draft-v{{version}}/"
        ),
        row_company_id=company_id,
        use_platform_user_id_as_created_by=True,
        audit_event_prefix="company.template_reconciled_",
        audit_target_type="template",
        audit_extra_data={"company_id": co_str},
    )


# ---------------------------------------------------------------------------
# Outcome + stats
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """Result of processing one inbox folder.

    status:
      - "created"               -- new active inserted; no previous active existed.
      - "archived_and_replaced" -- previous active archived; new active inserted.
      - "created_draft"         -- new draft inserted; no active row touched.
      - "skipped"               -- validation failed; reason is set.
    """

    status: str
    reason: str | None = None


@dataclass
class ReconcileStats:
    """Tally for a reconcile pass. Field names are stable -- the
    existing test files in tests/test_reconcile_*.py assert on these.
    """

    inspected: int = 0
    created: int = 0
    created_draft: int = 0
    archived_and_replaced: int = 0
    skipped: int = 0
    skipped_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure helpers (no DB or MinIO IO)
# ---------------------------------------------------------------------------


def _parse_folder_name(folder_name: str) -> tuple[str, str]:
    """Split `<kind>__<lang>` on the LAST `__` into (kind, language).

    The kind portion can legitimately contain a single underscore
    (`purchase_agreement`); splitting on the LAST `__` keeps that intact.
    """
    head, _, tail = folder_name.rpartition("__")
    return head, tail


def _classify_folder_files(
    files: dict[str, str],
) -> tuple[str | None, str | None, dict[str, tuple[str, str]], list[str]]:
    """Partition the filenames in one inbox folder into the four buckets
    reconcile cares about.

    Returns:
        (sidecar_key, html_key, assets, stray) where
          - sidecar_key: MinIO key of `_meta.cbsmeta.json`, or None.
          - html_key: MinIO key of `template.html`, or None.
          - assets: {filename: (key, mime)} for files with a whitelisted
                    image extension.
          - stray: list of filenames that are neither sidecar / html nor
                   recognised-extension assets. A non-empty stray list
                   blocks activation -- the folder is either a typo or
                   an attempted exfiltration.
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
        ext = (
            "." + filename.rsplit(".", 1)[-1].lower()
            if "." in filename
            else ""
        )
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
    """Validate template.html against the per-kind placeholder allow-list
    plus its own asset_data_uri('...') references (R2 §4.8).

    Returns:
        (referenced_assets, error) where
          - referenced_assets: set of filenames quoted inside the HTML
            (literal-string calls only -- see ASSET_DATA_URI_RE comment).
          - error: None on success, or a human-readable reason on failure.
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
# MinIO helpers
# ---------------------------------------------------------------------------


async def _list_inbox_folders(
    inbox_prefix: str,
) -> list[tuple[str, dict[str, str]]]:
    """Group MinIO objects under inbox_prefix by their first subfolder
    name.

    Returns:
        List of (folder_name, {filename: full_key}) tuples sorted by
        folder_name. Folders with no `__` separator are dropped with a
        warning -- they cannot be parsed into (kind, language).
    """
    keys = await list_objects(inbox_prefix)

    folders: dict[str, dict[str, str]] = {}
    for key in keys:
        # <inbox_prefix><folder>/<filename>
        relative = key[len(inbox_prefix):]
        parts = relative.split("/", 1)
        if len(parts) != 2 or not parts[1]:
            continue
        folder_name, filename = parts
        folders.setdefault(folder_name, {})[filename] = key

    result: list[tuple[str, dict[str, str]]] = []
    for folder_name in sorted(folders.keys()):
        if "__" not in folder_name:
            logger.warning(
                "reconcile_inbox_skip_no_separator",
                folder=folder_name,
            )
            continue
        result.append((folder_name, folders[folder_name]))
    return result


async def _move_to_canonical(
    *,
    inbox_key: str,
    canonical_key: str,
    content_type: str,
) -> None:
    """Copy one object from inbox to canonical, then delete the inbox copy.

    Not atomic on MinIO -- a failure between upload and delete leaves
    a duplicate. iter 2.3 accepted this trade-off because the reconcile
    is single-writer and the inbox folder is re-walked on every run.
    """
    data = await get_object_bytes(inbox_key)
    await upload_object(canonical_key, data, content_type)
    await delete_object(inbox_key)


# ---------------------------------------------------------------------------
# DB helpers (scope-aware, no commit)
# ---------------------------------------------------------------------------


async def _archive_previous_active(
    session: AsyncSession,
    scope: ReconcileScope,
    *,
    kind: DocumentTemplateKind | str,
    language: str,
) -> CompanyDocumentTemplate | None:
    """Find the active row for (scope, kind, language) and flip it to
    archived. Returns the now-archived row, or None if there was no
    active row to archive.

    Uses with_for_update() so two parallel reconciles can't both archive
    the same active row and both insert version=N+1 (one of them would
    fail on the UniqueConstraint with the savepoint left dirty).
    """
    stmt = (
        select(CompanyDocumentTemplate)
        .where(
            scope.where_company_id_match(),
            CompanyDocumentTemplate.kind == kind,
            CompanyDocumentTemplate.language == language,
            CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    previous = result.scalar_one_or_none()
    if previous is None:
        return None
    previous.status = TemplateStatus.ARCHIVED
    await session.flush()
    return previous


async def _get_max_version_for_pair(
    session: AsyncSession,
    scope: ReconcileScope,
    *,
    kind: DocumentTemplateKind | str,
    language: str,
) -> int:
    """Return max(version) across all statuses for (scope, kind, language).

    Used to compute the version of a fresh row. Returns 0 when no rows
    exist so the caller writes version=1.

    Looks at every status, not just active: drafts and historical
    archived rows can occupy version slots that a new active must skip
    over (R2 §4.8 BUG-NEW-01).
    """
    stmt = select(func.max(CompanyDocumentTemplate.version)).where(
        scope.where_company_id_match(),
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
    )
    result = await session.execute(stmt)
    return result.scalar() or 0


# ---------------------------------------------------------------------------
# Per-folder activation
# ---------------------------------------------------------------------------


async def _activate_folder(
    session: AsyncSession,
    scope: ReconcileScope,
    *,
    folder_name: str,
    files: dict[str, str],
    dry_run: bool,
    platform_user_id: UUID,
) -> Outcome:
    """Validate + activate-or-stage one inbox folder.

    ORDER OF OPERATIONS (matters for ТЗ §4 пункт 4):
      Steps 1-5 read MinIO only. No DB or MinIO mutation. A failure
        here returns Outcome("skipped", reason).
      Step 6 is a dry-run short-circuit: peek at the existing active row
        to compute the would-be outcome label, then return without
        mutating anything.
      Steps 7-9 perform DB mutations (archive + insert + audit), flushed
        but NOT committed. Caller's savepoint owns the transaction.
      Step 10 performs MinIO mutations strictly AFTER the DB flush.
        If MinIO raises, savepoint rollback discards the DB changes.
      Step 11 invalidates the Redis cache (best-effort, Redis errors
        are logged and swallowed -- they must NOT roll back DB+MinIO).
    """
    # === Step 1: classify folder contents ===================================
    sidecar_key, html_key, assets, stray = _classify_folder_files(files)
    if sidecar_key is None:
        return Outcome("skipped", f"missing {SIDECAR_NAME}")
    if html_key is None:
        return Outcome("skipped", f"missing {HTML_NAME}")
    if stray:
        return Outcome("skipped", f"stray files in folder: {sorted(stray)}")

    # === Step 2: parse + validate sidecar ===================================
    try:
        sidecar_bytes = await get_object_bytes(sidecar_key)
        metadata = TemplateInboxMetadata.model_validate_json(sidecar_bytes)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return Outcome("skipped", f"invalid sidecar: {exc}")

    # === Step 3: cross-check folder name vs sidecar =========================
    folder_kind, folder_lang = _parse_folder_name(folder_name)
    if folder_kind != metadata.kind:
        return Outcome(
            "skipped",
            f"folder kind {folder_kind!r} != sidecar kind {metadata.kind!r}",
        )
    if folder_lang != metadata.language:
        return Outcome(
            "skipped",
            f"folder language {folder_lang!r} != sidecar language "
            f"{metadata.language!r}",
        )

    # === Step 4: parse + validate HTML ======================================
    try:
        html_bytes = await get_object_bytes(html_key)
        html = html_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return Outcome("skipped", f"{HTML_NAME} is not valid utf-8: {exc}")

    asset_filenames = set(assets.keys())
    _, html_error = _validate_html_against_kind(
        html, metadata.kind, asset_filenames
    )
    if html_error is not None:
        return Outcome("skipped", html_error)

    sidecar_active = metadata.status == "active"

    # === Step 5: dry-run short-circuit ======================================
    # Validation passed. In dry-run we compute the outcome label the real
    # run WOULD reach without touching DB or MinIO.
    if dry_run:
        if not sidecar_active:
            return Outcome("created_draft", None)
        peek_stmt = select(CompanyDocumentTemplate).where(
            scope.where_company_id_match(),
            CompanyDocumentTemplate.kind == metadata.kind,
            CompanyDocumentTemplate.language == metadata.language,
            CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
        )
        peek_existing = (
            await session.execute(peek_stmt)
        ).scalar_one_or_none()
        return Outcome(
            "archived_and_replaced" if peek_existing is not None else "created",
            None,
        )

    # === Step 6: compute the version off the full series ====================
    max_version = await _get_max_version_for_pair(
        session,
        scope,
        kind=metadata.kind,
        language=metadata.language,
    )
    new_version = max_version + 1

    # === Step 7: archive previous active iff sidecar says active ============
    # Drafts must NOT archive the previous active -- the operator wants
    # to stage a candidate without taking production offline.
    previous: CompanyDocumentTemplate | None = None
    if sidecar_active:
        previous = await _archive_previous_active(
            session,
            scope,
            kind=metadata.kind,
            language=metadata.language,
        )

    canonical_prefix = scope.format_canonical(
        kind=metadata.kind, language=metadata.language
    )
    if sidecar_active:
        target_prefix = canonical_prefix
    else:
        # Draft uploads route to a versioned `.draft-v<N>/` subfolder so
        # the active row's canonical bytes are never clobbered (R2 §4.8
        # BUG-DRAFT-01).
        target_prefix = scope.format_draft(
            kind=metadata.kind,
            language=metadata.language,
            version=new_version,
        )

    # === Step 8: insert new row =============================================
    new_row = CompanyDocumentTemplate(
        company_id=scope.row_company_id,
        kind=metadata.kind,
        language=metadata.language,
        version=new_version,
        title=metadata.title,
        storage_prefix=target_prefix,
        asset_files=sorted(asset_filenames),
        status=(
            TemplateStatus.ACTIVE if sidecar_active else TemplateStatus.DRAFT
        ),
        created_by=scope.row_created_by(platform_user_id),
    )
    session.add(new_row)
    await session.flush()

    # === Step 9: record audit ==============================================
    if not sidecar_active:
        outcome_label = "created_draft"
    elif previous is None:
        outcome_label = "created"
    else:
        outcome_label = "archived_and_replaced"

    audit_data: dict[str, Any] = {
        "kind": str(metadata.kind),
        "language": metadata.language,
        "version": new_version,
        "storage_prefix": target_prefix,
        "asset_files": sorted(asset_filenames),
    }
    if previous is not None:
        audit_data["old_template_id"] = str(previous.id)
        audit_data["old_version"] = previous.version
    if scope.audit_extra_data:
        audit_data.update(scope.audit_extra_data)

    await record_audit(
        session=session,
        event=scope.audit_event(outcome_label),
        actor_id=platform_user_id,
        actor_type="system",
        target_type=scope.audit_target_type,
        target_id=new_row.id,
        data=audit_data,
    )

    # === Step 10: MinIO operations (strictly AFTER DB flush) ================
    # If any of these raises, the surrounding savepoint rolls back the
    # archive + insert + audit triple as a unit. MinIO may end up
    # partially moved; that is acceptable degradation per ТЗ §4 пункт 4.
    # What is NOT acceptable -- previous archived without replacement --
    # cannot happen because archive + insert live in the same savepoint.
    await _move_to_canonical(
        inbox_key=html_key,
        canonical_key=target_prefix + HTML_NAME,
        content_type=HTML_CONTENT_TYPE,
    )
    for filename, (asset_key, mime) in assets.items():
        await _move_to_canonical(
            inbox_key=asset_key,
            canonical_key=target_prefix + filename,
            content_type=mime,
        )
    # Sidecar metadata is captured in the DB row; drop it from MinIO.
    await delete_object(sidecar_key)

    # === Step 11: cache invalidation (best-effort) ==========================
    # A Redis outage must NOT roll back a successful DB+MinIO reconcile.
    # Cache TTL (5 minutes) is the correctness backstop -- the next reader
    # rebuilds the cache from the new canonical bytes.
    if sidecar_active:
        try:
            await invalidate_template_html_cache(canonical_prefix)
        except Exception as exc:
            logger.warning(
                "template_cache_invalidate_failed",
                storage_prefix=canonical_prefix,
                error=str(exc),
            )

    return Outcome(outcome_label, None)


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------


class _SavepointAbort(Exception):
    """Internal sentinel used to force a savepoint rollback for the
    skipped / dry-run paths without surfacing as an error to the caller.
    """


async def reconcile_with_scope(
    session: AsyncSession,
    scope: ReconcileScope,
    *,
    dry_run: bool = False,
) -> ReconcileStats:
    """Reconcile every inbox folder for the given scope.

    Each folder runs in its own SAVEPOINT (session.begin_nested()):
      - Clean success -> savepoint released into the outer transaction
        (pending until the caller commits the outer txn).
      - Skipped / dry-run -> savepoint rolled back via an internal
        sentinel; no side effects bleed to the next folder.
      - Unhandled exception -> savepoint rolled back, recorded as a
        skip with the exception text for visibility.

    DOES NOT commit or roll back the OUTER transaction. The caller owns
    it -- CLI commits once at the end of the run; tests rely on conftest
    rollback at teardown.

    Args:
        session: Active DB session. Caller manages the outer transaction.
        scope: platform_scope() or company_scope(uuid).
        dry_run: When True, report would-be outcomes without writing.

    Returns:
        ReconcileStats with per-outcome counters.
    """
    stats = ReconcileStats()
    folders = await _list_inbox_folders(scope.inbox_prefix)
    stats.inspected = len(folders)
    if not folders:
        return stats

    # platform_user_id is required for system-actor audit attribution
    # AND for the per-company scope's created_by stamp. Resolve once;
    # the helper reads from the existing session so no commit is needed.
    from app.modules.auth.service import get_platform_user_id

    platform_user_id = await get_platform_user_id(session)

    for folder_name, files in folders:
        outcome: Outcome | None = None

        # SAVEPOINT per folder. On any path that should NOT persist
        # (skipped, dry-run, exception), the savepoint is rolled back
        # and the outer transaction stays clean for the next folder.
        try:
            async with session.begin_nested():
                outcome = await _activate_folder(
                    session,
                    scope,
                    folder_name=folder_name,
                    files=files,
                    dry_run=dry_run,
                    platform_user_id=platform_user_id,
                )
                if outcome.status == "skipped" or dry_run:
                    # Force the savepoint to roll back. For "skipped"
                    # there is nothing to undo (validation-only path),
                    # but the explicit rollback keeps the contract clean.
                    # For dry-run, the SELECT peek is safely discarded.
                    raise _SavepointAbort()
                # On a clean exit the savepoint releases into the outer
                # transaction (pending until the caller commits).
        except _SavepointAbort:
            # Expected control-flow exit, NOT an error.
            pass
        except Exception as exc:
            # Anything else is an unexpected error inside _activate_folder.
            # The savepoint already rolled back; just record the skip.
            logger.exception(
                "reconcile_folder_unhandled_error",
                folder=folder_name,
            )
            stats.skipped += 1
            stats.skipped_reasons.append(
                f"{folder_name}: unhandled error: {exc}"
            )
            continue

        # Tally the outcome.
        if outcome is None:
            # Should not happen: an exception was swallowed without
            # outcome being set. Treat as a skip so the operator notices.
            stats.skipped += 1
            stats.skipped_reasons.append(
                f"{folder_name}: internal error, no outcome reported"
            )
            continue

        if outcome.status == "skipped":
            stats.skipped += 1
            if outcome.reason is not None:
                stats.skipped_reasons.append(
                    f"{folder_name}: {outcome.reason}"
                )
            continue

        if outcome.status == "created":
            stats.created += 1
        elif outcome.status == "created_draft":
            stats.created_draft += 1
        elif outcome.status == "archived_and_replaced":
            stats.archived_and_replaced += 1
        else:
            # Defensive: unknown status. Don't silently swallow.
            stats.skipped += 1
            stats.skipped_reasons.append(
                f"{folder_name}: unknown outcome status: {outcome.status!r}"
            )

    return stats
