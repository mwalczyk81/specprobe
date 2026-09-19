"""Unit tests for the FastEmbed engine wrapper."""

import pytest

from specprobe.index.embedder import DENSE_VECTOR_SIZE, FastEmbedEngine


@pytest.fixture(scope="module")
def engine():
    return FastEmbedEngine()


def test_embed_dense(engine):
    """Verify dense embeddings produce 384-dimensional float vectors."""
    texts = ["GET /pets — List all pets", "POST /orders — Create order"]
    vectors = engine.embed_dense(texts)
    assert len(vectors) == 2
    assert len(vectors[0]) == DENSE_VECTOR_SIZE
    assert len(vectors[1]) == DENSE_VECTOR_SIZE
    assert all(isinstance(v, float) for v in vectors[0])


def test_embed_query(engine):
    """Verify embed_query delegates directly to embed_dense([query])[0]."""
    query = "retrieve all pets"
    vector = engine.embed_query(query)
    expected = engine.embed_dense([query])[0]
    assert vector == expected
    assert len(vector) == DENSE_VECTOR_SIZE
    assert all(isinstance(v, float) for v in vector)


def test_embed_sparse(engine):
    """Verify sparse BM25 embeddings return valid token indices and weights."""
    texts = ["GET /pets — List all pets"]
    sparse_embs = engine.embed_sparse(texts)
    assert len(sparse_embs) == 1
    indices, values = sparse_embs[0]
    assert len(indices) > 0
    assert len(indices) == len(values)
    assert all(isinstance(idx, int) for idx in indices)
    assert all(isinstance(val, float) for val in values)


def test_rerank(engine):
    """Verify cross-encoder reranking produces ordinal relevance scores."""
    query = "retrieve a pet"
    docs = [
        "GET /pets/{petId} — Retrieve a pet by ID",
        "DELETE /orders/{orderId} — Cancel and delete an order",
    ]
    scores = engine.rerank(query, docs)
    assert len(scores) == 2
    # The pet endpoint should score higher than the order deletion endpoint
    assert scores[0] > scores[1]
