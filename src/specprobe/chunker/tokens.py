"""Deterministic token estimation heuristic for SpecProbe chunks."""

import json
from typing import Any


def estimate_tokens(payload: dict[str, Any] | str) -> int:
    """Estimate token count for a JSON chunk or text using ~4 characters per token heuristic.

    Uses canonical compact JSON serialization when a dictionary is provided.
    Always returns at least 1 token for non-empty payloads.
    """
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    if not text:
        return 0
    return max(1, round(len(text) / 4))


def evaluate_token_budget(estimated_tokens: int, max_tokens: int, operation_id: str = "") -> str | None:
    """Check if token count exceeds budget and return an advisory warning message if so."""
    if estimated_tokens > max_tokens:
        prefix = f"Operation '{operation_id}' " if operation_id else "Chunk "
        return f"{prefix}({estimated_tokens} tokens) exceeds configured budget of {max_tokens} tokens"
    return None
