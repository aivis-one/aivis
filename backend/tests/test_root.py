# =============================================================================
# CBSHOME Backend -- Root Endpoint Tests
# =============================================================================

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_returns_api_info(client: AsyncClient) -> None:
    """GET / returns name and version."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "CBSHOME API"
    assert "version" in data


@pytest.mark.asyncio
async def test_root_version_is_string(client: AsyncClient) -> None:
    """Version field is a non-empty string."""
    response = await client.get("/")
    version = response.json()["version"]
    assert isinstance(version, str)
    assert len(version) > 0
