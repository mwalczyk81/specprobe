"""FastEmbed model wrapper for dense, sparse (BM25), and cross-encoder reranking."""

from collections.abc import Iterable, Sequence

from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

DEFAULT_DENSE_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_SPARSE_MODEL = "Qdrant/bm25"
DEFAULT_RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
DENSE_VECTOR_SIZE = 384


class FastEmbedEngine:
    """Manages local ONNX-based embedding and reranking models."""

    def __init__(
        self,
        dense_model_name: str = DEFAULT_DENSE_MODEL,
        sparse_model_name: str = DEFAULT_SPARSE_MODEL,
        reranker_model_name: str = DEFAULT_RERANKER_MODEL,
    ) -> None:
        self.dense_model_name = dense_model_name
        self.sparse_model_name = sparse_model_name
        self.reranker_model_name = reranker_model_name

        self._dense_model: TextEmbedding | None = None
        self._sparse_model: SparseTextEmbedding | None = None
        self._reranker_model: TextCrossEncoder | None = None

    @property
    def dense_model(self) -> TextEmbedding:
        if self._dense_model is None:
            self._dense_model = TextEmbedding(model_name=self.dense_model_name)
        return self._dense_model

    @property
    def sparse_model(self) -> SparseTextEmbedding:
        if self._sparse_model is None:
            self._sparse_model = SparseTextEmbedding(model_name=self.sparse_model_name)
        return self._sparse_model

    @property
    def reranker_model(self) -> TextCrossEncoder:
        if self._reranker_model is None:
            self._reranker_model = TextCrossEncoder(model_name=self.reranker_model_name)
        return self._reranker_model

    def embed_dense(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute dense vector embeddings for a sequence of texts."""
        if not texts:
            return []
        embeddings = self.dense_model.embed(texts)
        return [vec.tolist() for vec in embeddings]

    def embed_query(self, query: str) -> list[float]:
        """Compute a dense vector embedding for a single search query."""
        return self.embed_dense([query])[0]

    def embed_sparse(self, texts: Sequence[str]) -> list[tuple[list[int], list[float]]]:
        """Compute sparse token embeddings (indices and values) for a sequence of texts."""
        if not texts:
            return []
        embeddings = self.sparse_model.embed(texts)
        results: list[tuple[list[int], list[float]]] = []
        for emb in embeddings:
            results.append((emb.indices.tolist(), emb.values.tolist()))
        return results

    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Compute cross-encoder relevance scores for (query, document) pairs.

        Scores are uncalibrated logits used exclusively for ordinal candidate ranking
        within a single query pass.
        """
        if not documents:
            return []
        scores_iter: Iterable[float] = self.reranker_model.rerank(query, documents)
        return list(scores_iter)
