## Task: Migrate chat-agent FastAPI app from SQLAlchemy/PostgreSQL to AWS DynamoDB

### Working directory
/Users/derek/Documents/claude/chat-agent

### Current stack (what exists now)
- FastAPI app with async SQLAlchemy 2.0 + PostgreSQL/SQLite via asyncpg/aiosqlite
- Alembic migrations in migrations/
- Two ORM models in app/models/db.py: Conversation and Message
- AWS Lambda deployment via Mangum (handler in app/main.py)
- boto3 already present (used by app/llm/bedrock.py)
- pyproject.toml manages deps

### Goal
Replace all SQLAlchemy/Alembic/PostgreSQL code with DynamoDB using aioboto3 for async access.
Keep all existing API contracts identical except pagination cursors (see below).
Do not change: auth, LLM providers, tool system, rate limiting, SSE streaming, or URL paths.

---

### DynamoDB table design

**Table 1: `chat_conversations`** (name from settings)
- PK: `id` (String, UUID)
- GSI named `user_id-created_at-index`: PK=`user_id` (String), SK=`created_at` (String, ISO8601)
- Attributes: id, user_id, title, system_prompt, provider, model, max_history_messages,
  enabled_tools (stored as JSON string), created_at, updated_at
- BillingMode: PAY_PER_REQUEST

**Table 2: `chat_messages`** (name from settings)
- PK: `conversation_id` (String)
- SK: `sort_key` (String) — value is `<created_at_iso>#<message_id>`, e.g. `2025-04-27T12:00:00.000000#<uuid>`
  This gives time-ordered range queries and a stable cursor.
- Attributes: id, conversation_id, sort_key, role, content, tool_calls (JSON string or None),
  tool_call_id, model_used, token_count, created_at
- BillingMode: PAY_PER_REQUEST

---

### Files to create

**app/dynamodb.py**
- Holds the aioboto3 session and exposes get_dynamodb_resource() as an async context manager
- Provides two async dependency functions for FastAPI: get_conversations_table() and get_messages_table()
- Uses settings.DYNAMODB_ENDPOINT_URL (empty string = real AWS), settings.AWS_REGION

**app/repositories/__init__.py** (empty)

