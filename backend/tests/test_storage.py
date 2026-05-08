# =============================================================================
# CBSHOME Backend -- Storage Layer Tests (Refactor 2 iter 2.1)
# =============================================================================
#
# Integration tests for app/core/storage.py. Run against the real MinIO
# instance from docker-compose (no moto, no mock) using the dedicated
# `cbshome-attachments-test` bucket created by minio-init.
#
# FIXTURE LIFECYCLE:
#   use_test_bucket (autouse, function-scoped):
#       1. Monkeypatch settings.minio_bucket -> "cbshome-attachments-test".
#       2. Wipe the bucket (list + delete every object).
#       3. Yield to the test.
#   The post-cleanup is intentionally skipped: pre-cleanup on the next
#   test handles it, and a failed test leaves the bucket in a state we
#   can inspect manually via `mc ls local/cbshome-attachments-test`.
#
# COVERAGE PER PUBLIC API:
#   upload_object            -> tests 1, 2, 5, 8, 10
#   delete_object            -> tests 8, 9
#   generate_presigned_url   -> test 10
#   object_exists            -> tests 3, 4, 8
#   get_object_metadata      -> tests 1, 7
#   get_object_bytes         -> tests 5, 6
#   list_objects             -> tests 11, 12
# =============================================================================

from collections.abc import AsyncGenerator

import httpx
import pytest

from app.core.config import settings
from app.core.storage import (
    StorageError,
    StorageNotFoundError,
    delete_object,
    generate_presigned_url,
    get_object_bytes,
    get_object_metadata,
    list_objects,
    object_exists,
    upload_object,
)

TEST_BUCKET = "cbshome-attachments-test"
TEST_PREFIX = "test_storage/"


# ---------------------------------------------------------------------------
# Fixture: redirect storage to the test bucket and keep it clean
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def use_test_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[None, None]:
    """Point storage at the test bucket and wipe it before each test."""
    monkeypatch.setattr(settings, "minio_bucket", TEST_BUCKET)

    # Drain the bucket -- previous test runs may have left objects.
    keys = await list_objects("")
    for key in keys:
        await delete_object(key)

    yield


# ---------------------------------------------------------------------------
# 1: upload_object + get_object_metadata roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_and_get_metadata() -> None:
    """upload + head returns matching size and content_type."""
    key = f"{TEST_PREFIX}meta.bin"
    payload = b"hello cbshome"

    returned_key = await upload_object(key, payload, "application/octet-stream")
    assert returned_key == key

    meta = await get_object_metadata(key)
    assert meta["size"] == len(payload)
    assert meta["content_type"] == "application/octet-stream"
    assert meta["last_modified"] is not None


# ---------------------------------------------------------------------------
# 2: upload_object overwrites existing key (versioning is OFF per spec §1.6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_overwrites_existing() -> None:
    """Uploading to the same key twice keeps only the latest payload."""
    key = f"{TEST_PREFIX}overwrite.txt"

    await upload_object(key, b"first", "text/plain")
    await upload_object(key, b"second", "text/plain")

    body = await get_object_bytes(key)
    assert body == b"second"


# ---------------------------------------------------------------------------
# 3: object_exists returns True for an uploaded object
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_object_exists_true() -> None:
    """exists() returns True after upload."""
    key = f"{TEST_PREFIX}exists.txt"
    await upload_object(key, b"x", "text/plain")
    assert await object_exists(key) is True


# ---------------------------------------------------------------------------
# 4: object_exists returns False for a missing key (no raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_object_exists_false_when_missing() -> None:
    """exists() returns False (does NOT raise) when the object is missing."""
    assert await object_exists(f"{TEST_PREFIX}does-not-exist") is False


