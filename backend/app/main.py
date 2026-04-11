# =============================================================================
# CBSHOME Backend -- Application Entry Point
# =============================================================================
#
# ROUTERS:
#   auth_router               -> /api/v1/auth/* (Sprint 1.3)
#   users_router              -> /api/v1/users/* (Sprint 1.3)
#   kyc_router                -> /api/v1/kyc/* (Sprint 2.1)
#   documents_router          -> /api/v1/documents/* (Sprint 2.2)
#   staff_documents_router    -> /api/v1/staff/documents/* (Sprint 2.2)
#   staff_users_router        -> /api/v1/staff/users/* (Sprint 3.1)
#   avatar_router             -> /api/v1/staff/avatar/* (Sprint 3.2)
#   dashboard_router          -> /api/v1/staff/dashboard/* (Sprint 3.1)
#   kyc_admin_router          -> /api/v1/staff/kyc/* (Sprint 2.1)
#   companies_router          -> /api/v1/companies/* (Sprint 4.1)
#   staff_companies_router    -> /api/v1/staff/companies/* (Sprint 4.1)
#   products_router           -> /api/v1/products/* (Sprint 4.2)
#   staff_products_router     -> /api/v1/staff/products/* (Sprint 4.2)
#   payments_router           -> /api/v1/payments/* (Sprint 5.2)
#   payments_webhook_router   -> /api/v1/payments/crypto/* (Sprint 5.2)
#   staff_payments_router     -> /api/v1/staff/payments/* (Sprint 5.3)
#   purchases_router          -> /api/v1/products/{id}/purchase (Sprint 6.1)
#   installment_create_router -> /api/v1/installments/* (Sprint 6.2)
#   installment_query_router  -> /api/v1/installments/* (Sprint 6.2)
#   withdrawals_router        -> /api/v1/withdrawals/* (Sprint 6.3)
#   staff_withdrawals_router  -> /api/v1/staff/withdrawals/* (Sprint 6.3)
#   transactions_router       -> /api/v1/transactions/* (Sprint 6.4)
#   consistency_router        -> /api/v1/staff/consistency (Sprint 6.4)
#   agent_applications_router -> /api/v1/agent-applications/* (Sprint 7.1)
#
# LIFESPAN:
#   startup:  setup_logging -> init_redis -> start daemons
#   shutdown: cancel daemons -> close_redis -> dispose_engine
#
# DAEMONS:
#   payment_confirmation_worker -- calls run_confirmation_batch() (Sprint 5.3)
#   installment_payment_worker  -- calls run_installment_batch() (Sprint 6.2)
#
# MIDDLEWARE (applied in reverse order -- outermost last):
#   CORSMiddleware -> TraceIdMiddleware
# =============================================================================

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, UTC

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.requests import Request

