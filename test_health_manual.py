import asyncio
import os
import sys
sys.path.insert(0, '/Users/derek/Documents/claude/chat-agent')

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.dynamodb import get_conversations_table, get_messages_table
from app.postgres import get_spec_source_repo, get_postgres_pool
from app.auth.jwt import get_current_user
from app.auth import UserClaims

# Mock user
TEST_USER = UserClaims(sub="test-user-123", email="test@example.com")

# Mock postgres pool
class MockConnection:
    async def fetchval(self, query):
        print(f"MockConnection.fetchval called with: {query}")
        return 0  # Return 0 for COUNT(*) queries

class MockPool:
    async def acquire(self):
        print("MockPool.acquire called")
        return MockConnection()
    async def release(self, conn):
        print("MockPool.release called")

async def mock_postgres_pool():
    yield MockPool()

# Mock other dependencies
async def mock_conv_table():
    yield None  # We don't need this for health check

async def mock_msg_table():
    yield None

async def mock_spec_repo():
    yield None

def mock_auth():
    return TEST_USER

async def test_health():
    # Set overrides
    app.dependency_overrides[get_postgres_pool] = mock_postgres_pool
    app.dependency_overrides[get_conversations_table] = mock_conv_table
    app.dependency_overrides[get_messages_table] = mock_msg_table
    app.dependency_overrides[get_spec_source_repo] = mock_spec_repo
    app.dependency_overrides[get_current_user] = mock_auth

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/health")
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")

if __name__ == "__main__":
    asyncio.run(test_health())