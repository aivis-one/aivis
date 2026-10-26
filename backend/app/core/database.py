# =============================================================================
# AIVIS.ONE Backend -- Database Connection
# =============================================================================
#
# LAZY ENGINE:
#   Engine is NOT created at import time -- created on first call to
#   get_engine(). Prevents "Future attached to a different loop" errors
#   in pytest where the event loop is created after module imports.
#
# SESSIONS:
#   get_db_session() -- read-write: commits on success, rolls back on error.
#   get_db_reader()  -- read-only: always rolls back.
#
# WHEN THE TRANSACTION ENDS (H46): when the endpoint has returned and its
#   response is built and serialized -- BEFORE the first byte of the response
#   is sent. Each session lives in an inner yield dependency declared ONCE,
#   with scope="function", inside a plain wrapper (_transaction behind
#   get_db_session, _read_transaction behind get_db_reader). FastAPI closes
#   function-scoped yield dependencies right after the endpoint and the
#   serialization (fastapi/routing.py: the function stack inside the request
#   stack) and sends the response afterwards. A yield dependency of the
#   default request scope -- what get_db_session was until H46 -- closes only
#   after the response has been sent: a client held a 200 for a commit that
#   had not happened yet, and could be refused. Measured for H44 under
#   uvicorn; tests/test_db_session_order.py holds the order.
#
# RULE (P-01): routers do not call session.commit(); the transaction above
#   commits once, before the response. flush() + refresh() give
#   database-generated values inside the request.
#   THE ONE EXCEPTION, by design: POST /auth/telegram/link/confirm
#   (auth/router.py) commits mid-route to ORDER a commit before an action
#   outside the transaction -- the claim's commit before end_other_sessions
#   in Redis. The commit at the end then finds nothing left and is a no-op;
#   committing twice is allowed (SQLAlchemy 2 begins a new transaction on
#   demand).
#
# CONTRACT for code built on these sessions: a session is committed (or
#   rolled back) and CLOSED when the endpoint returns. Anything that runs
#   after that -- a BackgroundTasks task, a streaming response body, the
#   code after the yield of a request-scoped dependency -- must open a
#   session of its own (the failed-login audit in auth/service.py does).
# =============================================================================

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


# ---------------------------------------------------------------------------
# Lazy singletons -- created on first access, not at import time
# ---------------------------------------------------------------------------
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async engine (singleton)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return _engine


async def dispose_engine() -> None:
    """Dispose engine and reset singletons. Called at shutdown and in tests."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create session factory bound to current engine (singleton)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def _transaction() -> AsyncGenerator[AsyncSession, None]:
    """The request's write transaction: commit on success, rollback on error.

    Consumed ONLY through get_db_session, which declares it with
    scope="function". Nothing else Depends() on it directly: a second
    declaration with another scope is another cache key, i.e. a second
    session and a second transaction in the same request.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db_session(
    session: AsyncSession = Depends(_transaction, scope="function"),
) -> AsyncSession:
    """Transactional read-write session (auto-commit/rollback).

    Use for all write operations. The commit runs when the endpoint returns,
    BEFORE the response is sent (module header): a failed commit reaches the
    client as an error response, never as a 200 for writes that were rolled
    back. An exception raised by the endpoint passes through _transaction,
    which rolls back before any exception handler builds the response.

    One session per request: every Depends(get_db_session) in the tree --
    endpoint parameters, get_current_user_write and the other dependencies --
    resolves to the same cache key, hence the same session.

    Routers do not commit. The one exception is named in the module header
    (POST /auth/telegram/link/confirm: a commit ordered before an action
    outside the transaction).
    """
    return session


async def _read_transaction() -> AsyncGenerator[AsyncSession, None]:
    """The request's read-only session: always rolled back.

    Consumed ONLY through get_db_reader (scope="function", see
    _transaction for why nothing else declares it).
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


async def get_db_reader(
    session: AsyncSession = Depends(_read_transaction, scope="function"),
) -> AsyncSession:
    """Read-only session -- always rolls back.

    Use for GET endpoints that do not modify any data. Ended, like the
    write session, before the response is sent: the connection goes back to
    the pool before the first byte instead of after the last.
    """
    return session
