# =============================================================================
# CBSHOME Backend -- pytest conftest (iter 2.5 mini-fix #3 -- isolation rewrite)
# =============================================================================
#
# WHY THIS FILE EXISTS:
#   Until this rewrite, tests shared a single physical Postgres database
#   with the dev site. Every painful symptom (cleanup_test_users helper,
#   email-prefix-based cleanup fixtures, magic seed ordering in
#   `cbshome update`, T2/T3 mutating platform defaults, no parallelism,
#   ~17 tests failing whenever one of them archived a platform row) was
#   downstream of that one decision.
#
#   This conftest replaces shared state with per-worker ephemeral
#   resources:
#
#     - Per-worker Postgres DB cloned from cbshome_test_template via
#       CREATE DATABASE ... TEMPLATE (~100ms per worker).
#     - Per-worker MinIO bucket populated with platform template files.
#     - Per-worker Redis logical DB (numbers 1..15; db 0 is prod).
#
#   pytest_unconfigure tears them down. Crashed workers leak resources
#   but `bootstrap_test_template.py` sweeps them on the next run.
#
# DEFERRED IMPORTS:
#   Top-level `from app.core.config import settings` would instantiate
#   Settings() with whatever DATABASE_URL was in os.environ at conftest
#   import time -- i.e. prod. So this file does NOT import anything from
#   `app.*` at module level. pytest_configure rewrites the env vars
#   first; only then do fixture bodies pull app modules in.
#
# CONTRACT WITH bootstrap_test_template.py:
#   That script runs BEFORE pytest in `cbshome update`. It:
#     1. drops stale `cbshome_test_*` DBs and `cbshome-attachments-pytest-*`
#        buckets,
#     2. builds the template DB (alembic + seed_platform + seed_platform_templates).
#   This conftest assumes the template exists. If a developer runs pytest
#   directly without bootstrap first, the worker provisioning will fail
#   with a clear "template database does not exist" error from Postgres.
# =============================================================================

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest

# NO top-level imports from `app.*`. Settings() reads DATABASE_URL at
# import time; we must rewrite env vars in pytest_configure first.


# Module-level mutable state -- pytest_configure assigns, pytest_unconfigure
# reads, and a session-scoped fixture exposes the values to tests that
# might want them.
_worker_resources: dict[str, str] = {}


TEMPLATE_DB_NAME = "cbshome_test_template"


# ---------------------------------------------------------------------------
# pytest_configure / pytest_unconfigure -- per-worker resource lifecycle
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Provision the per-worker DB / bucket / Redis db, and rewrite
    DATABASE_URL / REDIS_URL / MINIO_BUCKET in os.environ so that any
    subsequent `from app.core.config import settings` reads the
    worker-scoped values.

    Runs once per worker process. With xdist:
      * the controller (master process, no PYTEST_XDIST_WORKER) skips
        provisioning -- it never runs tests itself, so it has no DB to
        clone.
      * each gw0/gw1/... worker provisions its own resources.
    Without xdist:
      * the single process gets worker_id="master".
    """
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    xdist_active = config.pluginmanager.has_plugin("xdist")

    if xdist_active and worker_id is None:
        # We are the xdist controller. Workers will provision their own
        # resources when they start. Do nothing here.
        return

    worker_id = worker_id or "master"

    test_db = f"cbshome_test_{worker_id}"
    redis_db_num = _worker_redis_db(worker_id)
    test_bucket = f"cbshome-attachments-pytest-{worker_id}"

    # Rewrite env vars BEFORE any `app.*` import happens. Test modules
    # collected after this point will see the worker-scoped URLs.
    os.environ["DATABASE_URL"] = _swap_dbname(
        os.environ["DATABASE_URL"], test_db
    )
    os.environ["REDIS_URL"] = _swap_redis_db(
        os.environ["REDIS_URL"], redis_db_num
    )
    os.environ["MINIO_BUCKET"] = test_bucket

    # Clone template -> worker DB; create + populate MinIO bucket.
    asyncio.run(_provision_worker(test_db, test_bucket))

    _worker_resources.update(
        {
            "worker_id": worker_id,
            "db": test_db,
            "bucket": test_bucket,
            "redis_db": str(redis_db_num),
        }
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    """Tear down the per-worker resources. Symmetric to pytest_configure.

    If the worker crashed before this hook (SIGKILL, OOM), the resources
    leak. They are reaped on the next `cbshome update` by
    bootstrap_test_template.py.
    """
    if not _worker_resources:
        return  # xdist controller or never provisioned

    asyncio.run(
        _teardown_worker(
            test_db=_worker_resources["db"],
            test_bucket=_worker_resources["bucket"],
        )
    )


# ---------------------------------------------------------------------------
# Worker provisioning
# ---------------------------------------------------------------------------


async def _provision_worker(test_db: str, test_bucket: str) -> None:
    """Clone the template DB, create the worker's MinIO bucket, and
    upload platform template files into it.
    """
    # 1. CREATE DATABASE ... TEMPLATE. Atomic file-level clone in Postgres.
    import asyncpg

    maint_url = _maintenance_url(os.environ["DATABASE_URL"])
    conn = await asyncpg.connect(maint_url)
    try:
        # Defensive DROP -- a prior crashed run with the same worker_id
        # would otherwise collide. bootstrap_test_template already
        # sweeps these, but a developer re-running pytest in the same
        # session also benefits.
        await conn.execute(
            f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'
        )
        await conn.execute(
            f'CREATE DATABASE "{test_db}" TEMPLATE {TEMPLATE_DB_NAME}'
        )
    finally:
        await conn.close()

    # 2. MinIO bucket.
    await _create_bucket(test_bucket)

    # 3. Upload platform template files. Tests that render purchase
    #    agreements / ownership certificates need these on disk-in-bucket.
    await _upload_platform_templates(test_bucket)


async def _teardown_worker(test_db: str, test_bucket: str) -> None:
    """Reverse of _provision_worker. Tolerant of partial state -- a
    pytest_unconfigure that fires after a crashed test must not raise.
    """
    # Close any app-level connections before DROP DATABASE.
    try:
        from app.core.database import dispose_engine

        await dispose_engine()
    except Exception:
        pass

    try:
        from app.core.redis import close_redis, get_redis

        try:
            redis = get_redis()
            await redis.flushdb()
        except Exception:
            pass
        await close_redis()
    except Exception:
        pass

    # Drop MinIO bucket (with contents).
    await _drop_bucket(test_bucket)

    # Drop Postgres DB.
    import asyncpg

    maint_url = _maintenance_url(os.environ["DATABASE_URL"])
    conn = await asyncpg.connect(maint_url)
    try:
        await conn.execute(
            f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# URL manipulation -- duplicated from bootstrap_test_template.py because
# conftest deliberately avoids importing from app.* / scripts.* at module
# load time. Three short helpers; not worth a shared utility module.
# ---------------------------------------------------------------------------


def _swap_dbname(url: str, new_db: str) -> str:
    """`postgresql+asyncpg://u:p@h:port/dbname` -> `.../new_db`."""
    base, _, _ = url.rpartition("/")
    return f"{base}/{new_db}"


def _swap_redis_db(url: str, db_num: int) -> str:
    """`redis://:pass@host:port/N` -> `.../db_num`."""
    base, _, _ = url.rpartition("/")
    return f"{base}/{db_num}"


def _maintenance_url(url: str) -> str:
    """Build an asyncpg URL pointing at the `postgres` maintenance DB,
    stripping SQLAlchemy's `+asyncpg` dialect prefix that asyncpg
    itself does not recognise.
    """
    base, _, _ = url.rpartition("/")
    base = base.replace("postgresql+asyncpg://", "postgresql://")
    return f"{base}/postgres"


def _worker_redis_db(worker_id: str) -> int:
    """Map a worker id to a Redis logical DB number in [1..15].

    Redis defaults to 16 logical DBs (0..15). db 0 is reserved for prod.
    Master worker (no xdist) -> 1. xdist workers: gw0 -> 2, gw1 -> 3,
    ..., wrapping at 15 (so >14 workers collide; we never realistically
    run that many).
    """
    if worker_id == "master":
        return 1
    n = int(worker_id.removeprefix("gw"))
    return 2 + (n % 14)


# ---------------------------------------------------------------------------
# MinIO helpers (low-level aiobotocore, no `app.*` dependency)
# ---------------------------------------------------------------------------


def _s3_client_kwargs() -> dict[str, str]:
    return dict(
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        region_name=os.environ.get("MINIO_REGION", "us-east-1"),
    )


async def _create_bucket(bucket: str) -> None:
    """Create one MinIO bucket. Idempotent -- existing bucket is benign."""
    import aiobotocore.session
    from botocore.exceptions import ClientError

    session = aiobotocore.session.get_session()
    async with session.create_client("s3", **_s3_client_kwargs()) as client:
        try:
            await client.create_bucket(Bucket=bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise


async def _drop_bucket(bucket: str) -> None:
    """Empty + delete a MinIO bucket. Missing bucket -> no-op."""
    import aiobotocore.session
    from botocore.exceptions import ClientError

    session = aiobotocore.session.get_session()
    async with session.create_client("s3", **_s3_client_kwargs()) as client:
        try:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket):
                objs = page.get("Contents") or []
                if objs:
                    await client.delete_objects(
                        Bucket=bucket,
                        Delete={
                            "Objects": [{"Key": o["Key"]} for o in objs],
                            "Quiet": True,
                        },
                    )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "NoSuchBucket":
                raise

        try:
            await client.delete_bucket(Bucket=bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "NoSuchBucket":
                raise


async def _upload_platform_templates(bucket: str) -> None:
    """Walk `backend/scripts/templates/_default/<kind>/<lang>/*` and upload
    every file under `_platform/templates/<kind>/<lang>/<file>` in the
    worker's bucket.

    Mirrors what `install_cbshome.sh` does via `mc cp -r` for the prod
    bucket; done in Python here so we depend only on aiobotocore.
    """
    import aiobotocore.session

    # /app/scripts/templates/_default (the Dockerfile COPYies scripts/ to /app).
    templates_dir = Path(__file__).resolve().parent.parent / "scripts" / "templates" / "_default"
    if not templates_dir.exists():
        # Safety net for unusual local runs; production container always has it.
        return

    session = aiobotocore.session.get_session()
    async with session.create_client("s3", **_s3_client_kwargs()) as client:
        for kind_dir in sorted(templates_dir.iterdir()):
            if not kind_dir.is_dir():
                continue
            for lang_dir in sorted(kind_dir.iterdir()):
                if not lang_dir.is_dir():
                    continue
                for file_path in sorted(lang_dir.iterdir()):
                    if not file_path.is_file():
                        continue
                    key = (
                        f"_platform/templates/{kind_dir.name}/"
                        f"{lang_dir.name}/{file_path.name}"
                    )
                    body = file_path.read_bytes()
                    content_type = _content_type_for(file_path)
                    await client.put_object(
                        Bucket=bucket,
                        Key=key,
                        Body=body,
                        ContentType=content_type,
                    )


def _content_type_for(path: Path) -> str:
    """Tiny MIME mapper. The renderer reads files mostly for content,
    not content-type, but presigned URLs use this on download.
    """
    ext = path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".json": "application/json",
    }.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# Session-scoped fixtures -- app resources mirror main.py lifespan
# (init_redis + close_redis) MINUS the background daemons. Daemons are
# explicitly excluded; integration tests that exercise daemon logic call
# the underlying functions directly.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
async def init_app_resources() -> AsyncGenerator[None, None]:
    """Initialise the Redis client for the worker. The DB engine
    initialises lazily on first session use.
    """
    from app.core.redis import close_redis, init_redis

    await init_redis()
    yield
    await close_redis()


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncGenerator[Any, None]:
    """An httpx.AsyncClient bound to the FastAPI app via ASGITransport.

    Note: ASGITransport does NOT trigger FastAPI lifespan events. That
    is intentional -- lifespan starts background daemons that would
    mutate the worker DB out-of-band. init_redis() runs via the
    session-scoped init_app_resources fixture instead.
    """
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[Any, None]:
    """Direct read/write SQLAlchemy session on the worker DB.

    NO rollback magic. Commits inside tests are real commits -- but they
    target the worker DB, which disappears in pytest_unconfigure. Tests
    that need pristine state for a specific table use targeted DELETEs
    in their own setup (e.g. test_seed_platform_templates wipes
    platform-default rows before each scenario).
    """
    from app.core.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture(autouse=True)
def mock_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the verification email in tests. Otherwise we hit SMTP
    timeouts in the test environment because Mailgun / Postfix are not
    expected to be reachable from container land.
    """

    async def _noop(_email: str, _code: str) -> None:
        return None

    monkeypatch.setattr(
        "app.modules.auth.service._send_verification_email", _noop
    )


@pytest.fixture(autouse=True)
async def clear_rate_limit() -> None:
    """Clear the email-auth rate-limit key before each test.

    The worker has its own Redis logical DB, so this is just defending
    against in-test repetition (a single test calling register_user
    more than auth_rate_limit_max_requests times within the window).
    """
    try:
        from app.core.redis import get_redis

        redis = get_redis()
        await redis.delete("email_auth:127.0.0.1")
    except RuntimeError:
        # init_redis hasn't fired yet (e.g. test collection error path).
        pass
