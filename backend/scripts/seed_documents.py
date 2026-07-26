#!/usr/bin/env python3
# =============================================================================
# AIVIS.ONE Backend -- Seed Legal Documents
# =============================================================================
#
# Syncs frontend/public/legal/<language>/*.html (mounted read-only at
# /legal in the app container) into the `documents` table.
#
# Each HTML file must carry:
#   <meta name="cbs-document-type"      content="privacy_policy">
#   <meta name="cbs-language"           content="en">            (must match folder)
#   <meta name="cbs-required-for-roles" content="investor,agent"> (optional)
#   <title>Human-readable title</title>                          (optional)
#
# SYNC RULES, per (type, language):
#   no active row                -> create v1 active
#   active row, body hash matches -> metadata-only update (title/roles)
#   active row, body hash differs -> archive current, create v+1 active
#
# For every active row in the DB whose (type, language) is no longer
# present among the files -> archive it.
#
# The script is idempotent: a second run with no file changes is a no-op.
#
# Role values are NOT validated -- a role typo simply means the document
# is never shown to anyone. Adding or renaming types does not require a
# code change; it requires dropping an HTML file into the legal folder.
#
# Folder structure:
#   /legal/en/privacy_policy.html
#   /legal/ru/privacy_policy.html
#   ...
# Files directly in /legal/ (without a language subdirectory) are ignored.
#
# USAGE:
#   docker compose exec -T app python scripts/seed_documents.py
#
# Called by install_aivis.sh after seed_platform.py / seed_admin.py.
# =============================================================================

import asyncio
import hashlib
import sys
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID

# Ensure app package is importable when running as a standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import select

from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.modules.documents.models import Document, DocumentStatus
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

# Frontend static root is bind-mounted read-only at /legal by docker-compose.
LEGAL_DIR = Path("/legal")

# Terminal colors (match other seed scripts).
G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[SEED]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


# ---------------------------------------------------------------------------
# HTML metadata parser
# ---------------------------------------------------------------------------


