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
#   get_my_links()           -- paginated links + per-link counters (Task 1 D)
#   get_my_stats()           -- agent referral stats (incl. clicks/regs)
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
from app.modules.purchases.constants import PurchaseStatus
from app.modules.purchases.models import Purchase
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
) -> tuple[list[tuple[ReferralLink, int, int]], int]:
    """Return paginated agent links enriched with per-link counters.

    Returns ([(link, registration_count, purchase_count), ...], total).
    click_count rides on the ReferralLink row itself.

    Anti-N+1 (Task 1 Block D, same batching as commissions/service.py
    Round-4 fix): exactly two aggregate queries per page, both scoped
    to the current page's link_ids -- one COUNT GROUP BY over users
    (registrations) and one over referral_attributions (purchases).
    Never a query inside the links loop.
    """
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

    link_ids = [link.id for link in links]

    registrations_map: dict[UUID, int] = {}
    purchases_map: dict[UUID, int] = {}

    if link_ids:
        # Batch 1: registrations per link (users.referred_by_link_id,
        # indexed by migration 0035).
        reg_stmt = (
            select(User.referred_by_link_id, func.count())
            .where(User.referred_by_link_id.in_(link_ids))
            .group_by(User.referred_by_link_id)
        )
        reg_rows = (await session.execute(reg_stmt)).all()
        registrations_map = {row[0]: row[1] for row in reg_rows}

        # Batch 2: purchases per link (referral_attributions).
        purch_stmt = (
            select(ReferralAttribution.referral_link_id, func.count())
            .where(ReferralAttribution.referral_link_id.in_(link_ids))
            .group_by(ReferralAttribution.referral_link_id)
        )
        purch_rows = (await session.execute(purch_stmt)).all()
        purchases_map = {row[0]: row[1] for row in purch_rows}

    enriched = [
        (
            link,
            registrations_map.get(link.id, 0),
            purchases_map.get(link.id, 0),
        )
        for link in links
    ]

    return enriched, total


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

    Returns dict with: total_links, total_clicks, total_registrations,
    total_purchases, total_commission_cents.
    """
    # Count links.
    links_stmt = (
        select(func.count())
        .select_from(ReferralLink)
        .where(ReferralLink.agent_id == agent_id)
    )
    total_links = (await session.execute(links_stmt)).scalar_one()

    # Sum of raw clicks across all the agent's links (Task 1 Block D).
    clicks_stmt = select(
        func.coalesce(func.sum(ReferralLink.click_count), 0)
    ).where(ReferralLink.agent_id == agent_id)
    total_clicks = (await session.execute(clicks_stmt)).scalar_one()

    # Subquery of the agent's link ids -- shared by the registrations
    # and purchases aggregates below.
    link_ids_stmt = select(ReferralLink.id).where(
        ReferralLink.agent_id == agent_id
    )

    # Registrations attributed to any of the agent's links (Task 1 D,
    # mirrors the total_purchases subquery shape). Pre-0035 users have
    # referred_by_link_id = NULL and are correctly excluded.
    registrations_stmt = (
        select(func.count())
        .select_from(User)
        .where(User.referred_by_link_id.in_(link_ids_stmt))
    )
    total_registrations = (
        await session.execute(registrations_stmt)
    ).scalar_one()

    # Count purchases via agent's links.
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
        "total_clicks": total_clicks,
        "total_registrations": total_registrations,
        "total_purchases": total_purchases,
        "total_commission_cents": total_commission_cents,
    }


# ---------------------------------------------------------------------------
# Downline (Task 2b Block A)
# ---------------------------------------------------------------------------


async def _active_agents_under(
    parent_ids: list[UUID],
    seen: set[UUID],
    session: AsyncSession,
) -> list[User]:
    """One batched hop down the agent subtree.

    Returns ACTIVE agents whose referred_by is in parent_ids, excluding
    ids already seen (dedup guard against a malformed referred_by graph;
    depth-3 bounds the runtime anyway). Single IN query -- never a
    query per node.
    """
    if not parent_ids:
        return []
    stmt = select(User).where(
        User.referred_by.in_(parent_ids),
        User.role == UserRole.AGENT,
        User.is_active.is_(True),
        User.id.notin_(seen) if seen else True,  # noqa: E712
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_downline(
    agent_id: UUID,
    session: AsyncSession,
) -> tuple[
    list[tuple[User, int, int]],
    list[tuple[User, int, int, int, int]],
]:
    """Agent's downline: investors and sub-agents by level (Task 2b).

    LEVEL SEMANTICS -- commission-mirror (boss decision #2): the
    investor's level equals the number of agent hops from the investor
    up to the requesting agent X -- the same definition get_agent_chain
    uses to pay commissions. Concretely:

      agents_d1 = active agents with referred_by == X      (sub level 1)
      agents_d2 = active agents under agents_d1            (sub level 2)
      agents_d3 = active agents under agents_d2            (sub level 3)
      investors under X         -> L1
      investors under agents_d1 -> L2
      investors under agents_d2 -> L3
      investors under agents_d3 would be L4 -> EXCLUDED (outside the
      3-level commission area).

    Traversal goes through ACTIVE agents only (decision #6) -- an
    inactive sub-agent breaks the chain exactly like get_agent_chain
    stops on `not is_active`, so the screen never shows investors X is
    not commissioned on. INVESTOR leaves are shown regardless of their
    own is_active (decision #9): their historical volume already paid
    X's commission, hiding them would understate the picture.

    ANTI-N+1: the whole walk is 7 batched queries -- 3 agent hops, one
    combined investor query, and 3 aggregate GROUP BYs. No query ever
    runs inside a per-node loop.

    Returns raw rows; response assembly and PII masking happen in the
    router (Pattern 6):
      investors:  [(User, level, purchase_volume_cents)]
      sub_agents: [(User, level, recruited_investor_count,
                    direct_volume_cents, own_purchase_volume_cents)]
    """
    # -- Agent subtree, 3 hops, batched, deduped. --
    seen: set[UUID] = {agent_id}
    agents_d1 = await _active_agents_under([agent_id], seen, session)
    seen.update(a.id for a in agents_d1)
    agents_d2 = await _active_agents_under(
        [a.id for a in agents_d1], seen, session
    )
    seen.update(a.id for a in agents_d2)
    agents_d3 = await _active_agents_under(
        [a.id for a in agents_d2], seen, session
    )
    seen.update(a.id for a in agents_d3)

    sub_agent_levels: dict[UUID, int] = {}
    for level, bucket in ((1, agents_d1), (2, agents_d2), (3, agents_d3)):
        for a in bucket:
            sub_agent_levels[a.id] = level
    all_sub_agents = agents_d1 + agents_d2 + agents_d3

    # -- Investors: one combined query; level = parent agent depth + 1.
    # Parents at depth 3 (agents_d3) are intentionally absent -- their
    # investors would be L4. No is_active filter (decision #9).
    parent_level: dict[UUID, int] = {agent_id: 0}
    for a in agents_d1:
        parent_level[a.id] = 1
    for a in agents_d2:
        parent_level[a.id] = 2

    inv_stmt = select(User).where(
        User.referred_by.in_(list(parent_level.keys())),
        User.role == UserRole.INVESTOR,
    )
    investors = list((await session.execute(inv_stmt)).scalars().all())

    # -- Aggregate 1: ACTIVE purchase volume per buyer, ONE query for
    # investors AND sub-agents' own purchases together (decision #8:
    # agents are buyers too -- their purchases feed X's commission).
    buyer_ids = [u.id for u in investors] + [a.id for a in all_sub_agents]
    volumes: dict[UUID, int] = {}
    if buyer_ids:
        vol_stmt = (
            select(
                Purchase.investor_id,
                func.coalesce(func.sum(Purchase.paid_cents), 0),
            )
            .where(
                Purchase.investor_id.in_(buyer_ids),
                Purchase.status == PurchaseStatus.ACTIVE,
            )
            .group_by(Purchase.investor_id)
        )
        volumes = {
            row[0]: int(row[1])
            for row in (await session.execute(vol_stmt)).all()
        }

    sub_agent_ids = [a.id for a in all_sub_agents]
    recruited: dict[UUID, int] = {}
    direct_volume: dict[UUID, int] = {}
    if sub_agent_ids:
        # -- Aggregate 2: direct recruited INVESTOR count per sub-agent.
        # No is_active filter -- count mirrors investor visibility (#9).
        cnt_stmt = (
            select(User.referred_by, func.count())
            .where(
                User.referred_by.in_(sub_agent_ids),
                User.role == UserRole.INVESTOR,
            )
            .group_by(User.referred_by)
        )
        recruited = {
            row[0]: int(row[1])
            for row in (await session.execute(cnt_stmt)).all()
        }

        # -- Aggregate 3: direct volume per sub-agent = ACTIVE purchases
        # of their direct INVESTORS (role filter is explicit so agent
        # buyers never leak in here -- they are covered by decision #8's
        # own_purchase_volume_cents, never double-counted).
        dvol_stmt = (
            select(
                User.referred_by,
                func.coalesce(func.sum(Purchase.paid_cents), 0),
            )
            .select_from(Purchase)
            .join(User, Purchase.investor_id == User.id)
            .where(
                User.referred_by.in_(sub_agent_ids),
                User.role == UserRole.INVESTOR,
                Purchase.status == PurchaseStatus.ACTIVE,
            )
            .group_by(User.referred_by)
        )
        direct_volume = {
            row[0]: int(row[1])
            for row in (await session.execute(dvol_stmt)).all()
        }

    # -- Assemble raw rows, stable order: level ASC, registered ASC. --
    investors_out = sorted(
        (
            (u, parent_level[u.referred_by] + 1, volumes.get(u.id, 0))
            for u in investors
        ),
        key=lambda t: (t[1], t[0].created_at),
    )
    sub_agents_out = sorted(
        (
            (
                a,
                sub_agent_levels[a.id],
                recruited.get(a.id, 0),
                direct_volume.get(a.id, 0),
                volumes.get(a.id, 0),
            )
            for a in all_sub_agents
        ),
        key=lambda t: (t[1], t[0].created_at),
    )

    return investors_out, sub_agents_out
