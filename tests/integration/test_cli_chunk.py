"""Integration tests for baseline JSONL streaming chunk command."""

import json
from pathlib import Path

from click.testing import CliRunner

from specprobe.cli import cli


def test_cli_chunk_jsonl_streaming(valid_openapi_30_path: Path) -> None:
    """Verify specprobe chunk outputs valid JSONL with one chunk per operation."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(valid_openapi_30_path)])

    assert result.exit_code == 0, f"Command failed: {result.output}"

    lines = [line.strip() for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) == 4, f"Expected 4 operations, got {len(lines)}"

    # Verify each line is an independent valid JSON chunk object
    chunks = [json.loads(line) for line in lines]
    op_ids = {c["metadata"]["operationId"] for c in chunks}
    assert op_ids == {"listPets", "createPets", "showPetById", "delete_pets_pet_id"}

    for chunk in chunks:
        assert "metadata" in chunk
        assert "operation" in chunk
        assert "components" in chunk
        assert chunk["metadata"]["estimated_tokens"] > 0
        assert chunk["metadata"]["source_title"] == "Petstore Probe API"


def test_cli_chunk_circular_spec(circular_spec_path: Path) -> None:
    """Verify specprobe chunk terminates and emits valid chunks for circular specifications."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(circular_spec_path)])

    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) == 2

    chunks = [json.loads(line) for line in lines]
    tree_chunk = next(c for c in chunks if c["metadata"]["operationId"] == "getTree")
    assert "Node" in tree_chunk["components"]["schemas"]


def test_cli_chunk_depth_capping(deep_chain_spec_path: Path) -> None:
    """Verify default schema depth 2 truncates deeper levels and reports warnings in chunk
    metadata.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(deep_chain_spec_path)])

    assert result.exit_code == 0, f"Command failed: {result.output}"
    chunk = json.loads(result.output.strip())

    # Included within depth 2
    assert "Level1" in chunk["components"]["schemas"]
    assert "Level2" in chunk["components"]["schemas"]
    # Truncated beyond depth 2
    assert "Level3" not in chunk["components"]["schemas"]
    assert "Level4" not in chunk["components"]["schemas"]

    # Warning attached to chunk metadata
    warnings = chunk["metadata"]["warnings"]
    assert len(warnings) == 1
    assert (
        "Schema 'Level3' at depth 3 exceeds schema depth limit of 2 and was truncated."
        in warnings[0]
    )


def test_cli_chunk_schema_depth_flag(deep_chain_spec_path: Path) -> None:
    """Verify --schema-depth CLI option overrides default depth limit."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(deep_chain_spec_path), "--schema-depth", "4"])

    assert result.exit_code == 0, f"Command failed: {result.output}"
    chunk = json.loads(result.output.strip())

    # All 4 levels included
    schemas = chunk["components"]["schemas"]
    assert {"Level1", "Level2", "Level3", "Level4"} <= set(schemas.keys())
    assert chunk["metadata"]["warnings"] == []
