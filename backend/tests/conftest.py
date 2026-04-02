# =============================================================================
# CBSHOME Backend -- Pytest Configuration & Fixtures
# =============================================================================
#
# LIFECYCLE (session-scoped):
#   1. Run Alembic migrations (tables must exist before any test)
#   2. Initialize Redis client
#   3. Run tests
#   4. Close Redis + dispose engine
#
# FIXTURES:
#   client      -- async HTTP client (in-memory, no network)
#   db_session  -- direct DB session for setup/assertions
#
# SESSION ISOLATION:
#   db_session rolls back before closing -- discards any uncommitted state
#   left by a failing test. Tests that need persistent data call
#   session.commit() explicitly.
# =============================================================================

import subprocess
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import dispose_engine, get_session_factory
from app.core.redis import close_redis, init_redis
from app.main import app


@pytest.fixture(scope="session", autouse=True)
async def setup_infrastructure() -> AsyncGenerator[None, None]:
    """Run migrations + init Redis once before all tests."""
    # Run Alembic migrations -- subprocess because alembic env.py
    # uses asyncio.run() which cannot nest inside pytest's event loop.
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Alembic migration failed:\n{result.stderr}\n{result.stdout}"
        )

    await init_redis()

    yield

    await close_redis()
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client -- requests go directly to FastAPI in memory."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Direct database session for test setup and assertions.

    Rolls back before closing to discard uncommitted state from
    failing tests, preventing bleed-through to subsequent tests.
    Tests that need data to persist call session.commit() explicitly.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
