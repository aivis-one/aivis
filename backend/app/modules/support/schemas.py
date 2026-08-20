# =============================================================================
# AIVIS.ONE Backend -- Support: request bodies (T-65)
# =============================================================================
#
# Only REQUEST shapes live here. Responses are comms' own payloads,
# forwarded as they are: re-declaring them would be a second copy of a
# contract this product does not own, guaranteed to drift from it.
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

from pydantic import BaseModel, ConfigDict, Field

# Longest message this channel accepts. Not a comms limit -- its body
# column is unbounded -- but a support message is typed by a person into
# a box, and an unbounded body is an unbounded row.
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


class SendMessageIn(BaseModel):
    """One message into the caller's own conversation.

    `body` is the whole request. There is no thread id: the caller has
    exactly one conversation and it is resolved from the local pointer,
    never from the wire.

    T-66: the operator side reuses this model for its reply. Same field,
    same ceiling, and a second model would be a second place to change
    the limit in.
    """

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class SetStatusIn(BaseModel):
    """An operator moving a conversation along (T-66).

    `open` IS NOT AN OPTION, and its absence is the point. comms allows
    no manual reopen whatsoever -- `closed` has an empty set of allowed
    manual transitions, and a thread comes back to life only when the
    CLIENT writes into it. Offering `open` here would be a field that
    always yields a 422 from comms: an endpoint documenting a state
    change that cannot be made.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["resolved", "closed"]
