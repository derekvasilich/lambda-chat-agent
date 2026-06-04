# Copilot Instructions for `chat-agent`

## Project Overview
This repository implements a secure, enterprise-grade asynchronous AI agent orchestration backend.

It is built as a FastAPI application with pluggable LLM providers, secure AWS Cognito/JWKS-based authentication, tool orchestration, OpenAPI discovery, conversational state storage, and support for AWS Lambda deployment.

## Key Responsibilities
- `app/main.py`: FastAPI app and router wiring.
- `app/config.py`: Pydantic settings and environment configuration.
- `app/auth/jwt.py`: JWT validation and Cognito/JWKS checks.
- `app/llm/`: pluggable model provider implementations for OpenAI, Anthropic, Bedrock, etc.
- `app/openapi/`: OpenAPI spec fetching, parsing, embeddings, and discovery logic.
- `app/repositories/`: persistence abstractions for conversations, messages, documents, and spec sources.
- `app/tools/`: registered tool execution logic for calculator, web search, and OpenAPI discovery.
- `app/models/`: object models and domain data types.
- `app/middleware/`: rate limiting and request middleware.

## Important Context
- The app is designed for secure multi-tenant environments and must avoid leaking sensitive authentication or model configuration data.
- Data is stored in DynamoDB for conversation/message state and PostgreSQL/pgvector for OpenAPI spec embeddings.
- Tests run under `pytest` and use in-memory mocks for external dependencies.
- The repo uses Python 3.11 and `hatchling` for packaging.

## Common Commands
- Install dependencies: `uv venv && uv pip install -e ".[test]"`
- Run locally: `uvicorn app.main:app --reload`
- Run tests: `pytest tests/ -v`

## Behavior Guidance
- Preserve existing API paths under `/v1/*` and the current enterprise security model.
- Prefer async implementations and avoid blocking I/O in request-handling code.
- When editing model provider code, keep provider-specific behavior isolated to `app/llm/`.
- Keep AWS and infrastructure changes separate from application logic unless the user explicitly asks for deployment changes.

## When in doubt
Use the repository structure and README as the source of truth for architecture, deployment, and test conventions.
