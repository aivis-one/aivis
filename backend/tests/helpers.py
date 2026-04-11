# =============================================================================
# CBSHOME Backend -- Shared Test Helpers
# =============================================================================
#
# Utility functions used across multiple test files.
# Not a conftest (no fixtures) -- just plain functions.
#
# EMAIL AUTH:
#   register_user() and login_user() call the email auth endpoints.
#
# TELEGRAM AUTH (Sprint 1.2):
#   build_init_data() creates a valid signed Telegram initData string.
#   BOT_TOKEN is read from settings to match the runtime token.
#   _init_data_counter ensures unique query_id on every call to avoid
#   anti-replay rejection when multiple calls happen in the same second.
#
# STAFF (Sprint 3.1):
#   create_staff_user() registers a user, promotes to staff role,
#   creates StaffProfile with default permissions. Returns (user_data, token).
#   create_admin_user() same but with all permissions True (admin).
#
# CLEANUP:
#   cleanup_test_users()          -- by email prefix
#   cleanup_telegram_test_users() -- by telegram_id list
#
# Sprint 4.1:
#   _cleanup_user_related_data() extended with company table cleanup
#   (CompanyRoadmapItem, CompanyPriceHistory, CompanyProfile).
#
# Sprint 5.1:
#   _cleanup_user_related_data() extended with ledger table cleanup
#   (ActiveLedger, PassiveLedger).
#
# Sprint 5.2:
#   _cleanup_user_related_data() extended with payment table cleanup
#   (Payment, CryptoAddress). Order: ledger entries first (FK to payments),
#   then payments, then crypto_addresses.
#
# Sprint 6.1:
#   _cleanup_user_related_data() extended with Purchase cleanup.
#   Order: purchases before ledger entries (no FK dependency, but
#   logically purchases reference users/products/companies).
#
# Sprint 6.2:
#   _cleanup_user_related_data() extended with InstallmentPlan/Tranche cleanup.
#   Order: tranches first (FK to plans + purchases), then plans.
#
# Sprint 6.3:
#   _cleanup_user_related_data() extended with Withdrawal cleanup.
#
# Sprint 6.4:
#   _cleanup_user_related_data() extended with Transaction cleanup.
#
# Sprint 7.1:
#   _cleanup_user_related_data() extended with AgentApplication cleanup.
#
# Sprint 7.3:
#   _cleanup_user_related_data() extended with LeaderboardSnapshot + VolumePayout cleanup.
#
# Sprint 8.1:
#   _cleanup_user_related_data() extended with NotificationDelivery + Notification cleanup.
#   Deliveries first (FK to notifications.id), then notifications.
# =============================================================================

import hashlib
import hmac
import itertools
import json
import time
from urllib.parse import urlencode
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.config import settings
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS, VALID_PERMISSION_KEYS
from app.modules.staff.models import AvatarSession, StaffProfile
from app.modules.users.models import User, UserRole

# Read from settings -- must match the token used by the router
# for HMAC validation.
BOT_TOKEN = settings.telegram_bot_token

# Module-level counter: unique query_id per build_init_data() call.
_init_data_counter = itertools.count(1)


