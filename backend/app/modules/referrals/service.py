# =============================================================================
# CBSHOME Backend -- Referral Service (Sprint 7.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   resolve_referral_link()  -- code -> validated ReferralLink or None (Task 1 C)
#   resolve_referral_code()  -- code -> agent_id or None (thin wrapper)
#   create_link()            -- generate unique referral link for agent
#   record_click()           -- atomic click_count increment by code (Task 1 B)
#   get_agent_chain()        -- walk User.referred_by up to max_depth
#   create_attribution()     -- record purchase-to-link mapping
#   get_my_links()           -- paginated list of agent's links
#   get_my_stats()           -- agent referral stats
#
# RESOLVE SEMANTICS:
#   Invalid/expired/deactivated codes return None (never raise).
#   Caller falls back to platform_id on None. All validation lives in
#   resolve_referral_link(); resolve_referral_code() only narrows the
#   result to agent_id for callers that don't need the link itself.
#
# AGENT CHAIN:
#   Walks User.referred_by upward. Stops when:
#     - role == platform (root reached)
#     - max_depth exhausted (driven by len(agent_levels))
#     - user is_active == False (chain broken)
#     - role != agent (non-agent in chain skipped, chain broken)
#     - cycle detected (seen set prevents infinite loops)
#
# N+1 OPTIMIZATION:
#   First query loads investor. Each subsequent iteration reuses the
#   previous referrer object, loading only the next referrer.
#   Total: max_depth + 1 queries instead of 2 * max_depth.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

import secrets
from uuid import UUID

import structlog
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.modules.referrals.models import ReferralAttribution, ReferralLink
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Code resolution
# ---------------------------------------------------------------------------


async def resolve_referral_link(
    code: str,
    session: AsyncSession,
) -> ReferralLink | None:
    """Resolve a referral code to a fully validated ReferralLink (Task 1 C).

    Single source of resolve validation. Returns None if code not
    found, link deactivated, agent inactive, or agent role changed.
    Callers fall back to platform attribution on None.
    """
    stmt = (
        select(ReferralLink)
        .where(ReferralLink.code == code)
    )
    result = await session.execute(stmt)
    link = result.scalar_one_or_none()

    if link is None:
        logger.debug("referral_code_not_found", code=code)
        return None

    # Check link is active.
    if not link.is_active:
        logger.debug("referral_link_deactivated", code=code)
        return None

    # Verify agent is still valid.
    agent_stmt = select(User).where(User.id == link.agent_id)
    agent_result = await session.execute(agent_stmt)
    agent = agent_result.scalar_one_or_none()

    if agent is None or not agent.is_active or agent.role != UserRole.AGENT:
        logger.debug(
            "referral_code_agent_invalid",
            code=code,
            agent_id=str(link.agent_id),
        )
        return None

    return link


async def resolve_referral_code(
    code: str,
    session: AsyncSession,
) -> UUID | None:
    """Resolve a referral code to the owning agent's UUID.

    Thin wrapper over resolve_referral_link() kept for callers that
    only need the agent. Same None semantics: code not found, link
    deactivated, agent inactive, or agent role changed -> None.
    """
    link = await resolve_referral_link(code, session)
    return link.agent_id if link is not None else None


# ---------------------------------------------------------------------------
# Referral link validation
# ---------------------------------------------------------------------------


async def validate_referral_link_id(
    referral_link_id: UUID,
    session: AsyncSession,
) -> UUID | None:
    """Validate that a referral_link_id exists and is active.

    Returns the validated UUID if valid, None otherwise.
    Prevents analytics pollution from fabricated UUIDs.
    """
    stmt = select(ReferralLink.id).where(
        ReferralLink.id == referral_link_id,
        ReferralLink.is_active == True,  # noqa: E712
    )
    result = await session.execute(stmt)
    link_id = result.scalar_one_or_none()
    return link_id


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------


async def create_link(
    agent: User,
    session: AsyncSession,
) -> ReferralLink:
    """Create a new referral link with unique code.

    Code: 8 chars alphanumeric via secrets.token_urlsafe(6).
    Retries once on collision (begin_nested + IntegrityError).
    """
    for _attempt in range(3):
        code = secrets.token_urlsafe(6)
        link = ReferralLink(agent_id=agent.id, code=code)

        try:
            async with session.begin_nested():
                session.add(link)
                await session.flush()

            await session.refresh(link)

            await record_audit(
                session=session,
                event="referral.link_created",
                actor_id=agent.id,
                actor_type="agent",
                target_type="referral_link",
                target_id=link.id,
                data={"code": code},
            )

            logger.info(
                "referral_link_created",
                agent_id=str(agent.id),
                link_id=str(link.id),
                code=code,
            )

            return link
        except IntegrityError:
            # Code collision, retry with new code.
            logger.debug("referral_code_collision", code=code)
            continue

    # Extremely unlikely: 3 collisions in a row.
    raise RuntimeError("Failed to generate unique referral code after 3 attempts")


