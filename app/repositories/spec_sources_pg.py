from datetime import datetime
from typing import Any, Optional

import asyncpg
from pydantic import json

from app.models.db import utcnow
from app.schemas.spec_source import SpecSourceCreate, SpecSourceResponse


def _row_to_response(row: asyncpg.Record) -> SpecSourceResponse:
    return SpecSourceResponse(
        id=row["id"],
        url=row["url"],
        description=row["description"],
        auth=json.loads(row["auth"]) if row["auth"] else None,
        cache_etag=row.get("cache_etag"),
        last_fetched_at=row.get("last_fetched_at"),
        operation_count=row.get("operation_count"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SpecSourceRepositoryPG:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get(self, id: str) -> Optional[SpecSourceResponse]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, url, description, auth, cache_etag, last_fetched_at, operation_count, created_at, updated_at FROM spec_sources WHERE id = $1",
                id,
            )
            if row is None:
                return None
            return _row_to_response(row)

    async def list(self) -> list[SpecSourceResponse]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, url, description, auth, cache_etag, last_fetched_at, operation_count, created_at, updated_at FROM spec_sources ORDER BY id",
            )
            return [_row_to_response(row) for row in rows]

    async def create(self, data: SpecSourceCreate) -> SpecSourceResponse:
        now = utcnow()
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO spec_sources (id, url, description, auth, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6)",
                data.id,
                data.url,
                data.description,
                json.dumps(data.auth.model_dump()) if data.auth else None,
                now,
                now,
            )
        return SpecSourceResponse(
            id=data.id,
            url=data.url,
            description=data.description,
            auth=json.loads(json.dumps(data.auth.model_dump())) if data.auth else None,
            cache_etag=None,
            last_fetched_at=None,
            operation_count=None,
            created_at=now,
            updated_at=now,
        )

    async def update_cache_metadata(
        self,
        id: str,
        cache_etag: Optional[str],
        operation_count: int,
    ) -> Optional[SpecSourceResponse]:
        now = utcnow()
        parts = ["last_fetched_at = $2", "updated_at = $3", "operation_count = $4"]
        values: list[Any] = [id, now, now, operation_count]
        if cache_etag is not None:
            parts.append("cache_etag = $5")
            values.append(cache_etag)
        query = f"UPDATE spec_sources SET {', '.join(parts)} WHERE id = $1 RETURNING id, url, description, auth, cache_etag, last_fetched_at, operation_count, created_at, updated_at"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            if row is None:
                return None
            return _row_to_response(row)

    async def delete(self, id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM spec_sources WHERE id = $1", id)
            return result.endswith("1")
