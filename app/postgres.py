from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from app.config import settings
from app.repositories.spec_sources_pg import SpecSourceRepositoryPG

_pool: asyncpg.Pool | None = None

async def get_postgres_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        _pool = await asyncpg.create_pool(settings.DATABASE_URL)
    return _pool

@asynccontextmanager
async def get_postgres_connection() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_postgres_pool()
    async with pool.acquire() as conn:
        yield conn

async def get_spec_source_repo() -> AsyncIterator[SpecSourceRepositoryPG]:
    pool = await get_postgres_pool()
    yield SpecSourceRepositoryPG(pool)
