# =============================================================================
# AIVIS.ONE Backend -- Storage Abstraction Layer (Refactor 2 iter 2.1)
# =============================================================================
#
# Thin async wrapper around aiobotocore for the S3-compatible object
# storage (RustFS since H32 P-120; MinIO before it). Business code
# never imports aiobotocore directly -- it goes
# through this module. See AIVIS-Refactor-Company-Docs.md §2.
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
#   StorageError              -- generic upstream failure, including a
#                                missing bucket.
#   StorageNotFoundError      -- the requested KEY does not exist in an
#                                otherwise-healthy bucket.
#
#   These are intentionally distinct: a missing bucket points at a broken
#   stack (typo in STORAGE_BUCKET, failed storage-init) and must NOT be
#   silently treated as "object missing".
#
# HEAD-BASED DISAMBIGUATION:
#   S3 servers return a generic HTTP 404 for `head_object` on both
#   "key missing" and "bucket missing" cases (it does NOT echo
#   NoSuchBucket the way put_object / get_object / delete_object do).
#   So object_exists() and get_object_metadata() additionally call
#   head_bucket() when they receive a 404, to tell the two apart.
#   This costs one extra round-trip in the negative path; we accept it
#   because these functions are called from read endpoints that are not
#   in any hot path.
#
#   delete_object and get_object_bytes do NOT need this disambiguation
#   because their underlying S3 calls (DeleteObject, GetObject) report
#   NoSuchBucket explicitly.
#
# CLIENT LIFECYCLE:
#   aiobotocore session is a module-level lazy singleton. Each public
#   call opens a short-lived S3 client via `async with session.create_client`.
#   Per-call client is intentional: low traffic in MVP, no benefit from
#   keeping a long-lived client; per-call avoids leaked connections on
#   error paths and is trivially compatible with pytest's nested loops.
#
# BUCKET:
#   Every call reads settings.storage_bucket fresh. Tests redirect to
#   `aivis-attachments-test` via monkeypatch on settings.
#
# DELETE IDEMPOTENCY:
#   delete_object on a missing KEY is a no-op (logged, no raise). A
#   missing BUCKET still raises StorageError -- see exception note above.
# =============================================================================

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, BinaryIO

import aiobotocore.session
import structlog
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError

from app.core.config import settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StorageError(Exception):
    """Generic upstream storage failure (network, auth, missing bucket, etc).

    A missing bucket lands here, not in StorageNotFoundError -- a missing
    bucket means the deployment is broken, not that we're looking up a
    missing object.
    """


class StorageNotFoundError(StorageError):
    """The requested object KEY does not exist (bucket is otherwise OK)."""


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


# SigV4 and path-style, stated rather than left to botocore's defaults.
# Without signature_version botocore PRESIGNS with SigV2
# (AWSAccessKeyId/Signature/Expires): a deprecated scheme whose signature
# does not cover the host. SigV4 binds every link to the host it was
# signed for -- which is what lets one client sign for the public address
# while the other talks to the storage on the internal one (H32 P-121).
# Path-style (<endpoint>/<bucket>/<key>) because the public site proxies
# one host to the storage; virtual-host buckets would need a host per
# bucket.
_S3_CONFIG = AioConfig(
    signature_version="s3v4",
    s3={"addressing_style": "path"},
)


def _client_context(endpoint_url: str | None = None) -> Any:
    """Open an async context manager that yields an S3 client.

    endpoint_url defaults to the INTERNAL address (settings.storage_endpoint)
    every operation goes to. _presign_client_context passes the public one.

    Reads settings on every call so test monkeypatches on
    settings.storage_endpoint / storage_access_key / storage_secret_key /
    storage_region apply without reloading the module.
    """
    return _get_session().create_client(
        "s3",
        endpoint_url=endpoint_url or settings.storage_endpoint,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name=settings.storage_region,
        config=_S3_CONFIG,
    )


