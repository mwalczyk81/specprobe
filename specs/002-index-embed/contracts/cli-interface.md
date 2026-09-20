# CLI Contract: `specprobe index` & `specprobe search`

**Feature**: `002-index-embed`
**Date**: 2026-09-19
**Status**: Draft

---

## 1. `specprobe index`

Ingests JSON Lines (`.jsonl`) emitted by `specprobe chunk` and updates the local on-disk vector store.

### Usage
```bash
specprobe index [OPTIONS] [CHUNK_FILE]
```

### Arguments
- `[CHUNK_FILE]`: Path to a `.jsonl` file containing operation chunks. If omitted, chunks are read from standard input (`stdin`).

### Options
- `--index-dir PATH`: Directory where Qdrant on-disk vector files are stored. Defaults to `./.specprobe/index` (or `SPECPROBE_INDEX_DIR` environment variable).
- `--stats`: Diagnostic inspection mode. Prints index health, total chunk count, unique specifications, and vector configuration to `stdout`. Mutually exclusive with ingesting chunks from `stdin` or file.
- `--help`: Show this help message and exit.

### Exit Codes
- `0`: Successful indexing or successful `--stats` display.
- `1`: Missing input file, invalid JSONL format, missing index directory (in `--stats` mode), or storage error.

### Stdin / Stdout / Stderr Behavior
- **Ingestion Mode**:
  - `stdin`: Stream of newline-delimited JSON `OperationChunk` objects.
  - `stdout`: Informational progress summary (e.g. `Indexed 42 operations from 'Petstore API v1.0.0' into .specprobe/index (generation: c4b8f0...)`).
  - `stderr`: Parsing errors or diagnostics on failure.
- **`--stats` Mode**:
  - `stdout`: Human-readable structured diagnostics report.
  - `stderr`: Error if index does not exist or cannot be read.

---

## 2. `specprobe search`

Executes semantic and lexical search queries against the local on-disk vector store.

### Usage
```bash
specprobe search [OPTIONS] QUERY
```

### Arguments
- `QUERY`: Natural language search query string (required).

### Options
- `--mode [dense|hybrid|hybrid-rerank]`: Retrieval algorithm. Defaults to `hybrid`.
  > **Note on Scores**: The `score` field in search output is an ordinal metric valid only within a single search call. Scores are **not comparable** across `--mode` values (dense cosine similarity, hybrid RRF fusion score, and hybrid-rerank cross-encoder score are on different scales) and are **not comparable** across separate search queries.
- `-n, --limit INTEGER`: Maximum number of matches to return. Defaults to `5`.
- `--tag TEXT`: Filter matches to operations containing this tag.
- `--method TEXT`: Filter matches to operations with this HTTP method (case-insensitive, matched uppercase).
- `--deprecated / --no-deprecated`: Filter by deprecation status.
- `--source-title TEXT`: Filter to operations originating from this specification title.
- `--source-version TEXT`: Filter to operations originating from this specification version.
- `--full`: Include complete `OperationChunk` data payload (parameters and pruned schemas) in the `chunk` field of each match. Defaults to compact output.
- `--index-dir PATH`: Directory where Qdrant vector files are located. Defaults to `./.specprobe/index` (or `SPECPROBE_INDEX_DIR` environment variable).
- `--help`: Show this help message and exit.

### Exit Codes
- `0`: Search completed successfully (even if 0 matches found).
- `1`: Index not found on disk, invalid option combination, or retrieval error.

### Output Format
Outputs a JSON array to `stdout`:
```json
[
  {
    "operationId": "getPetById",
    "path": "/pets/{petId}",
    "method": "GET",
    "score": 0.8421,
    "tags": ["pets"],
    "summary": "Find pet by ID",
    "source_title": "Swagger Petstore",
    "source_version": "1.0.0",
    "chunk": null
  }
]
```
When `--full` is passed, `chunk` contains the complete `OperationChunk` object.
