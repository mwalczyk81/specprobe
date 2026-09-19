"""Integration tests for disk caching, offline replay, and cache invalidation."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from specprobe.cli import cli
from specprobe.generator.models import GeneratedTestCase


def _mock_completion(content: str):
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp.choices = [mock_choice]
    return mock_resp


def test_generate_offline_cache_replay() -> None:
    """Verify 100% offline execution using pre-recorded disk cache fixtures in CI.

    litellm.completion is patched to fail unconditionally if invoked. The command
    must succeed instantly with 0 LLM calls by replaying pre-recorded fixtures.
    """
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"
    cache_dir = "tests/fixtures/cache"

    with patch("litellm.completion", side_effect=RuntimeError("Network disabled in CI")):
        result = runner.invoke(cli, ["generate", fixture_path, "--cache-dir", cache_dir])

    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    assert len(lines) == 2

    tc1 = GeneratedTestCase.model_validate_json(lines[0])
    tc2 = GeneratedTestCase.model_validate_json(lines[1])
    assert tc1.operation_id == "listPets"
    assert tc2.operation_id == "showPetById"


def test_generate_no_cache_bypasses_cache(tmp_path: Path) -> None:
    """Verify --no-cache bypasses pre-recorded disk cache entries and calls model."""
    import shutil

    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"
    cache_dir = tmp_path / "cache"
    shutil.copytree("tests/fixtures/cache", cache_dir)

    live_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Live generated test",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion(live_json)) as mock_complete:
        result = runner.invoke(
            cli,
            ["generate", fixture_path, "--cache-dir", str(cache_dir), "--no-cache"],
        )

    assert result.exit_code == 0
    assert mock_complete.call_count == 2  # Live inference invoked for both chunks


def test_generate_populates_cache_and_replays(tmp_path: Path) -> None:
    """Verify live generation populates disk cache, enabling zero-inference replay."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"
    tmp_cache = str(tmp_path / "cache")

    mock_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Populate cache test",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    # First run: live calls populate cache
    with patch("litellm.completion", return_value=_mock_completion(mock_json)) as mock_complete:
        res1 = runner.invoke(cli, ["generate", fixture_path, "--cache-dir", tmp_cache])

    assert res1.exit_code == 0
    assert mock_complete.call_count == 2

    # Verify cache files exist on disk
    cache_files = list(Path(tmp_cache).glob("*.json"))
    assert len(cache_files) == 2

    # Second run: network blocked, execution replays from newly created cache
    with patch("litellm.completion", side_effect=RuntimeError("Network unreachable")):
        res2 = runner.invoke(cli, ["generate", fixture_path, "--cache-dir", tmp_cache])

    assert res2.exit_code == 0
    lines = [line.strip() for line in res2.output.strip().split("\n") if line.strip()]
    assert len(lines) == 2


def test_cache_environment_variables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify SPECPROBE_CACHE_DIR and SPECPROBE_NO_CACHE environment variables."""
    import shutil

    # Copy fixture cache to isolated tmp_path
    tmp_cache = tmp_path / "cache"
    shutil.copytree("tests/fixtures/cache", tmp_cache)

    monkeypatch.setenv("SPECPROBE_CACHE_DIR", str(tmp_cache))
    monkeypatch.delenv("SPECPROBE_NO_CACHE", raising=False)

    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"

    # SPECPROBE_CACHE_DIR active: should hit cache with no CLI --cache-dir flag
    with patch("litellm.completion", side_effect=RuntimeError("Network disabled")):
        res = runner.invoke(cli, ["generate", fixture_path])

    assert res.exit_code == 0
    assert "listPets" in res.output

    # SPECPROBE_NO_CACHE active: should bypass cache and call live completion
    monkeypatch.setenv("SPECPROBE_NO_CACHE", "true")
    live_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Live with env var",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )
    with patch("litellm.completion", return_value=_mock_completion(live_json)) as mock_complete:
        res2 = runner.invoke(cli, ["generate", fixture_path])

    assert res2.exit_code == 0
    assert mock_complete.call_count == 2
