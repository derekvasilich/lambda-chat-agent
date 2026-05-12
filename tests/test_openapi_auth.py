import pytest

from app.openapi.auth import CompositeAuthResolver, RequestContext


def _ctx(token: str | None = None) -> RequestContext:
    return RequestContext(user_sub="u1", bearer_token=token)


@pytest.mark.asyncio
async def test_none_returns_empty_headers():
    r = CompositeAuthResolver()
    headers = await r.headers_for("billing", {"type": "none"}, _ctx())
    assert headers == {}


@pytest.mark.asyncio
async def test_passthrough_jwt_forwards_inbound_token():
    r = CompositeAuthResolver()
    headers = await r.headers_for(
        "billing", {"type": "passthrough_jwt"}, _ctx(token="eyJabc"),
    )
    assert headers == {"Authorization": "Bearer eyJabc"}


@pytest.mark.asyncio
async def test_passthrough_jwt_custom_header_name():
    r = CompositeAuthResolver()
    headers = await r.headers_for(
        "billing",
        {"type": "passthrough_jwt", "header_name": "X-Forwarded-Auth"},
        _ctx(token="eyJabc"),
    )
    assert headers == {"X-Forwarded-Auth": "Bearer eyJabc"}


@pytest.mark.asyncio
async def test_passthrough_jwt_raises_when_no_token():
    r = CompositeAuthResolver()
    with pytest.raises(PermissionError):
        await r.headers_for("billing", {"type": "passthrough_jwt"}, _ctx(token=None))


@pytest.mark.asyncio
async def test_bearer_env_uses_env_var(monkeypatch):
    monkeypatch.setenv("BILLING_TOKEN", "abc123")
    r = CompositeAuthResolver()
    headers = await r.headers_for(
        "billing", {"type": "bearer_env", "env_var": "BILLING_TOKEN"}, _ctx(),
    )
    assert headers == {"Authorization": "Bearer abc123"}


@pytest.mark.asyncio
async def test_bearer_env_missing_var_raises(monkeypatch):
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    r = CompositeAuthResolver()
    with pytest.raises(PermissionError):
        await r.headers_for(
            "billing", {"type": "bearer_env", "env_var": "MISSING_TOKEN"}, _ctx(),
        )


@pytest.mark.asyncio
async def test_api_key_env(monkeypatch):
    monkeypatch.setenv("INV_KEY", "k-789")
    r = CompositeAuthResolver()
    headers = await r.headers_for(
        "inventory",
        {"type": "api_key_env", "env_var": "INV_KEY", "header": "X-API-Key"},
        _ctx(),
    )
    assert headers == {"X-API-Key": "k-789"}


@pytest.mark.asyncio
async def test_basic_env(monkeypatch):
    monkeypatch.setenv("LU", "alice")
    monkeypatch.setenv("LP", "secret")
    r = CompositeAuthResolver()
    headers = await r.headers_for(
        "legacy",
        {"type": "basic_env", "username_env": "LU", "password_env": "LP"},
        _ctx(),
    )
    # Authorization: Basic <base64("alice:secret")>
    assert headers == {"Authorization": "Basic YWxpY2U6c2VjcmV0"}


@pytest.mark.asyncio
async def test_static_headers_forwarded():
    r = CompositeAuthResolver()
    headers = await r.headers_for(
        "anything",
        {"type": "static", "headers": {"User-Agent": "chat-agent/1.0", "X-Foo": "bar"}},
        _ctx(),
    )
    assert headers == {"User-Agent": "chat-agent/1.0", "X-Foo": "bar"}


@pytest.mark.asyncio
async def test_unknown_type_raises():
    r = CompositeAuthResolver()
    with pytest.raises(ValueError):
        await r.headers_for("x", {"type": "wat"}, _ctx())
