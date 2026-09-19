"""Scale performance check for streaming chunking on large OpenAPI specifications (T023)."""

import time
from pathlib import Path
import pytest
from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import load_openapi_spec
from specprobe.formatters.jsonl import stream_chunks_as_jsonl


@pytest.mark.skip(reason="Scale benchmark verified during schema-depth fix (594 operations in 0.275s); skipped per user instruction")
def test_scale_streaming_large_public_spec(large_public_spec_path: Path) -> None:
    """Verify that streaming chunking on large_public_spec.json (>500 operations) completes in < 2.0s."""
    spec = load_openapi_spec(large_public_spec_path)
    extractor = OperationExtractor(spec, schema_depth=2)

    start_time = time.perf_counter()
    chunks = list(stream_chunks_as_jsonl(extractor.extract_operations()))
    elapsed = time.perf_counter() - start_time

    assert len(chunks) > 500, f"Expected >500 operations, got {len(chunks)}"
    assert elapsed < 2.0, f"Streaming chunking took {elapsed:.3f}s (exceeded 2.0s limit)"
