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
#   staff_router           -> /api/v1/staff/users/* (Sprint 3.1)
#
# LIFESPAN:
#   startup:  setup_logging -> init_redis
#   shutdown: close_redis   -> dispose_engine
#
# MIDDLEWARE (applied in reverse order -- outermost last):
#   CORSMiddleware -> TraceIdMiddleware
# =============================================================================

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
from app.modules.documents.router import router as documents_router
from app.modules.documents.staff_router import router as staff_documents_router
from app.modules.kyc.router import router as kyc_router
from app.modules.staff.router import router as staff_router
from app.modules.users.router import router as users_router

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    setup_logging()
    await init_redis()
    logger.info("app_started", version=APP_VERSION)

    yield

    await close_redis()
    await dispose_engine()
    logger.info("app_stopped")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CBSHOME API",
    version=APP_VERSION,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TraceIdMiddleware)


# ---------------------------------------------------------------------------
# Exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(CBSError)
async def cbs_error_handler(request: Request, exc: CBSError) -> JSONResponse:
    """Handle application-level errors with consistent JSON format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(kyc_router)
app.include_router(documents_router)
app.include_router(staff_documents_router)
app.include_router(staff_router)


# ---------------------------------------------------------------------------
# Root endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> dict:
    """API info."""
    return {"name": "CBSHOME API", "version": APP_VERSION}


@app.get("/health")
async def health() -> JSONResponse:
    """Health check -- always returns 200.

    Reports component status but never fails the request.
    Use /ready for readiness probes that need to fail.
    """
    db_status = "ok"
    redis_status = "ok"

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        redis = get_redis()
        await redis.ping()
    except Exception:
        redis_status = "error"

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "db": db_status,
            "redis": redis_status,
        },
    )


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe -- 503 if any component is degraded.

    Kubernetes / load balancer should stop routing traffic
    until readiness is restored.
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
        status_code=200 if all_ok else 503,
        content={
            "status": "ok" if all_ok else "degraded",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    )
