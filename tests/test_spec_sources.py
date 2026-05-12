import pytest


@pytest.mark.asyncio
async def test_create_spec_source_passthrough_jwt(client):
    resp = await client.post(
        "/v1/spec-sources",
        json={
            "id": "billing",
            "url": "https://billing.internal/openapi.json",
            "description": "Invoices, refunds, subscriptions.",
            "auth": {"type": "passthrough_jwt"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == "billing"
    assert body["auth"]["type"] == "passthrough_jwt"
    assert body["operation_count"] is None
    assert body["last_fetched_at"] is None


@pytest.mark.asyncio
async def test_create_spec_source_bearer_env(client):
    resp = await client.post(
        "/v1/spec-sources",
        json={
            "id": "billing",
            "url": "https://billing.internal/openapi.json",
            "description": "Invoices, refunds, subscriptions.",
            "auth": {"type": "bearer_env", "env_var": "BILLING_API_TOKEN"},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["auth"]["env_var"] == "BILLING_API_TOKEN"


@pytest.mark.asyncio
async def test_create_spec_source_basic_env(client):
    resp = await client.post(
        "/v1/spec-sources",
        json={
            "id": "legacy",
            "url": "https://legacy.internal/openapi.json",
            "description": "Legacy reporting endpoints.",
            "auth": {
                "type": "basic_env",
                "username_env": "LEGACY_USER",
                "password_env": "LEGACY_PASS",
            },
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_invalid_spec_id_rejected(client):
    resp = await client.post(
        "/v1/spec-sources",
        json={
            "id": "Billing",  # uppercase not allowed
            "url": "https://billing.internal/openapi.json",
            "description": "Invoices.",
            "auth": {"type": "none"},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_auth_type_rejected(client):
    resp = await client.post(
        "/v1/spec-sources",
        json={
            "id": "billing",
            "url": "https://billing.internal/openapi.json",
            "description": "Invoices.",
            "auth": {"type": "made_up"},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bearer_env_requires_env_var(client):
    resp = await client.post(
        "/v1/spec-sources",
        json={
            "id": "billing",
            "url": "https://billing.internal/openapi.json",
            "description": "Invoices.",
            "auth": {"type": "bearer_env"},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_spec_id_returns_409(client):
    body = {
        "id": "billing",
        "url": "https://billing.internal/openapi.json",
        "description": "Invoices.",
        "auth": {"type": "none"},
    }
    first = await client.post("/v1/spec-sources", json=body)
    assert first.status_code == 201

    second = await client.post("/v1/spec-sources", json=body)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_list_spec_sources(client):
    await client.post("/v1/spec-sources", json={
        "id": "billing", "url": "https://x/openapi.json", "description": "a",
        "auth": {"type": "none"},
    })
    await client.post("/v1/spec-sources", json={
        "id": "identity", "url": "https://y/openapi.json", "description": "b",
        "auth": {"type": "none"},
    })

    resp = await client.get("/v1/spec-sources")
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = sorted(item["id"] for item in items)
    assert ids == ["billing", "identity"]


@pytest.mark.asyncio
async def test_get_spec_source(client):
    await client.post("/v1/spec-sources", json={
        "id": "billing", "url": "https://x/openapi.json", "description": "a",
        "auth": {"type": "none"},
    })

    resp = await client.get("/v1/spec-sources/billing")
    assert resp.status_code == 200
    assert resp.json()["id"] == "billing"


@pytest.mark.asyncio
async def test_get_nonexistent_spec_source_returns_404(client):
    resp = await client.get("/v1/spec-sources/nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_spec_source(client):
    await client.post("/v1/spec-sources", json={
        "id": "billing", "url": "https://x/openapi.json", "description": "a",
        "auth": {"type": "none"},
    })

    resp = await client.delete("/v1/spec-sources/billing")
    assert resp.status_code == 204

    follow = await client.get("/v1/spec-sources/billing")
    assert follow.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_spec_source_returns_404(client):
    resp = await client.delete("/v1/spec-sources/nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauth_create_rejected(unauth_client):
    resp = await unauth_client.post("/v1/spec-sources", json={
        "id": "billing", "url": "https://x/openapi.json", "description": "a",
        "auth": {"type": "none"},
    })
    assert resp.status_code == 403
