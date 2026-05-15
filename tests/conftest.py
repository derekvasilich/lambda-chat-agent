import os
import pytest
import pytest_asyncio
import boto3
from httpx import AsyncClient, ASGITransport
from moto import mock_aws

from app.main import app
from app.dynamodb import (
    get_conversations_table,
    get_messages_table,
)
from app.postgres import get_spec_source_repo, get_postgres_pool
from app.schemas.spec_source import SpecSourceCreate, SpecSourceResponse
from app.models.db import utcnow
from app.auth.jwt import get_current_user
from app.auth import UserClaims

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

TABLE_CONVERSATIONS = "chat_conversations"
TABLE_MESSAGES = "chat_messages"
TABLE_SPEC_SOURCES = "chat_spec_sources"

TEST_USER = UserClaims(sub="test-user-123", email="test@example.com")
TOKEN = "test-token"


# ---------------------------------------------------------------------------
# Async wrappers around sync boto3 Table so tests can use moto without
# needing aiobotocore's async HTTP layer (which moto doesn't patch).
# ---------------------------------------------------------------------------

class _AsyncBatchWriter:
    """Async context manager wrapping a sync boto3 BatchWriter."""

    def __init__(self, sync_table):
        self._sync_table = sync_table
        self._cm = None
        self._batch = None

    async def __aenter__(self):
        self._cm = self._sync_table.batch_writer()
        self._batch = self._cm.__enter__()
        return self

    async def __aexit__(self, *args):
        self._cm.__exit__(*args)

    async def delete_item(self, **kwargs):
        self._batch.delete_item(**kwargs)

    async def put_item(self, **kwargs):
        self._batch.put_item(**kwargs)


class AsyncTableWrapper:
    """Wraps a sync boto3 DynamoDB Table with async methods for testing."""

    def __init__(self, table):
        self._table = table

    async def put_item(self, **kwargs):
        return self._table.put_item(**kwargs)

    async def get_item(self, **kwargs):
        return self._table.get_item(**kwargs)

    async def query(self, **kwargs):
        return self._table.query(**kwargs)

    async def scan(self, **kwargs):
        return self._table.scan(**kwargs)

    async def update_item(self, **kwargs):
        return self._table.update_item(**kwargs)

    async def delete_item(self, **kwargs):
        return self._table.delete_item(**kwargs)

    async def load(self):
        self._table.reload()

    def batch_writer(self):
        return _AsyncBatchWriter(self._table)


class InMemorySpecSourceRepo:
    def __init__(self):
        self._items: dict[str, SpecSourceResponse] = {}

    async def get(self, id: str) -> SpecSourceResponse | None:
        return self._items.get(id)

    async def list(self) -> list[SpecSourceResponse]:
        return list(self._items.values())

    async def create(self, data: SpecSourceCreate) -> SpecSourceResponse:
        if data.id in self._items:
            raise ValueError(f"Spec source '{data.id}' already exists")
        now = utcnow()
        item = SpecSourceResponse(
            id=data.id,
            url=data.url,
            description=data.description,
            auth=data.auth,
            cache_etag=None,
            last_fetched_at=None,
            operation_count=None,
            created_at=now,
            updated_at=now,
        )
        self._items[data.id] = item
        return item

    async def update_cache_metadata(
        self,
        id: str,
        cache_etag: str | None,
        operation_count: int,
    ) -> SpecSourceResponse | None:
        item = self._items.get(id)
        if item is None:
            return None
        updated = item.model_copy(update={
            "cache_etag": cache_etag,
            "last_fetched_at": utcnow(),
            "operation_count": operation_count,
            "updated_at": utcnow(),
        })
        self._items[id] = updated
        return updated

    async def delete(self, id: str) -> bool:
        if id not in self._items:
            return False
        del self._items[id]
        return True


# ---------------------------------------------------------------------------
# Table creation helper
# ---------------------------------------------------------------------------

def _create_tables(ddb_client):
    ddb_client.create_table(
        TableName=TABLE_CONVERSATIONS,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "user_id-created_at-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb_client.create_table(
        TableName=TABLE_MESSAGES,
        KeySchema=[
            {"AttributeName": "conversation_id", "KeyType": "HASH"},
            {"AttributeName": "sort_key", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "conversation_id", "AttributeType": "S"},
            {"AttributeName": "sort_key", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb_client.create_table(
        TableName=TABLE_SPEC_SOURCES,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def aws_mock():
    with mock_aws():
        ddb_client = boto3.client("dynamodb", region_name="us-east-1")
        _create_tables(ddb_client)

        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        conv_table = AsyncTableWrapper(ddb.Table(TABLE_CONVERSATIONS))
        msg_table = AsyncTableWrapper(ddb.Table(TABLE_MESSAGES))
        spec_table = AsyncTableWrapper(ddb.Table(TABLE_SPEC_SOURCES))

        yield conv_table, msg_table, spec_table


@pytest_asyncio.fixture
async def client(aws_mock):
    conv_table, msg_table, spec_table = aws_mock

    async def mock_conv_table():
        yield conv_table

    async def mock_msg_table():
        yield msg_table

    async def mock_spec_table():
        yield spec_table

    def override_auth():
        return TEST_USER

    spec_repo = InMemorySpecSourceRepo()

    async def mock_spec_source_repo():
        yield spec_repo

    # Mock postgres pool
    class MockConnection:
        async def fetchval(self, query):
            return 0  # Return 0 for COUNT(*) queries

    class MockPool:
        async def acquire(self):
            return MockConnection()
        async def release(self, conn):
            pass

    async def mock_postgres_pool():
        yield MockPool()

    app.dependency_overrides[get_conversations_table] = mock_conv_table
    app.dependency_overrides[get_messages_table] = mock_msg_table
    app.dependency_overrides[get_spec_source_repo] = mock_spec_source_repo
    app.dependency_overrides[get_postgres_pool] = mock_postgres_pool
    app.dependency_overrides[get_current_user] = override_auth

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client(aws_mock):
    from fastapi import HTTPException

    conv_table, msg_table, spec_table = aws_mock

    async def mock_conv_table():
        yield conv_table

    async def mock_msg_table():
        yield msg_table

    async def mock_spec_table():
        yield spec_table

    def deny_auth():
        raise HTTPException(status_code=403, detail={
            "error": {"code": "unauthorized", "message": "Not authenticated", "details": {}}
        })

    spec_repo = InMemorySpecSourceRepo()

    async def mock_spec_source_repo():
        yield spec_repo

    # Mock postgres pool
    class MockConnection:
        async def fetchval(self, query):
            return 0  # Return 0 for COUNT(*) queries

    class MockPool:
        async def acquire(self):
            return MockConnection()
        async def release(self, conn):
            pass

    async def mock_postgres_pool():
        yield MockPool()

    app.dependency_overrides[get_conversations_table] = mock_conv_table
    app.dependency_overrides[get_messages_table] = mock_msg_table
    app.dependency_overrides[get_spec_source_repo] = mock_spec_source_repo
    app.dependency_overrides[get_postgres_pool] = mock_postgres_pool
    app.dependency_overrides[get_current_user] = deny_auth

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def conversation(client):
    resp = await client.post("/v1/conversations", json={"title": "Test Conversation"})
    assert resp.status_code == 201
    return resp.json()
