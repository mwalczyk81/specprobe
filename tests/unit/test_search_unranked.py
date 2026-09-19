"""Unit tests for unranked filter-only retrieval in SearchEngine."""

import json
from unittest.mock import MagicMock

import pytest

from specprobe.index.store import index_chunk_stream
from specprobe.search.engine import SearchEngine


@pytest.fixture(scope="module")
def populated_index(tmp_path_factory):
    """Create and populate a temporary index with multiple operations across specs."""
    index_path = tmp_path_factory.mktemp("search_unranked_index")

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
                "path": "/pets",
                "method": "POST",
                "operationId": "createPet",
                "tags": ["pets"],
                "deprecated": False,
                "source_title": "Petstore API",
                "source_version": "1.0.0",
                "estimated_tokens": 55,
                "warnings": [],
            },
            "operation": {
                "operationId": "createPet",
                "summary": "Create a pet",
                "description": "Creates a new pet in the store.",
                "tags": ["pets"],
                "responses": {"201": {"description": "Created"}},
            },
            "components": {},
        },
        {
            "metadata": {
                "path": "/pets/{petId}",
                "method": "GET",
                "operationId": "getPetById",
                "tags": ["pets"],
                "deprecated": True,
                "source_title": "Petstore API",
                "source_version": "1.0.0",
                "estimated_tokens": 60,
                "warnings": [],
            },
            "operation": {
                "operationId": "getPetById",
                "summary": "Find pet by ID (deprecated)",
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
        {
            "metadata": {
                "path": "/orders/{orderId}",
                "method": "GET",
                "operationId": "getOrderById",
                "tags": ["orders"],
                "deprecated": False,
                "source_title": "Store API",
                "source_version": "2.0.0",
                "estimated_tokens": 65,
                "warnings": [],
            },
            "operation": {
                "operationId": "getOrderById",
                "summary": "Get order by ID",
                "description": "Returns order details.",
                "tags": ["orders"],
                "responses": {"200": {"description": "OK"}},
            },
            "components": {},
        },
    ]

    lines = [json.dumps(c) for c in chunks]
    index_chunk_stream(lines, index_path=index_path)
    return index_path


def test_search_unranked_all_for_spec(populated_index):
    """Verify search_unranked returns all operations for a spec with score 0.0."""
    engine = SearchEngine(index_path=populated_index)
    matches = engine.search_unranked(source_title="Petstore API")

    # Petstore API has 3 operations
    assert len(matches) == 3
    op_ids = {m.operationId for m in matches}
    assert op_ids == {"listPets", "createPet", "getPetById"}

    # All matches must have score 0.0
    for match in matches:
        assert match.score == 0.0
        assert match.source_title == "Petstore API"
        assert match.chunk is None


def test_search_unranked_zero_embeddings(populated_index):
    """Verify search_unranked does not invoke the embedder."""
    mock_embedder = MagicMock()
    engine = SearchEngine(index_path=populated_index, embedder=mock_embedder)

    matches = engine.search_unranked(source_title="Store API")
    assert len(matches) == 2

    # Embedder must never be called during unranked search
    mock_embedder.embed_query.assert_not_called()
    mock_embedder.embed_dense.assert_not_called()
    mock_embedder.embed_sparse.assert_not_called()
    mock_embedder.rerank.assert_not_called()


def test_search_unranked_method_and_tag_filters(populated_index):
    """Verify search_unranked filters by HTTP method and tag."""
    engine = SearchEngine(index_path=populated_index)

    # Filter by method (case-insensitive)
    get_matches = engine.search_unranked(method="get")
    assert len(get_matches) == 3
    assert {m.operationId for m in get_matches} == {"listPets", "getPetById", "getOrderById"}

    # Filter by tag
    order_matches = engine.search_unranked(tag="orders")
    assert len(order_matches) == 2
    assert {m.operationId for m in order_matches} == {"createOrder", "getOrderById"}

    # Combined filter: method POST and tag pets
    post_pet_matches = engine.search_unranked(method="POST", tag="pets")
    assert len(post_pet_matches) == 1
    assert post_pet_matches[0].operationId == "createPet"


def test_search_unranked_deprecated_filter(populated_index):
    """Verify search_unranked filters by deprecation status."""
    engine = SearchEngine(index_path=populated_index)

    dep_matches = engine.search_unranked(source_title="Petstore API", deprecated=True)
    assert len(dep_matches) == 1
    assert dep_matches[0].operationId == "getPetById"

    non_dep_matches = engine.search_unranked(source_title="Petstore API", deprecated=False)
    assert len(non_dep_matches) == 2
    assert {m.operationId for m in non_dep_matches} == {"listPets", "createPet"}


def test_search_unranked_limit(populated_index):
    """Verify search_unranked respects explicit limit when provided."""
    engine = SearchEngine(index_path=populated_index)

    # Petstore has 3 operations; limit=2 should return exactly 2
    limited_matches = engine.search_unranked(source_title="Petstore API", limit=2)
    assert len(limited_matches) == 2
    for m in limited_matches:
        assert m.score == 0.0

    # Limit <= 0 should return empty list
    empty_matches = engine.search_unranked(source_title="Petstore API", limit=0)
    assert empty_matches == []


def test_search_unranked_full_payload(populated_index):
    """Verify search_unranked populates full chunk when full=True."""
    engine = SearchEngine(index_path=populated_index)

    matches = engine.search_unranked(source_title="Store API", method="POST", full=True)
    assert len(matches) == 1
    match = matches[0]
    assert match.operationId == "createOrder"
    assert match.chunk is not None
    assert match.chunk["metadata"]["operationId"] == "createOrder"
    assert match.chunk["operation"]["summary"] == "Create an order"


def test_search_unranked_no_matches(populated_index):
    """Verify search_unranked returns empty list when no points match filters."""
    engine = SearchEngine(index_path=populated_index)
    matches = engine.search_unranked(tag="non_existent_tag_xyz")
    assert matches == []


def test_search_unranked_empty_collection(tmp_path):
    """Verify search_unranked on empty index returns empty list."""
    empty_index = tmp_path / "empty_index"
    engine = SearchEngine(index_path=empty_index)
    matches = engine.search_unranked(source_title="Any Spec")
    assert matches == []
