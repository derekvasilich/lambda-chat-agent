import json
from typing import Any, Dict, List, Optional, Protocol

import httpx
import structlog

from app.config import settings
from app.openapi.auth import AuthResolver, RequestContext
from app.openapi.discovery_context import get_discovery_context
from app.openapi.embeddings import Embedder
from app.openapi.operation import Operation
from app.openapi.registry import SpecRegistry
from app.schemas.spec_source import SpecSourceResponse
from app.tools.base import BaseTool

logger = structlog.get_logger()


class SpecSourceProvider(Protocol):
    async def get(self, spec_id: str) -> Optional[SpecSourceResponse]: ...
    async def list(self) -> List[SpecSourceResponse]: ...


class OpenAPIDiscoveryTool(BaseTool):
    name = "openapi_discovery"
    description = (
        "Discover and call operations from registered OpenAPI services. "
        "Use action='list_specs' to see available services, "
        "action='list_operations' (with a natural-language query) to find relevant operations, "
        "and action='call_operation' to invoke one. "
        "Always call list_specs or list_operations before call_operation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_specs", "list_operations", "call_operation"],
                "description": "Which discovery action to perform.",
            },
            "spec_id": {
                "type": "string",
                "description": "ID of the spec source. Required for call_operation, optional for list_operations.",
            },
            "query": {
                "type": "string",
                "description": "Natural-language description of what you're looking for. Used by list_operations.",
            },
            "operation_id": {
                "type": "string",
                "description": "Operation ID returned by list_operations. Required for call_operation.",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments for call_operation. Path params, query params, and (if applicable) request body under key 'body'.",
            },
        },
        "required": ["action"],
    }

    def __init__(
        self,
        spec_source_provider_factory,
        registry: SpecRegistry,
        embedder: Embedder,
        auth_resolver: AuthResolver,
        http_client_factory=None,
    ):
        self._provider_factory = spec_source_provider_factory
        self._registry = registry
        self._embedder = embedder
        self._auth_resolver = auth_resolver
        self._http_client_factory = http_client_factory or _default_http_client

    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action")
        try:
            ctx = get_discovery_context()
        except RuntimeError as e:
            return _err(str(e))

        if action == "list_specs":
            return await self._list_specs(ctx.enabled_specs)
        if action == "list_operations":
            query = kwargs.get("query") or ""
            spec_id = kwargs.get("spec_id")
            return await self._list_operations(query, spec_id, ctx.enabled_specs)
        if action == "call_operation":
            spec_id = kwargs.get("spec_id")
            operation_id = kwargs.get("operation_id")
            arguments = kwargs.get("arguments") or {}
            if not spec_id or not operation_id:
                return _err("call_operation requires spec_id and operation_id")
            return await self._call_operation(
                spec_id, operation_id, arguments, ctx.request_context, ctx.enabled_specs,
            )
        return _err(f"Unknown action: {action!r}")

    async def _list_specs(self, enabled_specs: List[str]) -> str:
        if not enabled_specs:
            return json.dumps({"specs": [], "note": "No specs enabled on this conversation."})

        provider = await self._provider_factory()
        items = []
        for spec_id in enabled_specs:
            metadata = await provider.get(spec_id)
            if metadata is None:
                continue
            items.append({"spec_id": metadata.id, "description": metadata.description})
        return json.dumps({"specs": items})

    async def _list_operations(
        self,
        query: str,
        spec_id: Optional[str],
        enabled_specs: List[str],
    ) -> str:
        if not enabled_specs:
            return json.dumps({"matches": [], "note": "No specs enabled on this conversation."})

        scope = [spec_id] if spec_id else list(enabled_specs)
        if spec_id and spec_id not in enabled_specs:
            return _err(f"spec_id {spec_id!r} is not enabled on this conversation")

        await self._ensure_specs_loaded(scope)

        if not query.strip():
            ops = self._gather_operations(scope)
            slim = [op.slim_view() for op in ops[: settings.OPENAPI_LIST_OPERATIONS_TOP_K]]
            return json.dumps({"matches": slim})

        query_vec = (await self._embedder.embed([query]))[0]
        results = self._registry.index.search(
            query_vec, spec_ids=scope, top_k=settings.OPENAPI_LIST_OPERATIONS_TOP_K
        )
        ops_by_key = {(op.spec_id, op.op_id): op for op in self._gather_operations(scope)}
        slim = []
        for sid, op_id, _score in results:
            op = ops_by_key.get((sid, op_id))
            if op is not None:
                slim.append(op.slim_view())
        return json.dumps({"matches": slim})

    async def _call_operation(
        self,
        spec_id: str,
        operation_id: str,
        arguments: Dict[str, Any],
        request_context: RequestContext,
        enabled_specs: List[str],
    ) -> str:
        if spec_id not in enabled_specs:
            return _err(f"spec_id {spec_id!r} is not enabled on this conversation")

        await self._ensure_specs_loaded([spec_id])
        entry = self._registry.get_entry(spec_id)
        if entry is None:
            return _err(f"spec {spec_id!r} not found")

        operation = next((op for op in entry.operations if op.op_id == operation_id), None)
        if operation is None:
            return _err(f"operation {operation_id!r} not found in spec {spec_id!r}")

        auth_config = entry.metadata.auth
        if hasattr(auth_config, "model_dump"):
            auth_config = auth_config.model_dump()
        try:
            headers = await self._auth_resolver.headers_for(
                spec_id, auth_config, request_context,
            )
        except PermissionError as e:
            return _err(f"auth resolution failed: {e}")

        url, query_params, body, header_params = _build_request(operation, arguments)
        # Header params from spec parameters get merged into auth headers
        merged_headers = {**headers, **header_params}

        async with self._http_client_factory() as client:
            try:
                resp = await client.request(
                    operation.method.upper(),
                    url,
                    params=query_params or None,
                    json=body,
                    headers=merged_headers,
                )
            except httpx.HTTPError as e:
                return _err(f"upstream request failed: {e}")

        body_text = resp.text
        try:
            body_value = json.loads(body_text) if body_text else None
        except json.JSONDecodeError:
            body_value = body_text

        return json.dumps({
            "status_code": resp.status_code,
            "body": body_value,
            "operation": {"spec_id": spec_id, "operation_id": operation_id},
        })

    async def _ensure_specs_loaded(self, spec_ids: List[str]) -> None:
        provider = await self._provider_factory()
        for sid in spec_ids:
            if self._registry.get_entry(sid) is not None:
                continue
            metadata = await provider.get(sid)
            if metadata is None:
                continue
            await self._registry.ensure_loaded(metadata)

    def _gather_operations(self, spec_ids: List[str]) -> List[Operation]:
        ops: List[Operation] = []
        for sid in spec_ids:
            entry = self._registry.get_entry(sid)
            if entry is not None:
                ops.extend(entry.operations)
        return ops


def _build_request(
    operation: Operation,
    arguments: Dict[str, Any],
) -> tuple[str, Dict[str, Any], Optional[Dict[str, Any]], Dict[str, str]]:
    locations = operation.param_schema.get("x-param-locations", {})
    base_url = operation.servers[0].rstrip("/") if operation.servers else ""
    path = operation.path_template

    query_params: Dict[str, Any] = {}
    header_params: Dict[str, str] = {}
    body: Optional[Dict[str, Any]] = None

    for name, value in arguments.items():
        loc = locations.get(name, "query")
        if loc == "path":
            path = path.replace("{" + name + "}", str(value))
        elif loc == "header":
            header_params[name] = str(value)
        elif loc == "body":
            body = value if isinstance(value, dict) else {"value": value}
        else:
            query_params[name] = value

    url = f"{base_url}{path}" if base_url else path
    return url, query_params, body, header_params


def _default_http_client():
    return httpx.AsyncClient(timeout=30.0)


def _err(message: str) -> str:
    return json.dumps({"error": message})
