"""Integration tests for the specprobe generate CLI command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from specprobe.cli import cli
from specprobe.generator.models import GeneratedTestCase


def _mock_completion_response(content: str):
    """Create a mock LiteLLM completion response object."""
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp.choices = [mock_choice]
    return mock_resp


def test_generate_from_file() -> None:
    """Verify generate reads search results from file and outputs valid JSONL."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"

    mock_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pets successfully",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_json)):
        result = runner.invoke(cli, ["generate", fixture_path, "--no-cache"])

    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    # listPets is secured -> 3 test cases (positive, 401, 403);
    # showPetById is unsecured -> 1 test case (positive)
    assert len(lines) == 4

    test_cases = [GeneratedTestCase.model_validate_json(line) for line in lines]
    assert len([tc for tc in test_cases if tc.test_type == "positive"]) == 2
    assert len([tc for tc in test_cases if tc.test_type == "negative_auth_missing"]) == 1
    assert len([tc for tc in test_cases if tc.test_type == "negative_auth_invalid"]) == 1


def test_generate_from_stdin_pipe() -> None:
    """Verify generate reads search results piped via stdin and outputs valid JSONL."""
    runner = CliRunner()
    fixture_path = Path("tests/fixtures/search_full_results.json")
    content = fixture_path.read_text(encoding="utf-8")

    mock_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pets successfully",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_json)):
        result = runner.invoke(cli, ["generate", "--no-cache"], input=content)

    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    # listPets is secured -> 3 test cases; showPetById is unsecured -> 1 test case
    assert len(lines) == 4

    test_cases = [GeneratedTestCase.model_validate_json(line) for line in lines]
    assert len([tc for tc in test_cases if tc.test_type == "positive"]) == 2
    assert len([tc for tc in test_cases if tc.test_type == "negative_auth_missing"]) == 1
    assert len([tc for tc in test_cases if tc.test_type == "negative_auth_invalid"]) == 1


def test_generate_rejects_compact_search_results() -> None:
    """Verify that compact search results without 'chunk' payloads are rejected with exit code 1."""
    runner = CliRunner()
    compact_results = json.dumps(
        [
            {
                "operationId": "listPets",
                "path": "/pets",
                "method": "GET",
                "score": 0.88,
                "tags": ["pets"],
                "chunk": None,
            }
        ]
    )

    result = runner.invoke(cli, ["generate"], input=compact_results)
    assert result.exit_code == 1
    assert "missing full 'chunk' payload" in result.output
    assert "--full" in result.output


def test_generate_rejects_malformed_json() -> None:
    """Verify that unparseable input is rejected with exit code 1."""
    runner = CliRunner()
    result = runner.invoke(cli, ["generate"], input="invalid json not an array")
    assert result.exit_code == 1
    assert "Invalid JSON input" in result.output


def test_generate_rejects_non_array_json() -> None:
    """Verify that a JSON object instead of an array is rejected with exit code 1."""
    runner = CliRunner()
    result = runner.invoke(cli, ["generate"], input='{"not": "array"}')
    assert result.exit_code == 1
    assert "expected a JSON array of search results" in result.output


def test_generate_empty_array() -> None:
    """Verify that an empty search results array exits with code 0 and empty stdout."""
    runner = CliRunner()
    result = runner.invoke(cli, ["generate"], input="[]")
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_generate_missing_file() -> None:
    """Verify that specifying a non-existent results file fails with exit code 1."""
    runner = CliRunner()
    result = runner.invoke(cli, ["generate", "non_existent_results.json"])
    assert result.exit_code == 1
    assert "Results file not found" in result.output


def test_generate_all_failed_exits_code_1() -> None:
    """Verify that when 100% of operations fail test generation, the process exits with code 1."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"

    # Model returns invalid schema (status_code out of range)
    bad_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pets",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 9999, "headers": {}, "schema_shape": None},
            "tags": [],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(bad_json)):
        result = runner.invoke(cli, ["generate", fixture_path, "--no-cache"])

    assert result.exit_code == 1
    assert "failed test generation" in result.output


def test_generate_partial_success_exits_code_0() -> None:
    """Verify that when at least one operation succeeds, exit code is 0."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"

    good_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pets successfully",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    # First call succeeds, second call fails
    with patch(
        "litellm.completion",
        side_effect=[
            _mock_completion_response(good_json),
            RuntimeError("Connection refused"),
        ],
    ):
        result = runner.invoke(cli, ["generate", fixture_path, "--no-cache"])

    assert result.exit_code == 0
    # listPets produces 3 test cases (happy path, 401, 403)
    valid_lines = [
        line
        for line in result.output.split("\n")
        if line.strip().startswith("{") and "listPets" in line
    ]
    assert len(valid_lines) == 3


def test_generate_cli_options_forwarding() -> None:
    """Verify that CLI options are correctly resolved and forwarded to LiteLLM."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"

    mock_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pets successfully",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    with patch(
        "litellm.completion", return_value=_mock_completion_response(mock_json)
    ) as mock_complete:
        result = runner.invoke(
            cli,
            [
                "generate",
                fixture_path,
                "--no-cache",
                "--model",
                "openai/custom-local",
                "--api-base",
                "http://127.0.0.1:8080/v1",
                "--temperature",
                "0.7",
            ],
        )

    assert result.exit_code == 0
    assert mock_complete.call_count == 2
    call_args = mock_complete.call_args[1]
    assert call_args["model"] == "openai/custom-local"
    assert call_args["api_base"] == "http://127.0.0.1:8080/v1"
    assert call_args["temperature"] == 0.7


def test_generate_no_negative_auth_flag() -> None:
    """Verify --no-negative-auth flag suppresses 401 and 403 negative test generation (T020)."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"

    mock_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pets successfully",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_json)):
        result = runner.invoke(
            cli,
            ["generate", fixture_path, "--no-cache", "--no-negative-auth"],
        )

    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    # When negative auth is disabled, only positive test cases are produced (2 total)
    assert len(lines) == 2
    for line in lines:
        tc = GeneratedTestCase.model_validate_json(line)
        assert tc.test_type == "positive"
        assert tc.response.status_code == 200


def test_generate_explicit_negative_auth_flag() -> None:
    """Verify --negative-auth flag explicitly enables 401 and 403 generation."""
    runner = CliRunner()
    fixture_path = "tests/fixtures/search_full_results.json"

    mock_json = json.dumps(
        {
            "operation_id": "listPets",
            "description": "Fetch pets successfully",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["pets"],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_json)):
        result = runner.invoke(
            cli,
            ["generate", fixture_path, "--no-cache", "--negative-auth"],
        )

    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().split("\n") if line.strip()]
    assert len(lines) == 4
    test_cases = [GeneratedTestCase.model_validate_json(line) for line in lines]
    assert len([tc for tc in test_cases if tc.test_type == "positive"]) == 2
    assert len([tc for tc in test_cases if tc.test_type == "negative_auth_missing"]) == 1
    assert len([tc for tc in test_cases if tc.test_type == "negative_auth_invalid"]) == 1
