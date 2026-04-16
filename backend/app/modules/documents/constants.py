# =============================================================================
# CBSHOME Backend -- Document Constants (Sprint 2.2, updated by 0024)
# =============================================================================
#
# VALID_STATUS_TRANSITIONS:
#   Allowed status transitions per State Machines v1.4 section 5.
#
# Since migration 0024 the per-role document mapping lives in the DB
# (documents.required_for_roles JSONB), not here. Do NOT reintroduce a
# Python-side mapping -- adding new document types must not require a
# code change. Role membership is declared via
# <meta name="cbs-required-for-roles"> inside each HTML file under
# frontend/public/legal/ and is picked up by seed_documents.py.
# =============================================================================

from app.modules.documents.models import DocumentStatus


VALID_STATUS_TRANSITIONS: dict[str, list[str]] = {
    DocumentStatus.DRAFT: [
        DocumentStatus.ACTIVE,
        DocumentStatus.ARCHIVED,
    ],
    DocumentStatus.ACTIVE: [
        DocumentStatus.DRAFT,
        DocumentStatus.ARCHIVED,
    ],
    DocumentStatus.ARCHIVED: [],  # terminal
}
