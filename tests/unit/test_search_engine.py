"""Unit tests for SearchEngine and multi-mode retrieval."""

import json

import pytest

from specprobe.index.store import index_chunk_stream
from specprobe.search.engine import SearchEngine, SearchMode


@pytest.fixture(scope="module")
def populated_index(tmp_path_factory):
    index_path = tmp_path_factory.mktemp("search_test_index")

    chunks = [
        {
            "metadata": {
                "path": "/pets",
                "method": "GET",
                "operationId": "listPets",
                "tags": ["pets"],
                "deprecated": False,
                "source_title": "Petstore API",
                "source_version": "1.0.0",
                "estimated_tokens": 50,
                "warnings": [],
            },
            "operation": {
                "operationId": "listPets",
                "summary": "List all pets",
                "description": "Returns a collection of pets.",
                "tags": ["pets"],
                "responses": {"200": {"description": "OK"}},
            },
            "components": {},
        },
        {
            "metadata": {
                "path": "/pets/{petId}",
                "method": "GET",
                "operationId": "getPetById",
                "tags": ["pets"],
                "deprecated": False,
                "source_title": "Petstore API",
                "source_version": "1.0.0",
                "estimated_tokens": 60,
                "warnings": [],
            },
            "operation": {
                "operationId": "getPetById",
                "summary": "Find pet by ID",
                "description": "Returns single pet matching the identifier.",
                "tags": ["pets"],
                "parameters": [
                    {"name": "petId", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {"200": {"description": "OK"}},
            },
            "components": {},
        },
        {
            "metadata": {
                "path": "/orders",
                "method": "POST",
                "operationId": "createOrder",
                "tags": ["orders"],
                "deprecated": False,
                "source_title": "Store API",
                "source_version": "2.0.0",
                "estimated_tokens": 70,
                "warnings": [],
            },
            "operation": {
                "operationId": "createOrder",
                "summary": "Create an order",
                "description": "Places a new order for pets.",
                "tags": ["orders"],
                "responses": {"201": {"description": "Created"}},
            },
            "components": {},
        },
    ]

    lines = [json.dumps(c) for c in chunks]
    index_chunk_stream(lines, index_path=index_path)
    return index_path


def test_dense_search(populated_index):
    """Verify dense retrieval finds relevant pet lookup operation."""
    engine = SearchEngine(index_path=populated_index)
    matches = engine.search("find a pet by id", mode=SearchMode.DENSE, limit=2)
    assert len(matches) > 0
    assert matches[0].operationId == "getPetById"
    assert isinstance(matches[0].score, float)
    assert matches[0].chunk is None


def test_hybrid_search(populated_index):
    """Verify hybrid search returns RRF-fused matches."""
    engine = SearchEngine(index_path=populated_index)
    matches = engine.search("list all pets", mode=SearchMode.HYBRID, limit=2)
    assert len(matches) > 0
    assert matches[0].operationId == "listPets"
    assert isinstance(matches[0].score, float)


def test_hybrid_rerank_search(populated_index):
    """Verify hybrid-rerank scores candidates via cross-encoder."""
    engine = SearchEngine(index_path=populated_index)
    matches = engine.search("place a new order", mode=SearchMode.HYBRID_RERANK, limit=2)
    assert len(matches) > 0
    assert matches[0].operationId == "createOrder"
    assert isinstance(matches[0].score, float)


def test_filters(populated_index):
    """Verify metadata filtering restricts candidates."""
    engine = SearchEngine(index_path=populated_index)

    # Filter by method POST
    post_matches = engine.search("pets", method="POST")
    assert all(m.method == "POST" for m in post_matches)

    # Filter by tag orders
    order_matches = engine.search("pets", tag="orders")
    assert all("orders" in m.tags for m in order_matches)

    # Filter by source title
    store_matches = engine.search("pets", source_title="Store API")
    assert all(m.source_title == "Store API" for m in store_matches)


def test_full_payload(populated_index):
    """Verify --full returns raw chunk payload."""
    engine = SearchEngine(index_path=populated_index)
    matches = engine.search("list all pets", limit=1, full=True)
    assert len(matches) == 1
    assert matches[0].chunk is not None
    assert "metadata" in matches[0].chunk
    assert "operation" in matches[0].chunk
