"""Cryptographic disk cache for LLM completions enforcing deterministic offline replay."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "DiskCache",
    "compute_cache_key",
]


def compute_cache_key(
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> str:
    """Compute deterministic SHA-256 cache key from model parameters and prompt messages.

    Strictly complies with SpecProbe Constitution Principle IV:
    The hash includes (messages, model, temperature). The endpoint routing URL
    (api_base) is strictly excluded so that cache entries recorded against local
    servers hit reliably in offline CI environments without live model runtimes.

    Parameters
    ----------
    model : str
        Model identifier string.
    messages : list[dict[str, str]]
        Full chat conversation history.
    temperature : float
        Sampling temperature.

    Returns
    -------
    str
        64-character hexadecimal SHA-256 hash.
    """
    payload: dict[str, Any] = {
        "messages": messages,
        "model": model,
        "temperature": float(temperature),
    }
    canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


class DiskCache:
    """Persistent on-disk cache for LiteLLM completion calls."""

    def __init__(
        self,
        cache_dir: str | Path = ".specprobe/cache",
        no_cache: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.no_cache = no_cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> str | None:
        """Retrieve cached completion text if present and valid.

        Returns None if no_cache is True, entry does not exist, or file is corrupted.
        """
        if self.no_cache:
            return None

        key = compute_cache_key(model=model, messages=messages, temperature=temperature)
        cache_file = self.cache_dir / f"{key}.json"
        if not cache_file.exists():
            return None

        try:
            content = cache_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict) and "completion_text" in data:
                return str(data["completion_text"])
        except Exception:
            # Corrupted or unreadable cache file; treat as cache miss
            return None

        return None

    def set(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        completion_text: str,
        api_base: str | None = None,
    ) -> str:
        """Atomically persist completion text and audit metadata to disk cache.

        Parameters
        ----------
        model : str
            Model identifier string.
        messages : list[dict[str, str]]
            Chat conversation history.
        temperature : float
            Sampling temperature.
        completion_text : str
            Raw text returned by model completion.
        api_base : str | None
            Endpoint URL preserved as audit metadata (not part of key hash).

        Returns
        -------
        str
            The 64-character SHA-256 cache key.
        """
        key = compute_cache_key(model=model, messages=messages, temperature=temperature)
        cache_file = self.cache_dir / f"{key}.json"
        temp_file = self.cache_dir / f".{key}.tmp"

        record: dict[str, Any] = {
            "cache_key": key,
            "model": model,
            "api_base": api_base,
            "messages": messages,
            "temperature": float(temperature),
            "completion_text": completion_text,
            "created_at": datetime.now(UTC).isoformat(),
        }

        canonical_data = json.dumps(record, indent=2, ensure_ascii=False)
        temp_file.write_text(canonical_data, encoding="utf-8")
        os.replace(temp_file, cache_file)

        return key
