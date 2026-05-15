from typing import Dict, List
from app.tools.base import BaseTool
from app.tools.calculator import CalculatorTool, WebSearchStubTool

_REGISTRY: Dict[str, BaseTool] = {}


def register_tool(tool: BaseTool):
    _REGISTRY[tool.name] = tool


def unregister_tool(name: str) -> None:
    _REGISTRY.pop(name, None)


def get_tool(name: str) -> BaseTool | None:
    return _REGISTRY.get(name)


def list_tools() -> List[str]:
    return list(_REGISTRY.keys())


def get_tools_for_conversation(enabled_tools: List[str]) -> List[BaseTool]:
    return [_REGISTRY[name] for name in enabled_tools if name in _REGISTRY]


# Register built-in tools
register_tool(CalculatorTool())
register_tool(WebSearchStubTool())


def register_default_openapi_discovery() -> None:
    from app.config import settings
    from app.openapi.auth import CompositeAuthResolver
    from app.openapi.embeddings import TitanBedrockEmbedder
    from app.openapi.fetcher import SpecFetcher
    from app.openapi.pgvector import PgvectorEmbeddingIndex
    from app.openapi.registry import SpecRegistry
    from app.postgres import get_postgres_pool
    from app.repositories.spec_sources_pg import SpecSourceRepositoryPG
    from app.tools.openapi_discovery import OpenAPIDiscoveryTool

    embedder = TitanBedrockEmbedder()
    index = PgvectorEmbeddingIndex(
        pool_factory=get_postgres_pool,
        table_name=settings.PGVECTOR_EMBEDDINGS_TABLE,
    )
    spec_reg = SpecRegistry(fetcher=SpecFetcher(), embedder=embedder, index=index)
    auth_resolver = CompositeAuthResolver()

    async def provider_factory():
        pool = await get_postgres_pool()
        return SpecSourceRepositoryPG(pool)

    tool = OpenAPIDiscoveryTool(
        spec_source_provider_factory=provider_factory,
        registry=spec_reg,
        embedder=embedder,
        auth_resolver=auth_resolver,
    )
    register_tool(tool)


register_default_openapi_discovery()
