# =============================================================================
# AIVIS.ONE Backend -- Application Entry Point
# =============================================================================
#
# FastAPI application with lifespan-managed background daemons.
#
# ROUTERS:
#   auth_router               -> /api/v1/auth/* (Sprint 1.1, 1.2)
#   users_router              -> /api/v1/users/* (Sprint 1.3)
#   kyc_router                -> /api/v1/kyc/* (Sprint 2.1)
#   documents_router          -> /api/v1/documents/* (Sprint 2.2)
#   staff_documents_router    -> /api/v1/staff/documents/* (Sprint 2.2)
#   staff_users_router        -> /api/v1/staff/users/* (Sprint 3.1)
#   avatar_router             -> /api/v1/staff/avatar/* (Sprint 3.2)
#   dashboard_router          -> /api/v1/staff/dashboard/* (Sprint 3.3)
#   kyc_admin_router          -> /api/v1/staff/kyc/* (Sprint 3.3)
#   companies_router          -> /api/v1/companies/* (Sprint 4.1)
#   staff_companies_router    -> /api/v1/staff/companies/* (Sprint 4.1)
#   staff_company_audit_router -> /api/v1/staff/audit/companies (TASK-30
#                                 ruling 3 / F2, read-only feed over
#                                 AuditLog target_type="company")
#   attachments_router        -> /api/v1/companies/{id}/attachments/*
#                                (Refactor 2 iter 2.2, auth-flow)
#   public_attachments_router -> /api/v1/public/companies/{id}/attachments/*
#                                (Refactor 2 iter 2.2, public-flow, no auth,
#                                 rate-limited per IP)
#   staff_attachments_router  -> /api/v1/staff/companies/{id}/attachments/*
#                                (Refactor 2 iter 2.2, staff-flow, multipart
#                                 upload + replace + hard-delete admin-only)
#   staff_templates_router    -> /api/v1/staff/companies/{id}/templates/*
#                                (Refactor 2 iter 2.3, staff-flow, read-only
#                                 inspection of per-company + platform-default
#                                 templates)
#   public_products_router    -> /api/v1/public/products/* (iter 2.4 R1 §1.6.2)
#   staff_products_router     -> /api/v1/staff/products/* (Sprint 4.2)
#   staff_pools_router        -> /api/v1/staff/companies/{id}/pool (Sprint 4.3)
#   company_dashboard_router  -> /api/v1/company/* (Sprint 4.3 / B5)
#   payments_router           -> /api/v1/payments/* (Sprint 5.1)
#   staff_payments_router     -> /api/v1/staff/payments/* (Sprint 5.3)
#   purchases_router          -> /api/v1/purchases/* (Sprint 6.1)
#   staff_purchases_router    -> /api/v1/staff/purchases/* (R-2.2)
#   installment_create_router -> /api/v1/installments/* (Sprint 6.2)
#   installment_query_router  -> /api/v1/installments/* (Sprint 6.2)
#   withdrawals_router        -> /api/v1/withdrawals/* (Sprint 6.3)
#   staff_withdrawals_router  -> /api/v1/staff/withdrawals/* (Sprint 6.3)
#   transactions_router       -> /api/v1/transactions/* (Sprint 6.4)
#   consistency_router        -> /api/v1/staff/consistency (Sprint 6.4)
#   agent_applications_router -> /api/v1/agent/* (Sprint 7.1)
#   staff_agent_applications_router -> /api/v1/staff/agent-applications/* (Sprint 7.1)
#   referrals_router          -> /api/v1/referrals/* (Sprint 7.2)
#   referrals_public_router   -> /api/v1/public/referral-click (Task 1 Block B)
#   commissions_router        -> /api/v1/agent/* (Sprint 7.3)
#   posts_router              -> /api/v1/posts/* (Sprint 9.1)
#   events_router             -> /api/v1/events/* (Sprint 9.1)
#   staff_posts_router        -> /api/v1/staff/posts/* (Sprint 9.1)
#   staff_events_router       -> /api/v1/staff/events/* (Sprint 9.1)
#   company_posts_router      -> /api/v1/company/posts/* (TASK-30,
#                                 company self-service CRUD on its own
#                                 Post rows, owner_type=company)
#   investor_dashboard_router -> /api/v1/dashboard/* (Sprint 9.2)
#   portfolio_router          -> /api/v1/portfolio/* (Sprint 9.2)
#   agreement_router          -> /api/v1/purchases/{id}/agreement (Refactor 2 iter 2.4)
#   ownership_router          -> /api/v1/companies/{id}/ownership-certificate
#                                (Refactor 2 iter 2.4)
#   support_router            -> /api/v1/support/* (T-65, user side of the
#                                support request channel; proxies comms)
#   staff_support_router      -> /api/v1/staff/support/* (T-66, operator
#                                side: queue, claim, reply, close)
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - +staff_pools_router for POST/PATCH /staff/companies/{id}/pool.
#     Wired right after staff_products_router so the staff-side
#     company/product/pool admin trio stays grouped.
#   - +company_dashboard_router (B5) for the company-side read endpoints
#     /api/v1/company/dashboard and /api/v1/company/analytics. Wired
#     after staff_pools_router so the company self-service routes sit
#     next to the company admin routes in the OpenAPI doc.
#
# Refactor 2 iter 2.2 CHANGES:
#   - +attachments_router (auth-flow): /api/v1/companies/{id}/attachments
#     and /download. Wired right after staff_companies_router so the
#     company / staff-company / attachments group stays adjacent.
#   - +public_attachments_router (public-flow, no auth, rate-limited):
#     /api/v1/public/companies/{id}/attachments and /download. Wired
#     right after attachments_router.
#   - +staff_attachments_router (staff-flow, multipart upload, hard-delete
#     admin-only): /api/v1/staff/companies/{id}/attachments/*. Wired
#     right after public_attachments_router so all three attachment
#     routers sit together in the OpenAPI doc.
#
# Refactor 2 iter 2.3 CHANGES:
#   - +staff_templates_router (staff-flow, read-only): /api/v1/staff/
#     companies/{id}/templates/*. Wired right after staff_attachments_router
#     so the staff company-content trio (attachments + templates) sits
#     together in the OpenAPI doc. MVP exposes only GET endpoints --
#     templates are uploaded through MinIO Web UI + reconcile (R2 §4.8);
#     the post-MVP UI editor will add POST/PATCH on the same prefix.
#
# Refactor 2 iter 2.4 CHANGES (R2 §5.3):
#   - BREAKING: certificate_router REMOVED. The endpoints
#       GET  /api/v1/purchases/{id}/certificate
#       POST /api/v1/purchases/{id}/certificate/email
#     are gone; no 301/302 redirect. Replaced by:
#       GET  /api/v1/purchases/{id}/agreement
#       POST /api/v1/purchases/{id}/agreement/email
#     served by the new agreement_router.
#   - +ownership_router: /api/v1/companies/{id}/ownership-certificate
#     and /ownership-certificate/email. Live aggregate of investor's
#     non-reversed Purchases per company (R2 §5.3).
#   - Both routers live in app/modules/purchases/agreement_router.py
#     because they share the same Jinja2 / MinIO / xhtml2pdf rendering
#     machinery.
#
# LIFESPAN:
#   startup:  setup_logging -> init_redis -> start daemons
#   shutdown: cancel daemons -> close_redis -> dispose_engine
#
# DAEMONS:
#   payment_confirmation_worker -- calls run_confirmation_batch() (Sprint 5.3)
#   installment_payment_worker  -- calls run_installment_batch() (Sprint 6.2)
#   leaderboard_worker          -- calls run_leaderboard_update() + payouts (Sprint 7.3)
#
# MIDDLEWARE (applied in reverse order -- outermost last):
#   CORSMiddleware -> TraceIdMiddleware
# =============================================================================

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

