# =============================================================================
# AIVIS.ONE Backend -- The accepted Buyer Agreement (purchase agreement Annex)
# =============================================================================
#
# A purchase agreement reproduces, in its Annex, the text of the Buyer
# Agreement in the version the Buyer accepted, and prints the date and time
# of that acceptance in clause 2.1 and under the Buyer's signature.
#
# WHAT THE HOUSE KEEPS. The Buyer's click is a DocumentSigning row (user,
# Document, signed_at); the Document row names the accepted version and holds
# the sha256 of its file (content_hash); the text itself is the file
# frontend/public/legal/<language>/buyer_agreement.html, mounted at /legal in
# the app container. Only the current file exists: a version since replaced
# is not kept, only its hash.
#
# THE RULE. The Annex is the file's article when the sha256 of the file equals
# the accepted Document's content_hash. When it does not (the accepted
# version was replaced by a later one), the Annex names the accepted version
# and its hash and prints no text, because printing the current text under the
# name of an older version would put words into the Buyer's agreement that
# the Buyer did not accept. The same happens when the file cannot be read or
# no acceptance is recorded.
#
# Read-only: nothing here writes or commits.
# =============================================================================

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from markupsafe import Markup, escape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentSigning
from app.modules.purchases.models import Purchase

BUYER_AGREEMENT_TYPE = "buyer_agreement"

# The app container mounts frontend/public/legal read-only at /legal; a
# checkout outside the container reads it from the repository.
LEGAL_DIRS = (
    Path("/legal"),
    Path(__file__).resolve().parents[4] / "frontend" / "public" / "legal",
)

_ARTICLE_RE = re.compile(
    r"<article\b[^>]*>(?P<body>.*)</article>", re.DOTALL | re.IGNORECASE
)
_H1_RE = re.compile(r"<h1\b[^>]*>.*?</h1>\s*", re.DOTALL | re.IGNORECASE)
_EDITION_RE = re.compile(
    r'<p\s+class="edition">.*?</p>\s*', re.DOTALL | re.IGNORECASE
)


@dataclass
class AcceptedBuyerAgreement:
    """The Buyer's recorded acceptance and what could be shown of it."""

    signed_at: datetime | None
    version: int | None
    content_hash: str | None
    annex_html: Markup  # the text, the version-and-hash line, or empty


async def accepted_buyer_agreement_signing(
    purchase: Purchase, session: AsyncSession
) -> tuple[DocumentSigning, Document] | None:
    """The Buyer's latest acceptance of the Buyer Agreement at or before the
    purchase row was created (the purchase click writes it)."""
    row = (
        await session.execute(
            select(DocumentSigning, Document)
            .join(Document, Document.id == DocumentSigning.document_id)
            .where(
                DocumentSigning.user_id == purchase.investor_id,
                Document.type == BUYER_AGREEMENT_TYPE,
                DocumentSigning.signed_at <= purchase.created_at,
            )
            .order_by(DocumentSigning.signed_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def _read_legal_file(language: str) -> bytes | None:
    for base in LEGAL_DIRS:
        path = base / language / f"{BUYER_AGREEMENT_TYPE}.html"
        try:
            return path.read_bytes()
        except OSError:
            continue
    return None


def annex_html_from_file(raw: bytes) -> Markup | None:
    """The Annex body: the file's article without its own title and edition
    line (the Annex heading and clause 2.1 carry those), clause headings
    one level down. None when the file has no article."""
    match = _ARTICLE_RE.search(raw.decode("utf-8", errors="replace"))
    if match is None:
        return None
    body = _H1_RE.sub("", match.group("body"), count=1)
    body = _EDITION_RE.sub("", body, count=1)
    body = re.sub(r"<(/?)h2\b", r"<\1h3", body, flags=re.IGNORECASE)
    return Markup(body.strip())  # noqa: S704 -- our own tracked legal file


def annex_for_document(document: Document) -> Markup | None:
    """The accepted version's text when the file still is that version."""
    raw = _read_legal_file(document.language)
    if raw is None:
        return None
    if hashlib.sha256(raw).hexdigest() != document.content_hash:
        return None
    return annex_html_from_file(raw)


def annex_fallback_html(document: Document | None, language: str) -> Markup:
    """What the Annex prints when the text cannot be shown: the accepted
    version and its hash, and nothing else."""
    if document is None:
        return Markup("")
    label = "Версия" if language == "ru" else "Version"
    return Markup("<p>{label} {version}, SHA-256 {digest}</p>").format(
        label=label,
        version=document.version, digest=escape(document.content_hash)
    )


async def load_accepted_buyer_agreement(
    purchase: Purchase, session: AsyncSession, language: str
) -> AcceptedBuyerAgreement:
    """The acceptance and the Annex for one purchase. annex_html is the
    accepted version's text, or the version-and-hash line when the text
    cannot be shown, or empty when no acceptance is recorded."""
    found = await accepted_buyer_agreement_signing(purchase, session)
    if found is None:
        return AcceptedBuyerAgreement(None, None, None, Markup(""))
    signing, document = found
    return AcceptedBuyerAgreement(
        signed_at=signing.signed_at,
        version=document.version,
        content_hash=document.content_hash,
        annex_html=annex_for_document(document)
        or annex_fallback_html(document, language),
    )


__all__ = [
    "AcceptedBuyerAgreement",
    "annex_fallback_html",
    "annex_for_document",
    "annex_html_from_file",
    "load_accepted_buyer_agreement",
    "accepted_buyer_agreement_signing",
]

