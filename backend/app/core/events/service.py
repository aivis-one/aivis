# =============================================================================
# AIVIS.ONE Backend -- Transactional Outbox: emit_event (Phase 1 / T-62)
# =============================================================================
#
# The single producer-side entry point:
#
#     await emit_event(session, EVENT_USER_UPSERTED, {...})
#
# inserts an OutboxEvent row into the CALLER'S session -- the same
# transaction as the domain change, so the caller's commit or rollback
# is the event's commit or rollback. No commit here (P-01). A flush IS
# issued, and only for one reason: BIGSERIAL ids are assigned at flush
# time, and the relay publishes in id order, so flushing keeps emission
# order and publication order the same within one transaction.
#
# NOTHING CALLS THIS YET. The emitters are later deliveries; this one
# exists so they have somewhere to write.
#
# CONTRACT MIRROR (comms app/transport/events.py, frozen):
#   - the envelope {event, data} is assembled by the relay; this module
#     stores `data` and stamps the required version field "v";
#   - the comms consumer validates "v" on EVERY event and STRICTLY as
#     an int -- a v2 payload must land in its dead-letter queue rather
#     than be parsed under v1 semantics. A missing "v" is a producer
#     bug, which is why the version is stamped here and never accepted
#     from the caller;
#   - all data values must be JSON scalars or JSON trees -- checked
#     here so a producer bug dies in an aivis test rather than in the
#     comms DLQ, hours later and in another service's logs.
#
# The constants below are a MIRROR, not an import: aivis must not
# import comms code across the service boundary. If they are ever found
# to diverge -- ASK. Do not silently fix either side.
#
# THE SET DESCRIBES THE CONTRACT, NOT OUR INTENTIONS. reminder_cancel
# is here although nothing in aivis emits it, because the set is the
# list of names the wire accepts. Audience keys (contact-book group
# names) are deliberately NOT here: they belong to whoever knows this
# product's audience, and that is the emitter, not this module.
# =============================================================================

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.models import OutboxEvent

logger = structlog.get_logger()

# -- Contract mirror (comms transport/events.py) ------------------------------

SCHEMA_VERSION = 1

EVENT_NOTIFICATION_REQUEST = "notification_request"
EVENT_USER_UPSERTED = "user_upserted"
EVENT_GROUP_CHANGED = "group_changed"
EVENT_REMINDER_CANCEL = "reminder_cancel"
# T-67: one operator declared (or undeclared) as serving one comms
# section. The section travels as a KEY -- its id lives in the comms
# database and does not survive a rebuild there, which is why this
# product deliberately stores it nowhere (see modules/support/service).
EVENT_SECTION_MEMBERSHIP_CHANGED = "section_membership_changed"

KNOWN_EVENT_TYPES = frozenset(
    {
        EVENT_NOTIFICATION_REQUEST,
        EVENT_USER_UPSERTED,
        EVENT_GROUP_CHANGED,
        EVENT_REMINDER_CANCEL,
        EVENT_SECTION_MEMBERSHIP_CHANGED,
    }
)

_SCALAR_TYPES = (str, int, float, bool, type(None))


def _validate_json_tree(value: Any, path: str) -> None:
    """Reject values that cannot travel the wire as JSON.

    Mirrors the comms consumer's scalar discipline early: a UUID or a
    datetime serialized by accident would either crash the relay's
    json.dumps or dead-letter in comms -- both worse, and both later,
    than a ValueError raised in the test that emitted it.
    """
    if isinstance(value, _SCALAR_TYPES):
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _validate_json_tree(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(
                    f"outbox event data: key at {path} must be a "
                    f"non-empty string, got {key!r}"
                )
            _validate_json_tree(item, f"{path}.{key}")
        return
    raise ValueError(
        f"outbox event data: {path} is {type(value).__name__}, "
        f"expected a JSON scalar/list/object (stringify UUIDs and "
        f"datetimes at the emit site)"
    )


async def emit_event(
    session: AsyncSession,
    event_type: str,
    data: dict[str, Any],
) -> OutboxEvent:
    """Insert one outgoing event into the caller's transaction.

    Args:
        session: The caller's read-write session. The event commits and
            rolls back WITH the caller's domain change.
        event_type: One of KNOWN_EVENT_TYPES (the envelope event name).
        data: The event data document per the frozen comms contract,
            WITHOUT "v" -- the version is stamped here. JSON-scalar
            values only (str/int/float/bool/None, lists, objects).

    Returns:
        The pending OutboxEvent row, flushed so its id is assigned.

    Raises:
        ValueError: unknown event type, a caller-supplied "v", or a
            value that is not JSON.
    """
    if event_type not in KNOWN_EVENT_TYPES:
        raise ValueError(
            f"unknown outbox event type {event_type!r}; known: "
            f"{sorted(KNOWN_EVENT_TYPES)}"
        )
    if "v" in data:
        raise ValueError(
            "outbox event data must not carry 'v' -- the schema "
            "version is stamped by emit_event"
        )
    _validate_json_tree(data, path="data")

    event = OutboxEvent(
        event_type=event_type,
        payload={"v": SCHEMA_VERSION, **data},
    )
    session.add(event)
    # Assign the BIGSERIAL id now, so events emitted later in the same
    # session are guaranteed a higher id. This is a flush, not a commit:
    # the row is still inside the caller's transaction and disappears
    # with its rollback.
    await session.flush()

    logger.info(
        "outbox_event_emitted",
        event_id=event.id,
        event_type=event_type,
    )
    return event