def _presign_client_context() -> Any:
    """A client that SIGNS links for the address a browser can reach.

    Signing is a computation -- no request leaves the process -- so this
    client never needs to reach settings.storage_public_url itself. The
    public storage site forwards the request to the storage with
    the Host header unchanged, and the SigV4 signature, made for that host,
    verifies there. Empty storage_public_url (development only; the
    validator refuses it elsewhere) signs for the internal address, which
    a laptop and the test runner can reach directly.
    """
    return _client_context(settings.storage_public_url or None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Codes that mean "the KEY does not exist" -- bucket is fine.
# botocore normalises some HTTP 404s into the literal "404" while named
# operations (head_object) return "NoSuchKey". On the storage specifically,
# head_object also returns "404" when the BUCKET is missing, which is
# why object_exists() / get_object_metadata() additionally probe with
# head_bucket() to disambiguate.
_KEY_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey"})


def _is_key_not_found(exc: ClientError) -> bool:
    """True iff the ClientError code is in the "key missing" set.

    Note: on the storage head_object also returns "404" for a missing bucket,
    so callers that use head_object must additionally verify the bucket
    via _assert_bucket_exists() before treating the error as "key gone".
    """
    code = exc.response.get("Error", {}).get("Code", "")
    return code in _KEY_NOT_FOUND_CODES


async def _assert_bucket_exists(client: Any) -> None:
    """Raise StorageError if the configured bucket is missing or unreachable.

    Used by head_object-based functions to disambiguate "key not found"
    from "bucket not found", because the storage collapses both into HTTP 404
    on head_object responses.

    Args:
        client: An open aiobotocore S3 client (from _client_context()).

    Raises:
        StorageError: If head_bucket fails for any reason -- bucket
            missing, auth refused, network broken, etc.
    """
    try:
        await client.head_bucket(Bucket=settings.storage_bucket)
    except ClientError as exc:
        logger.error(
            "storage_bucket_missing",
            bucket=settings.storage_bucket,
            error=str(exc),
        )
        raise StorageError(
            f"Bucket {settings.storage_bucket!r} is missing or unreachable: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def upload_object(
    key: str,
    data: bytes | BinaryIO,
    content_type: str,
    *,
    content_length: int | None = None,
) -> str:
    """Upload an object to the configured bucket.

    Args:
        key: Object key (full path, no leading slash).
        data: bytes or a binary file-like object readable in one pass.
            For file-like objects, the file pointer must be at the start
            of the payload (caller's responsibility).
        content_type: MIME type stored as object metadata.
        content_length: Explicit body length in bytes. Required when
            `data` is a non-seekable stream so the storage gets a proper
            Content-Length header instead of falling back to chunked
            transfer encoding. Optional when `data` is `bytes` (boto3
            derives the length automatically).

    Returns:
        The stored key (echoed for caller convenience).

    Raises:
        StorageError: On any upstream failure, including a missing bucket.
    """
    # ContentLength is forwarded straight to the storage. For bytes the param
    # is redundant but harmless; for streams it's the only way to avoid
    # `Transfer-Encoding: chunked`, which some S3-compatible setups
    # (and signature-v4 in strict mode) reject.
    extra: dict[str, int] = {}
    if content_length is not None:
        extra["ContentLength"] = content_length

    try:
        async with _client_context() as client:
            await client.put_object(
                Bucket=settings.storage_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                **extra,
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
        bucket=settings.storage_bucket,
    )
    return key


async def delete_object(key: str) -> None:
    """Delete an object. Idempotent on a missing KEY; raises on a missing BUCKET.

    DeleteObject on the storage reports NoSuchBucket explicitly (not as a
    generic 404), so we don't need head_bucket disambiguation here.

    Args:
        key: Object key.

    Raises:
        StorageError: Missing bucket, auth failure, network error, etc.
    """
    try:
        async with _client_context() as client:
            await client.delete_object(
                Bucket=settings.storage_bucket,
                Key=key,
            )
    except ClientError as exc:
        if _is_key_not_found(exc):
            logger.info("storage_delete_missing_key", key=key)
            return
        logger.error("storage_delete_failed", key=key, error=str(exc))
        raise StorageError(f"Failed to delete {key}: {exc}") from exc

    logger.info("storage_deleted", key=key, bucket=settings.storage_bucket)


async def generate_presigned_url(
    key: str,
    ttl_seconds: int,
    *,
    download_filename: str | None = None,
) -> str:
    """Generate a presigned GET URL for downloading the object.

    The URL is signed with the backend service account for the PUBLIC
    storage address (settings.storage_public_url), so the browser can open
    it directly; the caller needs no storage credentials. Returned as JSON
    by the attachment, KYC and roadmap-cover endpoints, and opened by the
    frontend as a navigation.

    Args:
        key: Object key.
        ttl_seconds: URL validity (in seconds). Spec mandates 900 for
            authenticated downloads, 86400 for public downloads.
        download_filename: When provided, instructs the browser via
            Content-Disposition: attachment; filename="..." to download
            the object instead of rendering it inline. This is the
            primary defence against stored-XSS through an SVG/HTML
            payload uploaded under a "trusted" extension (Round 4
            SEC-01). The storage honours the boto3 `ResponseContentDisposition`
            param by adding `response-content-disposition=...` to the
            signed URL, so the browser sees the header on GET.

    Returns:
        Full URL on the public storage address.

    Raises:
        StorageError: On any upstream failure.
    """
    params: dict[str, str] = {
        "Bucket": settings.storage_bucket,
        "Key": key,
    }
    if download_filename:
        # Quote the filename to keep RFC-6266-friendly and safe against
        # whitespace / unicode in the attachment name.
        safe_name = download_filename.replace('"', "")
        params["ResponseContentDisposition"] = (
            f'attachment; filename="{safe_name}"'
        )

    try:
        async with _presign_client_context() as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=ttl_seconds,
            )
    except ClientError as exc:
        logger.error("storage_presign_failed", key=key, error=str(exc))
        raise StorageError(f"Failed to presign {key}: {exc}") from exc

    return str(url)


