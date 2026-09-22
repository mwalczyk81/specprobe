"""Integration tests for the specprobe index --stats diagnostic command."""

import json
import time

from click.testing import CliRunner

from specprobe.cli import cli


def _sample_chunk(op_id: str, title: str, version: str) -> dict:
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
            "tags": ["test"],
            "responses": {"200": {"description": "OK"}},
        },
        "components": {},
    }


def test_empty_index_stats(tmp_path):
    """Verify --stats on a non-existent or empty index reports 0 operations without crashing."""
    runner = CliRunner()
    index_dir = str(tmp_path / "empty_index")

    result = runner.invoke(cli, ["index", "--stats", "--index-dir", index_dir])
    assert result.exit_code == 0
    assert "SpecProbe Vector Index Statistics:" in result.output
    assert "Status: empty" in result.output
    assert "Total Indexed Operations: 0" in result.output
    assert "Unique Specifications: 0" in result.output


def test_populated_multi_spec_stats(tmp_path):
    """Verify --stats outputs detailed breakdowns for multiple specifications."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")

    # Index spec 1 (2 ops)
    batch1 = (
        f"{json.dumps(_sample_chunk('op1', 'Petstore API', '1.0.0'))}\n"
        f"{json.dumps(_sample_chunk('op2', 'Petstore API', '1.0.0'))}\n"
    )
    runner.invoke(cli, ["index", "--index-dir", index_dir], input=batch1)

    # Index spec 2 (1 op)
    batch2 = f"{json.dumps(_sample_chunk('pay1', 'Billing API', '2.1.0'))}\n"
    runner.invoke(cli, ["index", "--index-dir", index_dir], input=batch2)

    # Run stats
    start_time = time.perf_counter()
    result = runner.invoke(cli, ["index", "--stats", "--index-dir", index_dir])
    duration = time.perf_counter() - start_time

    assert result.exit_code == 0
    assert "Status: healthy" in result.output
    assert "Total Indexed Operations: 3" in result.output
    assert "Unique Specifications: 2" in result.output
    assert "Spec Title" in result.output
    assert "Version" in result.output
    assert "Operation Count" in result.output
    assert "Petstore API" in result.output
    assert "Billing API" in result.output
    assert "dense: 384 (Cosine)" in result.output
    assert "sparse: BM25 token weights" in result.output
    # SC-007: stats mode completes in under 100 milliseconds in production; allow
    # margin for test harness and coverage tracing overhead on CI runners.
    assert duration < 0.500  # Allow overhead for testing harness and coverage tracing


def test_stats_exclusive_mode(tmp_path):
    """Verify --stats runs in exclusive diagnostic mode and does not consume stdin."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")

    # Pass stdin while requesting --stats
    result = runner.invoke(
        cli,
        ["index", "--stats", "--index-dir", index_dir],
        input="SOME_RAW_STDIN_SHOULD_BE_IGNORED\n",
    )
    assert result.exit_code == 0
    assert "SpecProbe Vector Index Statistics:" in result.output


def test_chunk_stats_output(valid_openapi_30_path):
    """Verify specprobe chunk --stats renders a rich table with chunking statistics."""
    runner = CliRunner()
    result = runner.invoke(cli, ["chunk", str(valid_openapi_30_path), "--stats"])

    assert result.exit_code == 0
    assert "Chunking" in result.output
    assert "Statistics" in result.output
    assert "Total Operations" in result.output
    assert "Min Tokens" in result.output
    assert "Max Tokens" in result.output
    assert "Median Tokens" in result.output
    assert "Avg Tokens" in result.output
    assert "Oversized Chunks" in result.output
    assert "Warnings" in result.output
    # Must NOT stream JSONL chunks when --stats is active (exclusive mode)
    assert '{"metadata":' not in result.output
