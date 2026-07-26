# =============================================================================
# AIVIS.ONE Backend -- Pool Constants (Sprint 4.4)
# =============================================================================
#
# Pool status string literals. Mirror OptionPool.status column values
# (the column is plain String(20) -- no DB-side enum).
#
# Sprint 4.4 EXTRACTION:
#   Previously these were duplicated as private `_POOL_STATUS_ACTIVE`
#   in three modules (pools/service, purchases/service,
#   company_dashboard/service). Centralising removes the synchronisation
#   risk: any future status (e.g. "draining", "frozen") lands in one
#   place and all read paths pick it up automatically.
# =============================================================================

POOL_STATUS_ACTIVE = "active"