from app.core.config import APP_VERSION, settings
from app.core.database import dispose_engine, get_engine
from app.core.exceptions import CBSError
from app.core.logging import setup_logging
from app.core.middleware import TraceIdMiddleware
from app.core.redis import close_redis, get_redis, init_redis
from app.modules.agent_applications.router import router as agent_applications_router
from app.modules.auth.router import router as auth_router
from app.modules.companies.router import router as companies_router
from app.modules.companies.staff_router import router as staff_companies_router
from app.modules.documents.router import router as documents_router
from app.modules.documents.staff_router import router as staff_documents_router
from app.modules.installments.router import (
    create_router as installment_create_router,
    query_router as installment_query_router,
)
from app.modules.installments.worker import run_installment_batch
from app.modules.kyc.router import router as kyc_router
from app.modules.payments.confirmation import run_confirmation_batch
from app.modules.payments.router import router as payments_router
from app.modules.payments.staff_router import router as staff_payments_router
from app.modules.payments.webhook_router import router as payments_webhook_router
from app.modules.products.router import router as products_router
from app.modules.products.staff_router import router as staff_products_router
from app.modules.purchases.router import router as purchases_router
from app.modules.staff.admin_router import dashboard_router, kyc_admin_router
from app.modules.staff.avatar_router import router as avatar_router
from app.modules.staff.consistency.router import router as consistency_router
from app.modules.staff.router import router as staff_users_router
from app.modules.transactions.router import router as transactions_router
from app.modules.users.router import router as users_router
from app.modules.withdrawals.router import router as withdrawals_router
from app.modules.withdrawals.staff_router import router as staff_withdrawals_router

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

    Runs daily at INSTALLMENT_WORKER_HOUR (UTC). Each cycle delegates
    to run_installment_batch() in installments/worker.py.

    Fix #34: batch runs BEFORE first sleep so any tranches that accumulated
    during downtime are processed immediately on startup, not deferred to
    the next scheduled hour.
    """
    target_hour = settings.installment_worker_hour
    logger.info(
        "installment_worker_started",
        target_hour_utc=target_hour,
    )

    while True:
        try:
            # Batch-first: process accumulated tranches immediately.
            await run_installment_batch()

            # Calculate sleep until next target hour.
            now = datetime.now(UTC)
            next_run = now.replace(
                hour=target_hour, minute=0, second=0, microsecond=0
            )
            if next_run <= now:
                # Target hour already passed today -- schedule for tomorrow.
                next_run = next_run + timedelta(days=1)

            sleep_seconds = (next_run - now).total_seconds()
            logger.info(
                "installment_worker_sleeping",
                next_run=next_run.isoformat(),
                sleep_seconds=int(sleep_seconds),
            )

            await asyncio.sleep(sleep_seconds)

        except asyncio.CancelledError:
            logger.info("installment_worker_stopped")
            break
        except Exception:
            logger.exception("installment_worker_error")
            # Sleep 1 hour before retry to avoid tight error loop.
            await asyncio.sleep(3600)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    setup_logging()
    await init_redis()

    # Start background daemons.
    confirmation_task = asyncio.create_task(
        _payment_confirmation_worker(),
        name="payment_confirmation_worker",
    )
    installment_task = asyncio.create_task(
        _installment_payment_worker(),
        name="installment_payment_worker",
    )

    logger.info(
        "app_started",
        env=settings.app_env,
        log_level=settings.log_level,
        version=APP_VERSION,
    )

    yield

    # Stop background daemons.
    confirmation_task.cancel()
    installment_task.cancel()
    try:
        await confirmation_task
    except asyncio.CancelledError:
        pass
    try:
        await installment_task
    except asyncio.CancelledError:
        pass

    await close_redis()
    await dispose_engine()
    logger.info("app_stopped")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CBSHOME API",
    description="Investment platform",
    version=APP_VERSION,
    lifespan=lifespan,
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
app.include_router(staff_companies_router)
app.include_router(products_router)
app.include_router(staff_products_router)
app.include_router(payments_router)
app.include_router(payments_webhook_router)
app.include_router(staff_payments_router)
app.include_router(purchases_router)
app.include_router(installment_create_router)
app.include_router(installment_query_router)
app.include_router(withdrawals_router)
app.include_router(staff_withdrawals_router)
app.include_router(transactions_router)
app.include_router(consistency_router)
app.include_router(agent_applications_router)


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(CBSError)
async def cbs_error_handler(request: Request, exc: CBSError) -> JSONResponse:
    """Convert CBSError exceptions into proper HTTP JSON responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# ---------------------------------------------------------------------------
# Health + Root
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
async def root() -> dict:
    """API info endpoint."""
    return {
        "name": "CBSHOME API",
        "version": APP_VERSION,
        "status": "running",
    }


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Health check -- DB + Redis."""
    result: dict = {"status": "ok", "checks": {}}

    # DB check.
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        result["checks"]["database"] = "ok"
    except Exception as e:
        result["status"] = "degraded"
        result["checks"]["database"] = str(e)

    # Redis check.
    try:
        redis = get_redis()
        await redis.ping()
        result["checks"]["redis"] = "ok"
    except Exception as e:
        result["status"] = "degraded"
        result["checks"]["redis"] = str(e)

    return result


@app.get("/ready", tags=["health"])
async def ready() -> JSONResponse:
    """Readiness probe -- returns 503 if any dependency is down."""
    checks: dict = {}
    all_ok = True

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)
        all_ok = False

    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = str(e)
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )
