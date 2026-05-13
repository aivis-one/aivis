#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Bootstrap Test Template Database
#                     (iter 2.5 mini-fix #3 -- pytest isolation rewrite)
# =============================================================================
#
# WHAT THIS DOES (run once per `cbshome update`, before pytest):
#
#   1. Drop every stale `cbshome_test_*` database in Postgres. Crashed
#      pytest workers can leave their per-worker DB behind; this is the
#      garbage collector.
#   2. Drop every stale `cbshome-attachments-pytest-*` bucket in MinIO,
#      same reasoning -- emptied + deleted.
#   3. Create the FROZEN template DB `cbshome_test_template`:
#        a) DROP IF EXISTS (with FORCE -- terminates any stragglers).
#        b) CREATE DATABASE.
#        c) alembic upgrade head against the template.
#        d) seed_platform.py against the template (Platform user --
#           singleton row some tests rely on via record_audit).
#        e) seed_platform_templates.py against the template (16 active
#           platform-default rows for find_active_template stage 4).
#
# AFTER THIS:
#   The template DB is ready. pytest workers in conftest.py do
#   `CREATE DATABASE cbshome_test_<worker> TEMPLATE cbshome_test_template`
#   which clones the file directory on disk -- takes ~100ms instead of
#   running migrations+seeds again per worker.
#
# WHY THIS LIVES OUTSIDE conftest.py:
#   pytest_configure runs once per worker; the bootstrap must run BEFORE
#   any worker starts. Cleanest split: this script is the producer of
#   the template, conftest.py is the consumer. install_cbshome.sh runs
#   this in `cbshome update` BEFORE pytest.
#
# IDEMPOTENCY:
#   Every step is idempotent. Re-running is safe (and intended -- a
#   developer who manually re-runs after fixing a migration just
#   restarts the bootstrap to rebuild the template).
#
# CONNECTION CONTRACT:
#   asyncpg connects to the `postgres` maintenance database, NOT to the
#   template (CREATE DATABASE ... TEMPLATE forbids connections to the
#   template). Subprocess calls (alembic, seeds) open their own
#   connections to the template using DATABASE_URL override and close
#   them at process exit; by the time conftest.py runs, no process has
#   the template open.
#
# CLI:
#   docker compose exec -T app python -m scripts.bootstrap_test_template
# =============================================================================

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Ensure app package is importable when running as standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))


TEMPLATE_DB_NAME = "cbshome_test_template"
TEMPLATE_PREFIX = "cbshome_test_"
BUCKET_PREFIX = "cbshome-attachments-pytest-"


# ---------------------------------------------------------------------------
# Colour helpers (match the other scripts/ files)
# ---------------------------------------------------------------------------

G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[BOOTSTRAP-TEST]{N} {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}", flush=True)


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}", flush=True)


# ---------------------------------------------------------------------------
# URL manipulation
# ---------------------------------------------------------------------------


