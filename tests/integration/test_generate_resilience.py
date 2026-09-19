"""Integration tests for retry self-correction and graceful batch error resilience."""

import json
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


def _make_search_result(op_id: str, path: str = "/test", method: str = "GET") -> dict:
    return {
        "operationId": op_id,
        "path": path,
        "method": method,
        "score": 0.9,
        "tags": ["test"],
        "source_title": "Test API",
        "source_version": "1.0.0",
        "chunk": {
            "metadata": {
                "path": path,
                "method": method,
                "operationId": op_id,
                "tags": ["test"],
                "security": [],
                "deprecated": False,
                "source_title": "Test API",
                "source_version": "1.0.0",
                "estimated_tokens": 100,
                "warnings": [],
            },
            "operation": {
                "operationId": op_id,
                "summary": f"Summary for {op_id}",
                "responses": {"200": {"description": "OK"}},
            },
            "components": {},
        },
    }


def test_batch_retry_self_correction_and_continuation() -> None:
    """Verify acceptance scenario:
    Op 1 succeeds on attempt 1.
    Op 2 fails attempt 1, succeeds on attempt 2 (self-correction).
    Op 3 fails both attempts.
    Result: Op 1 and Op 2 are emitted to stdout, Op 3 error is logged, exit code is 0.
    """
    runner = CliRunner()

    items = [
        _make_search_result("op1"),
        _make_search_result("op2"),
        _make_search_result("op3"),
    ]
    input_json = json.dumps(items)

    op1_success = json.dumps(
        {
            "operation_id": "op1",
            "description": "Op 1 success",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["test"],
        }
    )
    op2_bad = json.dumps(
        {
            "operation_id": "op2",
            "description": "Op 2 bad",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 999, "headers": {}, "schema_shape": None},  # invalid
            "tags": ["test"],
        }
    )
    op2_good = json.dumps(
        {
            "operation_id": "op2",
            "description": "Op 2 corrected",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["test"],
        }
    )
    op3_bad_1 = "bad completion 1"
    op3_bad_2 = "bad completion 2"

    with patch(
        "litellm.completion",
        side_effect=[
            _mock_completion(op1_success),  # Op 1: attempt 1 -> OK
            _mock_completion(op2_bad),  # Op 2: attempt 1 -> fail
            _mock_completion(op2_good),  # Op 2: attempt 2 -> OK
            _mock_completion(op3_bad_1),  # Op 3: attempt 1 -> fail
            _mock_completion(op3_bad_2),  # Op 3: attempt 2 -> fail
        ],
    ) as mock_complete:
        result = runner.invoke(cli, ["generate", "--no-cache"], input=input_json)

    assert result.exit_code == 0
    assert mock_complete.call_count == 5

    # Check stdout contains 2 valid JSONL objects
    stdout_lines = [
        line.strip() for line in result.output.split("\n") if line.strip().startswith("{")
    ]
    assert len(stdout_lines) == 2

    tc1 = GeneratedTestCase.model_validate_json(stdout_lines[0])
    tc2 = GeneratedTestCase.model_validate_json(stdout_lines[1])
    assert tc1.operation_id == "op1"
    assert tc2.operation_id == "op2"

    # Check stderr diagnostics
    assert "Validation failed for operation 'op3'" in result.output


def test_batch_all_operations_fail_after_retry_exits_code_1() -> None:
    """Verify that when all operations in a batch fail after retry, exit code is 1."""
    runner = CliRunner()
    items = [_make_search_result("failOp1"), _make_search_result("failOp2")]
    input_json = json.dumps(items)

    bad_resp = "not json"

    with patch(
        "litellm.completion",
        side_effect=[
            _mock_completion(bad_resp),
            _mock_completion(bad_resp),
            _mock_completion(bad_resp),
            _mock_completion(bad_resp),
        ],
    ):
        result = runner.invoke(cli, ["generate", "--no-cache"], input=input_json)

    assert result.exit_code == 1
    assert "All 2 operation(s) failed test generation" in result.output
