# =============================================================================
# CBSHOME Backend -- FastAPI Application Entry Point
# =============================================================================
#
# ENDPOINTS:
#   GET /        -> API name + version
#   GET /health  -> DB + Redis connectivity (always 200)
#   GET /ready   -> Readiness probe (503 if degraded)
#
# LIFESPAN:
#   startup:  setup_logging -> init_redis
#   shutdown: close_redis   -> dispose_engine
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

from app.core.config import settings
from app.core.database import dispose_engine, get_engine
from app.core.exceptions import CBSError
from app.core.logging import setup_logging
from app.core.middleware import TraceIdMiddleware
from app.core.redis import close_redis, get_redis, init_redis

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    # -- Startup --
    setup_logging()
    await init_redis()
    logger.info(
        "app_started",
        env=settings.app_env,
        log_level=settings.log_level,
    )

    yield

    # -- Shutdown --
    await close_redis()
    await dispose_engine()
    logger.info("app_stopped")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CBSHOME API",
    description="Investment platform",
    version="0.1.0",
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
    # List headers explicitly -- Fetch spec forbids allow_headers=["*"]
    # with allow_credentials=True.
    allow_headers=["Authorization", "Content-Type", "X-Trace-ID"],
)

# TraceIdMiddleware must be added AFTER CORSMiddleware.
# Starlette applies middleware in LIFO order, so TraceId becomes outermost.
app.add_middleware(TraceIdMiddleware)


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(CBSError)
async def cbs_error_handler(request: Request, exc: CBSError) -> JSONResponse:
    """Convert CBSError exceptions into proper HTTP JSON responses."""
    if exc.status_code >= 500:
        logger.error(
            "cbs_error",
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
    else:
        logger.warning(
            "cbs_error",
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for unexpected exceptions -- return generic 500."""
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# System Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint -- API info."""
    return {"name": "CBSHOME API", "version": "0.1.0"}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check -- always returns 200.

    Reports individual component status without failing the probe.
    Used by Docker healthcheck and monitoring.
    """
    result: dict[str, str] = {"status": "ok", "db": "ok", "redis": "ok"}

    # Check DB.
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        result["db"] = "error"
        result["status"] = "degraded"

    # Check Redis.
    try:
        redis = get_redis()
        await redis.ping()
    except Exception:
        result["redis"] = "error"
        result["status"] = "degraded"

    return result


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe -- returns 503 if any component is degraded.

    Used by Docker depends_on condition and load balancers to know
    when the app is ready to receive traffic.
    """
    result: dict[str, str] = {"status": "ok", "db": "ok", "redis": "ok"}
    degraded = False

    # Check DB.
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        result["db"] = "error"
        result["status"] = "degraded"
        degraded = True

    # Check Redis.
    try:
        redis = get_redis()
        await redis.ping()
    except Exception:
        result["redis"] = "error"
        result["status"] = "degraded"
        degraded = True

    status_code = 503 if degraded else 200
    return JSONResponse(status_code=status_code, content=result)
