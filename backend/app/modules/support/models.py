# =============================================================================
# AIVIS.ONE Backend -- Support: the local thread pointer (T-65)
# =============================================================================
#
# WHY THIS TABLE EXISTS AT ALL, AND WHY IT IS NOT A CONVENIENCE.
#
# comms has no client-side read surface. Its thread list
# (GET /api/v1/threads) is OPERATOR-scoped -- visible(me) = assignee is
# me OR (section thread AND unassigned) -- so asking it for a user's own
# conversations returns the wrong set twice over: it hides the thread as
# soon as a staff member claims it, and it shows every UNCLAIMED thread
# in the pool, which belongs to other people. There is also no
# "get one thread by id" endpoint anywhere in that API; only the message
# feed takes a thread id.
#
# So this table is the ONLY source for two questions the product must
# answer without asking comms:
#
#   1. "which conversations are mine" -- the list endpoint reads this
#      table and nothing else;
#   2. "is thread T mine" -- checked HERE, before any comms call, on
#      every route that takes a thread id from the wire. comms trusts
#      whatever actor the product sends it, so without this check a
#      guessed thread id would open somebody else's conversation.
#
# ONE ROW PER USER. `user_id` is UNIQUE, mirroring the shape chosen in
# service.py (operator_kind="section", kind="dm", no subject_ref): comms
# itself dedups that combination to one eternal thread per (client,
# section) pair, and the constraint keeps this table honest under the
# same invariant instead of letting a second local row point at a thread
# that already has one.
#
# `comms_thread_id` is UNIQUE too, and for a different reason: it is the
# lookup key of the ownership check. Two rows carrying the same thread id
# would mean two users own one conversation, which is the exact failure
# this table exists to prevent.
#
# THE COMMS SECTION ID IS NEVER STORED HERE. It lives in comms' database
# and does not survive a comms teardown -- a persisted copy would go
# stale silently. It is resolved per process instead (service.py).
# =============================================================================

from uuid import UUID

from sqlalchemy import UUID as SA_UUID
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin


class SupportThread(UUIDMixin, TimestampMixin, Base):
    """This product's pointer to one user's comms support thread."""

    __tablename__ = "support_threads"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The comms thread id. Opaque to us: we never parse it, only carry
    # it back to comms and compare it to what comms last told us.
    comms_thread_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_support_threads_user"),
        UniqueConstraint(
            "comms_thread_id", name="uq_support_threads_comms_id"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SupportThread id={self.id} user={self.user_id} "
            f"thread={self.comms_thread_id}>"
        )
