import pytest


@pytest.mark.asyncio
async def test_get_config(client, conversation):
    conv_id = conversation["id"]
    resp = await client.get(f"/v1/conversations/{conv_id}/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == conv_id
    assert "model" in data
    assert "provider" in data
    assert "enabled_tools" in data


@pytest.mark.asyncio
async def test_update_config(client, conversation):
    conv_id = conversation["id"]
    resp = await client.patch(f"/v1/conversations/{conv_id}/config", json={
        "model": "gpt-4o",
        "provider": "openai",
        "enabled_tools": ["calculator"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "gpt-4o"
    assert data["provider"] == "openai"
    assert "calculator" in data["enabled_tools"]


@pytest.mark.asyncio
async def test_update_system_prompt(client, conversation):
    conv_id = conversation["id"]
    resp = await client.patch(f"/v1/conversations/{conv_id}/config", json={
        "system_prompt": "You are a pirate.",
    })
    assert resp.status_code == 200
    assert resp.json()["system_prompt"] == "You are a pirate."


@pytest.mark.asyncio
async def test_config_not_found(client):
    resp = await client.get("/v1/conversations/no-such/config")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_config_auth_required(unauth_client):
    resp = await unauth_client.get("/v1/conversations/any-id/config")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_enabled_specs(client, conversation):
    conv_id = conversation["id"]
    resp = await client.patch(f"/v1/conversations/{conv_id}/config", json={
        "enabled_specs": ["billing", "identity"],
    })
    assert resp.status_code == 200
    assert resp.json()["enabled_specs"] == ["billing", "identity"]


@pytest.mark.asyncio
async def test_get_config_includes_enabled_specs(client, conversation):
    conv_id = conversation["id"]
    resp = await client.get(f"/v1/conversations/{conv_id}/config")
    assert resp.status_code == 200
    assert "enabled_specs" in resp.json()