**app/repositories/conversations.py**
ConversationRepository class, takes a DynamoDB Table resource.
Methods (all async):
- get(id, user_id) -> ConversationResponse | None  — get by PK, check user_id ownership
- list(user_id, page_size, cursor) -> (list[ConversationResponse], next_cursor | None)
  Query GSI user_id-created_at-index, descending. cursor is base64-encoded LastEvaluatedKey JSON.
  Include the "first message preview" field (title only — no join needed, it's already on Conversation).
  Actually looking at the existing router, list returns conversations with a "preview" from the first message.
  For now, return conversations without message preview (it requires a cross-table query per item — too expensive).
  Add a TODO comment noting this.
- create(user_id, data: ConversationCreate) -> ConversationResponse
- update_config(id, user_id, data: ConversationConfigUpdate) -> ConversationResponse
  Use ConditionExpression to ensure item exists and user owns it (optimistic check on user_id attribute).
- delete(id, user_id) -> bool
  Delete conversation item, then batch-delete all its messages using BatchWriter on messages table.
  The repository needs both table references for delete.

**app/repositories/messages.py**
MessageRepository class, takes a DynamoDB Table resource.
Methods (all async):
- list(conversation_id, limit, before_cursor) -> (list[MessageResponse], has_more, next_cursor | None)
  Query by PK=conversation_id, SK ascending. If before_cursor provided, decode it as ExclusiveStartKey.
  Return up to limit items. has_more = len(results) == limit (check one extra item).
- add(conversation_id, role, content, tool_calls, tool_call_id, model_used, token_count) -> MessageResponse
- get_history(conversation_id, max_messages) -> list[LLMMessage]
  Query last max_messages items (ScanIndexForward=False, limit=max_messages), reverse result for chronological order.
- delete_all(conversation_id) -> int  — batch delete all messages for a conversation, return count

**scripts/create_tables.py**
Standalone script (not Lambda handler) that creates both tables if they don't exist.
Idempotent — uses describe_table to check existence before creating.
Reads settings from environment / .env file.
Usage: python scripts/create_tables.py

---

### Files to modify

**app/config.py**
Add these settings:
- DYNAMODB_TABLE_CONVERSATIONS: str = "chat_conversations"
- DYNAMODB_TABLE_MESSAGES: str = "chat_messages"
- DYNAMODB_ENDPOINT_URL: str = ""   # empty = real AWS; "http://localhost:8000" for DynamoDB Local
- AWS_REGION: str = "us-east-1"
- CONVERSATION_TTL_DAYS: int = 0    # 0 = no TTL

**app/main.py**
- Remove: async engine creation, engine.dispose() in lifespan, all SQLAlchemy imports
- Add: aioboto3 session init in lifespan (just log that DynamoDB is ready — no persistent connection needed)
- Keep everything else identical

**app/models/db.py**
Replace SQLAlchemy ORM models with plain Pydantic BaseModel classes that match the DynamoDB item shapes.
These are used internally by repositories for serialization/deserialization.
Fields match the current ORM models exactly.

**app/routers/conversations.py**
- Replace AsyncSession dependency with ConversationRepository dependency
- Replace all SQLAlchemy queries with repository calls
- Pagination: replace page/page_size with page_size + cursor query params
  New query params: page_size: int = 20 (max 100), cursor: str | None = None
  Response: add next_cursor: str | None to ConversationListResponse

**app/routers/messages.py**
- Replace AsyncSession dependency with MessageRepository + ConversationRepository dependencies
- Replace all SQLAlchemy queries with repository calls
- Cursor pagination stays the same shape but now encodes DynamoDB LastEvaluatedKey

**app/routers/config.py**
- Replace AsyncSession dependency with ConversationRepository dependency
- Replace DB queries with repository calls

**app/schemas/conversation.py**
- Update ConversationListResponse: replace `page: int` with `next_cursor: str | None = None`
- Keep all other fields

**app/schemas/message.py**
- Update MessageListResponse: next_cursor field already exists — verify it's Optional[str]

**pyproject.toml**
- Add: aioboto3>=13.0.0
- Remove: sqlalchemy[asyncio], alembic, aiosqlite, asyncpg, greenlet

**docker-compose.yml**
- Remove PostgreSQL service
- Add DynamoDB Local service:
  image: amazon/dynamodb-local:latest
  ports: 8000:8000
  command: -jar DynamoDBLocal.jar -sharedDb -inMemory
- Add init service or startup command that runs `python scripts/create_tables.py` after DynamoDB Local is healthy

**requirements.txt**
Regenerate after dep changes.

---

### Files to delete
- app/database.py
- migrations/ (entire directory)
- migrate.py

---

### Tests
- Update tests/conftest.py: replace SQLite engine fixture with moto mock_aws fixture
  Use @mock_aws decorator from moto, create tables in fixture using create_tables logic
- Update all test files to use the new repository/DynamoDB fixtures
- Add moto>=5.0.0 to test dependencies in pyproject.toml

---

### Constraints
- Do NOT change any URL paths or HTTP methods
- Do NOT change the auth/JWT layer
- Do NOT change LLM providers or the tool system
- Do NOT change SSE streaming logic in messages.py (the ?stream=true path)
- Keep all existing Pydantic response schemas shape-compatible (only additions allowed)
- Use PAY_PER_REQUEST billing on all tables
- All DynamoDB calls must be async (use aioboto3, not boto3 directly)
- enabled_tools and tool_calls JSON fields: store as JSON strings in DynamoDB (DynamoDB supports List/Map natively — use native types, not strings, for these fields)
- Preserve the existing rate limiting behavior
- The app already uses Mangum for Lambda — keep that

---

### Local dev workflow after migration
1. docker-compose up  (starts DynamoDB Local)
2. python scripts/create_tables.py  (creates tables)
3. .venv/bin/uvicorn app.main:app --reload
