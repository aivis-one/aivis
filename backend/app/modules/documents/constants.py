# =============================================================================
# CBSHOME Backend -- Document Constants (Sprint 2.2)
# =============================================================================
#
# ROLE_REQUIRED_DOCUMENT_TYPES:
#   Maps user role to required document types for that role.
#   Used by list_documents_for_role() to filter documents.
#
# VALID_STATUS_TRANSITIONS:
#   Allowed status transitions per State Machines v1.4 section 5.
# =============================================================================

from app.modules.documents.models import DocumentStatus, DocumentType

ROLE_REQUIRED_DOCUMENT_TYPES: dict[str, list[str]] = {
    "investor": [
        DocumentType.PRIVACY_POLICY,
        DocumentType.TERMS_OF_SERVICE,
        DocumentType.INVESTMENT_AGREEMENT,
    ],
    "agent": [
        DocumentType.PRIVACY_POLICY,
        DocumentType.TERMS_OF_SERVICE,
        DocumentType.INVESTMENT_AGREEMENT,
        DocumentType.AGENT_AGREEMENT,
    ],
    "company": [
        DocumentType.COMPANY_AGREEMENT,
    ],
}

# State machine transitions (State Machines v1.4 section 5).
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
