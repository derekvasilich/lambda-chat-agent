import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_health_ok(client):
    with patch("app.routers.health.list_providers", return_value={}):
        resp = await client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "version" in data
    assert "database" in data


@pytest.mark.asyncio
async def test_health_no_auth_required(unauth_client):
    with patch("app.routers.health.list_providers", return_value={}):
        resp = await unauth_client.get("/v1/health")
    assert resp.status_code == 200
