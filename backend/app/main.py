# =============================================================================
# CBSHOME Backend -- FastAPI Application Entry Point
# =============================================================================
#
# ENDPOINTS:
#   GET /        -> API name + version
#   GET /health  -> DB + Redis connectivity (always 200)
#   GET /ready   -> Readiness probe (503 if degraded)
#
# ROUTERS:
#   auth_router            -> /api/v1/auth/* (Sprint 1.1+)
#   users_router           -> /api/v1/users/* (Sprint 1.3)
#   kyc_router             -> /api/v1/kyc/* (Sprint 2.1)
#   documents_router       -> /api/v1/documents/* (Sprint 2.2)
#   staff_documents_router -> /api/v1/staff/documents/* (Sprint 2.2)
#   staff_users_router     -> /api/v1/staff/users/* (Sprint 3.1+3.3)
#   avatar_router          -> /api/v1/staff/avatar/* (Sprint 3.2)
#   dashboard_router       -> /api/v1/staff/dashboard/* (Sprint 3.3)
#   kyc_admin_router       -> /api/v1/staff/kyc/* (Sprint 3.3)
#   companies_router       -> /api/v1/companies/* (Sprint 4.1)
#   staff_companies_router -> /api/v1/staff/companies/* (Sprint 4.1)
#   products_router        -> /api/v1/products/* (Sprint 4.2)
#   staff_products_router  -> /api/v1/staff/products/* (Sprint 4.2)
#   payments_router        -> /api/v1/payments/* (Sprint 5.2)
#   payments_webhook_router -> /api/v1/payments/crypto/* (Sprint 5.2)
#   staff_payments_router  -> /api/v1/staff/payments/* (Sprint 5.3)
#   purchases_router       -> /api/v1/products/*/purchase (Sprint 6.1)
#
# LIFESPAN:
#   startup:  setup_logging -> init_redis -> start confirmation daemon
#   shutdown: cancel daemon -> close_redis -> dispose_engine
#
# DAEMONS:
#   payment_confirmation_worker -- calls run_confirmation_batch() (Sprint 5.3)
#
# MIDDLEWARE (applied in reverse order -- outermost last):
#   CORSMiddleware -> TraceIdMiddleware
# =============================================================================

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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
from app.modules.auth.router import router as auth_router
from app.modules.companies.router import router as companies_router
from app.modules.companies.staff_router import router as staff_companies_router
from app.modules.documents.router import router as documents_router
from app.modules.documents.staff_router import router as staff_documents_router
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
from app.modules.staff.router import router as staff_users_router
from app.modules.users.router import router as users_router

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Payment confirmation daemon (Sprint 5.3)
# ---------------------------------------------------------------------------


async def _payment_confirmation_worker() -> None:
    """Background task: confirm frozen ledger entries and payments.

    Runs every CONFIRMATION_WORKER_INTERVAL_MINUTES. Each cycle delegates
    to run_confirmation_batch() in payments/confirmation.py.
    """
    interval = settings.confirmation_worker_interval_minutes * 60
    logger.info(
        "confirmation_worker_started",
        interval_minutes=settings.confirmation_worker_interval_minutes,
    )

    while True:
        try:
            await asyncio.sleep(interval)
            await run_confirmation_batch()
        except asyncio.CancelledError:
            logger.info("confirmation_worker_stopped")
            break
        except Exception:
            logger.exception("confirmation_worker_error")
            # Continue running -- loop will sleep at the top.


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

    logger.info(
        "app_started",
        env=settings.app_env,
        log_level=settings.log_level,
        version=APP_VERSION,
    )

    yield

    # Stop background daemons.
    confirmation_task.cancel()
    try:
        await confirmation_task
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


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(CBSError)
async def cbs_error_handler(request: Request, exc: CBSError) -> JSONResponse:
    """Convert CBSError exceptions into proper HTTP JSON responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


# ---------------------------------------------------------------------------
# Root + Health + Ready
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> dict:
    """API info."""
    return {"name": "CBSHOME API", "version": APP_VERSION}


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
