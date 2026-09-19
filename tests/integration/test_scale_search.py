"""Scale performance and query latency benchmark across retrieval modes (T026).

Verifies that multi-mode semantic search latency remains within performance targets
for a local Qdrant collection containing 1,000 indexed operations:
- Dense retrieval: < 250ms
- Hybrid retrieval (Dense + Sparse BM25 via RRF): < 250ms
- Hybrid + Cross-Encoder Reranking: < 1000ms (1.0s)
"""

import time
from collections.abc import Generator

import pytest

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.index.embedder import FastEmbedEngine
from specprobe.index.store import QdrantIndexStore, index_chunk_stream
from specprobe.search.engine import SearchEngine, SearchMode


@pytest.fixture(scope="module")
def scale_search_engine(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[SearchEngine, None, None]:
    """Populate a temporary embedded Qdrant store with 1,000 operation chunks and yield a warmed
    SearchEngine.

    Why module scope:
    Synthesizing, embedding, and indexing 1,000 operations takes ~6-8 seconds on CPU.
    Running it once per test module allows all three retrieval mode benchmark tests to evaluate
    steady-state search latencies against the exact same 1,000-point index without redundant setup.
    """
    index_dir = tmp_path_factory.mktemp("scale_index_1000")
    engine = FastEmbedEngine()

    # Generate 1,000 distinct OpenAPI operation chunks across multiple categories
    lines: list[str] = []
    categories = [
        "items",
        "orders",
        "customers",
        "inventory",
        "payments",
        "shipping",
        "analytics",
        "webhooks",
    ]
    for i in range(1000):
        category = categories[i % len(categories)]
        chunk = OperationChunk(
            metadata=ChunkMetadata(
                path=f"/{category}/{i}",
                method="GET" if i % 2 == 0 else "POST",
                operationId=f"op_{category}_{i}",
                source_title="ScaleCommerceAPI",
                source_version="2.0.0",
                tags=[category, f"partition_{i % 5}"],
            ),
            operation={
                "summary": f"Manage and process {category} record {i} within store catalog",
                "description": (
                    f"Extended operational endpoint handling lifecycle workflows for {category} "
                    f"entity {i}."
                ),
            },
            components={},
        )
        lines.append(chunk.model_dump_json())

    indexed_count, _, _ = index_chunk_stream(lines, index_path=index_dir, embedder=engine)
    assert indexed_count == 1000, f"Expected 1000 indexed operations, got {indexed_count}"

    with QdrantIndexStore(index_dir) as store:
        searcher = SearchEngine(index_dir, embedder=engine, store=store)

        # Warm up ONNX session runtimes so benchmarks measure search query execution,
        # not initial model weights loading from disk
        searcher.search("warmup query", mode=SearchMode.DENSE, limit=1)
        searcher.search("warmup query", mode=SearchMode.HYBRID, limit=1)
        searcher.search("warmup query", mode=SearchMode.HYBRID_RERANK, limit=1)

        yield searcher


def test_scale_dense_search_latency(scale_search_engine: SearchEngine) -> None:
    """Verify that dense vector search on 1,000 indexed operations executes in < 250ms.

    Why this matters:
    Dense search computes a single 384-dim BGE embedding for the query and executes an HNSW/cosine
    vector search in embedded Qdrant. This must complete well within the interactive CLI budget.
    """
    latencies: list[float] = []
    matches = []
    for _ in range(3):
        start_time = time.perf_counter()
        matches = scale_search_engine.search(
            "retrieve customer payments and billing records",
            mode=SearchMode.DENSE,
            limit=5,
        )
        latencies.append(time.perf_counter() - start_time)

    best_latency = min(latencies)
    assert len(matches) == 5, f"Expected 5 matches, got {len(matches)}"
    assert best_latency < 0.250, f"Dense search took {best_latency * 1000:.1f}ms (target < 250ms)"


def test_scale_hybrid_search_latency(scale_search_engine: SearchEngine) -> None:
    """Verify that hybrid search (Dense + BM25 via RRF) on 1,000 indexed operations
    executes in < 250ms.

    Why this matters:
    Hybrid search generates both dense and sparse BM25 query vectors, executes dual prefetch
    queries in Qdrant, and computes Reciprocal Rank Fusion on the candidate lists. It is the default
    CLI search mode and must feel near-instantaneous (< 250ms).
    """
    latencies: list[float] = []
    matches = []
    for _ in range(3):
        start_time = time.perf_counter()
        matches = scale_search_engine.search(
            "manage store catalog inventory items",
            mode=SearchMode.HYBRID,
            limit=5,
        )
        latencies.append(time.perf_counter() - start_time)

    best_latency = min(latencies)
    assert len(matches) == 5, f"Expected 5 matches, got {len(matches)}"
    assert best_latency < 0.250, f"Hybrid search took {best_latency * 1000:.1f}ms (target < 250ms)"


def test_scale_hybrid_rerank_search_latency(scale_search_engine: SearchEngine) -> None:
    """Verify that hybrid retrieval with cross-encoder reranking on 1,000 operations
    executes in < 1000ms.

    Why this matters:
    Hybrid-rerank fetches a pool of up to 20 candidates and evaluates token-level cross-attention
    using the local Xenova/ms-marco-MiniLM-L-6-v2 cross-encoder model on CPU.
    Although compute-intensive, it must comfortably meet the relaxed 1,000ms interactive threshold.
    """
    latencies: list[float] = []
    matches = []
    for _ in range(3):
        start_time = time.perf_counter()
        matches = scale_search_engine.search(
            "manage store catalog inventory items",
            mode=SearchMode.HYBRID_RERANK,
            limit=5,
        )
        latencies.append(time.perf_counter() - start_time)

    best_latency = min(latencies)
    assert len(matches) == 5, f"Expected 5 matches, got {len(matches)}"
    assert best_latency < 1.000, (
        f"Hybrid-rerank search took {best_latency * 1000:.1f}ms (target < 1000ms)"
    )
