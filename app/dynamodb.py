from contextlib import asynccontextmanager
from typing import AsyncIterator

import aioboto3
from app.config import settings

_session = aioboto3.Session()

@asynccontextmanager
async def get_dynamodb_resource():
    kwargs = {"region_name": settings.AWS_REGION}
    if settings.DYNAMODB_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.DYNAMODB_ENDPOINT_URL
    async with _session.resource("dynamodb", **kwargs) as dynamodb:
        yield dynamodb


async def get_conversations_table():
    async with get_dynamodb_resource() as dynamodb:
        yield await dynamodb.Table(settings.DYNAMODB_TABLE_CONVERSATIONS)


async def get_messages_table():
    async with get_dynamodb_resource() as dynamodb:
        yield await dynamodb.Table(settings.DYNAMODB_TABLE_MESSAGES)


async def get_spec_sources_table():
    async with get_dynamodb_resource() as dynamodb:
        yield await dynamodb.Table(settings.DYNAMODB_TABLE_SPEC_SOURCES)
