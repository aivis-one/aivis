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

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    setup_logging()
    await init_redis()
    logger.info(
        "app_started",
        env=settings.app_env,
        log_level=settings.log_level,
        version=APP_VERSION,
    )

    yield

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
# Health Checks (shared logic -- DRY)
# ---------------------------------------------------------------------------

async def _check_components() -> tuple[dict[str, str], bool]:
    """Check DB and Redis connectivity. Returns (result_dict, is_degraded)."""
    result: dict[str, str] = {"status": "ok", "db": "ok", "redis": "ok"}
    degraded = False

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        result["db"] = "error"
        degraded = True

    try:
        redis = get_redis()
        await redis.ping()
    except Exception:
        result["redis"] = "error"
        degraded = True

    if degraded:
        result["status"] = "degraded"

    return result, degraded


# ---------------------------------------------------------------------------
# System Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint -- API info."""
    return {"name": "CBSHOME API", "version": APP_VERSION}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check -- always returns 200."""
    result, _ = await _check_components()
    return result


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe -- returns 503 if any component is degraded."""
    result, degraded = await _check_components()
    return JSONResponse(
        status_code=503 if degraded else 200,
        content=result,
    )