async def object_exists(key: str) -> bool:
    """Check whether the object exists.

    Returns False on a missing KEY in a healthy bucket. Raises
    StorageError on a missing BUCKET or any other upstream failure.

    Implementation note: the storage's head_object returns HTTP 404 for both
    "key missing" and "bucket missing", so we disambiguate by probing
    head_bucket on every 404. One extra round-trip in the negative path.
    """
    async with _client_context() as client:
        try:
            await client.head_object(
                Bucket=settings.storage_bucket,
                Key=key,
            )
            return True
        except ClientError as exc:
            if not _is_key_not_found(exc):
                logger.error("storage_head_failed", key=key, error=str(exc))
                raise StorageError(f"Failed to HEAD {key}: {exc}") from exc
            # Got a "key not found"-style code. On the storage this also fires
            # for missing buckets -- verify the bucket independently.
            # _assert_bucket_exists raises StorageError if the bucket is
            # missing; otherwise execution continues and we return False.
            await _assert_bucket_exists(client)
            return False


async def get_object_metadata(key: str) -> dict[str, Any]:
    """Fetch object metadata via HEAD.

    Returns:
        dict with keys:
            "size"          -- int, bytes
            "content_type"  -- str (may be "" if not set on upload)
            "last_modified" -- datetime (timezone-aware UTC)

    Raises:
        StorageNotFoundError: When the KEY is missing in an existing bucket.
        StorageError: When the BUCKET is missing or on any other failure.

    Implementation note: same head_bucket disambiguation as object_exists.
    """
    async with _client_context() as client:
        try:
            response = await client.head_object(
                Bucket=settings.storage_bucket,
                Key=key,
            )
        except ClientError as exc:
            if not _is_key_not_found(exc):
                logger.error("storage_head_failed", key=key, error=str(exc))
                raise StorageError(f"Failed to HEAD {key}: {exc}") from exc
            # Key-not-found code received. Disambiguate vs missing bucket.
            await _assert_bucket_exists(client)
            raise StorageNotFoundError(f"Object not found: {key}") from exc

    return {
        "size": int(response.get("ContentLength", 0)),
        "content_type": response.get("ContentType", "") or "",
        "last_modified": response.get("LastModified"),
    }


async def get_object_bytes(key: str) -> bytes:
    """Download the full object body as bytes.

    WARNING: loads the entire object into memory. Suitable for templates
    and metadata files (typically under 2 MB). For arbitrary attachments,
    prefer generate_presigned_url() so the client downloads directly
    from the storage without going through the backend process.

    Used by the templates module (Refactor 2 iter 2.2 §4.4) to render
    HTML stored in the storage, and by reconcile scripts that need to inspect
    companion `.cbsmeta.json` files.

    GetObject on the storage reports NoSuchBucket explicitly (not as a generic
    404), so we don't need head_bucket disambiguation here.

    Raises:
        StorageNotFoundError: When the KEY is missing in an existing bucket.
        StorageError: When the BUCKET is missing or on any other failure.
    """
    try:
        async with _client_context() as client:
            response = await client.get_object(
                Bucket=settings.storage_bucket,
                Key=key,
            )
            # Body is a StreamingBody (async). Read fully then close.
            async with response["Body"] as stream:
                payload: bytes = await stream.read()
                return payload
    except ClientError as exc:
        if _is_key_not_found(exc):
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
        StorageError: On any upstream failure, including missing bucket.
    """
    keys: list[str] = []
    try:
        async with _client_context() as client:
            paginator = client.get_paginator("list_objects_v2")
            page_iter: AsyncIterator[dict[str, Any]] = paginator.paginate(
                Bucket=settings.storage_bucket,
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
