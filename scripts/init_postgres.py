import asyncio
import os

import asyncpg

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
PGVECTOR_EMBEDDINGS_TABLE = os.getenv("PGVECTOR_EMBEDDINGS_TABLE", "openapi_operation_embeddings")
OPENAPI_EMBEDDING_DIM = int(os.getenv("OPENAPI_EMBEDDING_DIM", "1536"))

def _schema_sql(table_name: str, dim: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS spec_sources (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    description TEXT NOT NULL,
    auth JSONB NOT NULL,
    cache_etag TEXT,
    last_fetched_at TIMESTAMPTZ,
    operation_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS {table_name} (
    spec_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    vector VECTOR({dim}) NOT NULL,
    PRIMARY KEY (spec_id, operation_id)
);

CREATE INDEX IF NOT EXISTS idx_{table_name}_spec_id ON {table_name} (spec_id);
"""

async def main() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            _schema_sql(PGVECTOR_EMBEDDINGS_TABLE, OPENAPI_EMBEDDING_DIM)
        )
        print("PostgreSQL schema initialized successfully")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
