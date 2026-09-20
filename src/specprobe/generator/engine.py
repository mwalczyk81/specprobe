"""Generation engine orchestrating prompt construction, LLM completion, and validation."""

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from specprobe.chunker.models import OperationChunk
from specprobe.generator.gateway import LLMGateway
from specprobe.generator.models import GeneratedTestCase
from specprobe.generator.prompt import (
    PromptBuilder,
    clean_markdown_fences,
    resolve_operation_id,
)

__all__ = [
    "BatchResult",
    "GenerationEngine",
    "parse_search_results",
]


@dataclass
class BatchResult:
    """Summary of batch generation execution metrics and artifacts."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    test_cases: list[GeneratedTestCase] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Extract and parse a JSON object from raw model completion text."""
    # First, try standard fence cleaning
    cleaned = clean_markdown_fences(raw_text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Second, attempt to extract JSON within markdown fences if preamble/postamble present
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        try:
            data = json.loads(fenced_match.group(1).strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Third, attempt substring extraction between outermost curly braces
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end > start:
        candidate = raw_text[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Model completion did not contain a valid JSON object. Output snippet: {raw_text[:200]}"
    )


def parse_search_results(input_data: str | list[Any]) -> list[OperationChunk]:
    """Parse search results JSON into a validated list of OperationChunk instances.

    Parameters
    ----------
    input_data : str | list[Any]
        Raw JSON string or deserialized list of search match objects matching
        'specprobe search --full' output.

    Returns
    -------
    list[OperationChunk]
        Validated operation chunks ready for test case generation.

    Raises
    ------
    ValueError
        If the input is not valid JSON, not a JSON array, or lacks conforming
        'chunk' payloads.
    """
    if isinstance(input_data, str):
        try:
            data = json.loads(input_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON input: {exc}") from exc
    elif isinstance(input_data, list):
        data = input_data
    else:
        raise ValueError("Invalid input format: expected a JSON array of search results.")

    if not isinstance(data, list):
        raise ValueError("Invalid input format: expected a JSON array of search results.")

    chunks: list[OperationChunk] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(
                f"Invalid item at index {idx}: expected an object, got {type(item).__name__}."
            )

        op_id = item.get("operationId") or f"item #{idx}"

        if "chunk" not in item or item["chunk"] is None:
            raise ValueError(
                f"Search result for '{op_id}' is missing full 'chunk' payload. "
                "Ensure 'specprobe search' was run with the '--full' flag."
            )

        chunk_data = item["chunk"]
        if not isinstance(chunk_data, dict):
            obj_type = type(chunk_data).__name__
            raise ValueError(
                f"Invalid 'chunk' payload for '{op_id}': expected object, got {obj_type}."
            )

        try:
            chunk = OperationChunk.model_validate(chunk_data)
        except Exception as exc:
            raise ValueError(f"Invalid OperationChunk schema for '{op_id}': {exc}") from exc

        chunks.append(chunk)

    return chunks


class GenerationEngine:
    """Orchestrates LLM test case generation from operation chunks."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        cache: Any | None = None,
    ) -> None:
        self.gateway = gateway or LLMGateway()
        self.cache = cache

    def _validate_completion(self, raw_text: str, chunk: OperationChunk) -> GeneratedTestCase:
        """Parse raw model completion text and validate against GeneratedTestCase schema."""
        data = _extract_json_object(raw_text)

        # Ensure traceability to operation_id
        if not data.get("operation_id"):
            data["operation_id"] = resolve_operation_id(chunk)

        # Inherit tags if not populated by model
        if not data.get("tags"):
            chunk_tags = chunk.operation.get("tags") or chunk.metadata.tags
            if chunk_tags:
                data["tags"] = chunk_tags

        # Inherit method and path into request fixture if absent
        req = data.setdefault("request", {})
        if isinstance(req, dict):
            if not req.get("method") and chunk.metadata.method:
                req["method"] = chunk.metadata.method.upper()
            if not req.get("path") and chunk.metadata.path:
                req["path"] = chunk.metadata.path

        return GeneratedTestCase.model_validate(data)

    def generate_chunk(self, chunk: OperationChunk) -> GeneratedTestCase:
        """Generate and validate a single happy-path test case for an operation chunk.

        If schema validation fails on the initial attempt, retries exactly once with
        detailed validation error feedback per Constitution Principle V.

        Parameters
        ----------
        chunk : OperationChunk
            Target API operation chunk.

        Returns
        -------
        GeneratedTestCase
            Validated Pydantic test case model.

        Raises
        ------
        ValueError
            If validation fails after retry or the model output cannot be parsed.
        """
        op_id = resolve_operation_id(chunk)
        initial_messages = PromptBuilder.build_initial_messages(chunk)

        # Attempt 1
        raw_completion = self.gateway.complete(initial_messages, cache=self.cache)
        try:
            return self._validate_completion(raw_completion, chunk)
        except (ValidationError, ValueError) as first_exc:
            error_msg = str(first_exc)

        # Retry Attempt (Exactly once, augmenting context with specific schema feedback)
        retry_messages = list(initial_messages)
        retry_messages.append({"role": "assistant", "content": raw_completion})
        retry_messages.append(
            {
                "role": "user",
                "content": (
                    "The previous output failed strict Pydantic schema validation with "
                    f"the following error:\n{error_msg}\n\n"
                    "Please fix the validation error and return ONLY the corrected, "
                    "valid JSON object."
                ),
            }
        )

        retry_completion = self.gateway.complete(retry_messages, cache=self.cache)
        try:
            return self._validate_completion(retry_completion, chunk)
        except (ValidationError, ValueError) as retry_exc:
            raise ValueError(
                f"Validation failed after retry for operation '{op_id}': {retry_exc}"
            ) from retry_exc

    def generate_batch(
        self,
        chunks: list[OperationChunk],
        stream_stdout: bool = True,
        out_stream: Any = None,
        err_stream: Any = None,
    ) -> BatchResult:
        """Process a batch of operation chunks, isolating per-operation failures.

        Parameters
        ----------
        chunks : list[OperationChunk]
            List of operation chunks to process.
        stream_stdout : bool
            Whether to stream validated test cases as JSON Lines (JSONL).
        out_stream : Any | None
            Output stream for validated test cases (defaults to sys.stdout).
        err_stream : Any | None
            Error stream for diagnostic messages (defaults to sys.stderr).

        Returns
        -------
        BatchResult
            Summary of successful and failed generations.
        """
        if out_stream is None:
            out_stream = sys.stdout
        if err_stream is None:
            err_stream = sys.stderr

        result = BatchResult(total=len(chunks))

        for chunk in chunks:
            op_id = resolve_operation_id(chunk)
            try:
                test_case = self.generate_chunk(chunk)
                if stream_stdout:
                    out_stream.write(test_case.model_dump_json() + "\n")
                    out_stream.flush()
                result.test_cases.append(test_case)
                result.succeeded += 1
            except Exception as exc:
                err_stream.write(f"Validation failed for operation '{op_id}': {exc}\n")
                err_stream.flush()
                result.errors.append((op_id, str(exc)))
                result.failed += 1

        return result
