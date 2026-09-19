"""Unit tests for PromptBuilder and markdown code fence cleaning."""

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.generator.prompt import (
    PromptBuilder,
    clean_markdown_fences,
    resolve_operation_id,
)


def test_clean_markdown_fences_with_json_fence() -> None:
    """Verify that ```json ... ``` code blocks are cleanly stripped."""
    raw = '```json\n{\n  "operation_id": "testOp"\n}\n```'
    cleaned = clean_markdown_fences(raw)
    assert cleaned == '{\n  "operation_id": "testOp"\n}'


def test_clean_markdown_fences_with_plain_fence() -> None:
    """Verify that ``` ... ``` code blocks are cleanly stripped."""
    raw = '```\n{"operation_id": "testOp"}\n```'
    cleaned = clean_markdown_fences(raw)
    assert cleaned == '{"operation_id": "testOp"}'


def test_clean_markdown_fences_already_clean() -> None:
    """Verify that raw json without fences passes through cleanly."""
    raw = '{"operation_id": "testOp"}'
    cleaned = clean_markdown_fences(raw)
    assert cleaned == '{"operation_id": "testOp"}'


def test_resolve_operation_id() -> None:
    """Verify operation_id resolution order and fallback derivation."""
    # Explicit in operation dict
    chunk1 = OperationChunk(
        metadata=ChunkMetadata(path="/pets", method="GET", operationId="meta_pets"),
        operation={"operationId": "get_pets"},
    )
    assert resolve_operation_id(chunk1) == "get_pets"

    # Fallback to metadata operationId
    chunk2 = OperationChunk(
        metadata=ChunkMetadata(path="/pets", method="GET", operationId="meta_pets"),
        operation={},
    )
    assert resolve_operation_id(chunk2) == "meta_pets"

    # Fallback to method and path
    chunk3 = OperationChunk(
        metadata=ChunkMetadata(path="/pets/{petId}", method="DELETE", operationId=""),
        operation={},
    )
    assert resolve_operation_id(chunk3) == "DELETE_pets_petId"


def test_build_initial_messages() -> None:
    """Verify PromptBuilder synthesizes valid system and user messages."""
    chunk = OperationChunk(
        metadata=ChunkMetadata(path="/pets", method="GET", tags=["pets"], operationId="listPets"),
        operation={
            "operationId": "listPets",
            "summary": "List all pets",
            "parameters": [
                {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}}
            ],
            "responses": {"200": {"description": "OK"}},
        },
    )
    messages = PromptBuilder.build_initial_messages(chunk)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "You are an expert API testing engineer" in messages[0]["content"]

    assert messages[1]["role"] == "user"
    user_content = messages[1]["content"]
    assert "Target Operation: GET /pets" in user_content
    assert "Operation ID: listPets" in user_content
    assert "limit (query, optional, type: integer)" in user_content
    assert "200: OK" in user_content