import structlog
from app.core.background import publish_background_tasks
from app.core.config import APP_VERSION, settings
from app.core.database import dispose_engine, get_engine
from app.core.events.relay import run_relay
from app.core.exceptions import AivisError, RateLimitError
from app.core.logging import setup_logging
from app.core.middleware import TraceIdMiddleware
from app.core.redis import close_redis, get_redis, init_redis
from app.modules.agent_applications.router import router as agent_applications_router
from app.modules.agent_applications.staff_router import (
    router as staff_agent_applications_router,
)
from app.modules.audit.router import router as staff_company_audit_router
from app.modules.auth.router import router as auth_router
from app.modules.commissions.router import router as commissions_router
from app.modules.commissions.worker import (
    run_leaderboard_update,
    run_monthly_payout,
    run_quarterly_payout,
)
from app.modules.companies.attachments_company_router import (
    router as company_attachments_router,
)
from app.modules.companies.attachments_public_router import (
    router as public_attachments_router,
)
from app.modules.companies.attachments_router import router as attachments_router
from app.modules.companies.attachments_staff_router import (
    router as staff_attachments_router,
)
from app.modules.companies.public_router import (
    router as public_companies_router,
)
from app.modules.companies.roadmap_company_router import (
    router as company_roadmap_router,
)
from app.modules.companies.router import router as companies_router
from app.modules.companies.staff_router import router as staff_companies_router
from app.modules.companies.templates_staff_router import (
    router as staff_templates_router,
)
from app.modules.company_dashboard.router import router as company_dashboard_router
from app.modules.dashboard.router import router as investor_dashboard_router
from app.modules.documents.router import router as documents_router
from app.modules.documents.staff_router import router as staff_documents_router
from app.modules.installments.router import (
    create_router as installment_create_router,
)
from app.modules.installments.router import (
    query_router as installment_query_router,
)
from app.modules.installments.worker import run_installment_batch
from app.modules.kyc.router import router as kyc_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.confirmation import run_confirmation_batch
from app.modules.payments.router import router as payments_router
from app.modules.payments.staff_router import router as staff_payments_router
from app.modules.pools.router import router as staff_pools_router
from app.modules.portfolio.router import router as portfolio_router
from app.modules.posts.company_router import router as company_posts_router
from app.modules.posts.router import events_router, posts_router
from app.modules.posts.staff_router import staff_events_router, staff_posts_router
from app.modules.products.public_router import (
    router as public_products_router,
)
from app.modules.products.staff_router import router as staff_products_router

