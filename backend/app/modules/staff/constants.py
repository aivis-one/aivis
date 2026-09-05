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
#
# TASK-30 SS7 ruling 6/8 (project_manage):
#   Added project_manage, gating write routes on companies, pools,
#   products, and company attachments to admin-only staff. It first
#   shipped defaulting True on the theory that a False default would
#   silently strip admin status from every legacy full-permission
#   profile (is_admin() = all(VALID_PERMISSION_KEYS), and this dict
#   defines that set). True was wrong for a different reason: every
#   other key here except translation_edit already defaults True, so a
#   True default for project_manage narrowed nothing -- ordinary staff
#   could still write project data exactly as before, defeating the
#   ruling. The correct fix is False here PLUS a one-time backfill
#   migration (2026_08_26_0043_project_manage_backfill) that
#   writes project_manage: true into every profile that was already an
#   admin under the other 9 keys, so is_admin() reads the same for
#   every pre-existing admin across the deploy. Ship this default flip
#   without that migration and real admins lose admin-gated actions
#   the instant the app restarts.
# =============================================================================

# Default permissions for newly created staff.
# Admin overrides these per-staff via PATCH /staff/users/{id}/permissions.
DEFAULT_STAFF_PERMISSIONS: dict[str, bool] = {
    "avatar_mode": True,
    # H12 P-46d: False, and it used to be True. Until this pass, hiring
    # anybody handed them every user's passport -- harmless while the
    # applications were empty, and exactly wrong the moment H12 gave
    # them documents to hold. The key now gates three things: reading
    # the documents, deciding the application, and moving the platform's
    # verification mode. The third arrived by attachment rather than by
    # design -- a new permission key would break is_admin() for every
    # existing profile (see the project_manage note above) -- and it
    # means granting somebody the right to look at passports also grants
    # the right to switch how the platform verifies. Named in the H12
    # report's Observations; it comes apart when a second setting needs
    # a different permission and the key -> permission map earns itself.
    "kyc_approve": False,
    "payment_review": True,
    "user_block": True,
    "financial_operations": True,
    "agent_application_review": True,
    "translation_edit": False,
    "company_manage": True,
    "content_manage": True,
    "project_manage": False,
}

# All valid permission keys. Used for request validation.
VALID_PERMISSION_KEYS: frozenset[str] = frozenset(DEFAULT_STAFF_PERMISSIONS.keys())


def is_admin(permissions: dict[str, bool]) -> bool:
    """Check if the given permission set represents full admin access.

    Admin = every known permission key is present and True.
    Missing keys are treated as False (not admin).
    """
    return all(permissions.get(key, False) for key in VALID_PERMISSION_KEYS)