def _read_database_url() -> str:
    """Read DATABASE_URL from the environment. Crashes fast if missing --
    bootstrap cannot proceed without a Postgres target.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Run inside the app container, "
            "where docker-compose injects it from .env."
        )
    return url


def _swap_dbname(url: str, new_db: str) -> str:
    """Replace the database name in a DATABASE_URL by rewriting the
    segment after the LAST slash. Robust against passwords containing
    slashes (asyncpg URL-encodes those anyway, but rsplit is defensive).
    """
    base, _, _ = url.rpartition("/")
    return f"{base}/{new_db}"


def _maintenance_url(url: str) -> str:
    """Build an asyncpg-compatible maintenance URL.

    SQLAlchemy uses `postgresql+asyncpg://...` -- asyncpg's connect()
    does not recognise the `+asyncpg` dialect prefix, so strip it. Point
    at the `postgres` database (always present in a stock cluster) so we
    can DROP / CREATE other databases without holding them open.
    """
    base, _, _ = url.rpartition("/")
    base = base.replace("postgresql+asyncpg://", "postgresql://")
    return f"{base}/postgres"


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------


async def _drop_stale_test_dbs(maintenance_url: str) -> None:
    """Drop every database whose name starts with cbshome_test_, including
    the template itself.

    Connections to the doomed DBs are terminated via `WITH (FORCE)`
    (Postgres 13+ feature, our stack is 16). pg_terminate_backend is
    implicit there.
    """
    import asyncpg

    conn = await asyncpg.connect(maintenance_url)
    try:
        rows = await conn.fetch(
            "SELECT datname FROM pg_database WHERE datname LIKE $1",
            f"{TEMPLATE_PREFIX}%",
        )
        if not rows:
            log("no stale cbshome_test_* databases found")
            return

        for row in rows:
            name = row["datname"]
            await conn.execute(
                f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'
            )
            log(f"dropped stale database: {name}")
    finally:
        await conn.close()


async def _create_template_db(maintenance_url: str) -> None:
    """Create an empty cbshome_test_template database.

    Caller has already dropped any pre-existing copy in
    _drop_stale_test_dbs, so this is an unconditional CREATE.
    """
    import asyncpg

    conn = await asyncpg.connect(maintenance_url)
    try:
        await conn.execute(f'CREATE DATABASE "{TEMPLATE_DB_NAME}"')
        log(f"created database: {TEMPLATE_DB_NAME}")
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Subprocess pipeline against the template DB
# ---------------------------------------------------------------------------


def _run_against_template(*, prod_url: str, cmd: list[str], label: str) -> None:
    """Run a subprocess (alembic / seed) against the template DB.

    Overrides DATABASE_URL in the child environment so the child's
    `settings = Settings()` reads the template, not prod. The child is
    an independent Python interpreter, so module-level singletons (such
    as the lazy engine in app.core.database) do not leak from prod into
    the bootstrap.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = _swap_dbname(prod_url, TEMPLATE_DB_NAME)

    log(f"{label}: running {' '.join(cmd)}")
    result = subprocess.run(  # noqa: S603 -- internal command, no shell.
        cmd,
        cwd=str(_backend_dir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err(f"{label} failed (exit {result.returncode})")
        if result.stdout:
            err(f"stdout:\n{result.stdout}")
        if result.stderr:
            err(f"stderr:\n{result.stderr}")
        raise RuntimeError(f"bootstrap step {label!r} failed")
    log(f"{label}: ok")


def _populate_template(prod_url: str) -> None:
    """Run alembic + seeds against the freshly-created template DB."""
    # Alembic migrations.
    _run_against_template(
        prod_url=prod_url,
        cmd=["python", "-m", "alembic", "upgrade", "head"],
        label="alembic upgrade head",
    )

    # Platform user (singleton; required by record_audit for
    # actor_type="system" attribution from seed_platform_templates).
    _run_against_template(
        prod_url=prod_url,
        cmd=["python", "scripts/seed_platform.py"],
        label="seed_platform.py",
    )

    # 16 active platform-default CompanyDocumentTemplate rows.
    _run_against_template(
        prod_url=prod_url,
        cmd=["python", "-m", "scripts.seed_platform_templates"],
        label="seed_platform_templates",
    )


# ---------------------------------------------------------------------------
# MinIO helpers (low-level aiobotocore -- no dependency on app.*)
# ---------------------------------------------------------------------------


def _s3_client_kwargs() -> dict[str, str]:
    """Build the client kwargs from env vars. Same env-var names as
    app/core/storage.py so a docker-compose change touches both at once.
    """
    return dict(
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        region_name=os.environ.get("MINIO_REGION", "us-east-1"),
    )


async def _drop_stale_test_buckets() -> None:
    """Empty + delete every bucket whose name starts with
    cbshome-attachments-pytest-.

    The prefix is intentionally distinct from the shared
    `cbshome-attachments-test` bucket created by docker-compose minio-init
    (which other things might use); we own only `pytest-*`.
    """
    import aiobotocore.session
    from botocore.exceptions import ClientError

    session = aiobotocore.session.get_session()
    async with session.create_client("s3", **_s3_client_kwargs()) as client:
        try:
            response = await client.list_buckets()
        except ClientError as exc:
            err(f"list_buckets failed: {exc}")
            raise

        buckets = response.get("Buckets") or []
        targets = [b["Name"] for b in buckets if b["Name"].startswith(BUCKET_PREFIX)]
        if not targets:
            log("no stale cbshome-attachments-pytest-* buckets found")
            return

        for bucket in targets:
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
                await client.delete_bucket(Bucket=bucket)
                log(f"dropped stale bucket: {bucket}")
            except ClientError as exc:
                # Bucket vanished between list and delete -- benign.
                code = exc.response.get("Error", {}).get("Code", "")
                if code != "NoSuchBucket":
                    raise


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


async def bootstrap() -> None:
    """Run the full bootstrap pipeline. Single async entrypoint so the
    MinIO step and the Postgres step share one event loop.
    """
    prod_url = _read_database_url()
    maintenance_url = _maintenance_url(prod_url)

    # 1. Drop stale per-worker test DBs from previous crashed runs +
    #    the previous template.
    log("Cleaning stale test databases...")
    await _drop_stale_test_dbs(maintenance_url)

    # 2. Drop stale per-worker MinIO buckets.
    log("Cleaning stale test buckets...")
    await _drop_stale_test_buckets()

    # 3. Create empty template DB.
    log("Creating template database...")
    await _create_template_db(maintenance_url)

    # 4. Populate template via subprocess (alembic + seeds).
    log("Populating template (alembic + seeds)...")
    _populate_template(prod_url)

    log("Bootstrap complete.")


def main() -> None:
    try:
        asyncio.run(bootstrap())
    except Exception as exc:
        err(f"bootstrap failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
