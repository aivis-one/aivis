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
    """

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
