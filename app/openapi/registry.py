import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import structlog

from app.openapi.embeddings import Embedder, EmbeddingIndex, index_operations
from app.openapi.fetcher import SpecFetcher
from app.openapi.operation import Operation
from app.openapi.parser import parse_spec
from app.schemas.spec_source import SpecSourceResponse

logger = structlog.get_logger()


@dataclass
class SpecCacheEntry:
    metadata: SpecSourceResponse
    operations: List[Operation] = field(default_factory=list)
    cache_etag: Optional[str] = None


class SpecRegistry:
    def __init__(self, fetcher: SpecFetcher, embedder: Embedder, index: EmbeddingIndex | None = None):
        self._fetcher = fetcher
        self._embedder = embedder
        self._entries: Dict[str, SpecCacheEntry] = {}
        self._index = index or EmbeddingIndex()
        self._locks: Dict[str, asyncio.Lock] = {}

    @property
    def index(self) -> EmbeddingIndex:
        return self._index

    def get_entry(self, spec_id: str) -> Optional[SpecCacheEntry]:
        return self._entries.get(spec_id)

    def list_entries(self) -> List[SpecCacheEntry]:
        return list(self._entries.values())

    async def remove(self, spec_id: str) -> None:
        self._entries.pop(spec_id, None)
        await self._index.remove_spec(spec_id)

    async def ensure_loaded(self, metadata: SpecSourceResponse) -> SpecCacheEntry:
        lock = self._locks.setdefault(metadata.id, asyncio.Lock())
        async with lock:
            existing = self._entries.get(metadata.id)
            if existing is not None:
                # Refresh metadata in case description/auth changed
                existing.metadata = metadata
                return existing
            return await self._load(metadata)

    async def force_reload(self, metadata: SpecSourceResponse) -> SpecCacheEntry:
        lock = self._locks.setdefault(metadata.id, asyncio.Lock())
        async with lock:
            await self._index.remove_spec(metadata.id)
            self._entries.pop(metadata.id, None)
            return await self._load(metadata)

    async def _load(self, metadata: SpecSourceResponse) -> SpecCacheEntry:
        try:
            fetch_result = await self._fetcher.fetch(metadata.url, etag=metadata.cache_etag)
        except Exception as e:
            logger.warning("spec_fetch_failed", spec_id=metadata.id, error=str(e))
            entry = SpecCacheEntry(metadata=metadata, operations=[], cache_etag=metadata.cache_etag)
            self._entries[metadata.id] = entry
            return entry

        if fetch_result.not_modified:
            entry = SpecCacheEntry(metadata=metadata, operations=[], cache_etag=metadata.cache_etag)
            self._entries[metadata.id] = entry
            return entry

        operations = parse_spec(metadata.id, fetch_result.spec)
        await index_operations(self._embedder, self._index, operations)
        entry = SpecCacheEntry(
            metadata=metadata,
            operations=operations,
            cache_etag=fetch_result.etag,
        )
        self._entries[metadata.id] = entry
        return entry
