import pytest

from app.openapi.embeddings import EmbeddingIndex, index_operations
from app.openapi.operation import Operation


class StubEmbedder:
    def __init__(self, mapping: dict[str, list[float]]):
        self._mapping = mapping
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [self._mapping[t] for t in texts]


def _op(spec_id: str, op_id: str, text_keywords: str) -> Operation:
    return Operation(
        spec_id=spec_id,
        op_id=op_id,
        method="get",
        path_template=f"/{op_id}",
        summary=text_keywords,
        description="",
        param_schema={"type": "object", "properties": {}},
    )


@pytest.mark.asyncio
async def test_cosine_ordering():
    index = EmbeddingIndex()
    await index.add("a", "x", [1.0, 0.0])
    await index.add("a", "y", [0.0, 1.0])
    await index.add("a", "z", [0.7, 0.7])

    results = await index.search([1.0, 0.0], spec_ids=None, top_k=3)
    assert results[0][1] == "x"
    assert results[1][1] == "z"
    assert results[2][1] == "y"


@pytest.mark.asyncio
async def test_search_filters_by_spec_ids():
    index = EmbeddingIndex()
    await index.add("a", "x", [1.0, 0.0])
    await index.add("b", "x", [1.0, 0.0])

    results = await index.search([1.0, 0.0], spec_ids=["a"], top_k=10)
    assert len(results) == 1
    assert results[0][0] == "a"


@pytest.mark.asyncio
async def test_top_k_limits_results():
    index = EmbeddingIndex()
    for i in range(50):
        await index.add("a", f"op{i}", [float(i), 1.0])

    results = await index.search([1.0, 1.0], spec_ids=None, top_k=5)
    assert len(results) == 5


@pytest.mark.asyncio
async def test_remove_spec_drops_vectors():
    index = EmbeddingIndex()
    await index.add("a", "x", [1.0])
    await index.add("b", "y", [1.0])

    await index.remove_spec("a")
    assert await index.get("a", "x") is None
    assert await index.get("b", "y") == [1.0]


@pytest.mark.asyncio
async def test_index_operations_populates_index():
    ops = [
        _op("billing", "listInvoices", "List invoices"),
        _op("billing", "createRefund", "Create a refund"),
    ]
    mapping = {ops[0].embedding_text(): [1.0, 0.0], ops[1].embedding_text(): [0.0, 1.0]}
    embedder = StubEmbedder(mapping)
    index = EmbeddingIndex()

    await index_operations(embedder, index, ops)
    assert await index.get("billing", "listInvoices") == [1.0, 0.0]
    assert await index.get("billing", "createRefund") == [0.0, 1.0]


@pytest.mark.asyncio
async def test_index_operations_noop_on_empty():
    embedder = StubEmbedder({})
    index = EmbeddingIndex()
    await index_operations(embedder, index, [])
    assert embedder.calls == []


@pytest.mark.asyncio
async def test_mismatched_dims_returns_zero_similarity():
    index = EmbeddingIndex()
    await index.add("a", "x", [1.0, 0.0])
    # Query with wrong dim
    results = await index.search([1.0, 0.0, 0.0], spec_ids=None, top_k=5)
    assert results[0][2] == 0.0
