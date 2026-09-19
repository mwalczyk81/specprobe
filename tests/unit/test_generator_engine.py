"""Unit tests for GenerationEngine and search results input parsing."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.generator.engine import GenerationEngine, parse_search_results
from specprobe.generator.gateway import LLMGateway
from specprobe.generator.models import GeneratedTestCase


@pytest.fixture
def sample_chunk() -> OperationChunk:
    return OperationChunk(
        metadata=ChunkMetadata(
            path="/pets",
            method="GET",
            operationId="listPets",
            tags=["pets"],
            deprecated=False,
            source_title="Petstore",
            source_version="1.0.0",
        ),
        operation={
            "operationId": "listPets",
            "summary": "List all pets",
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer"},
                }
            ],
            "responses": {
                "200": {"description": "A list of pets"},
            },
            "tags": ["pets"],
        },
        components={},
    )


# ---------------------------------------------------------------------------
# Tests for parse_search_results
# ---------------------------------------------------------------------------


def test_parse_search_results_valid_fixture() -> None:
    """Verify parsing a valid search_full_results.json fixture produces OperationChunks."""
    fixture_path = Path("tests/fixtures/search_full_results.json")
    content = fixture_path.read_text(encoding="utf-8")
    chunks = parse_search_results(content)

    assert len(chunks) == 2
    assert all(isinstance(c, OperationChunk) for c in chunks)
    assert chunks[0].metadata.operationId == "listPets"
    assert chunks[0].metadata.path == "/pets"
    assert chunks[0].metadata.method == "GET"
    assert chunks[1].metadata.operationId == "showPetById"
    assert chunks[1].metadata.path == "/pets/{petId}"


def test_parse_search_results_empty_array() -> None:
    """Verify parsing an empty JSON array returns an empty list."""
    chunks = parse_search_results("[]")
    assert chunks == []


def test_parse_search_results_invalid_json() -> None:
    """Verify unparseable JSON raises ValueError."""
    with pytest.raises(ValueError, match="Invalid JSON input"):
        parse_search_results("{invalid json")


def test_parse_search_results_not_array() -> None:
    """Verify non-array JSON raises ValueError."""
    with pytest.raises(ValueError, match="expected a JSON array of search results"):
        parse_search_results('{"operationId": "listPets"}')


def test_parse_search_results_missing_chunk() -> None:
    """Verify search results without 'chunk' payload are rejected with informative error."""
    compact_results = json.dumps(
        [
            {
                "operationId": "listPets",
                "path": "/pets",
                "method": "GET",
                "score": 0.88,
                "chunk": None,
            }
        ]
    )
    with pytest.raises(ValueError, match="missing full 'chunk' payload.*--full"):
        parse_search_results(compact_results)


def test_parse_search_results_invalid_chunk_schema() -> None:
    """Verify invalid chunk schema within search results raises ValueError."""
    invalid_chunk = json.dumps(
        [
            {
                "operationId": "listPets",
                "path": "/pets",
                "method": "GET",
                "chunk": {"not_a_valid_chunk": True},
            }
        ]
    )
    with pytest.raises(ValueError, match="Invalid OperationChunk schema"):
        parse_search_results(invalid_chunk)


# ---------------------------------------------------------------------------
# Tests for GenerationEngine.generate_chunk
# ---------------------------------------------------------------------------


def test_generate_chunk_success(sample_chunk: OperationChunk) -> None:
    """Verify successful test case generation from a valid LLM response."""
    valid_llm_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Retrieve pets with limit query parameter",
            "request": {
                "path_params": {},
                "query_params": {"limit": 10},
                "headers": {"Accept": "application/json"},
                "body": None,
            },
            "response": {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "schema_shape": {"type": "array"},
            },
            "tags": ["pets"],
        }
    )

    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.return_value = valid_llm_json

    engine = GenerationEngine(gateway=mock_gateway)
    test_case = engine.generate_chunk(sample_chunk)

    assert isinstance(test_case, GeneratedTestCase)
    assert test_case.operation_id == "listPets"
    assert test_case.description == "Retrieve pets with limit query parameter"
    assert test_case.request.query_params == {"limit": 10}
    assert test_case.response.status_code == 200
    assert test_case.tags == ["pets"]
    mock_gateway.complete.assert_called_once()


def test_generate_chunk_strips_markdown_fences_and_preamble(
    sample_chunk: OperationChunk,
) -> None:
    """Verify model responses enclosed in markdown code fences with preamble are parsed."""
    fenced_output = (
        "Here is the generated test case for listPets:\n"
        "```json\n"
        "{\n"
        '  "operation_id": "listPets",\n'
        '  "description": "Fetch pet list successfully",\n'
        '  "request": {\n'
        '    "path_params": {},\n'
        '    "query_params": {},\n'
        '    "headers": {},\n'
        '    "body": null\n'
        "  },\n"
        '  "response": {\n'
        '    "status_code": 200,\n'
        '    "headers": {},\n'
        '    "schema_shape": null\n'
        "  },\n"
        '  "tags": ["pets"]\n'
        "}\n"
        "```\n"
        "Hope this helps!"
    )

    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.return_value = fenced_output

    engine = GenerationEngine(gateway=mock_gateway)
    test_case = engine.generate_chunk(sample_chunk)

    assert isinstance(test_case, GeneratedTestCase)
    assert test_case.operation_id == "listPets"
    assert test_case.response.status_code == 200


def test_generate_chunk_operation_id_fallback(sample_chunk: OperationChunk) -> None:
    """Verify that omitted operation_id falls back to resolve_operation_id."""
    llm_json_no_op_id = json.dumps(
        {
            "description": "Fetch pet list successfully",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": [],
        }
    )

    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.return_value = llm_json_no_op_id

    engine = GenerationEngine(gateway=mock_gateway)
    test_case = engine.generate_chunk(sample_chunk)

    assert test_case.operation_id == "listPets"
    assert test_case.tags == ["pets"]  # Inherited from sample_chunk


def test_generate_chunk_invalid_schema_raises(sample_chunk: OperationChunk) -> None:
    """Verify that schema validation errors (e.g. invalid status code) raise ValidationError."""
    invalid_status_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pet list",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {
                "status_code": 999,  # Invalid HTTP status code (> 599)
                "headers": {},
                "schema_shape": None,
            },
            "tags": [],
        }
    )

    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.return_value = invalid_status_json

    engine = GenerationEngine(gateway=mock_gateway)
    with pytest.raises(ValueError, match="Validation failed after retry"):
        engine.generate_chunk(sample_chunk)


def test_generate_chunk_non_json_raises(sample_chunk: OperationChunk) -> None:
    """Verify that non-JSON output from the model raises ValueError."""
    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.return_value = "I am an AI and cannot generate test cases."

    engine = GenerationEngine(gateway=mock_gateway)
    with pytest.raises(ValueError, match="JSON"):
        engine.generate_chunk(sample_chunk)
