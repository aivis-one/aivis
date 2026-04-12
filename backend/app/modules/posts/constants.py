# =============================================================================
# CBSHOME Backend -- Posts Constants (Sprint 9.1)
# =============================================================================
#
# OwnerType determines who owns the post:
#   platform -- system-level news, created by staff
#   company  -- company blog post, created by staff on behalf of a company
# =============================================================================

import enum


class OwnerType(enum.StrEnum):
    """Post owner type."""

    PLATFORM = "platform"
    COMPANY = "company"
