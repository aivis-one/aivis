# =============================================================================
# AIVIS.ONE Backend -- the suite's own isolation (H42)
# =============================================================================
#
# Two things the suite does to itself, pinned here:
#
#   1. it runs on its OWN Redis database: tests/conftest.py refuses a run
#      whose REDIS_URL names any database but AIVIS_TEST_REDIS_DB (never
#      0, the application's own), the way it refuses a database whose name
#      does not end in `_test`;
#   2. it hashes passwords with argon2 at its minimum cost -- and only the
#      suite does: the product's hasher keeps argon2's defaults.
# =============================================================================

import os

import pytest
from argon2 import PasswordHasher
from argon2.profiles import RFC_9106_LOW_MEMORY

from app.core.config import settings
from app.modules.auth import service as auth_service
from tests.conftest import TEST_REDIS_DB_ENV, non_test_redis_refusal

# ---------------------------------------------------------------------------
# 1. The test Redis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "test_db", "why"),
    [
        # the application's database, by number or by omission
        ("redis://:pw@redis:6379/0", "15", "names Redis database 0"),
        ("redis://:pw@redis:6379", "15", "names Redis database none"),
        # another database than the one the run was given
        ("redis://:pw@redis:6379/14", "15", "names Redis database 14"),
        ("redis://:pw@redis:6379/115", "15", "names Redis database 115"),
        # no number given, or not a number
        ("redis://:pw@redis:6379/15", None, "is not set"),
        ("redis://:pw@redis:6379/15", "", "is not set"),
        ("redis://:pw@redis:6379/15", "fifteen", "is not a number"),
        ("redis://:pw@redis:6379/15", "-15", "is not a number"),
        # 0 named as the test database is still the application's
        ("redis://:pw@redis:6379/0", "0", "application's own"),
    ],
)
def test_a_run_off_the_test_redis_database_is_refused(
    url: str, test_db: str | None, why: str
) -> None:
    refusal = non_test_redis_refusal(url, test_db)
    assert refusal is not None
    assert why in refusal
    assert "pw" not in refusal  # nothing of the URL but numbers is shown


@pytest.mark.parametrize(
    "url",
    [
        "redis://:pw@redis:6379/15",
        "redis://127.0.0.1:6379/15",
        # a "/" in the password is not the database number
        "redis://:p%2Fw@redis:6379/15",
    ],
)
def test_the_test_redis_database_starts(url: str) -> None:
    """The pair: the guard does let the right database through."""
    assert non_test_redis_refusal(url, "15") is None


def test_this_run_is_on_its_test_redis_database() -> None:
    """The guard ran for this very session, and on what it checks."""
    assert (
        non_test_redis_refusal(settings.redis_url, os.environ.get(TEST_REDIS_DB_ENV))
        is None
    )
    assert os.environ[TEST_REDIS_DB_ENV] != "0"


# ---------------------------------------------------------------------------
# 2. Password hashing
# ---------------------------------------------------------------------------


def test_the_products_hasher_keeps_argon2s_defaults(
    production_password_hasher: PasswordHasher,
) -> None:
    """What the product hashes with outside the suite: argon2's own
    defaults (RFC 9106, low memory) -- nothing weakened."""
    assert (
        production_password_hasher.time_cost,
        production_password_hasher.memory_cost,
        production_password_hasher.parallelism,
    ) == (
        RFC_9106_LOW_MEMORY.time_cost,
        RFC_9106_LOW_MEMORY.memory_cost,
        RFC_9106_LOW_MEMORY.parallelism,
    )


def test_the_suite_hashes_cheaply_and_its_hashes_still_verify(
    production_password_hasher: PasswordHasher,
) -> None:
    """The pair: under the suite the module's hasher is the cheap one, and
    an argon2 hash carries its parameters -- either verifies the other's."""
    cheap = auth_service._ph
    assert cheap is not production_password_hasher
    assert cheap.memory_cost == 8
    assert production_password_hasher.verify(cheap.hash("x"), "x")
    assert cheap.verify(production_password_hasher.hash("y"), "y")


@pytest.mark.asyncio
async def test_hash_password_uses_the_cheap_hasher_in_the_suite() -> None:
    hashed = await auth_service.hash_password("secret")
    assert "m=8,t=1,p=1" in hashed
    assert await auth_service.verify_password("secret", hashed)
