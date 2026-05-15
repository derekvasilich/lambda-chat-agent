from typing import List, Optional

import asyncpg


class PgvectorEmbeddingIndex:
    def __init__(self, pool_factory, table_name: str):
        self._pool_factory = pool_factory
        self._table_name = table_name

    async def _get_pool(self) -> asyncpg.Pool:
        return await self._pool_factory()

    async def add(self, spec_id: str, op_id: str, vector: List[float]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {self._table_name} (spec_id, operation_id, vector) VALUES ($1, $2, $3) "
                "ON CONFLICT (spec_id, operation_id) DO UPDATE SET vector = EXCLUDED.vector",
                spec_id,
                op_id,
                vector,
            )

    async def remove_spec(self, spec_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {self._table_name} WHERE spec_id = $1",
                spec_id,
            )

    async def get(self, spec_id: str, op_id: str) -> Optional[List[float]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT vector FROM {self._table_name} WHERE spec_id = $1 AND operation_id = $2",
                spec_id,
                op_id,
            )
            return list(row["vector"]) if row is not None else None

    async def search(
        self,
        query_vector: List[float],
        spec_ids: List[str] | None,
        top_k: int,
    ) -> List[tuple[str, str, float]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if spec_ids:
                rows = await conn.fetch(
                    f"SELECT spec_id, operation_id, 1 - (vector <#> $1) AS score "
                    f"FROM {self._table_name} WHERE spec_id = ANY($2::text[]) "
                    "ORDER BY vector <#> $1 LIMIT $3",
                    query_vector,
                    spec_ids,
                    top_k,
                )
            else:
                rows = await conn.fetch(
                    f"SELECT spec_id, operation_id, 1 - (vector <#> $1) AS score "
                    f"FROM {self._table_name} ORDER BY vector <#> $1 LIMIT $2",
                    query_vector,
                    top_k,
                )
            return [(row["spec_id"], row["operation_id"], row["score"]) for row in rows]
