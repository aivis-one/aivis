# =============================================================================
# CBSHOME Backend -- Storage Abstraction Layer (Refactor 2 iter 2.1)
# =============================================================================
#
# Thin async wrapper around aiobotocore for MinIO (S3-compatible) object
# storage. Business code never imports aiobotocore directly -- it goes
# through this module. See CBSHOME-Refactor-Company-Docs.md §2.
#
# PUBLIC API (per spec §2.1):
#   upload_object(key, data, content_type) -> str
#   delete_object(key) -> None
#   generate_presigned_url(key, ttl_seconds) -> str
#   object_exists(key) -> bool
#   get_object_metadata(key) -> dict
#   get_object_bytes(key) -> bytes
#   list_objects(prefix) -> list[str]      # extension, used by reconcile
#
# EXCEPTIONS:
#   StorageError              -- generic upstream failure
#   StorageNotFoundError      -- object not found (404 / NoSuchKey)
#
# CLIENT LIFECYCLE:
#   aiobotocore session is a module-level lazy singleton. Each public
#   call opens a short-lived S3 client via `async with session.create_client`.
#   Per-call client is intentional: low traffic in MVP, no benefit from
#   keeping a long-lived client; per-call avoids leaked connections on
#   error paths and is trivially compatible with pytest's nested loops.
#
# BUCKET:
#   Every call reads settings.minio_bucket fresh. Tests redirect to
#   `cbshome-attachments-test` via monkeypatch on settings.
#
# DELETE IDEMPOTENCY:
#   delete_object on a missing key is a no-op (logged, no raise).
#   Mirrors S3 default semantics and lets reconcile run repeatedly.
# =============================================================================

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, BinaryIO

import aiobotocore.session
import structlog
from botocore.exceptions import ClientError

from app.core.config import settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StorageError(Exception):
    """Generic upstream storage failure (network, auth, server-side error)."""


class StorageNotFoundError(StorageError):
    """The requested object does not exist in the bucket."""


# ---------------------------------------------------------------------------
# Session / client factory
# ---------------------------------------------------------------------------


# Module-level singleton. Created on first use; aiobotocore Sessions are
# cheap, but a single instance keeps any internal caches warm.
_session: aiobotocore.session.AioSession | None = None


def _get_session() -> aiobotocore.session.AioSession:
    """Return the module-level aiobotocore session (lazy init)."""
    global _session
    if _session is None:
        _session = aiobotocore.session.get_session()
    return _session


def _client_context() -> Any:
    """Open an async context manager that yields an S3 client.

    Reads settings on every call so test monkeypatches on
    settings.minio_endpoint / minio_access_key / minio_secret_key /
    minio_region apply without reloading the module.
    """
    return _get_session().create_client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name=settings.minio_region,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Error codes that S3 (or MinIO) returns when an object or bucket is
# missing. botocore normalises some HTTP 404s into "404" while named
# operations (head_object) return "NoSuchKey".
_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NoSuchBucket"})


def _is_not_found(exc: ClientError) -> bool:
    """True when the ClientError represents a missing-object / -bucket."""
    code = exc.response.get("Error", {}).get("Code", "")
    return code in _NOT_FOUND_CODES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def upload_object(
    key: str,
    data: bytes | BinaryIO,
    content_type: str,
) -> str:
    """Upload an object to the configured bucket.

    Args:
        key: Object key (full path, no leading slash).
        data: bytes or a binary file-like object readable in one pass.
        content_type: MIME type stored as object metadata.

    Returns:
        The stored key (echoed for caller convenience).

    Raises:
        StorageError: On any upstream failure.
    """
    try:
        async with _client_context() as client:
            await client.put_object(
                Bucket=settings.minio_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
    except ClientError as exc:
        logger.error(
            "storage_upload_failed",
            key=key,
            content_type=content_type,
            error=str(exc),
        )
        raise StorageError(f"Failed to upload {key}: {exc}") from exc

    logger.info(
        "storage_uploaded",
        key=key,
        content_type=content_type,
        bucket=settings.minio_bucket,
    )
    return key


async def delete_object(key: str) -> None:
    """Delete an object. Idempotent: missing object is logged and ignored.

    Args:
        key: Object key.

    Raises:
        StorageError: On any upstream failure other than "missing".
    """
    try:
        async with _client_context() as client:
            await client.delete_object(
                Bucket=settings.minio_bucket,
                Key=key,
            )
    except ClientError as exc:
        if _is_not_found(exc):
            logger.info("storage_delete_missing", key=key)
            return
        logger.error("storage_delete_failed", key=key, error=str(exc))
        raise StorageError(f"Failed to delete {key}: {exc}") from exc

    logger.info("storage_deleted", key=key, bucket=settings.minio_bucket)


async def generate_presigned_url(key: str, ttl_seconds: int) -> str:
    """Generate a presigned GET URL for downloading the object.

    The URL is signed with the backend service account; the caller does
    not need any MinIO credentials. Used for 302 redirects from auth
    and public download endpoints.

    Args:
        key: Object key.
        ttl_seconds: URL validity (in seconds). Spec mandates 900 for
            authenticated downloads, 86400 for public downloads.

    Returns:
        Full HTTPS URL.

    Raises:
        StorageError: On any upstream failure.
    """
    try:
        async with _client_context() as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.minio_bucket,
                    "Key": key,
                },
                ExpiresIn=ttl_seconds,
            )
    except ClientError as exc:
        logger.error("storage_presign_failed", key=key, error=str(exc))
        raise StorageError(f"Failed to presign {key}: {exc}") from exc

    return str(url)


