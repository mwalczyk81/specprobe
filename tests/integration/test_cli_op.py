"""Integration tests for specprobe chunk --op spot check option."""

import json
from pathlib import Path
from click.testing import CliRunner
from specprobe.cli import cli


def test_cli_chunk_op_explicit_id(valid_openapi_30_path: Path) -> None:
    """Verify --op outputs a single pretty-printed chunk for an explicit operationId."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(valid_openapi_30_path), "--op", "listPets"])

    assert result.exit_code == 0, f"Command failed: {result.output}"

    # Verify output is valid single-object JSON, not multiple JSONL lines
    chunk = json.loads(result.output)
    assert isinstance(chunk, dict)
    assert chunk["metadata"]["operationId"] == "listPets"
    assert chunk["metadata"]["method"] == "GET"
    assert chunk["metadata"]["path"] == "/pets"
    assert "Pet" in chunk["components"]["schemas"]

    # Verify pretty printing (indented formatted JSON)
    assert "\n  " in result.output


def test_cli_chunk_op_synthesized_id(valid_openapi_30_path: Path) -> None:
    """Verify --op locates and outputs a chunk with a synthesized operationId."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(valid_openapi_30_path), "--op", "delete_pets_pet_id"])

    assert result.exit_code == 0, f"Command failed: {result.output}"

    chunk = json.loads(result.output)
    assert chunk["metadata"]["operationId"] == "delete_pets_pet_id"
    assert chunk["metadata"]["method"] == "DELETE"
    assert chunk["metadata"]["path"] == "/pets/{petId}"
    assert chunk["metadata"]["deprecated"] is True


def test_cli_chunk_op_not_found(valid_openapi_30_path: Path) -> None:
    """Verify --op exits with code 1 and descriptive error when operationId is not found."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(valid_openapi_30_path), "--op", "unknown_operation_123"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()
    assert "unknown_operation_123" in result.output