class _MetadataParser(HTMLParser):
    """Extract <title> and <meta name="..."> tags using stdlib only."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.meta: dict[str, str] = {}
        self._in_title = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            attr_map = dict(attrs)
            name = attr_map.get("name")
            content = attr_map.get("content")
            if name and content is not None:
                self.meta[name] = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None:
            text = data.strip()
            if text:
                self.title = text


def _parse_metadata(file_path: Path, folder_language: str) -> dict | None:
    """Parse one HTML file -> metadata dict, or None if invalid.

    Returns {type, language, title, required_for_roles, content_hash}.
    The file's language is the folder it lives in; the value of the
    `cbs-language` meta must match (so humans can't drift the two apart).

    The hash covers raw file bytes; any whitespace change triggers a
    version bump, which is acceptable for legal documents.
    """
    content = file_path.read_bytes()

    parser = _MetadataParser()
    parser.feed(content.decode("utf-8", errors="replace"))

    doc_type = (parser.meta.get("cbs-document-type") or "").strip()
    if not doc_type:
        warn(
            f"Skipping {file_path}: missing "
            f'<meta name="cbs-document-type">'
        )
        return None

    meta_language = (parser.meta.get("cbs-language") or "").strip()
    if not meta_language:
        warn(
            f"Skipping {file_path}: missing "
            f'<meta name="cbs-language">'
        )
        return None

    if meta_language != folder_language:
        warn(
            f"Skipping {file_path}: language mismatch "
            f"(folder={folder_language!r}, meta={meta_language!r})"
        )
        return None

    roles_raw = (parser.meta.get("cbs-required-for-roles") or "").strip()
    roles = [r.strip() for r in roles_raw.split(",") if r.strip()]

    title = (parser.title or doc_type).strip()

    return {
        "type": doc_type,
        "language": folder_language,
        "title": title,
        "required_for_roles": roles,
        "content_hash": hashlib.sha256(content).hexdigest(),
    }


# ---------------------------------------------------------------------------
# Creator resolver
# ---------------------------------------------------------------------------


async def _pick_creator_id(session) -> UUID:
    """Return a user id to put into documents.created_by.

    Prefer staff (seeded by seed_admin.py); fall back to Platform user
    (seeded by seed_platform.py). Both seeds run before this script in
    install_aivis.sh, so one of them is always available.
    """
    stmt = (
        select(User.id)
        .where(User.role == UserRole.STAFF)
        .limit(1)
    )
    result = await session.execute(stmt)
    staff_id = result.scalar_one_or_none()
    if staff_id is not None:
        return staff_id

    stmt = (
        select(User.id)
        .where(User.role == UserRole.PLATFORM)
        .limit(1)
    )
    result = await session.execute(stmt)
    platform_id = result.scalar_one_or_none()
    if platform_id is None:
        raise RuntimeError(
            "No staff or platform user found. "
            "Run seed_platform.py (and seed_admin.py) first."
        )
    return platform_id


# ---------------------------------------------------------------------------
# Main sync routine
# ---------------------------------------------------------------------------


async def seed_documents() -> None:
    """Sync /legal/<lang>/*.html into the documents table."""
    setup_logging()

    if not LEGAL_DIR.is_dir():
        err(f"Legal directory not found: {LEGAL_DIR}")
        sys.exit(1)

    # Parse every HTML file one level deep. LEGAL_DIR/<language>/<type>.html.
    parsed: dict[tuple[str, str], dict] = {}
    for lang_dir in sorted(p for p in LEGAL_DIR.iterdir() if p.is_dir()):
        folder_language = lang_dir.name
        for f in sorted(lang_dir.glob("*.html")):
            meta = _parse_metadata(f, folder_language)
            if meta is None:
                continue
            key = (meta["type"], meta["language"])
            if key in parsed:
                warn(
                    f"Duplicate {key[0]!r} [{key[1]}] -- "
                    f"{f} overrides earlier file"
                )
            parsed[key] = meta

    factory = get_session_factory()
    async with factory() as session:
        try:
            creator_id = await _pick_creator_id(session)

            # Current active row per (type, language).
            active_stmt = select(Document).where(
                Document.status == DocumentStatus.ACTIVE,
            )
            active_result = await session.execute(active_stmt)
            active_by_key: dict[tuple[str, str], Document] = {
                (d.type, d.language): d
                for d in active_result.scalars().all()
            }

            created = 0
            bumped = 0
            metadata_updated = 0
            unchanged = 0
            archived = 0

            # 1) For every file: create / no-op / bump version.
            for key, meta in parsed.items():
                existing = active_by_key.get(key)
                doc_type, language = key

                if existing is None:
                    # Brand new (type, language) -> v1 active.
                    doc = Document(
                        type=doc_type,
                        version=1,
                        language=language,
                        title=meta["title"],
                        required_for_roles=list(meta["required_for_roles"]),
                        content_hash=meta["content_hash"],
                        status=DocumentStatus.ACTIVE,
                        created_by=creator_id,
                    )
                    session.add(doc)
                    created += 1
                    continue

                if existing.content_hash == meta["content_hash"]:
                    # Body unchanged. Refresh title / roles if drifted
                    # (legal tweaked metadata without touching body).
                    changed = False
                    if existing.title != meta["title"]:
                        existing.title = meta["title"]
                        changed = True
                    existing_roles = list(existing.required_for_roles or [])
                    if existing_roles != meta["required_for_roles"]:
                        existing.set_jsonb(
                            "required_for_roles",
                            list(meta["required_for_roles"]),
                        )
                        changed = True
                    if changed:
                        metadata_updated += 1
                    else:
                        unchanged += 1
                    continue

                # Body changed: archive current, create new version.
                existing.status = DocumentStatus.ARCHIVED
                new_doc = Document(
                    type=doc_type,
                    version=existing.version + 1,
                    language=language,
                    title=meta["title"],
                    required_for_roles=list(meta["required_for_roles"]),
                    content_hash=meta["content_hash"],
                    status=DocumentStatus.ACTIVE,
                    created_by=creator_id,
                )
                session.add(new_doc)
                bumped += 1

            # 2) Active rows whose file was removed -> archive.
            #    Never delete: DocumentSigning rows still reference them.
            for key, doc in active_by_key.items():
                if key not in parsed:
                    doc.status = DocumentStatus.ARCHIVED
                    archived += 1

            await session.commit()

            log(
                f"Documents seeded: {created} created, {bumped} bumped, "
                f"{metadata_updated} metadata-updated, "
                f"{unchanged} unchanged, {archived} archived "
                f"(of {len(parsed)} files)"
            )
            logger.info(
                "documents_seeded",
                created=created,
                bumped=bumped,
                metadata_updated=metadata_updated,
                unchanged=unchanged,
                archived=archived,
                files_found=len(parsed),
            )

        except Exception as exc:
            await session.rollback()
            err(f"Failed to seed documents: {exc}")
            raise
        finally:
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed_documents())