async def object_exists(key: str) -> bool:
    """Check whether the object exists.

    Returns False on missing object. Raises StorageError on any other
    upstream failure (auth, network, etc).
    """
    try:
        async with _client_context() as client:
            await client.head_object(
                Bucket=settings.minio_bucket,
                Key=key,
            )
    except ClientError as exc:
        if _is_not_found(exc):
            return False
        logger.error("storage_head_failed", key=key, error=str(exc))
        raise StorageError(f"Failed to HEAD {key}: {exc}") from exc

    return True


async def get_object_metadata(key: str) -> dict[str, Any]:
    """Fetch object metadata via HEAD.

    Returns:
        dict with keys:
            "size"          -- int, bytes
            "content_type"  -- str (may be "" if not set on upload)
            "last_modified" -- datetime (timezone-aware UTC)

    Raises:
        StorageNotFoundError: When the object is missing.
        StorageError: On any other upstream failure.
    """
    try:
        async with _client_context() as client:
            response = await client.head_object(
                Bucket=settings.minio_bucket,
                Key=key,
            )
    except ClientError as exc:
        if _is_not_found(exc):
            raise StorageNotFoundError(f"Object not found: {key}") from exc
        logger.error("storage_head_failed", key=key, error=str(exc))
        raise StorageError(f"Failed to HEAD {key}: {exc}") from exc

    return {
        "size": int(response.get("ContentLength", 0)),
        "content_type": response.get("ContentType", "") or "",
        "last_modified": response.get("LastModified"),
    }


async def get_object_bytes(key: str) -> bytes:
    """Download the full object body as bytes.

    Used by the templates module (Refactor 2 iter 2.2 §4.4) to render
    HTML stored in MinIO, and by reconcile scripts that need to inspect
    companion `.cbsmeta.json` files.

    Raises:
        StorageNotFoundError: When the object is missing.
        StorageError: On any other upstream failure.
    """
    try:
        async with _client_context() as client:
            response = await client.get_object(
                Bucket=settings.minio_bucket,
                Key=key,
            )
            # Body is a StreamingBody (async). Read fully then close.
            async with response["Body"] as stream:
                payload: bytes = await stream.read()
                return payload
    except ClientError as exc:
        if _is_not_found(exc):
            raise StorageNotFoundError(f"Object not found: {key}") from exc
        logger.error("storage_get_failed", key=key, error=str(exc))
        raise StorageError(f"Failed to GET {key}: {exc}") from exc


async def list_objects(prefix: str) -> list[str]:
    """List object keys whose path starts with the given prefix.

    Used by reconcile scripts (Refactor 2 iter 2.1 §3.7, iter 2.2 §4.8,
    iter 2.3 §4.9) to scan inbox folders. Returned keys are full paths
    (NOT stripped of the prefix). Order is not guaranteed -- callers
    that need stable order should sort.

    Pagination is handled internally; the result is fully materialised
    in memory. For our scale (a few thousand objects per bucket at
    most) this is fine.

    Args:
        prefix: Key prefix (e.g. "companies/<uuid>/inbox/"). May be
            empty to list the entire bucket.

    Returns:
        List of full object keys. Empty list if no matches.

    Raises:
        StorageError: On any upstream failure.
    """
    keys: list[str] = []
    try:
        async with _client_context() as client:
            paginator = client.get_paginator("list_objects_v2")
            page_iter: AsyncIterator[dict[str, Any]] = paginator.paginate(
                Bucket=settings.minio_bucket,
                Prefix=prefix,
            )
            async for page in page_iter:
                for obj in page.get("Contents", []) or []:
                    key = obj.get("Key")
                    if isinstance(key, str):
                        keys.append(key)
    except ClientError as exc:
        logger.error("storage_list_failed", prefix=prefix, error=str(exc))
        raise StorageError(f"Failed to list {prefix!r}: {exc}") from exc

    return keys
