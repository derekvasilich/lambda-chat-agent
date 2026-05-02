import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def make_mock_providers():
    mock_p = MagicMock()
    mock_p.list_models = AsyncMock(return_value=[{"id": "mock-model", "name": "Mock Model"}])
    return {"mock": mock_p}


@pytest.mark.asyncio
async def test_list_models(client):
    with patch("app.routers.models.list_providers", return_value=make_mock_providers()):
        resp = await client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["provider"] == "mock"
    assert data[0]["id"] == "mock-model"


@pytest.mark.asyncio
async def test_models_auth_required(unauth_client):
    resp = await unauth_client.get("/v1/models")
    assert resp.status_code == 403
