import json
from typing import Optional

import httpx
import pytest
import respx

from app.openapi.auth import CompositeAuthResolver, RequestContext
from app.openapi.discovery_context import (
    DiscoveryContext,
    clear_discovery_context,
    set_discovery_context,
)
from app.openapi.fetcher import SpecFetcher
from app.openapi.registry import SpecRegistry
from app.schemas.spec_source import SpecSourceResponse
from app.tools.openapi_discovery import OpenAPIDiscoveryTool


SAMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Billing", "version": "1.0"},
    "servers": [{"url": "https://billing.test"}],
    "paths": {
        "/invoices": {
            "get": {
                "operationId": "listInvoices",
                "summary": "List invoices",
                "parameters": [
                    {"name": "status", "in": "query", "schema": {"type": "string"}}
                ],
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/invoices/{id}": {
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
            ],
            "get": {
                "operationId": "getInvoice",
                "summary": "Get invoice by ID",
                "responses": {"200": {"description": "ok"}},
            },
        },
    },
}


class StubEmbedder:
    """Deterministic embedder: maps any text to a low-dim vector by hashing word counts."""

    def __init__(self):
        self._vocab = ["invoice", "list", "get", "refund", "outstanding", "by", "id"]

    async def embed(self, texts):
        vectors = []
        for t in texts:
            t_low = t.lower()
            v = [float(t_low.count(w)) for w in self._vocab]
            vectors.append(v)
        return vectors


class StubProvider:
    def __init__(self, specs: dict[str, SpecSourceResponse]):
        self._specs = specs

    async def get(self, spec_id: str) -> Optional[SpecSourceResponse]:
        return self._specs.get(spec_id)

    async def list(self):
        return list(self._specs.values())


def _make_metadata(spec_id: str, auth: dict) -> SpecSourceResponse:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return SpecSourceResponse(
        id=spec_id,
        url=f"https://specs.test/{spec_id}.json",
        description=f"{spec_id.title()} service",
        auth=auth,
        created_at=now,
        updated_at=now,
    )


def _make_tool(provider: StubProvider) -> OpenAPIDiscoveryTool:
    embedder = StubEmbedder()
    spec_registry = SpecRegistry(fetcher=SpecFetcher(), embedder=embedder)

    async def provider_factory():
        return provider

    return OpenAPIDiscoveryTool(
        spec_source_provider_factory=provider_factory,
        registry=spec_registry,
        embedder=embedder,
        auth_resolver=CompositeAuthResolver(),
    )


def _set_ctx(enabled_specs: list[str], token: str | None = "test-token"):
    set_discovery_context(DiscoveryContext(
        request_context=RequestContext(user_sub="u1", bearer_token=token),
        enabled_specs=enabled_specs,
    ))


@pytest.fixture(autouse=True)
def _clear_ctx():
    clear_discovery_context()
    yield
    clear_discovery_context()


@pytest.mark.asyncio
async def test_list_specs_returns_enabled_ones_only():
    provider = StubProvider({
        "billing": _make_metadata("billing", {"type": "none"}),
        "identity": _make_metadata("identity", {"type": "none"}),
    })
    tool = _make_tool(provider)

    _set_ctx(enabled_specs=["billing"])
    result = json.loads(await tool.execute(action="list_specs"))
    assert len(result["specs"]) == 1
    assert result["specs"][0]["spec_id"] == "billing"


@pytest.mark.asyncio
async def test_list_specs_returns_note_when_none_enabled():
    tool = _make_tool(StubProvider({}))
    _set_ctx(enabled_specs=[])
    result = json.loads(await tool.execute(action="list_specs"))
    assert result["specs"] == []
    assert "No specs enabled" in result["note"]


@pytest.mark.asyncio
async def test_list_operations_returns_matches():
    provider = StubProvider({"billing": _make_metadata("billing", {"type": "none"})})
    tool = _make_tool(provider)
    _set_ctx(enabled_specs=["billing"])

    with respx.mock:
        respx.get("https://specs.test/billing.json").mock(
            return_value=httpx.Response(
                200, content=json.dumps(SAMPLE_SPEC),
                headers={"content-type": "application/json"},
            )
        )
        result = json.loads(await tool.execute(
            action="list_operations", query="list invoices"
        ))

    op_ids = [m["operation_id"] for m in result["matches"]]
    assert "listInvoices" in op_ids
    assert "getInvoice" in op_ids
    # listInvoices should rank above getInvoice for "list invoices"
    assert op_ids.index("listInvoices") < op_ids.index("getInvoice")


