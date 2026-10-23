# =============================================================================
# AIVIS.ONE Backend -- Cabinet account number (document render context)
# =============================================================================
#
# The Cabinet account number printed on the purchase agreement is the first 8
# hex characters of the user's id, uppercased -- the same rule the certificate
# number already uses for a purchase id. Eight characters can in principle be
# shared by two users, so the number is checked for uniqueness at render time
# against the users created EARLIER than this one (ties broken by id): when an
# earlier user shares the first 8 characters, the number is lengthened to the
# shortest prefix that tells them apart.
#
# STABLE FOR LIFE. A user is compared only with earlier users, and the set of
# earlier users never grows, so a user's number never changes once it has
# been printed: the earlier account of a colliding pair keeps its 8
# characters forever, and only the newcomer is lengthened.
#
# The module is read-only: it never writes and never commits.
# =============================================================================

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User

ACCOUNT_NUMBER_MIN_LENGTH = 8


def account_number_for(user_id: UUID, earlier_ids: Iterable[UUID]) -> str:
    """Return the shortest uppercased hex prefix of user_id (at least 8
    characters) that no id in earlier_ids shares.

    earlier_ids are the ids of the users created before this one. Pure:
    nothing here touches the database. With no collision the result is the
    first 8 hex characters of the id.
    """
    own = user_id.hex
    others = [o.hex for o in earlier_ids if o != user_id]
    for length in range(ACCOUNT_NUMBER_MIN_LENGTH, len(own) + 1):
        if all(o[:length] != own[:length] for o in others):
            return own[:length].upper()
    return own.upper()


async def resolve_account_number(user_id: UUID, session: AsyncSession) -> str:
    """The user's account number, unique among all users and never changed
    by a later user.

    One SELECT for the users created earlier (or at the same instant with a
    smaller id) whose id starts with the same 8 characters; the textual form
    of a UUID starts with its first 8 hex characters, so a LIKE on that
    prefix finds every candidate.
    """
    own_created = await session.scalar(
        select(User.created_at).where(User.id == user_id)
    )
    if own_created is None:
        return account_number_for(user_id, [])
    prefix = user_id.hex[:ACCOUNT_NUMBER_MIN_LENGTH]
    stmt = select(User.id).where(
        cast(User.id, String).like(f"{prefix}%"),
        User.id != user_id,
        or_(
            User.created_at < own_created,
            and_(User.created_at == own_created, User.id < user_id),
        ),
    )
    earlier = list((await session.execute(stmt)).scalars().all())
    return account_number_for(user_id, earlier)
