"""Newline-delimited JSON (JSONL) stream formatting module."""

import json
from typing import Iterable, Generator
from specprobe.chunker.models import OperationChunk


def format_chunk_as_jsonl(chunk: OperationChunk) -> str:
    """Serialize an OperationChunk to a compact single-line JSON string."""
    payload = chunk.model_dump(by_alias=True)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def stream_chunks_as_jsonl(chunks: Iterable[OperationChunk]) -> Generator[str, None, None]:
    """Stream an iterable of OperationChunk instances as newline-terminated JSON strings."""
    for chunk in chunks:
        yield format_chunk_as_jsonl(chunk) + "\n"
