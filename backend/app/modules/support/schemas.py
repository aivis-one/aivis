# =============================================================================
# AIVIS.ONE Backend -- Support: request bodies (T-65)
# =============================================================================
#
# Only REQUEST shapes live here. Responses are comms' own payloads --
# forwarded as they are, or with every message rendered for its reader in
# the two feeds (translation.py, H39): re-declaring them would be a second
# copy of a contract this product does not own, guaranteed to drift from
# it.
#
# EVERY MODEL FORBIDS EXTRA FIELDS, and that is the point rather than
# tidiness. comms trusts whatever actor a caller sends it -- client,
# sender, participant, operator, is_supervisor -- so those names must
# never be readable from a request. Silently ignoring them would be safe
# but mute; extra="forbid" turns an attempt into a 422 that says which
# field was refused, and makes "no handler reads them" checkable rather
# than promised.
# =============================================================================

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Longest message this channel accepts. comms DOES have a limit of its
# own -- its notifications.body column is String(5000), and its event
# contract rejects a longer body before it ever reaches the column --
# so this 4000 sits under that ceiling rather than above it. That is
# luck, not knowledge: the number was chosen because a support message
# is typed by a person into a box and an unbounded body is an unbounded
# row. Whoever raises it has to check the other side's 5000 first; the
# previous version of this comment said comms had no limit, which would
# have made that check look unnecessary.
MAX_MESSAGE_LENGTH = 4000


class EmptyBodyIn(BaseModel):
    """A body with no fields at all, for the two verbs that need none.

    Opening a request and marking it read are fully determined by the
    session: there is nothing to say beyond the verb itself. The model
    exists ONLY so that a body carrying an actor field is refused
    instead of ignored -- a handler with no body model at all would
    accept and discard it without a word.
    """

    model_config = ConfigDict(extra="forbid")


# The client's Idempotency-Key for one message (H23 P-112): generated when
# the person presses send, reused on every retry of that message. Bounded
# so the namespaced key the service forwards stays within comms' 200 --
# the sum is at support/service.py's _MESSAGE_KEY_PREFIX. A closed
# alphabet (a UUID fits it) keeps the header free of separators and
# whitespace that could make two keys look alike.
SUPPORT_CLIENT_KEY_MAX_LEN = 100
SUPPORT_CLIENT_KEY_PATTERN = r"^[A-Za-z0-9_-]+$"


class SendMessageIn(BaseModel):
    """One message into the caller's own conversation.

    `body` is the whole request. There is no thread id: the caller's
    conversation is ONE for them however many tickets it holds, and where
    the message goes is decided from the local pointers, never from the
    wire (service.send_dialog_message).

    T-66: the operator side reuses this model for its reply. Same field,
    same ceiling, and a second model would be a second place to change
    the limit in.
    """

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


# The codes of the support form's topics -- models.TOPICS is THE table;
# this literal must name exactly its keys (tests/test_support_tickets.py
# compares the two), because a schema cannot read a dict at type level.
TopicCode = Literal["payments", "withdrawal", "kyc", "purchases", "technical", "other"]
# The categories an operator filters by -- models.CATEGORIES, compared the
# same way.
CategoryCode = Literal[
    "payments", "withdrawals", "verification", "purchases", "tech", "other",
]
# Every status of a ticket (the list's filter) and the four an OPEN ticket
# is moved to (models.STATUSES / CLOSING_STATUSES). Back to `open` is its
# own verb, reopen: it has its own rules (the spam window).
TicketStatusCode = Literal["open", "resolved", "rejected", "duplicate", "spam"]
ClosingStatusCode = Literal["resolved", "rejected", "duplicate", "spam"]


class TicketIn(BaseModel):
    """One appeal through the support form (H40 item 1): a topic of the
    six and the text. The thread, the category and the status are ours to
    decide; the person names none of them."""

    model_config = ConfigDict(extra="forbid")

    topic: TopicCode
    body: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class SetTicketStatusIn(BaseModel):
    """An operator closing an OPEN ticket one of four ways (H40 item 4).

    `open` is not here: back to work is its own route (reopen), with its
    own rule for spam. comms' `closed` is not a status of ours at all --
    nothing moves a ticket's thread there (comms would tell the person).
    """

    model_config = ConfigDict(extra="forbid")

    status: ClosingStatusCode


class AssignIn(BaseModel):
    """Hand a ticket to another operator (H40 item 5). `assignee` is the
    TARGET of the handover, not the actor: the actor is the session's
    operator, always."""

    model_config = ConfigDict(extra="forbid")

    assignee: UUID
