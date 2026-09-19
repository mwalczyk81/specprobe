"""Integration tests for the specprobe index CLI command."""

import json

from click.testing import CliRunner

from specprobe.cli import cli
from specprobe.index.store import QdrantIndexStore


def _sample_chunk(op_id: str, title: str = "Test API", version: str = "1.0.0") -> dict:
    return {
        "metadata": {
            "path": f"/{op_id}",
            "method": "GET",
            "operationId": op_id,
            "tags": ["test"],
            "deprecated": False,
            "source_title": title,
            "source_version": version,
            "estimated_tokens": 50,
            "warnings": [],
        },
        "operation": {
            "operationId": op_id,
            "summary": f"Summary for {op_id}",
            "description": f"Detailed description for {op_id}",
            "tags": ["test"],
            "parameters": [
                {
                    "name": "id",
                    "in": "query",
                    "required": False,
                    "description": "Identifier query param",
                    "schema": {"type": "string"},
                }
            ],
            "responses": {
                "200": {
                    "description": "Success response",
                    "content": {"application/json": {"schema": {"type": "object"}}},
                }
            },
        },
        "components": {},
    }


def test_index_via_stdin_pipe(tmp_path):
    """Verify piping chunk stream through stdin indexes operations."""
    runner = CliRunner()
    index_dir = tmp_path / "index"

    chunk1 = _sample_chunk("op1")
    chunk2 = _sample_chunk("op2")
    input_data = f"{json.dumps(chunk1)}\n{json.dumps(chunk2)}\n"

    result = runner.invoke(
        cli,
        ["index", "--index-dir", str(index_dir)],
        input=input_data,
    )
    assert result.exit_code == 0
    assert "Indexed 2 operations" in result.output

    with QdrantIndexStore(index_path=index_dir) as store:
        stats = store.get_stats()
        assert stats.total_operations == 2
        assert stats.status == "healthy"


def test_index_via_file_argument(tmp_path):
    """Verify indexing from a saved chunk file path."""
    runner = CliRunner()
    index_dir = tmp_path / "index"
    chunk_file = tmp_path / "chunks.jsonl"

    chunk1 = _sample_chunk("opA")
    chunk_file.write_text(f"{json.dumps(chunk1)}\n", encoding="utf-8")

    result = runner.invoke(
        cli,
        ["index", str(chunk_file), "--index-dir", str(index_dir)],
    )
    assert result.exit_code == 0
    assert "Indexed 1 operations" in result.output


def test_idempotent_spec_replacement(tmp_path):
    """Verify re-indexing replaces prior spec operations rather than duplicating
    or leaving orphans.
    """
    runner = CliRunner()
    index_dir = tmp_path / "index"

    # Batch 1: op1 and op2
    batch1 = f"{json.dumps(_sample_chunk('op1'))}\n{json.dumps(_sample_chunk('op2'))}\n"
    res1 = runner.invoke(cli, ["index", "--index-dir", str(index_dir)], input=batch1)
    assert res1.exit_code == 0

    with QdrantIndexStore(index_path=index_dir) as store:
        assert store.get_stats().total_operations == 2

    # Batch 2: same spec title/version, but op2 removed, op3 added
    batch2 = f"{json.dumps(_sample_chunk('op1'))}\n{json.dumps(_sample_chunk('op3'))}\n"
    res2 = runner.invoke(cli, ["index", "--index-dir", str(index_dir)], input=batch2)
    assert res2.exit_code == 0

    with QdrantIndexStore(index_path=index_dir) as store:
        stats = store.get_stats()
        # Total operations should be 2 (op1 and op3), not 4
        assert stats.total_operations == 2
        assert len(stats.specifications) == 1
        assert stats.specifications[0].chunk_count == 2


def test_multi_spec_isolation(tmp_path):
    """Verify updating one specification leaves other specifications untouched."""
    runner = CliRunner()
    index_dir = tmp_path / "index"

    # Spec A: 2 ops
    spec_a = (
        "\n".join(
            [
                json.dumps(_sample_chunk("a1", "Spec A", "1.0")),
                json.dumps(_sample_chunk("a2", "Spec A", "1.0")),
            ]
        )
        + "\n"
    )
    runner.invoke(cli, ["index", "--index-dir", str(index_dir)], input=spec_a)

    # Spec B: 3 ops
    spec_b = (
        "\n".join(
            [
                json.dumps(_sample_chunk("b1", "Spec B", "2.0")),
                json.dumps(_sample_chunk("b2", "Spec B", "2.0")),
                json.dumps(_sample_chunk("b3", "Spec B", "2.0")),
            ]
        )
        + "\n"
    )
    runner.invoke(cli, ["index", "--index-dir", str(index_dir)], input=spec_b)

    with QdrantIndexStore(index_path=index_dir) as store:
        assert store.get_stats().total_operations == 5

    # Re-index Spec A with only 1 op
    spec_a_updated = f"{json.dumps(_sample_chunk('a1', 'Spec A', '1.0'))}\n"
    runner.invoke(cli, ["index", "--index-dir", str(index_dir)], input=spec_a_updated)

    with QdrantIndexStore(index_path=index_dir) as store:
        stats = store.get_stats()
        # Spec A has 1 op, Spec B still has 3 ops -> Total 4
        assert stats.total_operations == 4
        specs_dict = {s.source_title: s.chunk_count for s in stats.specifications}
        assert specs_dict["Spec A"] == 1
        assert specs_dict["Spec B"] == 3


def test_malformed_jsonl_error(tmp_path):
    """Verify malformed JSON line reports line number and preserves existing index."""
    runner = CliRunner()
    index_dir = tmp_path / "index"

    # Index valid chunk first
    valid = f"{json.dumps(_sample_chunk('valid_op'))}\n"
    runner.invoke(cli, ["index", "--index-dir", str(index_dir)], input=valid)

    # Try invalid JSON on line 2
    invalid_input = f"{json.dumps(_sample_chunk('valid_op'))}\nNOT_VALID_JSON\n"
    result = runner.invoke(cli, ["index", "--index-dir", str(index_dir)], input=invalid_input)
    assert result.exit_code == 1
    assert "Line 2: invalid JSONL operation chunk" in result.output

    # Existing index should still have 1 op
    with QdrantIndexStore(index_path=index_dir) as store:
        assert store.get_stats().total_operations == 1


def test_nonexistent_file(tmp_path):
    """Verify non-existent file argument returns error code 1."""
    runner = CliRunner()
    result = runner.invoke(cli, ["index", str(tmp_path / "nonexistent.jsonl")])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_empty_input_stream(tmp_path):
    """Verify empty input stream reports 0 operations without error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["index", "--index-dir", str(tmp_path / "index")], input="")
    assert result.exit_code == 0
    assert "Empty input stream: 0 operations indexed" in result.output
