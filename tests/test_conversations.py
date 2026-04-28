import pytest


@pytest.mark.asyncio
async def test_create_conversation(client):
    resp = await client.post("/v1/conversations", json={"title": "My Chat"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My Chat"
    assert "id" in data
    assert data["user_id"] == "test-user-123"


@pytest.mark.asyncio
async def test_list_conversations(client):
    await client.post("/v1/conversations", json={"title": "A"})
    await client.post("/v1/conversations", json={"title": "B"})
    resp = await client.get("/v1/conversations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_delete_conversation(client, conversation):
    conv_id = conversation["id"]
    resp = await client.delete(f"/v1/conversations/{conv_id}")
    assert resp.status_code == 204
    resp = await client.get("/v1/conversations")
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_conversation(client):
    resp = await client.delete("/v1/conversations/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("error", {}).get("code") == "not_found" or resp.status_code == 404


@pytest.mark.asyncio
async def test_auth_required(unauth_client):
    resp = await unauth_client.get("/v1/conversations")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pagination(client):
    for i in range(5):
        await client.post("/v1/conversations", json={"title": f"Conv {i}"})
    resp = await client.get("/v1/conversations?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
