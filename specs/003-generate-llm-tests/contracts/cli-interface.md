# CLI Interface Contracts: LLM Test Generation & Filter-Only Search

**Feature**: `003-generate-llm-tests`
**Date**: 2026-09-19
**Status**: Completed

---

## 1. `specprobe generate` Command Contract

Generates schema-validated test cases from `OperationChunk`-bearing search results using a local-first LLM gateway with cryptographic disk caching.

### Synopsis
```bash
specprobe generate [OPTIONS] [RESULTS_FILE]
# Or via pipeline:
specprobe search <QUERY_OR_FILTERS> --full | specprobe generate [OPTIONS]
```

### Arguments
- `RESULTS_FILE` *(optional, string)*: Path to a JSON file containing search results emitted by `specprobe search --full`. If omitted, input is read from standard input (`stdin`).

### Options
| Option | Type | Default | Environment Variable | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--model` | `str` | `openai/local-model` | `SPECPROBE_LLM_MODEL` | Model identifier string passed to LiteLLM. |
| `--api-base` | `str` | `http://localhost:1234/v1` | `SPECPROBE_LLM_API_BASE` | Base endpoint URL for model requests. |
| `--cache-dir` | `path` | `.specprobe/cache` | `SPECPROBE_CACHE_DIR` | Directory where LLM call cache files are stored. |
| `--no-cache` | `flag` | `False` | `SPECPROBE_NO_CACHE` | Bypass existing disk cache entries and refresh cache records. |
| `--temperature` | `float` | `0.0` | `SPECPROBE_LLM_TEMPERATURE` | Sampling temperature for LLM completions. |

### Input Contract
- Input MUST be a valid JSON array of search result objects containing full operation chunks (matching `specprobe search --full`).
- Each element in the array must contain:
  - `operationId`: string
  - `path`: string
  - `method`: string
  - `chunk`: object containing `metadata`, `operation`, and `components`
- Non-conforming payloads (compact search results missing `chunk`, raw JSONL, unparseable JSON) MUST be rejected with exit code 1 and a descriptive error on `stderr`.

### Output Contract
- Standard Output (`stdout`): Clean JSON Lines (JSONL). Exactly one line per successfully generated and validated `GeneratedTestCase` object.
- Standard Error (`stderr`): Progress indicators, cache hit/miss notifications, connection diagnostics, and validation failure details.

### Exit Codes
| Exit Code | Condition |
| :---: | :--- |
| `0` | Successful generation (at least one test case generated, or empty input stream). |
| `1` | Failure (unparseable input JSON, missing `chunk` schema payloads, unreachable model endpoint, or 100% of operations failed validation). |

---

## 2. `specprobe search` Command Contract Updates

Relaxes the search query argument to support unranked specification extraction.

### Synopsis
```bash
specprobe search [QUERY] [OPTIONS]
```

### Argument Relaxation
- `QUERY` *(optional, string, default: None)*:
  - When provided: executes multi-mode semantic search (`dense`, `hybrid`, `hybrid-rerank`), returning top-N ranked matches.
  - When omitted: executes unranked filter matching. At least one metadata filter MUST be provided.

### Option Behavior Changes
| Option | Changed Behavior When `QUERY` is Omitted |
| :--- | :--- |
| `-n`, `--limit` | Defaults to **unlimited** (all matching chunks returned) when `QUERY` is omitted. If an explicit `--limit <N>` is provided by the user, caps the unranked results to $N$. |
| `--mode` | Ignored in filter-only mode. No dense embeddings, sparse tokens, or cross-encoder rerankers are computed. |
| `score` (in output) | Returns `0.0` for all matches in filter-only mode to explicitly reflect unranked retrieval. |

### Validation Rule
If neither `QUERY` nor at least one filter (`--tag`, `--method`, `--deprecated`, `--source-title`, `--source-version`) is provided:
- Emit error to `stderr`: `Error: Either a search query or at least one filter (--tag, --method, --deprecated, --source-title, --source-version) must be provided.`
- Exit with code 1.

---

## 3. End-to-End Pipeline Contract

To extract an entire specification or tagged domain and generate full test coverage:
```bash
# Full specification test plan generation
specprobe search --source-title "Petstore API" --full | specprobe generate > tests/petstore_tests.jsonl

# Tagged domain test plan generation
specprobe search --tag "orders" --full | specprobe generate > tests/orders_tests.jsonl
```
