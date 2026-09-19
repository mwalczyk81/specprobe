"""Unit tests for single-retry self-correction and batch processing resilience."""

import io
import json
from unittest.mock import MagicMock

import pytest

from specprobe.chunker.models import ChunkMetadata, OperationChunk
from specprobe.generator.engine import BatchResult, GenerationEngine
from specprobe.generator.gateway import LLMGateway
from specprobe.generator.models import GeneratedTestCase


def _make_chunk(op_id: str, path: str = "/test", method: str = "GET") -> OperationChunk:
    return OperationChunk(
        metadata=ChunkMetadata(
            path=path,
            method=method,
            operationId=op_id,
            tags=["test"],
            deprecated=False,
            source_title="Test API",
            source_version="1.0.0",
        ),
        operation={
            "operationId": op_id,
            "summary": f"Summary for {op_id}",
            "responses": {"200": {"description": "OK"}},
            "tags": ["test"],
        },
        components={},
    )


def test_generate_chunk_retry_succeeds_on_second_attempt() -> None:
    """Verify that a validation failure triggers a retry with error feedback and succeeds."""
    chunk = _make_chunk("retryOp")

    # Attempt 1: invalid status code (> 599)
    bad_completion = json.dumps(
        {
            "operation_id": "retryOp",
            "description": "Initial bad attempt",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 999, "headers": {}, "schema_shape": None},
            "tags": ["test"],
        }
    )

    # Attempt 2: corrected valid response
    good_completion = json.dumps(
        {
            "operation_id": "retryOp",
            "description": "Corrected attempt",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["test"],
        }
    )

    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.side_effect = [bad_completion, good_completion]

    engine = GenerationEngine(gateway=mock_gateway)
    test_case = engine.generate_chunk(chunk)

    assert isinstance(test_case, GeneratedTestCase)
    assert test_case.operation_id == "retryOp"
    assert test_case.response.status_code == 200
    assert mock_gateway.complete.call_count == 2

    # Verify conversation turn in retry messages
    retry_call_args = mock_gateway.complete.call_args_list[1][0][0]
    assert len(retry_call_args) == 4  # system, user, assistant (bad), user (feedback)
    assert retry_call_args[2]["role"] == "assistant"
    assert retry_call_args[2]["content"] == bad_completion
    assert retry_call_args[3]["role"] == "user"
    assert (
        "The previous output failed strict Pydantic schema validation"
        in retry_call_args[3]["content"]
    )


def test_generate_chunk_retry_fails_twice_raises_error() -> None:
    """Verify that failing twice raises an exception and never triggers a 3rd attempt."""
    chunk = _make_chunk("failTwiceOp")

    bad_completion_1 = "Not even JSON"
    bad_completion_2 = json.dumps(
        {
            "operation_id": "failTwiceOp",
            "description": "Still bad",
            "request": {},
            "response": {"status_code": 888},
        }
    )

    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.side_effect = [bad_completion_1, bad_completion_2]

    engine = GenerationEngine(gateway=mock_gateway)
    with pytest.raises(
        Exception, match="Validation failed after retry for operation 'failTwiceOp'"
    ):
        engine.generate_chunk(chunk)

    assert mock_gateway.complete.call_count == 2


def test_generate_batch_isolates_failures() -> None:
    """Verify batch processing: 1 succeeds attempt 1, 1 self-corrects, 1 fails twice."""
    chunk1 = _make_chunk("op1")
    chunk2 = _make_chunk("op2")
    chunk3 = _make_chunk("op3")

    valid_json_1 = json.dumps(
        {
            "operation_id": "op1",
            "description": "Op1 success",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["test"],
        }
    )
    invalid_json_2 = json.dumps(
        {
            "operation_id": "op2",
            "description": "Op2 bad",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 700, "headers": {}, "schema_shape": None},
            "tags": ["test"],
        }
    )
    valid_json_2 = json.dumps(
        {
            "operation_id": "op2",
            "description": "Op2 corrected",
            "request": {"path_params": {}, "query_params": {}, "headers": {}, "body": None},
            "response": {"status_code": 200, "headers": {}, "schema_shape": None},
            "tags": ["test"],
        }
    )
    invalid_json_3_a = "bad json 3"
    invalid_json_3_b = "still bad json 3"

    mock_gateway = MagicMock(spec=LLMGateway)
    mock_gateway.complete.side_effect = [
        valid_json_1,
        invalid_json_2,
        valid_json_2,
        invalid_json_3_a,
        invalid_json_3_b,
    ]

    out_buf = io.StringIO()
    err_buf = io.StringIO()

    engine = GenerationEngine(gateway=mock_gateway)
    result = engine.generate_batch(
        [chunk1, chunk2, chunk3],
        stream_stdout=True,
        out_stream=out_buf,
        err_stream=err_buf,
    )

    assert isinstance(result, BatchResult)
    assert result.total == 3
    assert result.succeeded == 2
    assert result.failed == 1

    # Check stdout stream
    lines = [line.strip() for line in out_buf.getvalue().strip().split("\n") if line.strip()]
    assert len(lines) == 2
    tc1 = GeneratedTestCase.model_validate_json(lines[0])
    tc2 = GeneratedTestCase.model_validate_json(lines[1])
    assert tc1.operation_id == "op1"
    assert tc2.operation_id == "op2"

    # Check stderr stream
    err_output = err_buf.getvalue()
    assert "op3" in err_output
    assert "Validation failed" in err_output


def test_generate_batch_empty() -> None:
    """Verify batch processing on empty chunk list returns zero counts without error."""
    mock_gateway = MagicMock(spec=LLMGateway)
    engine = GenerationEngine(gateway=mock_gateway)

    result = engine.generate_batch([])
    assert result.total == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.test_cases == []
    assert result.errors == []
    assert mock_gateway.complete.call_count == 0
