# Free Public OpenAPI Specs for Testing

A curated list of real, publicly-hosted OpenAPI specs you can register with the chat-agent to exercise the discovery tool end-to-end. Listed in increasing order of complexity — start at the top to sanity-check the happy path, work down once retrieval and invocation are confirmed.

Replace `$TOKEN` with a valid bearer token (or any well-formed JWT in dev mode where `OAUTH2_JWKS_URL` is empty).

## 1. Swagger Petstore v3 — the canonical test target

- **Spec URL:** `https://petstore3.swagger.io/api/v3/openapi.json`
- **Size:** ~20 operations
- **Auth:** none
- **Best for:** sanity-checking discovery + invocation end-to-end. The same Petstore everyone uses for OpenAPI demos.

```bash
curl -X POST http://localhost:8000/v1/spec-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "petstore",
    "url": "https://petstore3.swagger.io/api/v3/openapi.json",
    "description": "Sample pet store: pets, orders, users. Public sandbox.",
    "auth": {"type": "none"}
  }'
```

Try asking the agent: *"Find a pet by ID 1"* or *"What pets are available?"*

**Caveat:** Petstore is a shared public sandbox. Any data you POST is visible to anyone else also testing against it, and will be wiped periodically.

## 2. Open-Meteo (weather, free, no auth)

- **Spec URL:** `https://api.open-meteo.com/openapi.json`
- **Size:** small but practical
- **Auth:** none, generous rate limits
- **Best for:** demoing a useful retrieve-then-invoke flow against a real production API.

```bash
curl -X POST http://localhost:8000/v1/spec-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "weather",
    "url": "https://api.open-meteo.com/openapi.json",
    "description": "Weather forecasts, historical data, air quality. Free public API.",
    "auth": {"type": "none"}
  }'
```

Try: *"What's the weather in San Francisco tomorrow?"* — exercises query-param construction with lat/lon and time ranges.

## 3. Nager.Date — public holidays

- **Spec URL:** `https://date.nager.at/swagger/v3/swagger.json`
- **Size:** ~10 operations
- **Auth:** none
- **Best for:** exercising path-parameter substitution.

```bash
curl -X POST http://localhost:8000/v1/spec-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "holidays",
    "url": "https://date.nager.at/swagger/v3/swagger.json",
    "description": "Public holidays by country and year.",
    "auth": {"type": "none"}
  }'
```

Try: *"What public holidays are in Germany next year?"* — should resolve to `GET /api/v3/PublicHolidays/{Year}/{CountryCode}` with both path params correctly substituted.

## 4. GitHub REST API — stress test for tool-list explosion

- **Spec URL:** `https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json`
- **Size:** ~900 operations across the entire GitHub surface (~16 MB spec)
- **Auth:** none for public read endpoints (60 req/hr unauthenticated); use a PAT for higher limits
- **Best for:** validating that the embedding retrieval is actually doing useful work. Substring matching would be unusable at this scale.

```bash
curl -X POST http://localhost:8000/v1/spec-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "github",
    "url": "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json",
    "description": "GitHub REST API: repositories, issues, pull requests, users, gists, actions.",
    "auth": {"type": "none"}
  }'
```

For higher rate limits or write access, use a personal access token:

```bash
export GITHUB_PAT="ghp_..."
# then register with:
"auth": {"type": "bearer_env", "env_var": "GITHUB_PAT"}
```

Try: *"List the open issues on the cli/cli repository"* — the model has to find `issues/list-for-repo` among hundreds of operations.

## Finding more

[APIs.guru](https://apis.guru) maintains a curated directory of thousands of public OpenAPI specs (governmental, financial, transit, weather, telecoms, etc.). The machine-readable index is at `https://api.apis.guru/v2/list.json`. Most entries don't require auth for read endpoints.

## Practical gotchas to expect

- **GitHub's spec is ~16 MB.** First fetch takes a few seconds; the embedding pass against Titan will be slower still (one Bedrock call per operation in v1, no batching). Petstore + Open-Meteo are seconds; GitHub may take a minute on first load. Subsequent calls hit the in-memory cache.

- **Some specs declare `securitySchemes` even when public endpoints work without auth.** The v1 design intentionally ignores the spec's `securitySchemes` and uses the operator's `auth` block instead — set `"type": "none"` and the agent will not attempt to attach any credentials.

- **Response sizes vary wildly.** GitHub's `list-issues` can return tens of KB of JSON. If conversation context starts ballooning, consider adding response truncation in `call_operation` — not on the v1 roadmap.

- **Petstore is a shared public sandbox** — anyone can POST a pet with `id: 1`. If two demos run simultaneously, they'll see each other's data. Fine for testing, not for anything stateful.

- **Rate limits.** Unauthenticated GitHub is 60 req/hr per IP. If you're iterating on prompts and burning tool calls, you'll hit this fast — use a PAT.

## Enabling a registered spec on a conversation

After registering one or more specs, enable them on a conversation along with the `openapi_discovery` tool:

```bash
curl -X PATCH http://localhost:8000/v1/conversations/$CONV_ID/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled_tools": ["openapi_discovery"],
    "enabled_specs": ["petstore", "weather"]
  }'
```

The system prompt will be auto-augmented with the descriptions of the enabled specs so the model knows what services are available without burning a `list_specs` call every turn.