async def _clear_email_rate_limit() -> None:
    """Clear email auth rate limit key for test environment.

    All test traffic comes from 127.0.0.1 via ASGITransport.
    Without clearing, rate limit counter accumulates across calls
    within a single test and blocks auth after 5 requests.
    """
    from app.core.redis import get_redis
    try:
        redis = get_redis()
        await redis.delete("email_auth:127.0.0.1")
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def auth_headers(token: str) -> dict[str, str]:
    """Build Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


async def register_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpass123",
) -> dict:
    """Register a user via email and return the full response body."""
    await _clear_email_rate_limit()
    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    return resp.json()


async def login_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpass123",
) -> dict:
    """Login a user via email and return the full response body."""
    await _clear_email_rate_limit()
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Telegram auth helpers (Sprint 1.2)
# ---------------------------------------------------------------------------


def build_init_data(
    user_data: dict,
    bot_token: str = BOT_TOKEN,
    auth_date: int | None = None,
) -> str:
    """Build a valid Telegram initData query string with correct HMAC.

    Includes a unique query_id on every call (via _init_data_counter) so
    that multiple calls for the same telegram_id within the same second
    produce different hashes and don't trigger anti-replay protection.
    """
    if auth_date is None:
        auth_date = int(time.time())

    counter = next(_init_data_counter)
    query_id = f"test-query-{auth_date}-{counter}"

    data_pairs = {
        "user": json.dumps(user_data, separators=(",", ":")),
        "auth_date": str(auth_date),
        "query_id": query_id,
    }

    # HMAC-SHA256 as per Telegram specification.
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data_pairs.items())
    )
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    data_pairs["hash"] = calculated_hash
    return urlencode(data_pairs)


# ---------------------------------------------------------------------------
# Staff helpers (Sprint 3.1)
# ---------------------------------------------------------------------------


async def create_staff_user(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str = "staff@example.com",
    password: str = "testpass123",
) -> tuple[dict, str]:
    """Register a user and promote to staff with default permissions.

    Returns (user_data_dict, session_token).
    """
    data = await register_user(client, email=email, password=password)
    user_id = UUID(data["user"]["id"])

    # Promote to staff directly in DB.
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.STAFF

    # Create StaffProfile with default permissions.
    profile = StaffProfile(
        user_id=user_id,
        permissions=dict(DEFAULT_STAFF_PERMISSIONS),
        is_active=True,
    )
    db_session.add(profile)
    await db_session.commit()

    # Re-login to get a session with updated role.
    login_data = await login_user(client, email=email, password=password)
    return login_data, login_data["session_token"]


async def create_admin_user(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str = "admin@example.com",
    password: str = "testpass123",
) -> tuple[dict, str]:
    """Register a user, promote to staff, create StaffProfile with full permissions.

    Returns (user_data_dict, session_token).
    Admin = all permission keys set to True.
    """
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    # Promote to staff directly in DB.
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.STAFF

    # Create StaffProfile with all permissions True (admin).
    all_true = {key: True for key in VALID_PERMISSION_KEYS}
    profile = StaffProfile(
        user_id=user_id,
        permissions=all_true,
        is_active=True,
    )
    db_session.add(profile)
    await db_session.commit()

    # Re-login to get a session with updated role.
    login_data = await login_user(client, email=email, password=password)
    return login_data, login_data["session_token"]


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def cleanup_test_users(
    session: AsyncSession,
    email_prefix: str,
) -> None:
    """Delete test users whose email starts with the given prefix.

    Also cleans up related audit_log entries (actor_id or target_id).
    """
    stmt = select(User.id).where(
        User.credentials["email"]["email"].as_string().startswith(email_prefix)
    )
    result = await session.execute(stmt)
    user_ids = [row[0] for row in result.all()]

    if not user_ids:
        return

    # Clean up tables that reference users.
    await _cleanup_user_related_data(session, user_ids)

    await session.execute(
        delete(AuditLog).where(
            AuditLog.actor_id.in_(user_ids) | AuditLog.target_id.in_(user_ids)
        )
    )

    await session.execute(
        delete(User).where(User.id.in_(user_ids))
    )

    await session.commit()


async def cleanup_telegram_test_users(
    session: AsyncSession,
    telegram_ids: list[int],
) -> None:
    """Delete test users by telegram_id in credentials JSONB.

    Uses single query with or_() instead of N+1 selects.
    Also cleans up related audit_log entries.
    """
    if not telegram_ids:
        return

    # Single query: find all user IDs matching any of the telegram_ids.
    conditions = [
        User.credentials["telegram"]["id"].as_integer() == tg_id
        for tg_id in telegram_ids
    ]
    stmt = select(User.id).where(or_(*conditions))
    result = await session.execute(stmt)
    user_ids = [row[0] for row in result.all()]

    if not user_ids:
        return

    # Clean up tables that reference users.
    await _cleanup_user_related_data(session, user_ids)

    await session.execute(
        delete(AuditLog).where(
            AuditLog.actor_id.in_(user_ids) | AuditLog.target_id.in_(user_ids)
        )
    )

    await session.execute(
        delete(User).where(User.id.in_(user_ids))
    )

    await session.commit()


async def _cleanup_user_related_data(
    session: AsyncSession,
    user_ids: list[UUID],
) -> None:
    """Clean up tables that have FK references to users.

    Called by cleanup_test_users and cleanup_telegram_test_users
    before deleting users.
    """
    from app.modules.agent_applications.models import AgentApplication
    from app.modules.companies.models import (
        CompanyPriceHistory,
        CompanyProfile,
        CompanyRoadmapItem,
    )
    from app.modules.documents.models import Document, DocumentSigning
    from app.modules.installments.models import InstallmentPlan, InstallmentTranche
    from app.modules.kyc.models import KYCApplication
    from app.modules.ledgers.models import ActiveLedger, PassiveLedger
    from app.modules.notifications.models import Notification, NotificationDelivery
    from app.modules.payments.models import CryptoAddress, Payment
    from app.modules.products.models import Product, ProductInstallment
    from app.modules.purchases.models import Purchase
    from app.modules.transactions.models import Transaction
    from app.modules.withdrawals.models import Withdrawal

    # Sprint 8.1: Notification deliveries (FK to users.id CASCADE).
    # Deliveries first, then orphaned notifications.
    await session.execute(
        delete(NotificationDelivery).where(
            NotificationDelivery.user_id.in_(user_ids)
        )
    )

    # Sprint 7.1: Agent applications (FK to users.id via user_id and reviewed_by).
    await session.execute(
        delete(AgentApplication).where(
            AgentApplication.user_id.in_(user_ids)
            | AgentApplication.reviewed_by.in_(user_ids)
        )
    )

    # Sprint 7.3: Volume payouts and leaderboard snapshots (FK to users.id).
    from app.modules.commissions.models import LeaderboardSnapshot, VolumePayout

    await session.execute(
        delete(VolumePayout).where(
            VolumePayout.agent_id.in_(user_ids)
        )
    )
    await session.execute(
        delete(LeaderboardSnapshot).where(
            LeaderboardSnapshot.agent_id.in_(user_ids)
        )
    )

    # Sprint 6.4: Transactions (FK to users.id).
    await session.execute(
        delete(Transaction).where(
            Transaction.user_id.in_(user_ids)
        )
    )

    # Sprint 6.3: Withdrawals (FK to users.id).
    await session.execute(
        delete(Withdrawal).where(
            Withdrawal.user_id.in_(user_ids)
        )
    )

    # Sprint 6.2: Installment tranches and plans by investor_id.
    # Tranches first (FK to installment_plans.id and purchases.id).
    plan_stmt = select(InstallmentPlan.id).where(
        InstallmentPlan.investor_id.in_(user_ids)
    )
    plan_result = await session.execute(plan_stmt)
    plan_ids = [row[0] for row in plan_result.all()]

    if plan_ids:
        await session.execute(
            delete(InstallmentTranche).where(
                InstallmentTranche.plan_id.in_(plan_ids)
            )
        )
        await session.execute(
            delete(InstallmentPlan).where(
                InstallmentPlan.id.in_(plan_ids)
            )
        )

    # Also clean plans where agent_id is one of the users.
    agent_plan_stmt = select(InstallmentPlan.id).where(
        InstallmentPlan.agent_id.in_(user_ids)
    )
    agent_plan_result = await session.execute(agent_plan_stmt)
    agent_plan_ids = [row[0] for row in agent_plan_result.all()]

    if agent_plan_ids:
        await session.execute(
            delete(InstallmentTranche).where(
                InstallmentTranche.plan_id.in_(agent_plan_ids)
            )
        )
        await session.execute(
            delete(InstallmentPlan).where(
                InstallmentPlan.id.in_(agent_plan_ids)
            )
        )

    # Sprint 7.2: Referral attributions (FK to purchases -- must go before purchases).
    from app.modules.referrals.models import ReferralAttribution, ReferralLink

    purchase_ids_for_attr = select(Purchase.id).where(
        Purchase.investor_id.in_(user_ids)
    )
    await session.execute(
        delete(ReferralAttribution).where(
            ReferralAttribution.purchase_id.in_(purchase_ids_for_attr)
        )
    )

    # Sprint 6.1: Purchases by investor_id (FK to users.id).
    await session.execute(
        delete(Purchase).where(
            Purchase.investor_id.in_(user_ids)
        )
    )

    # Sprint 5.1: Ledger entries (FK to users.id with RESTRICT).
    await session.execute(
        delete(ActiveLedger).where(
            ActiveLedger.user_id.in_(user_ids)
        )
    )
    await session.execute(
        delete(PassiveLedger).where(
            PassiveLedger.user_id.in_(user_ids)
        )
    )

    # Sprint 5.2: Payments and crypto addresses (FK to users.id with RESTRICT).
    # Deleted AFTER ledger entries because active_ledger.origin_payment_id
    # has FK to payments.id.
    await session.execute(
        delete(Payment).where(
            Payment.user_id.in_(user_ids)
        )
    )
    await session.execute(
        delete(CryptoAddress).where(
            CryptoAddress.user_id.in_(user_ids)
        )
    )

    # Phase 4.1+4.2: Company and product-related tables.
    # Find company profiles owned by these users.
    cp_stmt = select(CompanyProfile.id).where(
        CompanyProfile.user_id.in_(user_ids)
    )
    cp_result = await session.execute(cp_stmt)
    company_ids = [row[0] for row in cp_result.all()]

    if company_ids:
        # Find products belonging to these companies.
        prod_stmt = select(Product.id).where(
            Product.company_id.in_(company_ids)
        )
        prod_result = await session.execute(prod_stmt)
        product_ids = [row[0] for row in prod_result.all()]

        if product_ids:
            # Sprint 6.2: Installment plans/tranches referencing these products.
            prod_plan_stmt = select(InstallmentPlan.id).where(
                InstallmentPlan.product_id.in_(product_ids)
            )
            prod_plan_result = await session.execute(prod_plan_stmt)
            prod_plan_ids = [row[0] for row in prod_plan_result.all()]

            if prod_plan_ids:
                await session.execute(
                    delete(InstallmentTranche).where(
                        InstallmentTranche.plan_id.in_(prod_plan_ids)
                    )
                )
                await session.execute(
                    delete(InstallmentPlan).where(
                        InstallmentPlan.id.in_(prod_plan_ids)
                    )
                )

            # Sprint 7.2: Referral attributions for product-based purchases.
            prod_purchase_ids = select(Purchase.id).where(
                Purchase.product_id.in_(product_ids)
            )
            await session.execute(
                delete(ReferralAttribution).where(
                    ReferralAttribution.purchase_id.in_(prod_purchase_ids)
                )
            )

            # Sprint 6.1: Purchases referencing these products.
            await session.execute(
                delete(Purchase).where(
                    Purchase.product_id.in_(product_ids)
                )
            )

            # Product installments reference products.
            await session.execute(
                delete(ProductInstallment).where(
                    ProductInstallment.product_id.in_(product_ids)
                )
            )
            # Products reference company_profiles.
            await session.execute(
                delete(Product).where(
                    Product.id.in_(product_ids)
                )
            )

        # Roadmap items reference company_profiles.
        await session.execute(
            delete(CompanyRoadmapItem).where(
                CompanyRoadmapItem.company_id.in_(company_ids)
            )
        )
        # Price history references company_profiles and users (changed_by).
        await session.execute(
            delete(CompanyPriceHistory).where(
                CompanyPriceHistory.company_id.in_(company_ids)
            )
        )
        # Company profiles reference users.
        await session.execute(
            delete(CompanyProfile).where(
                CompanyProfile.id.in_(company_ids)
            )
        )

    # Also clean price history where changed_by is one of the users
    # (staff who changed price of a company owned by someone else).
    await session.execute(
        delete(CompanyPriceHistory).where(
            CompanyPriceHistory.changed_by.in_(user_ids)
        )
    )

    # Phase 3: Avatar sessions (staff_id or target_user_id).
    await session.execute(
        delete(AvatarSession).where(
            AvatarSession.staff_id.in_(user_ids)
            | AvatarSession.target_user_id.in_(user_ids)
        )
    )

    # Phase 3: Staff profiles.
    await session.execute(
        delete(StaffProfile).where(
            StaffProfile.user_id.in_(user_ids)
        )
    )

    # Document signings by user.
    await session.execute(
        delete(DocumentSigning).where(
            DocumentSigning.user_id.in_(user_ids)
        )
    )

    # Documents created by staff users being cleaned up.
    # First remove signings referencing those documents.
    doc_stmt = select(Document.id).where(
        Document.created_by.in_(user_ids)
    )
    doc_result = await session.execute(doc_stmt)
    doc_ids = [row[0] for row in doc_result.all()]

    if doc_ids:
        await session.execute(
            delete(DocumentSigning).where(
                DocumentSigning.document_id.in_(doc_ids)
            )
        )
        await session.execute(
            delete(Document).where(Document.id.in_(doc_ids))
        )

    # KYC applications.
    await session.execute(
        delete(KYCApplication).where(
            KYCApplication.user_id.in_(user_ids)
        )
    )

    # Sprint 7.2: Referral links (FK to users.id via agent_id).
    await session.execute(
        delete(ReferralLink).where(
            ReferralLink.agent_id.in_(user_ids)
        )
    )
