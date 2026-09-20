"""Integration tests for the specprobe search CLI command."""

import json
import os

from click.testing import CliRunner

from specprobe.cli import cli


def _index_fixture(runner, fixture_path: str, index_dir: str):
    """Helper to chunk and index a fixture file into index_dir."""
    chunk_res = runner.invoke(cli, ["chunk", fixture_path])
    assert chunk_res.exit_code == 0
    index_res = runner.invoke(cli, ["index", "--index-dir", index_dir], input=chunk_res.output)
    assert index_res.exit_code == 0


def test_default_compact_search(tmp_path):
    """Verify default search outputs compact JSON with required fields."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    result = runner.invoke(cli, ["search", "find a pet by id", "--index-dir", index_dir])
    assert result.exit_code == 0

    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert "operationId" in first
    assert "path" in first
    assert "method" in first
    assert "score" in first
    assert "tags" in first
    assert "summary" in first
    assert "source_title" in first
    assert "source_version" in first
    assert first["chunk"] is None


def test_full_payload_search(tmp_path):
    """Verify --full flag embeds the full OperationChunk data."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    result = runner.invoke(cli, ["search", "find pet", "--full", "--index-dir", index_dir])
    assert result.exit_code == 0

    data = json.loads(result.output)
    assert len(data) > 0
    first = data[0]
    assert first["chunk"] is not None
    assert "metadata" in first["chunk"]
    assert "operation" in first["chunk"]


def test_mode_selection_and_ranking(tmp_path):
    """Verify search across dense, hybrid, and hybrid-rerank retrieval modes."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/near_duplicate_operations.yaml", index_dir)

    query = "order shipment delivery tracking status updates"

    # Dense mode
    res_dense = runner.invoke(cli, ["search", query, "--mode", "dense", "--index-dir", index_dir])
    assert res_dense.exit_code == 0
    data_dense = json.loads(res_dense.output)
    assert len(data_dense) > 0

    # Hybrid mode
    res_hybrid = runner.invoke(cli, ["search", query, "--mode", "hybrid", "--index-dir", index_dir])
    assert res_hybrid.exit_code == 0
    data_hybrid = json.loads(res_hybrid.output)
    assert len(data_hybrid) > 0

    # Hybrid-rerank mode
    res_rerank = runner.invoke(
        cli, ["search", query, "--mode", "hybrid-rerank", "--index-dir", index_dir]
    )
    assert res_rerank.exit_code == 0
    data_rerank = json.loads(res_rerank.output)
    assert len(data_rerank) > 0


def test_metadata_filters(tmp_path):
    """Verify metadata filter options narrow search results."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/near_duplicate_operations.yaml", index_dir)

    # Filter by tag customers
    res_tag = runner.invoke(
        cli, ["search", "orders", "--tag", "customers", "--index-dir", index_dir]
    )
    assert res_tag.exit_code == 0
    data_tag = json.loads(res_tag.output)
    assert len(data_tag) == 1
    assert data_tag[0]["operationId"] == "getCustomerOrders"

    # Filter by source title
    res_title = runner.invoke(
        cli,
        ["search", "orders", "--source-title", "Order Management API", "--index-dir", index_dir],
    )
    assert res_title.exit_code == 0
    data_title = json.loads(res_title.output)
    assert all(m["source_title"] == "Order Management API" for m in data_title)


def test_limit_option(tmp_path):
    """Verify -n/--limit caps number of results."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    result = runner.invoke(cli, ["search", "pet", "-n", "1", "--index-dir", index_dir])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1


def test_missing_index_error(tmp_path):
    """Verify missing index directory exits with code 1 and descriptive error."""
    runner = CliRunner()
    nonexistent = str(tmp_path / "does_not_exist")
    result = runner.invoke(cli, ["search", "find pet", "--index-dir", nonexistent])
    assert result.exit_code == 1
    assert "Index not found" in result.output


def test_empty_results(tmp_path):
    """Verify search with no matches outputs empty array with exit code 0."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    # Filter with non-existent tag
    result = runner.invoke(
        cli, ["search", "pet", "--tag", "nonexistent_tag_123", "--index-dir", index_dir]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == []


def test_progress_bar_suppression_active():
    """Verify HF Hub and tqdm progress bars are disabled to prevent stdout/stderr pollution."""
    from huggingface_hub.utils import are_progress_bars_disabled, enable_progress_bars
    from tqdm.std import tqdm

    assert os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") == "1"
    assert os.environ.get("TQDM_DISABLE") == "1"
    assert are_progress_bars_disabled() is True
    assert tqdm(range(1)).disable is True

    # Progress bars must remain disabled even if downstream libraries invoke enable_progress_bars()
    enable_progress_bars()
    assert are_progress_bars_disabled() is True
