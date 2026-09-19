"""Unit tests for DiskCache: key hashing determinism, hits, misses, and recovery."""

import json
from pathlib import Path

from specprobe.generator.cache import DiskCache, compute_cache_key


def test_compute_cache_key_determinism() -> None:
    """Verify key hash determinism and that api_base is strictly excluded from key."""
    messages = [
        {"role": "system", "content": "You are an API tester."},
        {"role": "user", "content": "Generate test for GET /pets"},
    ]

    key1 = compute_cache_key(model="openai/local-model", messages=messages, temperature=0.0)
    key2 = compute_cache_key(model="openai/local-model", messages=messages, temperature=0.0)
    assert key1 == key2
    assert len(key1) == 64  # SHA-256 hex string

    # Changing model changes key
    key_other_model = compute_cache_key(model="gpt-4o", messages=messages, temperature=0.0)
    assert key1 != key_other_model

    # Changing temperature changes key
    key_other_temp = compute_cache_key(
        model="openai/local-model", messages=messages, temperature=0.7
    )
    assert key1 != key_other_temp

    # Changing message content changes key
    key_other_content = compute_cache_key(
        model="openai/local-model",
        messages=[{"role": "user", "content": "Different prompt"}],
        temperature=0.0,
    )
    assert key1 != key_other_content


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    """Verify cache miss returns None."""
    cache = DiskCache(cache_dir=tmp_path)
    messages = [{"role": "user", "content": "hello"}]
    assert cache.get(model="openai/local-model", messages=messages, temperature=0.0) is None


def test_cache_set_and_hit(tmp_path: Path) -> None:
    """Verify setting and retrieving cache entry, checking on-disk record format."""
    cache = DiskCache(cache_dir=tmp_path)
    messages = [{"role": "user", "content": "hello"}]
    completion = '{"operation_id": "testOp"}'

    cache_key = cache.set(
        model="openai/local-model",
        messages=messages,
        temperature=0.0,
        completion_text=completion,
        api_base="http://localhost:1234/v1",
    )

    cache_file = tmp_path / f"{cache_key}.json"
    assert cache_file.exists()

    record = json.loads(cache_file.read_text(encoding="utf-8"))
    assert record["cache_key"] == cache_key
    assert record["model"] == "openai/local-model"
    assert record["api_base"] == "http://localhost:1234/v1"
    assert record["completion_text"] == completion
    assert "created_at" in record

    # Retrieve from cache
    hit = cache.get(model="openai/local-model", messages=messages, temperature=0.0)
    assert hit == completion


def test_no_cache_flag_bypasses_read(tmp_path: Path) -> None:
    """Verify no_cache=True ignores existing on-disk entries on get()."""
    cache_normal = DiskCache(cache_dir=tmp_path, no_cache=False)
    cache_bypass = DiskCache(cache_dir=tmp_path, no_cache=True)

    messages = [{"role": "user", "content": "hello"}]
    completion = '{"operation_id": "testOp"}'

    cache_normal.set(
        model="openai/local-model",
        messages=messages,
        temperature=0.0,
        completion_text=completion,
    )

    hit = cache_normal.get(model="openai/local-model", messages=messages, temperature=0.0)
    assert hit == completion
    assert cache_bypass.get(model="openai/local-model", messages=messages, temperature=0.0) is None


def test_corrupted_cache_file_recovery(tmp_path: Path) -> None:
    """Verify that unparseable cache files are handled gracefully as a miss."""
    cache = DiskCache(cache_dir=tmp_path)
    messages = [{"role": "user", "content": "hello"}]

    key = compute_cache_key(model="openai/local-model", messages=messages, temperature=0.0)
    corrupted_file = tmp_path / f"{key}.json"
    corrupted_file.write_text("{corrupt json", encoding="utf-8")

    # Should not raise; returns None
    assert cache.get(model="openai/local-model", messages=messages, temperature=0.0) is None


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    """Verify atomic write leaves only the final .json file without temp files."""
    cache = DiskCache(cache_dir=tmp_path)
    messages = [{"role": "user", "content": "hello"}]

    key = cache.set(
        model="openai/local-model",
        messages=messages,
        temperature=0.0,
        completion_text='{"status": 200}',
    )

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == f"{key}.json"
