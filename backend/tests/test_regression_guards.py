# =============================================================================
# CBSHOME Backend -- Regression Guards
# =============================================================================
#
# Anti-regression tests for previously-fixed bugs. NOT CRUD coverage.
# These are kept here so a coordinated test-cleanup (removing CRUD tests
# en masse) cannot delete them by accident -- the file name announces
# that everything inside is load-bearing.
#
# Each test references the round / bug ID it guards against and explains
# what would silently regress without it. Stay static where possible
# (no fixtures, no DB) so the guards run cheaply and break at import
# time rather than during a full HTTP setup.
#
# Bug catalogue:
#   SEC-11-01  -- OwnershipData must not carry full User ORM (this file)
# =============================================================================

from app.modules.purchases.ownership_certificate_service import OwnershipData


# ---------------------------------------------------------------------------
# SEC-11-01: OwnershipData does not hold a full User ORM instance
# ---------------------------------------------------------------------------


def test_ownership_data_does_not_hold_user_object() -> None:
    """SEC-11-01 regression guard.

    OwnershipData MUST NOT carry a full User ORM instance. User has
    credentials (password hash), kyc_data, and other sensitive fields
    attached -- routing that through render context would have leaked
    them into Jinja templates and PDF generation memory. Only the
    minimal scalars required for render and audit-log correlation are
    allowed: investor_id (UUID) and investor_language (str), alongside
    the already-extracted investor_name / investor_email.

    Static dataclass-fields inspection -- no fixtures, no DB. Catches
    the regression at collection time without exercising the render
    pipeline.
    """
    fields = OwnershipData.__dataclass_fields__

    assert "investor_user" not in fields, (
        "OwnershipData.investor_user reintroduced -- SEC-11-01 regression. "
        "Carrying full User across render leaks credentials / password_hash "
        "into Jinja context. Use investor_id + investor_language instead."
    )
    assert "investor_id" in fields, (
        "OwnershipData must carry investor_id (UUID) for audit log "
        "correlation in send_ownership_email."
    )
    assert "investor_language" in fields, (
        "OwnershipData must carry investor_language (str) for template "
        "selection in render_ownership_html (4-stage fallback)."
    )
