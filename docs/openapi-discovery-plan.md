# OpenAPI Discovery Tool — Design Plan

## Goal

Let the chat agent discover and invoke operations from arbitrary OpenAPI specs at runtime, scoped per conversation, without registering every operation up front.

## Pattern: Retrieve-then-Invoke (Tool RAG)

This is the established pattern from Gorilla / ToolLLM / ToolBench. The agent does not see every operation as a first-class tool. Instead it sees one **discovery tool** with three actions:

1. `list_specs()` — what API surfaces are available on this conversation
2. `list_operations(query, spec_id?)` — semantic search over operations, optionally scoped to one spec
3. `call_operation(spec_id, operation_id, arguments)` — invoke

Embedding-based retrieval, not substring matching. Substring scales to ~50 ops, breaks at ~5000.

Reference implementations to read before building, not to copy:

- LangChain `OpenAPIToolkit` / `NLAToolkit` — most mature OSS, but uses bulk registration (Shape A in our taxonomy); shows the scaling failure mode.
- Microsoft Semantic Kernel `KernelPlugin.FromOpenApi` — cleaner auth abstraction worth borrowing from.
- OpenAI Plugins / Custom GPT Actions — defunct but the `.well-known/ai-plugin.json` + auth-type taxonomy (`none`/`service`/`oauth`) is reasonable prior art.

## Architecture

### Spec source as first-class entity

OpenAPI specs are not config baked into the tool. Each is a row in DynamoDB:

```
SpecSource
  id                 e.g. "billing"
  url                spec URL
  description        short human-readable, surfaced to LLM via system prompt
  auth               structured auth config (see "Auth config shapes" below)
  cache_etag         for conditional fetch
  last_fetched_at
```

Why separate: multiple conversations reference the same internal spec; auth credentials are environment-scoped, not conversation-scoped.

### Per-conversation scoping

Add `enabled_specs: List[str]` on the conversation model, parallel to existing `enabled_tools` in `app/models/db.py`. The discovery tool only ever sees specs in this list for the current conversation. Without scoping, every `list_operations` call would search every spec in the org — slow, noisy, and a blast-radius problem.

### Cross-spec design rules

- **No unification across specs.** Two specs each having `getUser` are distinct islands; the LLM picks. Auto-unifying would create silent footguns when semantics differ.
- **Namespacing for any promoted tool names** (future Shape C): `{spec_id}__{operation_id}` with `__` separator. Many provider tool-name regexes reject `.` and `/`.
- **Auth never crosses spec boundaries.** `AuthResolver.headers_for(spec_id, security)` — `spec_id` is load-bearing, not decoration.

### System prompt injection

At request build time, if `enabled_specs` is non-empty, prepend to `system_prompt`:

```
Available API services (use the openapi_discovery tool to explore):
- billing: Invoices, refunds, subscriptions
- identity: User accounts and SSO
```

The LLM orients itself without burning a `list_specs` call on every turn.

## Components

### `app/openapi/` — new package

- **`fetcher.py`** — async HTTP fetch with ETag caching, timeout, in-memory LRU. Reuses `httpx` if already a dependency.
- **`parser.py`** — resolve `$ref`, flatten `allOf`, normalize OpenAPI 3.x schema → JSON Schema (`nullable: true` → `type: [..., "null"]`, etc.). Tolerate slightly-broken specs; skip `openapi-spec-validator`.
- **`operation.py`** — `Operation` dataclass: `op_id`, `method`, `path_template`, `summary`, `description`, `param_schema`, `security`, `servers`.
- **`embeddings.py`** — embed `(method, path, summary, description)` once at spec-parse time. Store vectors in memory keyed by `(spec_id, op_id)`. Embedding model: provider-agnostic interface; **v1 default is Amazon Titan Embeddings v2** (`amazon.titan-embed-text-v2:0`) via Bedrock — already aligned with the existing `aioboto3` + `AsyncAnthropicBedrock` stack in `app/llm/bedrock.py`, no new SDK or credentials. Cohere Embed on Bedrock (`cohere.embed-english-v3`) is an alternative if multilingual or different-dim vectors are wanted later. Cache survives only process lifetime in v1; pgvector / OpenSearch is a v2 question.
- **`auth.py`** — `AuthResolver` protocol:

  ```python
  class AuthResolver(Protocol):
      async def headers_for(self, spec_id: str, security: list[dict]) -> dict[str, str]: ...
  ```

  Two implementations in v1: `EnvVarAuthResolver` (reads `OPENAPI_AUTH_{spec_id}_TOKEN` from env), `StaticAuthResolver` (per-spec config blob). OAuth2 client-credentials grant with token caching comes after v1. mTLS, Vault, Secrets Manager are interface-only — wired later.