# Refactor 2 iter 2.4: agreement_router + ownership_router replace certificate_router.
from app.modules.purchases.agreement_router import (
    agreement_router,
    ownership_router,
)
from app.modules.purchases.router import router as purchases_router
from app.modules.purchases.staff_router import router as staff_purchases_router
from app.modules.referrals.public_router import router as referrals_public_router
from app.modules.referrals.router import router as referrals_router
from app.modules.staff.admin_router import dashboard_router, kyc_admin_router
from app.modules.staff.avatar_router import router as avatar_router
from app.modules.staff.consistency.router import router as consistency_router
from app.modules.staff.router import router as staff_users_router
from app.modules.support.router import router as support_router
from app.modules.support.staff_router import router as staff_support_router
from app.modules.transactions.router import router as transactions_router
from app.modules.users.router import router as users_router
from app.modules.withdrawals.router import router as withdrawals_router
from app.modules.withdrawals.staff_router import router as staff_withdrawals_router
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.requests import Request

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Payment confirmation daemon (Sprint 5.3, fix review)
# ---------------------------------------------------------------------------


async def _payment_confirmation_worker() -> None:
    """Background task: confirm frozen ledger entries and payments.

    Runs every CONFIRMATION_WORKER_INTERVAL_MINUTES. Each cycle delegates
    to run_confirmation_batch() in payments/confirmation.py.

    Review fix: batch runs BEFORE sleep so frozen entries that are already
    past their frozen_until are confirmed immediately on startup, not after
    waiting one full interval.
    """
    interval = settings.confirmation_worker_interval_minutes * 60
    logger.info(
        "confirmation_worker_started",
        interval_minutes=settings.confirmation_worker_interval_minutes,
    )

    while True:
        try:
            await run_confirmation_batch()
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("confirmation_worker_stopped")
            break
        except Exception:
            logger.exception("confirmation_worker_error")
            # Sleep before retry to avoid tight error loop.
            await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Installment payment daemon (Sprint 6.2, fix #34)
# ---------------------------------------------------------------------------


async def _installment_payment_worker() -> None:
    """Background task: pay due tranches and default overdue plans.

    Runs daily at INSTALLMENT_WORKER_HOUR. Each cycle delegates to
    run_installment_batch() in installments/worker.py.

    Fix #34: batch runs BEFORE sleep so overdue tranches are processed
    immediately on startup, not after waiting one full day.
    """
    target_hour = settings.installment_worker_hour
    logger.info(
        "installment_worker_started",
        target_hour=target_hour,
    )

    while True:
        try:
            await run_installment_batch()

            # Sleep until next target_hour.
            now = datetime.now(UTC)
            next_run = now.replace(
                hour=target_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run = next_run + timedelta(days=1)

            sleep_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            logger.info("installment_worker_stopped")
            break
        except Exception:
            logger.exception("installment_worker_error")
            # Sleep an hour before retry to avoid tight error loop.
            await asyncio.sleep(3600)


# ---------------------------------------------------------------------------
# Leaderboard + volume bonus daemon (Sprint 7.3)
# ---------------------------------------------------------------------------


async def _leaderboard_worker() -> None:
    """Background task: update leaderboard + distribute volume bonuses.

    Runs every 60 minutes. Each cycle:
    1. Update leaderboard snapshots (current month).
    2. Check if monthly payout is due -> distribute.
    3. Check if quarterly payout is due -> distribute.
    """
    logger.info("leaderboard_worker_started")

    while True:
        try:
            await run_leaderboard_update()
            await run_monthly_payout()
            await run_quarterly_payout()
            await asyncio.sleep(settings.leaderboard_worker_interval_minutes * 60)
        except asyncio.CancelledError:
            logger.info("leaderboard_worker_stopped")
            break
        except Exception:
            logger.exception("leaderboard_worker_error")
            await asyncio.sleep(settings.leaderboard_worker_interval_minutes * 60)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    setup_logging()
    await init_redis()

    # Start the comms outbox relay (T-63). Unlike the daemons below it
    # is GATED, and by two things at once: the operator switch, and a
    # configured COMMS_REDIS_URL. An empty url means "this box has no
    # comms stack" -- the correct answer there is a relay that does not
    # run, not an application that will not start. The reason is logged
    # with both inputs, because a background task that silently never
    # existed is the kind of absence nobody notices for months.
    relay_task: asyncio.Task[None] | None = None
    if settings.comms_relay_enabled and settings.comms_redis_url:
        relay_task = asyncio.create_task(
            run_relay(),
            name="comms_outbox_relay",
        )
    else:
        logger.info(
            "comms_outbox_relay_disabled",
            enabled=settings.comms_relay_enabled,
            redis_url_configured=bool(settings.comms_redis_url),
        )

    # Start background daemons.
    confirmation_task = asyncio.create_task(
        _payment_confirmation_worker(),
        name="payment_confirmation_worker",
    )
    installment_task = asyncio.create_task(
        _installment_payment_worker(),
        name="installment_payment_worker",
    )
    leaderboard_task = asyncio.create_task(
        _leaderboard_worker(),
        name="leaderboard_worker",
    )

    logger.info(
        "app_started",
        env=settings.app_env,
        log_level=settings.log_level,
        version=APP_VERSION,
    )

    yield

    # Stop the comms outbox relay (T-63). Conditional because the task
    # may never have been created; awaited like the others so shutdown
    # does not return while the loop still holds its Redis connection.
    if relay_task is not None:
        relay_task.cancel()
        with suppress(asyncio.CancelledError):
            await relay_task

    # Stop background daemons.
    confirmation_task.cancel()
    installment_task.cancel()
    leaderboard_task.cancel()
    with suppress(asyncio.CancelledError):
        await confirmation_task
    with suppress(asyncio.CancelledError):
        await installment_task
    with suppress(asyncio.CancelledError):
        await leaderboard_task

    await close_redis()
    await dispose_engine()
    logger.info("app_stopped")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AIVIS.ONE API",
    description="Investment platform",
    version=APP_VERSION,
    lifespan=lifespan,
    # STAGE-III finding 20: a background task queued before a `raise` was
    # silently discarded, because FastAPI attaches them to the response built
    # from the endpoint's RETURN and an exception handler builds its own.
    # This publishes the instance on request.state so aivis_error_handler can
    # carry it. App-wide on purpose: per-route opt-in would leave the trap
    # armed for whoever adds the next task-before-raise, and that is a
    # symptomless hole -- it cost this project its whole failed-login audit
    # trail, 0 rows on the live database. Endpoints are untouched; they keep
    # their plain `background_tasks: BackgroundTasks` parameter.
    dependencies=[Depends(publish_background_tasks)],
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

_cors_origins = [o.strip() for o in settings.cors_origins.split(",")]
_allow_all = _cors_origins == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Trace-ID"],
)

app.add_middleware(TraceIdMiddleware)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(kyc_router)
app.include_router(documents_router)
app.include_router(staff_documents_router)
app.include_router(staff_users_router)
app.include_router(avatar_router)
app.include_router(dashboard_router)
app.include_router(kyc_admin_router)
app.include_router(companies_router)
# iter 2.4 R1 §1.6.2: public storefront for companies (list + detail
# with stats + roadmap). Lives at /api/v1/public/companies/* to match
# the attachments public-flow shape and centralise WAF / rate-limit
# config under a single prefix.
app.include_router(public_companies_router)
app.include_router(staff_companies_router)
# TASK-30 ruling 3 / F2: staff-only read feed of company (project)
# writes recorded via record_audit(). Separate prefix
# (/api/v1/staff/audit/*) rather than nesting under
# staff_companies_router's /api/v1/staff/companies/{company_id} route
# so it never needs the "declare the literal path before the {id}
# path" ordering trick transactions/router.py uses for /export.
app.include_router(staff_company_audit_router)
# Refactor 2 iter 2.2: company attachments (auth-flow + public-flow + staff-flow).
app.include_router(attachments_router)
app.include_router(public_attachments_router)
app.include_router(staff_attachments_router)
# Refactor 2 iter 2.3: company doc templates (staff-flow, read-only).
app.include_router(staff_templates_router)
app.include_router(public_products_router)
app.include_router(staff_products_router)
# Sprint 4.3: pool admin endpoints (POST/PATCH /staff/companies/{id}/pool).
app.include_router(staff_pools_router)
# Sprint 4.3 / B5: company self-service dashboard + analytics.
app.include_router(company_dashboard_router)
app.include_router(payments_router)
app.include_router(staff_payments_router)
app.include_router(purchases_router)
app.include_router(staff_purchases_router)
app.include_router(installment_create_router)
app.include_router(installment_query_router)
app.include_router(withdrawals_router)
app.include_router(staff_withdrawals_router)
app.include_router(transactions_router)
app.include_router(consistency_router)
app.include_router(agent_applications_router)
app.include_router(staff_agent_applications_router)
app.include_router(referrals_router)
# Task 1 Block B: public fire-and-forget click endpoint, wired right
# after referrals_router so both referral surfaces sit together in
# the OpenAPI doc.
app.include_router(referrals_public_router)
app.include_router(commissions_router)
app.include_router(posts_router)
app.include_router(events_router)
app.include_router(staff_posts_router)
app.include_router(staff_events_router)
app.include_router(company_posts_router)
app.include_router(company_roadmap_router)
app.include_router(company_attachments_router)
app.include_router(investor_dashboard_router)
app.include_router(portfolio_router)
# Refactor 2 iter 2.4: per-Purchase agreement + per-investor-company ownership
# certificate. Replaces certificate_router (BREAKING -- no redirect).
app.include_router(agreement_router)
app.include_router(ownership_router)

# T-65: the user side of the support request channel. A proxy to comms --
# the conversation lives there; what lives here is who the caller is and
# which threads are theirs.
app.include_router(support_router)

# T-66: the operator side of the same channel -- the queue, claim, reply,
# close. Wired next to its user-side twin so the two halves of one
# conversation sit together in the OpenAPI document.
app.include_router(staff_support_router)

# Phase 6: the bell. A proxy to comms' frozen inbox contract, same shape
# as support_router above -- the data lives in comms, this module only
# knows who the caller is. Wired next to support since both are thin
# comms-proxy modules with no native storage of their own.
app.include_router(notifications_router)


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(AivisError)
async def aivis_error_handler(request: Request, exc: AivisError) -> JSONResponse:
    """Convert AivisError exceptions into proper HTTP JSON responses.

    iter 2.5-finishing: RateLimitError carries retry_after_seconds and
    is surfaced with the standard HTTP `Retry-After` response header,
    so clients (frontend, monitoring, agents) can back off intelligently
    instead of busy-retrying the endpoint.
    """
    headers: dict[str, str] | None = None
    if (
        isinstance(exc, RateLimitError)
        and exc.retry_after_seconds is not None
    ):
        headers = {"Retry-After": str(exc.retry_after_seconds)}

    # STAGE-III finding 20: background tasks queued before a raise were lost
    # here. FastAPI attaches them to the response built from the endpoint's
    # RETURN, and an endpoint that raises never builds one -- this handler
    # did, with no `background` at all. That silently discarded the entire
    # failed-login audit trail (0 rows on the live database, whole lifetime).
    # Fixed APP-WIDE via publish_background_tasks, wired as a global
    # dependency on the FastAPI() constructor itself (see `app = FastAPI(...,
    # dependencies=[Depends(publish_background_tasks)])` above) -- every
    # route gets `request.state.background_tasks` published automatically,
    # no per-route opt-in. getattr's default keeps this handler safe even
    # for a request where that dependency somehow did not run. Only one
    # response is produced per request, so a task can never run twice.
    # (This comment named a since-renamed function, surviving_background_
    # tasks, until an adversarial review of an unrelated change caught the
    # drift -- the two names never referred to different mechanisms.)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
        headers=headers,
        background=getattr(request.state, "background_tasks", None),
    )


# ---------------------------------------------------------------------------
# Root + Health + Ready
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> dict:
    """API info."""
    return {"name": "AIVIS.ONE API", "version": APP_VERSION}


@app.get("/health")
async def health() -> JSONResponse:
    """Health check -- always returns 200.

    Reports DB and Redis connectivity status.
    """
    db_ok = True
    redis_ok = True

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    try:
        redis = get_redis()
        await redis.ping()
    except Exception:
        redis_ok = False

    all_ok = db_ok and redis_ok
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok" if all_ok else "degraded",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    )


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe -- 503 if any dependency is degraded."""
    db_ok = True
    redis_ok = True

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    try:
        redis = get_redis()
        await redis.ping()
    except Exception:
        redis_ok = False

    all_ok = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ok" if all_ok else "degraded",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    )
