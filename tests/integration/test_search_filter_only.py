"""Integration tests for filter-only unranked search and search-to-generate pipeline."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from specprobe.cli import cli
from specprobe.generator.models import GeneratedTestCase


def _mock_completion(content: str):
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp.choices = [mock_choice]
    return mock_resp


def _index_fixture(runner: CliRunner, fixture_path: str, index_dir: str) -> None:
    """Helper to chunk and index a fixture file into index_dir."""
    chunk_res = runner.invoke(cli, ["chunk", fixture_path])
    assert chunk_res.exit_code == 0
    index_res = runner.invoke(cli, ["index", "--index-dir", index_dir], input=chunk_res.output)
    assert index_res.exit_code == 0


def test_search_missing_query_and_filters() -> None:
    """Verify invoking search without query or filters exits with code 1 and error."""
    runner = CliRunner()

    # Completely omitted query and options
    res = runner.invoke(cli, ["search"])
    assert res.exit_code == 1
    assert "Error: Either a search query or at least one filter" in res.output

    # Whitespace-only query without filters
    res_ws = runner.invoke(cli, ["search", "   "])
    assert res_ws.exit_code == 1
    assert "Error: Either a search query or at least one filter" in res_ws.output


def test_search_filter_only_by_spec(tmp_path: Path) -> None:
    """Verify filter-only search returns all spec operations unranked (score=0.0)."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    res = runner.invoke(
        cli,
        ["search", "--source-title", "Petstore Probe API", "--index-dir", index_dir],
    )
    assert res.exit_code == 0

    data = json.loads(res.output)
    assert isinstance(data, list)
    assert len(data) == 4

    op_ids = {m["operationId"] for m in data}
    assert op_ids == {"listPets", "createPets", "showPetById", "delete_pets_pet_id"}

    for match in data:
        assert match["score"] == 0.0
        assert match["source_title"] == "Petstore Probe API"
        assert match["chunk"] is None


def test_search_filter_only_by_method_and_tag(tmp_path: Path) -> None:
    """Verify filter-only search narrows results by method and tag unranked."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    res = runner.invoke(
        cli,
        ["search", "--method", "POST", "--tag", "pets", "--index-dir", index_dir],
    )
    assert res.exit_code == 0

    data = json.loads(res.output)
    assert len(data) == 1
    assert data[0]["operationId"] == "createPets"
    assert data[0]["method"] == "POST"
    assert data[0]["score"] == 0.0


def test_search_filter_only_with_explicit_limit(tmp_path: Path) -> None:
    """Verify filter-only search respects explicit -n/--limit."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    res = runner.invoke(
        cli,
        [
            "search",
            "--source-title",
            "Petstore Probe API",
            "-n",
            "2",
            "--index-dir",
            index_dir,
        ],
    )
    assert res.exit_code == 0

    data = json.loads(res.output)
    assert len(data) == 2
    for m in data:
        assert m["score"] == 0.0


def test_search_filter_only_full_payload(tmp_path: Path) -> None:
    """Verify filter-only search with --full includes OperationChunk payload."""
    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    res = runner.invoke(
        cli,
        [
            "search",
            "--source-title",
            "Petstore Probe API",
            "--full",
            "--index-dir",
            index_dir,
        ],
    )
    assert res.exit_code == 0

    data = json.loads(res.output)
    assert len(data) == 4
    for match in data:
        assert match["chunk"] is not None
        assert "metadata" in match["chunk"]
        assert "operation" in match["chunk"]
        assert match["score"] == 0.0


def test_pipeline_filter_search_piped_to_generate(tmp_path: Path) -> None:
    """Verify end-to-end pipeline: specprobe search ... --full | specprobe generate."""
    import re

    runner = CliRunner()
    index_dir = str(tmp_path / "index")
    _index_fixture(runner, "tests/fixtures/valid_openapi_30.yaml", index_dir)

    # 1. Execute unranked filter-only search with --full
    search_res = runner.invoke(
        cli,
        [
            "search",
            "--source-title",
            "Petstore Probe API",
            "--full",
            "--index-dir",
            index_dir,
        ],
    )
    assert search_res.exit_code == 0

    # 2. Prepare isolated cache directory seeded with pre-recorded fixtures
    cache_dir = tmp_path / "cache"
    shutil.copytree("tests/fixtures/cache", cache_dir)

    def _mock_dispatch(*args, **kwargs):
        messages = kwargs.get("messages", [])
        op_id = "mockOp"
        for m in messages:
            content = m.get("content", "")
            match = re.search(r"Operation ID:\s*([^\s\n\r]+)", content, re.IGNORECASE)
            if match:
                op_id = match.group(1).strip()
                break
        return _mock_completion(
            json.dumps(
                {
                    "operation_id": op_id,
                    "description": f"Happy path test for {op_id}",
                    "request": {
                        "path_params": {},
                        "query_params": {},
                        "headers": {},
                        "body": None,
                    },
                    "response": {"status_code": 200, "headers": {}, "schema_shape": None},
                    "tags": ["pets"],
                }
            )
        )

    with patch("litellm.completion", side_effect=_mock_dispatch):
        # 3. Pipe search output into generate via stdin ('-')
        gen_res = runner.invoke(
            cli,
            ["generate", "-", "--cache-dir", str(cache_dir)],
            input=search_res.output,
        )

    assert gen_res.exit_code == 0
    lines = [line.strip() for line in gen_res.output.strip().split("\n") if line.strip()]
    # 4 operations: listPets (pos, 401, 403), createPets (pos, 401, 403),
    # showPetById (pos, 404), delete_pets_pet_id (pos, 401, 403, 404). Total: 12
    assert len(lines) == 12

    generated_cases = [GeneratedTestCase.model_validate_json(line) for line in lines]
    op_ids = {tc.operation_id for tc in generated_cases}
    assert op_ids == {"listPets", "createPets", "showPetById", "delete_pets_pet_id"}