@pytest.mark.asyncio
async def test_list_operations_rejects_disabled_spec():
    provider = StubProvider({"billing": _make_metadata("billing", {"type": "none"})})
    tool = _make_tool(provider)
    _set_ctx(enabled_specs=["billing"])

    result = json.loads(await tool.execute(
        action="list_operations", spec_id="identity", query="anything"
    ))
    assert "error" in result


@pytest.mark.asyncio
async def test_call_operation_passes_through_auth_and_returns_body():
    provider = StubProvider({"billing": _make_metadata("billing", {"type": "passthrough_jwt"})})
    tool = _make_tool(provider)
    _set_ctx(enabled_specs=["billing"], token="my-jwt")

    with respx.mock:
        respx.get("https://specs.test/billing.json").mock(
            return_value=httpx.Response(
                200, content=json.dumps(SAMPLE_SPEC),
                headers={"content-type": "application/json"},
            )
        )
        route = respx.get("https://billing.test/invoices/inv_123").mock(
            return_value=httpx.Response(
                200,
                content=json.dumps({"id": "inv_123", "amount": 100}),
                headers={"content-type": "application/json"},
            )
        )

        result = json.loads(await tool.execute(
            action="call_operation",
            spec_id="billing",
            operation_id="getInvoice",
            arguments={"id": "inv_123"},
        ))

    assert result["status_code"] == 200
    assert result["body"]["id"] == "inv_123"
    # Verify the inbound JWT was forwarded
    call = route.calls[0]
    assert call.request.headers["authorization"] == "Bearer my-jwt"


@pytest.mark.asyncio
async def test_call_operation_forwards_query_params():
    provider = StubProvider({"billing": _make_metadata("billing", {"type": "none"})})
    tool = _make_tool(provider)
    _set_ctx(enabled_specs=["billing"])

    with respx.mock:
        respx.get("https://specs.test/billing.json").mock(
            return_value=httpx.Response(
                200, content=json.dumps(SAMPLE_SPEC),
                headers={"content-type": "application/json"},
            )
        )
        route = respx.get("https://billing.test/invoices").mock(
            return_value=httpx.Response(200, content="[]",
                                        headers={"content-type": "application/json"})
        )

        await tool.execute(
            action="call_operation",
            spec_id="billing",
            operation_id="listInvoices",
            arguments={"status": "open"},
        )

    assert route.calls[0].request.url.params["status"] == "open"


@pytest.mark.asyncio
async def test_call_operation_rejects_disabled_spec():
    provider = StubProvider({"billing": _make_metadata("billing", {"type": "none"})})
    tool = _make_tool(provider)
    _set_ctx(enabled_specs=["other"])

    result = json.loads(await tool.execute(
        action="call_operation",
        spec_id="billing",
        operation_id="listInvoices",
        arguments={},
    ))
    assert "error" in result


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    tool = _make_tool(StubProvider({}))
    _set_ctx(enabled_specs=[])
    result = json.loads(await tool.execute(action="frobnicate"))
    assert "error" in result


@pytest.mark.asyncio
async def test_passthrough_without_token_returns_error():
    provider = StubProvider({"billing": _make_metadata("billing", {"type": "passthrough_jwt"})})
    tool = _make_tool(provider)
    _set_ctx(enabled_specs=["billing"], token=None)

    with respx.mock:
        respx.get("https://specs.test/billing.json").mock(
            return_value=httpx.Response(
                200, content=json.dumps(SAMPLE_SPEC),
                headers={"content-type": "application/json"},
            )
        )
        result = json.loads(await tool.execute(
            action="call_operation",
            spec_id="billing",
            operation_id="getInvoice",
            arguments={"id": "x"},
        ))

    assert "error" in result
    assert "passthrough_jwt" in result["error"]


@pytest.mark.asyncio
async def test_no_context_set_returns_error():
    tool = _make_tool(StubProvider({}))
    # Don't set context
    result = json.loads(await tool.execute(action="list_specs"))
    assert "error" in result
