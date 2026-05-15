# OpenAPI pgvector migration prompt

Goal:
- Migrate OpenAPI spec metadata from DynamoDB to PostgreSQL.
- Implement real vector search for OpenAPI operation discovery using pgvector.

Context:
- The current OpenAPI discovery flow stores `SpecSource` metadata in DynamoDB and keeps parsed operation embeddings in an in-memory index.
- `list_operations()` currently performs brute-force cosine similarity in Python and cannot scale.
- DynamoDB does not support vector search, so a Postgres-based pgvector implementation is required.

Requirements:
1. Add PostgreSQL configuration to `app/config.py`.
2. Add a Postgres connection module or helper.
3. Create a `spec_sources` relational table, including:
   - `id`, `url`, `description`, `auth`, `cache_etag`, `last_fetched_at`, `operation_count`, `created_at`, `updated_at`.
4. Create an `operation_embeddings` table with a `VECTOR` column for pgvector.
5. Implement a Postgres-backed `SpecSourceRepository` that matches the existing DynamoDB repository API.
6. Implement a pgvector-backed embedding index backend and keep the existing `Embedder` interface.
7. Update OpenAPI discovery wiring to use Postgres for spec metadata and pgvector for vector search.
8. Preserve existing tool contract and `openapi_discovery` actions.
9. Add migrations or init scripts for the new Postgres schema.
10. Add tests for Postgres-backed spec source CRUD and pgvector search.

Acceptance criteria:
- `app/config.py` exposes Postgres DB settings.
- The OpenAPI discovery tool can load spec metadata from Postgres.
- Vector search uses pgvector and returns top-K matching operations.
- Existing `list_specs`, `list_operations`, and `call_operation` semantics remain unchanged.
- The repo no longer depends on DynamoDB for OpenAPI spec metadata.
- The new prompt file is saved in `docs/openapi-pgvector-prompt.md`.
