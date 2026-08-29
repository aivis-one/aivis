# =============================================================================
# AIVIS.ONE Backend -- Company Audit Feed Schemas (TASK-30 ruling 3 / F2)
# =============================================================================
#
# RESPONSE SCHEMAS:
#   CompanyAuditEntryResponse -- one AuditLog row (target_type="company")
#   CompanyAuditFeedResponse  -- paginated list, same envelope as
#                                CompanyListResponse / PriceHistoryListResponse
#                                / TransactionListResponse elsewhere in this
#                                codebase.
#
# Read-only surface. No request schema exists on purpose -- there is
# nothing here for a client to submit. Entries are written by
# record_audit() (app/core/audit.py), called directly from whichever
# service performs the write (create_company / update_company /
# assign_company today; future project self-service write endpoints
# the same way).
#
# TASK-39 item 7 ADDS a second, DELIBERATELY NARROWER pair of schemas
# below -- CompanySelfAuditEntryResponse / CompanySelfAuditFeedResponse
# -- for the company-facing GET /api/v1/company/audit (audit/
# company_router.py). CompanyAuditEntryResponse above is STAFF-ONLY and
# must never be reused for that endpoint: it carries actor_id /
# performed_by / on_behalf_of (internal staff identity) and the raw
# `data` blob (which can carry values -- e.g. company.price_updated's
# old_price/new_price). See the new schemas' docstrings for the full
# reasoning.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import AuditLog


