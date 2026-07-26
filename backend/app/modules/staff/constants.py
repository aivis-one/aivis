# =============================================================================
# AIVIS.ONE Backend -- Staff Constants (Sprint 3.1, updated Sprint 4.1, 9.1)
# =============================================================================
#
# DEFAULT_STAFF_PERMISSIONS:
#   Applied when creating a new StaffProfile via POST /staff/users.
#   Admin can override per-staff via PATCH /staff/users/{id}/permissions.
#
# VALID_PERMISSION_KEYS:
#   Frozen set of allowed keys. Rejects unknown keys in update requests.
#
# ADMIN CHECK:
#   Admin = staff whose effective permissions are ALL True.
#   Checked by is_admin() helper. No separate role or flag needed.
#   "Gradations are defined by configuration, not separate roles in code."
#   (AIVIS-Design-Document.md, section 3.10)
#
# Sprint 4.1:
#   Added company_manage permission. Controls CRUD on CompanyProfile
#   and roadmap items. Financial operations on companies (create,
#   price change, distribution_config update) also require
#   financial_operations permission.
#
# Sprint 9.1:
#   Added content_manage permission. Controls CRUD on posts and events.
# =============================================================================

# Default permissions for newly created staff.
# Admin overrides these per-staff via PATCH /staff/users/{id}/permissions.
DEFAULT_STAFF_PERMISSIONS: dict[str, bool] = {
    "avatar_mode": True,
    "kyc_approve": True,
    "payment_review": True,
    "user_block": True,
    "financial_operations": True,
    "agent_application_review": True,
    "translation_edit": False,
    "company_manage": True,
    "content_manage": True,
}

# All valid permission keys. Used for request validation.
VALID_PERMISSION_KEYS: frozenset[str] = frozenset(DEFAULT_STAFF_PERMISSIONS.keys())


def is_admin(permissions: dict[str, bool]) -> bool:
    """Check if the given permission set represents full admin access.

    Admin = every known permission key is present and True.
    Missing keys are treated as False (not admin).
    """
    return all(permissions.get(key, False) for key in VALID_PERMISSION_KEYS)
