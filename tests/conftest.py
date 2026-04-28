import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, patch

from app.main import app
from app.database import Base, get_db
from app.auth.jwt import get_current_user
from app.auth import UserClaims

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)

TEST_USER = UserClaims(sub="test-user-123", email="test@example.com")
TOKEN = "test-token"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async def override_db():
        async with TestSession() as session:
            yield session

    def override_auth():
        return TEST_USER

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_auth

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client():
    from fastapi import HTTPException

    async def override_db():
        async with TestSession() as session:
            yield session

    def deny_auth():
        raise HTTPException(status_code=403, detail={
            "error": {"code": "unauthorized", "message": "Not authenticated", "details": {}}
        })

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = deny_auth

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def conversation(client):
    resp = await client.post("/v1/conversations", json={"title": "Test Conversation"})
    assert resp.status_code == 201
    return resp.json()