class CompanyAuditEntryResponse(BaseModel):
    """One company (project) write, as recorded by record_audit().

    `company_id` is AuditLog.target_id, renamed at the API boundary
    since target_type is constant ("company") for every row this feed
    returns and would add nothing by being surfaced.

    `actor_type` / `performed_by` / `on_behalf_of` are all exposed
    (rather than just actor_id) because the admin reading this feed
    needs to distinguish "the project account wrote this itself" from
    "a staff member wrote this on the project's behalf" -- including
    the avatar-mode case (Sprint 3.2: performed_by = staff acting,
    on_behalf_of = the identity they acted for), which record_audit()
    already auto-fills when the write happens inside an avatar
    session. Both are null for an ordinary (non-avatar) write.

    `data` defaults to {} rather than being Optional -- AuditLog.data
    is NOT NULL with a "{}" server_default, so the column is never
    actually null.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID = Field(validation_alias="target_id")
    event: str
    actor_id: UUID | None
    actor_type: str
    performed_by: UUID | None
    on_behalf_of: UUID | None
    data: dict  # type: ignore[type-arg]
    created_at: datetime


class CompanyAuditFeedResponse(BaseModel):
    """Paginated feed of company (project) writes (F2)."""

    items: list[CompanyAuditEntryResponse]
    total: int
    page: int
    per_page: int


# =============================================================================
# Company-facing schemas (TASK-39 item 7, GET /api/v1/company/audit)
# =============================================================================
#
# _VALUE_ONLY_KEYS / _derive_changed_fields() are the whole security
# property of this endpoint: no event's raw VALUES may ever reach a
# company, only the NAMES of the fields that changed.
#
# AuditLog.data is a free-form dict, shaped differently by every
# record_audit() call site in companies/service.py that writes
# target_type="company" (the set this feed filters to). Reading every
# one of those call sites (companies/service.py, grep "target_type=
# \"company\""):
#
#   - company.updated (staff-driven) / company.self_updated
#     (project-driven) write data={"fields": [...]} -- self_updated
#     ALSO writes "changes" (a literal {field: {old, new}} value dict)
#     alongside it. This is the authoritative case: when "fields" is
#     present as a list of strings, USE IT VERBATIM and ignore every
#     other key in `data` -- "changes" is never even inspected.
#
#   - company.created / company.assigned write the actual field
#     values directly under real CompanyProfile column names (name,
#     user_id, total_supply, shares_per_option). No "fields" key
#     exists for these two events, so they fall through to the
#     generic branch below -- but because these particular key NAMES
#     name genuine columns (not value-holder labels like "old_price"),
#     surfacing the KEYS (never the VALUES behind them) is safe and
#     matches "what area changed".
#
#   - company.price_updated writes {"old_price", "new_price",
#     "products_updated"}. None of these three keys is itself a field
#     name -- each exists ONLY to carry a value (the price before, the
#     price after, or a count of affected products). Price visibility
#     is a live, deliberately PARKED product question (owner-owned,
#     see TASK-39 item 7 task header) that this endpoint must not
#     decide in either direction, so every key here is denylisted.
#     This event yields changed_fields=[] -- the `event` string alone
#     ("company.price_updated") already tells the company that price
#     changed, without saying to what value or via which field label.
#
#   - every self-service roadmap_item_*/attachment_*/*_reordered
#     event that also carries target_type="company" (companies/
#     service.py's project-driven write paths) uses assorted
#     id/kind/category/storage_key/mime_type keys with no "fields"
#     key. Those key NAMES are safe, generic labels (never the values
#     behind them -- e.g. the key "title" is surfaced, never the
#     actual title text), so the generic fallback surfaces them
#     unchanged.
#
# WHITELIST, NOT GUESSWORK, for the one shape confirmed dangerous:
# _VALUE_ONLY_KEYS is a denylist of the exact key names confirmed (by
# reading every target_type="company" record_audit() call site above)
# to exist ONLY to carry a value, never to label a field. An unknown
# FUTURE event with an unfamiliar `data` shape still degrades safely:
# worst case it surfaces a harmless extra key name (never a value,
# since .values() is never read below), and any new "old_x"/"new_x"
# -style value-carrying pair should be added here defensively as soon
# as it lands.
_VALUE_ONLY_KEYS = frozenset({"old_price", "new_price", "changes", "products_updated"})


def _derive_changed_fields(data: dict) -> list[str]:  # type: ignore[type-arg]
    """Field-NAME-only view of an AuditLog row's `data` blob.

    Returns dict KEYS ONLY -- this function must never return a dict
    VALUE. See the module comment above for the full per-event
    reasoning; the two rules, in priority order:
      1. data["fields"] wins verbatim when it is a list[str] -- the
         authoritative shape company.updated / company.self_updated
         already write. Any sibling key (e.g. self_updated's
         "changes", a real before/after value dict) is ignored
         entirely in this branch, not merged in.
      2. Otherwise, fall back to data's own top-level keys, minus
         _VALUE_ONLY_KEYS -- keys confirmed to carry values rather
         than name fields (old_price / new_price / changes /
         products_updated) never survive this filter.
    """
    fields = data.get("fields")
    if isinstance(fields, list) and all(isinstance(f, str) for f in fields):
        return fields
    return [key for key in data.keys() if key not in _VALUE_ONLY_KEYS]


def _honest_actor_type(entry: AuditLog) -> str:
    """actor_type, corrected for staff acting through avatar mode.

    THE BUG THIS EXISTS TO PREVENT, and it is the opposite of a leak:
    every company self-service write path (update_own_company, the
    roadmap/attachment/post writers) hardcodes actor_type="user",
    because it names the AUTHENTICATED identity. In avatar mode that
    identity IS the company: staff/avatar_service.py puts the TARGET's
    user_id in the session, so get_current_user() returns the company
    itself and the row is stored as actor_type="user" even though a
    staff member made the change.

    Rendered naively, this feed would then tell the company "You"
    (comp.auditFeed.actor.user) for an edit AIVIS staff made while
    impersonating it -- not merely vague, but affirmatively wrong, in
    the one feature whose entire purpose is telling a project who
    changed what. avatar_guard.py's own header notes the product is
    currently exercised through the admin account, so this is the
    common path rather than a corner case.

    THE SIGNAL, and why it leaks nothing: core/audit.py back-fills
    performed_by with the avatar staff id (and on_behalf_of with the
    impersonated user) on every write made inside an avatar session.
    Its mere PRESENCE therefore means "a staff member did this". We
    read only that a value exists -- never the value itself, which
    stays out of the response exactly as this schema's docstring
    promises.
    """
    if entry.performed_by is not None:
        return "staff"
    return entry.actor_type


class CompanySelfAuditEntryResponse(BaseModel):
    """One row of the CALLER'S OWN company write history.

    DELIBERATELY NARROWER than CompanyAuditEntryResponse (the staff
    schema above) -- built via from_entry(), never via
    model_validate()/from_attributes, so there is no way for a future
    edit to accidentally widen this by re-enabling attribute-based
    validation against AuditLog:

      - NO actor_id / performed_by / on_behalf_of. A company may learn
        THAT staff changed something (actor_type="staff") but never
        WHICH staff member -- those three fields are internal user
        ids, exactly the identity leak CompanyAuditEntryResponse's own
        docstring documents as the reason they exist for STAFF's
        benefit specifically.
      - NO raw `data`. changed_fields (below) is the sole derived view
        of it -- see _derive_changed_fields() for why no value from
        `data` can ever reach the wire through this schema.

    actor_type: the coarse "user" | "staff" | "system" string already
    on AuditLog -- not identity, just which side of the platform wrote
    the row.

    changed_fields: field NAMES only (never values) -- see
    _derive_changed_fields().
    """

    model_config = ConfigDict(from_attributes=False)

    id: UUID
    event: str
    created_at: datetime
    actor_type: str
    changed_fields: list[str]

    @classmethod
    def from_entry(cls, entry: AuditLog) -> "CompanySelfAuditEntryResponse":
        """Build from an AuditLog ORM row -- the only supported path.

        Never model_validate(entry) here: that would read AuditLog's
        attributes structurally and could silently pull in a field
        (actor_id, data, ...) the moment one gets added to this model
        with a matching name. Explicit field-by-field construction is
        the guard against that.
        """
        return cls(
            id=entry.id,
            event=entry.event,
            created_at=entry.created_at,
            actor_type=_honest_actor_type(entry),
            changed_fields=_derive_changed_fields(entry.data or {}),
        )


class CompanySelfAuditFeedResponse(BaseModel):
    """Paginated feed of the caller's own company writes (TASK-39 item 7)."""

    items: list[CompanySelfAuditEntryResponse]
    total: int
    page: int
    per_page: int
