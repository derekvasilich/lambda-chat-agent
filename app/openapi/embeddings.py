import json
import math
from typing import List, Protocol, Sequence, Tuple

import aioboto3

from app.config import settings
from app.openapi.operation import Operation


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> List[List[float]]: ...


class TitanBedrockEmbedder:
    def __init__(self, model_id: str | None = None, region: str | None = None):
        self.model_id = model_id or settings.BEDROCK_EMBEDDING_MODEL
        self.region = region or settings.AWS_REGION
        self._session = aioboto3.Session()

    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        async with self._session.client("bedrock-runtime", region_name=self.region) as client:
            vectors: List[List[float]] = []
            for text in texts:
                body = json.dumps({"inputText": text})
                resp = await client.invoke_model(
                    modelId=self.model_id,
                    body=body,
                    accept="application/json",
                    contentType="application/json",
                )
                payload = await resp["body"].read()
                data = json.loads(payload)
                vectors.append(data["embedding"])
            return vectors


class EmbeddingIndex:
    def __init__(self):
        self._vectors: dict[Tuple[str, str], List[float]] = {}

    async def add(self, spec_id: str, op_id: str, vector: List[float]) -> None:
        self._vectors[(spec_id, op_id)] = vector

    async def remove_spec(self, spec_id: str) -> None:
        keys = [k for k in self._vectors if k[0] == spec_id]
        for k in keys:
            del self._vectors[k]

    async def get(self, spec_id: str, op_id: str) -> List[float] | None:
        return self._vectors.get((spec_id, op_id))

    async def search(
        self,
        query_vector: List[float],
        spec_ids: List[str] | None,
        top_k: int,
    ) -> List[Tuple[str, str, float]]:
        results: List[Tuple[str, str, float]] = []
        for (spec_id, op_id), vec in self._vectors.items():
            if spec_ids is not None and spec_id not in spec_ids:
                continue
            score = _cosine(query_vector, vec)
            results.append((spec_id, op_id, score))
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:top_k]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


async def index_operations(
    embedder: Embedder,
    index: EmbeddingIndex,
    operations: List[Operation],
) -> None:
    if not operations:
        return
    texts = [op.embedding_text() for op in operations]
    vectors = await embedder.embed(texts)
    for op, vec in zip(operations, vectors):
        await index.add(op.spec_id, op.op_id, vec)
