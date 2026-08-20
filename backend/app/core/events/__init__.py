# =============================================================================
# AIVIS.ONE Backend -- core/events: transactional outbox to comms (T-62)
# =============================================================================
#
# The product side of the aivis <-> comms transport: the OutboxEvent
# model plus emit_event, which inserts into the caller's transaction.
# The wire contract is FROZEN in comms app/transport/events.py; the
# mirrored constants live in service.py.
#
# The relay that ships these rows arrived with T-63 and lives in
# relay.py. It is deliberately NOT re-exported here: its entry point is
# a background loop that main.py imports directly, and a name in this
# namespace would invite product code to reach for it. What is still
# missing is the callers -- no product module emits an event yet.
# =============================================================================

from app.core.events.models import OutboxEvent
from app.core.events.service import emit_event

__all__ = ["OutboxEvent", "emit_event"]