# ---------------------------------------------------------------------------
# 5: get_object_bytes roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_object_bytes_roundtrip() -> None:
    """Bytes uploaded equal bytes downloaded."""
    key = f"{TEST_PREFIX}roundtrip.bin"
    payload = b"\x00\x01\x02ABC\xff" * 100  # binary noise

    await upload_object(key, payload, "application/octet-stream")
    body = await get_object_bytes(key)

    assert body == payload


# ---------------------------------------------------------------------------
# 6: get_object_bytes raises StorageNotFoundError on missing key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_object_bytes_not_found() -> None:
    """get_object_bytes raises StorageNotFoundError when object is missing."""
    with pytest.raises(StorageNotFoundError):
        await get_object_bytes(f"{TEST_PREFIX}missing.bin")


# ---------------------------------------------------------------------------
# 7: get_object_metadata raises StorageNotFoundError on missing key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_object_metadata_not_found() -> None:
    """get_object_metadata raises StorageNotFoundError when missing."""
    with pytest.raises(StorageNotFoundError):
        await get_object_metadata(f"{TEST_PREFIX}missing.bin")


# ---------------------------------------------------------------------------
# 8: delete_object removes the object
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_object() -> None:
    """delete() removes an existing object; subsequent exists() returns False."""
    key = f"{TEST_PREFIX}to-delete.txt"

    await upload_object(key, b"bye", "text/plain")
    assert await object_exists(key) is True

    await delete_object(key)
    assert await object_exists(key) is False


# ---------------------------------------------------------------------------
# 9: delete_object is idempotent on missing key (no raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_object_idempotent_when_missing() -> None:
    """delete() on a missing key is a no-op (mirrors S3 semantics)."""
    # Must not raise.
    await delete_object(f"{TEST_PREFIX}never-existed.txt")


# ---------------------------------------------------------------------------
# 10: generate_presigned_url returns a working URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_presigned_url_works() -> None:
    """Presigned URL fetches the object body without any auth headers.

    Validates the full round-trip through MinIO -- if the URL is
    malformed, the signature is wrong, or the endpoint is unreachable,
    httpx will surface it.
    """
    key = f"{TEST_PREFIX}presigned.txt"
    payload = b"hello presigned"
    await upload_object(key, payload, "text/plain")

    url = await generate_presigned_url(key, ttl_seconds=60)
    assert url.startswith("http"), "expected an http(s) URL"

    async with httpx.AsyncClient() as http:
        response = await http.get(url)
    assert response.status_code == 200
    assert response.content == payload


# ---------------------------------------------------------------------------
# 11: list_objects returns empty list for an empty prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_objects_empty_prefix() -> None:
    """list_objects returns [] when no objects match the prefix."""
    keys = await list_objects(f"{TEST_PREFIX}nothing-here/")
    assert keys == []


# ---------------------------------------------------------------------------
# 12: list_objects returns full keys filtered by prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_objects_with_prefix_filter() -> None:
    """list_objects returns only keys starting with the given prefix."""
    a1 = f"{TEST_PREFIX}groupA/file1.txt"
    a2 = f"{TEST_PREFIX}groupA/file2.txt"
    b1 = f"{TEST_PREFIX}groupB/file1.txt"

    await upload_object(a1, b"a1", "text/plain")
    await upload_object(a2, b"a2", "text/plain")
    await upload_object(b1, b"b1", "text/plain")

    listed = sorted(await list_objects(f"{TEST_PREFIX}groupA/"))
    assert listed == sorted([a1, a2])

    listed_all = sorted(await list_objects(TEST_PREFIX))
    assert listed_all == sorted([a1, a2, b1])


# ---------------------------------------------------------------------------
# 13: StorageError surfaces unexpected ClientError (smoke -- bad bucket)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_to_nonexistent_bucket_raises_storage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pointing at a bucket that doesn't exist raises StorageError, not raw ClientError."""
    monkeypatch.setattr(settings, "minio_bucket", "definitely-does-not-exist-xyz")

    with pytest.raises(StorageError):
        await upload_object("any-key", b"x", "text/plain")
