# =============================================================================
# AIVIS.ONE Backend -- core/events: transactional outbox to comms (T-62)
# =============================================================================
#
# The product side of the aivis <-> comms transport: the OutboxEvent
# model plus emit_event, which inserts into the caller's transaction.
# The wire contract is FROZEN in comms app/transport/events.py; the
# mirrored constants live in service.py.
#
# The relay that ships these rows, and the sync helpers that build
# them, are later deliveries -- nothing is re-exported for them here
# because nothing of them exists yet.
# =============================================================================

from app.core.events.models import OutboxEvent
from app.core.events.service import emit_event

__all__ = ["OutboxEvent", "emit_event"]