### `app/tools/openapi_discovery.py` — the tool

One `BaseTool` subclass with parameters discriminated on `action`:

```python
parameters = {
  "type": "object",
  "properties": {
    "action": {"enum": ["list_specs", "list_operations", "call_operation"]},
    "spec_id": {"type": "string"},
    "query": {"type": "string"},
    "operation_id": {"type": "string"},
    "arguments": {"type": "object"}
  },
  "required": ["action"]
}
```

`execute()` dispatches on `action`.

**Critical detail for usability:** `list_operations` returns a *slim* view — `(spec_id, op_id, one-line summary)` capped at top-20 by cosine similarity. Full `param_schema` is only returned on `call_operation` (or when the LLM explicitly asks for one op's schema). This is the single most important design choice for tool-list-size sanity.

### `app/models/db.py` — add

- `SpecSourceDB` model
- `enabled_specs: List[str]` field on the conversation model

### `app/repositories/spec_sources.py` — new

CRUD for `SpecSource` against a new DynamoDB table `spec_sources`.

### `app/routers/spec_sources.py` — new

Admin endpoints: `POST /spec-sources`, `GET /spec-sources`, `DELETE /spec-sources/{id}`. No LLM involvement.

### `app/schemas/spec_source.py` — new

Pydantic request/response models.

### `app/tools/registry.py` — minimal change

For v1 (Shape B only), no structural change. `OpenAPIDiscoveryTool()` is registered globally alongside `CalculatorTool` and `WebSearchStubTool`. The existing `enabled_tools` list on the conversation gates whether discovery is even available.

(Shape C — promoting selected operations to first-class tools mid-conversation — requires a per-conversation registry overlay. Deferred.)

### Agent loop — no changes

`app/routers/messages.py:147` already does `get_tool(name).execute(**args)`. No changes needed for v1.

(Pre-existing gap: the streaming path doesn't appear to handle tool calls. Out of scope for this feature.)

## Tool-list explosion — the discipline

The whole point of retrieve-then-invoke is keeping the LLM's visible tool list small. Rules:

1. Discovery tool is always exactly **one** entry in the tool list, regardless of spec count.
2. `list_operations` results are **slim** (no full schemas). Top-20 by similarity.
3. Full schemas are sent **only** on `call_operation`, just for the one op being called, embedded in the tool result.
4. If we ever add Shape C (activated tools), cap activations per conversation (suggest: 10). Hard limit, not advisory.

## Auth — pattern choice and roadmap

Auth for agentic tool use against enterprise APIs has no single ratified standard, but three patterns are converging across the industry. This project picks the one that fits its context (Cognito + internal microservices) as the default, while leaving the others available per-spec.

### The three patterns

1. **Delegated user auth within one IdP domain.** All services trust the same identity provider; the user's token flows downstream. Microsoft (Entra OBO / RFC 8693), Google Workspace, and most enterprise internal setups land here. Cognito's idiomatic version uses **resource server scopes** — each downstream service is a Cognito resource server with named scopes; the chat-agent app client is granted the scopes it needs to forward.

2. **Broker-managed delegated auth.** A connection broker (Composio, Arcade, Pipedream) holds per-user OAuth grants across many third-party SaaS APIs and injects the right token per call. Right answer for consumer multi-tenant AI products. Not applicable here — we have one IdP.

3. **Service-to-service identity with user propagation.** Agent has its own service credentials (mTLS, signed JWT, service token); calls downstream as itself; propagates user identity in a header for audit and authz. Right answer for high-blast-radius operations or services that don't trust the Cognito pool. Smaller prompt-injection blast radius than pattern 1.

### Pattern choice for this project

- **Default: pattern 1 (`passthrough_jwt`).** The inbound Cognito JWT is forwarded to the downstream service. Required prerequisite: target service is registered as a Cognito resource server, and the chat-agent app client has the scopes for it.
- **Fallback: pattern 3** (`bearer_env`, `basic_env`, mTLS later) for specs that are not Cognito-aware or where service-to-service identity is preferred for security reasons.
- **Pattern 2** (broker) is explicitly out of scope.

### Standards referenced

- OAuth 2.0 / 2.1 — base
- RFC 8693 (Token Exchange) — cross-audience minting; **Cognito does not natively support this**, so we accept the constraint that audiences must align (achieved via shared resource servers)
- RFC 9396 (Rich Authorization Requests) — fine-grained per-call scopes; not used in v1 but the spec's `securitySchemes` carries enough information to evolve toward it
- RFC 7523, RFC 8705 — service-to-service auth, used by pattern 3 (`bearer_env` is a coarse approximation; mTLS is the real form)
- MCP OAuth 2.1 + PKCE — Anthropic's emerging standard for the protocol-level case; informational, not used here

### Roadmap

- v1: `none`, `bearer_env`, `api_key_env`, `basic_env`, `static`, **`passthrough_jwt`**.
- v1.1: OAuth2 client-credentials with token cache (for service-to-service against non-Cognito specs).
- v1.2+: mTLS, Vault / Secrets Manager refs as env-var substitutes, scope filtering on `passthrough_jwt`.
- Out of roadmap: per-user OAuth broker (pattern 2), full RFC 8693 token exchange.

### Hard rules across all patterns

- **Tokens are never persisted.** Request-scoped only. Not in DynamoDB, not in conversation state, not in tool-call audit records.
- **No tokens in logs.** Including error traces. Strip `Authorization` headers from any structured log output.
- **Scope-narrowest credential wins.** If a spec only needs read access, the agent's Cognito client must not be granted write scopes for it.
- **User identity is always auditable downstream.** Pattern 1: via the JWT. Pattern 3: via a propagated `X-On-Behalf-Of-Sub` header (or equivalent — convention TBD per service).

### Plumbing implications

The `AuthResolver` protocol signature must carry request context so `passthrough_jwt` can read the inbound token:

```python
class AuthResolver(Protocol):
    async def headers_for(
        self,
        spec_id: str,
        security: list[dict],
        request_context: RequestContext,  # carries inbound JWT, user claims, trace IDs
    ) -> dict[str, str]: ...
```

`RequestContext` is populated in the FastAPI request pipeline — the existing `request.state.user` work in `app/auth/jwt.py` is extended to also stash the raw bearer token. Token is dropped at request end.

## Operator guide: adding a spec

This is the end-to-end flow an admin follows to make a new OpenAPI service discoverable by the agent.

### Step 1 — Pick a spec ID

The `id` is the stable identifier the LLM sees in `list_specs` results and the namespace used for any future activated tools. Rules:

- Lowercase, alphanumeric + underscores. Matches `^[a-z][a-z0-9_]{0,31}$`.
- Short and meaningful: `billing`, `identity`, `inventory`. Not `billing_service_v2_internal`.
- **Immutable.** Renaming requires deleting and re-creating, which invalidates any conversation references in `enabled_specs`.

### Step 2 — Write a good description

The `description` is injected into the system prompt of conversations that have this spec enabled. It is what the LLM uses to decide *which* spec to search. Treat it as prompt engineering, not as a README.

- One sentence, present tense, lists the resource nouns.
- Good: *"Invoices, refunds, subscriptions, payment methods."*
- Bad: *"The billing microservice handles all billing-related operations for the platform."* (too abstract — no nouns the LLM can match against)

### Step 3 — Configure credentials

Pick the auth shape (see "Auth config shapes" below). Decision tree:

1. **Is the target service behind the same Cognito pool as this chat-agent?** → Use `passthrough_jwt`. No env vars to set. Confirm the target service is registered as a Cognito **resource server** and that the chat-agent's app client has been granted the scopes it needs. This is the default for internal microservices and the industry-standard pattern for your stack.
2. **Is the target service S2S-authenticated (back-office tooling, third-party API with a fixed token)?** → Use `bearer_env` / `api_key_env` / `basic_env`. Set the environment variable on the chat-agent process **before** registering the spec.
3. **Does the target service need destructive operations called *as the agent, not the user*** (limit prompt-injection blast radius)? → Use `bearer_env` even if the service is Cognito-aware. Pattern-3 fallback. Document the reasoning in the `description` field.

For env-var-based shapes:

```bash
export BILLING_API_TOKEN="..."        # for bearer_env
export INVENTORY_API_KEY="..."        # for api_key_env
export LEGACY_USER="svc-account"      # for basic_env
export LEGACY_PASS="..."
```

In production, these come from whatever secret-injection mechanism wraps the process (ECS task secrets, K8s `envFrom`, etc.) — not from a shell. **Do not** use the `static` auth type for real secrets; it stores them in DynamoDB in plaintext. `static` exists only for non-secret values (e.g., a hardcoded `User-Agent`) and dev/local fixtures.

### Step 4 — Register the spec

For a Cognito-aware service (the common case):

```bash
curl -X POST https://chat-agent/spec-sources \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "billing",
    "url": "https://billing.internal/openapi.json",
    "description": "Invoices, refunds, subscriptions, payment methods.",
    "auth": { "type": "passthrough_jwt" }
  }'
```

For a service authenticated with a service-level bearer token:

```bash
curl -X POST https://chat-agent/spec-sources \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "billing",
    "url": "https://billing.internal/openapi.json",
    "description": "Invoices, refunds, subscriptions, payment methods.",
    "auth": {
      "type": "bearer_env",
      "env_var": "BILLING_API_TOKEN"
    }
  }'
```

On success, the server:

1. Fetches the spec immediately (caches `ETag`).
2. Parses and validates basic structure.
3. Computes embeddings for every operation (Titan v2 via Bedrock).
4. Stores the `SpecSource` row in DynamoDB.

Failures at any step return 4xx with the failing stage in the error body. The spec is not stored if step 1 or 2 fails.

### Step 5 — Verify discoverability

```bash
# List all registered specs
curl https://chat-agent/spec-sources -H "Authorization: Bearer $ADMIN_TOKEN"

# Force a re-fetch (e.g., after the upstream service deploys a new spec version)
curl -X POST https://chat-agent/spec-sources/billing/refresh -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Step 6 — Enable on a conversation

Specs are global; conversations opt in. Update the conversation's `enabled_specs` (existing config endpoint, parallel to `enabled_tools`):

```bash
curl -X PATCH https://chat-agent/conversations/{id}/config \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled_tools": ["openapi_discovery"],
    "enabled_specs": ["billing", "identity"]
  }'
```

`openapi_discovery` must be in `enabled_tools` for the discovery tool to be visible at all. `enabled_specs` then scopes which specs the discovery tool sees.

### Step 7 — Sanity-check end-to-end

Send a message that should trigger discovery: *"List my outstanding invoices."* Expected behavior in the agent loop:

1. Model calls `openapi_discovery(action="list_operations", query="outstanding invoices", spec_id="billing")`.
2. Server returns slim top-20 matches.
3. Model calls `openapi_discovery(action="call_operation", spec_id="billing", operation_id="listInvoices", arguments={...})`.
4. Server attaches the bearer token, calls the upstream, returns the result.

If the model goes to a wrong spec or skips discovery, the most common causes are (1) a vague spec `description`, (2) too many specs enabled at once, or (3) the system prompt is overriding tool-use behavior. Tighten the description first.

## Auth config shapes

Supported in v1:

| `type`             | Pattern | Required fields                  | Behavior                                                                                              |
|--------------------|---------|----------------------------------|-------------------------------------------------------------------------------------------------------|
| `passthrough_jwt`  | 1       | — (optionally `header_name`)     | Forwards the inbound `Authorization: Bearer <jwt>` from the active request. **Default for Cognito.** |
| `none`             | —       | —                                | No auth headers attached.                                                                             |
| `bearer_env`       | 3       | `env_var`                        | `Authorization: Bearer <env value>`                                                                   |
| `api_key_env`      | 3       | `env_var`, `header`              | `<header>: <env value>`                                                                               |
| `basic_env`        | 3       | `username_env`, `password_env`   | `Authorization: Basic <base64(user:pass)>`                                                            |
| `static`           | —       | `headers` (object)               | Headers attached verbatim. **Not for secrets.**                                                       |

(Pattern column refers to the three auth patterns described in "Auth — pattern choice and roadmap" above.)

Examples:

```json
{ "type": "passthrough_jwt" }

{ "type": "bearer_env", "env_var": "BILLING_API_TOKEN" }

{ "type": "api_key_env", "env_var": "INVENTORY_API_KEY", "header": "X-API-Key" }

{ "type": "basic_env", "username_env": "LEGACY_USER", "password_env": "LEGACY_PASS" }

{ "type": "static", "headers": { "User-Agent": "chat-agent/1.0" } }

{ "type": "none" }
```

Resolver dispatch: `AuthResolver.headers_for(spec_id, security, request_context)` reads the spec's stored `auth` config, dispatches by `type`, and returns the header dict. `passthrough_jwt` is the only shape that reads from `request_context`; the others are self-contained.

The OpenAPI spec's own `securitySchemes` are **informational** in v1 — the operator's `auth` block is what's actually applied. (Reconciling the two — e.g., warning when the operator picks `none` for a spec that declares OAuth2 — is a v1.1 concern.)

**Not yet supported (v1.1+):** OAuth2 client-credentials (token cache), per-user OAuth broker (pattern 2), mTLS, Vault / Secrets Manager refs as a substitute for env vars, scope filtering on `passthrough_jwt`, RFC 8693 token exchange.

## Documentation deliverables

The feature is not "done" until `README.md` reflects it. Specifically:

1. **Architecture diagram** ([README.md](../README.md) — the existing Mermaid diagram under `## Architecture`) must be updated to include:
   - A new `OpenAPI Discovery` node inside the `Tools` subgraph alongside `Calculator` and `WebSearch`.
   - A new subgraph (suggest: `OpenAPI Specs`) containing the registered external services, with the Lambda calling into them via the discovery tool.
   - The `SpecSource` table inside the `Data` subgraph (or a new edge from Lambda → DynamoDB labeled to show the new table).
   - An edge showing inbound JWT being forwarded to downstream services for `passthrough_jwt` specs.

2. **Request-flow paragraph** (immediately below the diagram) extended to describe the discover → invoke loop in one sentence: how `list_operations` / `call_operation` interact with cached spec embeddings and the auth resolver.

3. **Project Structure** section updated to list the new `app/openapi/` package and the `app/routers/spec_sources.py` admin router.

4. **New "Tool Discovery" subsection** under `## Design Notes` (or as a peer section): brief explanation of retrieve-then-invoke pattern, link to this plan doc for the full design, and the operator-facing pointer for "how to add a spec" — either inline summary or link to the operator guide section in this doc.

5. **Configuration table** (if `## Configuration` lists env vars) updated to include any new env vars introduced by auth resolvers (e.g., `BILLING_API_TOKEN` examples) and Bedrock embedding model config if it becomes settable.

Treat this as a non-skippable step in the order of operations, not a stretch goal. The README diagram is the entry point for anyone joining the project; if it shows `Tool Registry` containing only `Calculator` and `WebSearch` after this feature ships, the design will be invisible to readers.

## Tests

- **Parser:** fixture specs (Petstore, one with `$ref` chains, one with `oneOf/allOf`) → expected operation list.
- **Embeddings:** deterministic test using a stubbed embedding function; verify retrieval ordering.
- **Auth resolver:** env-var lookup, missing-cred error path.
- **Discovery tool unit:** `list_specs`, `list_operations` filtering, `call_operation` with `respx`-mocked upstream.
- **End-to-end:** local FastAPI test app serves a spec + endpoint; agent loop discovers and calls it.

## Out of scope for v1

- MCP discovery (similar pattern, separate package, follows later — or revisit via `openapi-to-mcp` bridge if MCP becomes the long-term substrate).
- Shape C (promoting ops to first-class tools).
- OAuth2 beyond client-credentials.
- Per-user credentials.
- Spec versioning beyond ETag.
- Streaming tool calls (existing gap).
- Persistent embedding store (pgvector / OpenSearch).
- RBAC on spec visibility beyond `enabled_specs`.

## Order of operations

1. `SpecSource` model + repo + admin endpoints. CRUD only; no LLM. Verify with curl.
2. `fetcher.py` + `parser.py`. Unit tests against Petstore + `$ref` fixture.
3. `embeddings.py` with pluggable embedder. Default to Amazon Titan Embeddings v2 via Bedrock.
4. `auth.py` with all v1 resolvers — `PassthroughJWTResolver`, `EnvVarAuthResolver` (covers `bearer_env`, `api_key_env`, `basic_env`), `StaticAuthResolver`, `NoneAuthResolver`. Thread `RequestContext` through the call chain.
5. `OpenAPIDiscoveryTool` — wire all three actions. Register globally.
6. `enabled_specs` on conversation + system-prompt injection.
7. End-to-end against a local test service. Iterate `list_operations` ranking based on actual LLM behavior.
8. **Update `README.md`** — diagram, request-flow paragraph, project structure, design notes, configuration. See "Documentation deliverables" section. Not optional.

## Resolved decisions

- **Embedding provider:** Amazon Titan Embeddings v2 via Bedrock (`amazon.titan-embed-text-v2:0`). Reuses existing AWS stack. `text-embedding-3-small` ruled out — not on Bedrock. The `embeddings.py` interface stays pluggable so an alternate impl (Cohere on Bedrock, local model, etc.) can be swapped without touching the discovery tool.
- **Spec source ownership:** Global. `SpecSource` rows are admin-managed via the new `/spec-sources` router. No per-user ownership in v1.
- **Unreachable spec at fetch time:** Serve stale parsed ops from in-memory cache; log a warning. The discovery call does not hard-fail. Cache miss + unreachable upstream is the only hard-fail case.