async def get_my_links(
    agent_id: UUID,
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[ReferralLink], int]:
    """Return paginated list of agent's referral links."""
    count_stmt = (
        select(func.count())
        .select_from(ReferralLink)
        .where(ReferralLink.agent_id == agent_id)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    offset = (page - 1) * per_page
    stmt = (
        select(ReferralLink)
        .where(ReferralLink.agent_id == agent_id)
        .order_by(ReferralLink.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    links = list(result.scalars().all())

    return links, total


# ---------------------------------------------------------------------------
# Click tracking (Task 1 Block B)
# ---------------------------------------------------------------------------


async def record_click(
    code: str,
    session: AsyncSession,
) -> bool:
    """Atomically increment click_count for the link matching `code`.

    Single UPDATE expression -- the increment happens DB-side, so
    concurrent clicks never lose counts (no load-modify-save race).
    update() is a SQLAlchemy ORM-enabled expression; the ORM-only rule
    is intact.

    Counts regardless of is_active: the click happened even if the
    agent later deactivated the link (boss-locked decision). Raw
    counter, no deduplication -- per-IP rate limiting at the router
    is anti-abuse, not dedup.

    Returns True if a link matched (counter incremented), False for an
    unknown code. The public endpoint replies 204 either way; the
    return value exists for logging and tests.

    Does NOT commit -- caller manages the transaction (P-01).
    """
    stmt = (
        update(ReferralLink)
        .where(ReferralLink.code == code)
        .values(click_count=ReferralLink.click_count + 1)
    )
    result = await session.execute(stmt)
    matched = result.rowcount > 0

    if matched:
        logger.debug("referral_click_recorded", code=code)
    else:
        # Unknown code: no increment, still 204 at the edge (do not
        # confirm code existence to unauthenticated callers).
        logger.debug("referral_click_unknown_code", code=code)

    return matched


# ---------------------------------------------------------------------------
# Agent chain
# ---------------------------------------------------------------------------


async def get_agent_chain(
    investor_id: UUID,
    session: AsyncSession,
    *,
    max_depth: int = 3,
) -> list[UUID]:
    """Walk User.referred_by chain upward, collecting agent UUIDs.

    Returns list of 0..max_depth agent UUIDs: [L1, L2, L3, ...].
    Stops when Platform is reached, max_depth exhausted, cycle detected,
    or chain broken (non-agent role or inactive user).

    N+1 optimized: reuses previous referrer object as current user
    for the next iteration. Total queries: max_depth + 1 (worst case).
    """
    chain: list[UUID] = []
    seen: set[UUID] = set()

    # Load investor to get first referred_by.
    stmt = select(User).where(User.id == investor_id)
    result = await session.execute(stmt)
    current = result.scalar_one_or_none()

    if current is None:
        return chain

    for _ in range(max_depth):
        referrer_id = current.referred_by

        # Cycle detection.
        if referrer_id in seen:
            logger.warning(
                "referral_chain_cycle_detected",
                investor_id=str(investor_id),
                cycle_at=str(referrer_id),
            )
            break

        # Load referrer.
        ref_stmt = select(User).where(User.id == referrer_id)
        ref_result = await session.execute(ref_stmt)
        referrer = ref_result.scalar_one_or_none()

        if referrer is None:
            break

        # Stop at Platform (root).
        if referrer.role == UserRole.PLATFORM:
            break

        # Only active agents earn commissions.
        if referrer.role != UserRole.AGENT or not referrer.is_active:
            break

        seen.add(referrer.id)
        chain.append(referrer.id)
        current = referrer  # Reuse for next iteration (N+1 fix).

    return chain


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


async def create_attribution(
    purchase_id: UUID,
    referral_link_id: UUID | None,
    session: AsyncSession,
) -> ReferralAttribution | None:
    """Record purchase-to-referral-link attribution.

    Created for every purchase. referral_link_id=None for organic.
    purchase_id is unique -- duplicate attributions are silently skipped
    via SAVEPOINT (begin_nested) to preserve outer transaction (P-01).
    """
    attribution = ReferralAttribution(
        purchase_id=purchase_id,
        referral_link_id=referral_link_id,
    )

    try:
        async with session.begin_nested():
            session.add(attribution)
            await session.flush()
    except IntegrityError:
        # Duplicate attribution (retry scenario) -- skip silently.
        # Savepoint rolled back, outer transaction still valid.
        logger.debug(
            "referral_attribution_duplicate",
            purchase_id=str(purchase_id),
        )
        return None

    return attribution


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def get_my_stats(
    agent_id: UUID,
    session: AsyncSession,
) -> dict:
    """Return referral stats for an agent.

    Returns dict with: total_links, total_purchases, total_commission_cents.
    """
    # Count links.
    links_stmt = (
        select(func.count())
        .select_from(ReferralLink)
        .where(ReferralLink.agent_id == agent_id)
    )
    total_links = (await session.execute(links_stmt)).scalar_one()

    # Count purchases via agent's links.
    link_ids_stmt = select(ReferralLink.id).where(
        ReferralLink.agent_id == agent_id
    )
    purchases_stmt = (
        select(func.count())
        .select_from(ReferralAttribution)
        .where(ReferralAttribution.referral_link_id.in_(link_ids_stmt))
    )
    total_purchases = (await session.execute(purchases_stmt)).scalar_one()

    # Sum commissions from passive ledger.
    from app.modules.ledgers.models import PassiveLedger

    commission_stmt = (
        select(func.coalesce(func.sum(PassiveLedger.amount_cents), 0))
        .where(
            PassiveLedger.user_id == agent_id,
            PassiveLedger.reason.startswith("commission:"),
        )
    )
    total_commission_cents = (await session.execute(commission_stmt)).scalar_one()

    return {
        "total_links": total_links,
        "total_purchases": total_purchases,
        "total_commission_cents": total_commission_cents,
    }
