"""Unit tests for the embedded Qdrant storage manager."""

import pytest
from qdrant_client import models

from specprobe.index.store import (
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    SPARSE_VECTOR_NAME,
    QdrantIndexStore,
    get_point_id,
)


@pytest.fixture
def store(tmp_path):
    return QdrantIndexStore(index_path=tmp_path / "index")


def test_collection_initialization(store):
    """Verify collection exists with named dense and sparse vector configurations."""
    assert store.client.collection_exists(store.collection_name)
    info = store.client.get_collection(store.collection_name)
    assert DENSE_VECTOR_NAME in info.config.params.vectors
    assert info.config.params.vectors[DENSE_VECTOR_NAME].size == DENSE_VECTOR_SIZE
    assert SPARSE_VECTOR_NAME in info.config.params.sparse_vectors


def test_upsert_and_generation_atomic_delete(store):
    """Verify points are upserted and older generation points are purged cleanly."""
    dense_vec = [0.1] * DENSE_VECTOR_SIZE
    sparse_vec = models.SparseVector(indices=[1, 2], values=[1.0, 0.5])

    # Generation 1: 2 operations
    gen1 = "gen-1111"
    pt1 = models.PointStruct(
        id=get_point_id("Petstore", "1.0.0", "op1"),
        vector={DENSE_VECTOR_NAME: dense_vec, SPARSE_VECTOR_NAME: sparse_vec},
        payload={
            "source_title": "Petstore",
            "source_version": "1.0.0",
            "operation_id": "op1",
            "generation_id": gen1,
        },
    )
    pt2 = models.PointStruct(
        id=get_point_id("Petstore", "1.0.0", "op2"),
        vector={DENSE_VECTOR_NAME: dense_vec, SPARSE_VECTOR_NAME: sparse_vec},
        payload={
            "source_title": "Petstore",
            "source_version": "1.0.0",
            "operation_id": "op2",
            "generation_id": gen1,
        },
    )
    store.upsert_points([pt1, pt2])

    stats1 = store.get_stats()
    assert stats1.total_operations == 2
    assert len(stats1.specifications) == 1
    assert stats1.specifications[0].chunk_count == 2

    # Generation 2: only op1 remains (op2 was removed in updated spec)
    gen2 = "gen-2222"
    pt1_v2 = models.PointStruct(
        id=get_point_id("Petstore", "1.0.0", "op1"),
        vector={DENSE_VECTOR_NAME: dense_vec, SPARSE_VECTOR_NAME: sparse_vec},
        payload={
            "source_title": "Petstore",
            "source_version": "1.0.0",
            "operation_id": "op1",
            "generation_id": gen2,
        },
    )
    store.upsert_points([pt1_v2])

    # Delete older generations
    store.delete_prior_generations("Petstore", "1.0.0", gen2)

    stats2 = store.get_stats()
    assert stats2.total_operations == 1
    assert stats2.specifications[0].chunk_count == 1


def test_empty_stats(tmp_path):
    """Verify stats on a newly created empty store."""
    empty_store = QdrantIndexStore(index_path=tmp_path / "empty_index")
    stats = empty_store.get_stats()
    assert stats.total_operations == 0
    assert stats.unique_specifications == 0
    assert stats.status == "empty"
