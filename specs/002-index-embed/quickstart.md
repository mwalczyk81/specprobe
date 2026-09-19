# Quickstart: Local Vector Indexing & Semantic Search

**Feature**: `002-index-embed`  
**Date**: 2026-09-19  
**Status**: Draft

---

## Overview

This guide walks through end-to-end validation of local vector indexing (`specprobe index`) and semantic search (`specprobe search`) using local Qdrant embedded storage, FastEmbed dense/sparse embeddings, and local cross-encoder reranking.

> [!IMPORTANT]
> **Understanding Relevance Scores**: The `score` field in `specprobe search` results is an **ordinal ranking metric valid only within a single search call**.
> - Scores **cannot be compared across `--mode` values**:
>   - `--mode dense`: Cosine similarity (typically `0.0` to `1.0`).
>   - `--mode hybrid`: Reciprocal Rank Fusion (RRF) score (typically small positive fractions `~0.01 - 0.05`).
>   - `--mode hybrid-rerank`: Cross-encoder logits/relevance score (typically floats ranging from `-12.0` to `+5.0`).
> - Scores **cannot be compared across separate search queries**. A score of `0.85` on query A does not mean query A had a better match than query B scoring `0.72`.

> [!NOTE]
> **Performance Expectations**:
> - `--mode dense` and `--mode hybrid`: Target **<250ms** query latency for collections up to 1,000 operations.
> - `--mode hybrid-rerank`: Target **<1000ms (1.0 second)** on modern multi-core CPUs, accounting for cross-attention evaluation over the top candidate pool.

---

## 1. Prerequisites

Verify Python 3.11+ and `uv` environment:
```bash
uv run specprobe --help
```
Ensure `specprobe chunk` works against standard fixtures:
```bash
uv run specprobe chunk tests/fixtures/valid_openapi_30.yaml -n 1
```

---

## 2. Ingestion & Indexing Scenarios

### Scenario A: Pipe Chunk Stream into Indexer
Stream operation chunks directly from `specprobe chunk` to `specprobe index`:
```bash
uv run specprobe chunk tests/fixtures/valid_openapi_30.yaml | uv run specprobe index
```
**Expected Outcome**:
- Indexing completes with exit code 0.
- Operations are vectorized into dense (`bge-small-en-v1.5`) and sparse (`bm25`) vectors.
- Points are written to `./.specprobe/index` tagged with a unique `generation_id`.
- Informational summary emitted: `Indexed 3 operations from 'Swagger Petstore 1.0.0' into .specprobe/index`.

### Scenario B: Index from Saved JSONL File
```bash
uv run specprobe chunk tests/fixtures/composition_31.json > chunks.jsonl
uv run specprobe index chunks.jsonl
```
**Expected Outcome**:
- Indexing completes with exit code 0.
- Persistent index now contains operations from both specifications.

### Scenario C: Collection Health & Statistics
```bash
uv run specprobe index --stats
```
**Expected Outcome**:
Outputs structured collection metrics:
```text
SpecProbe Vector Index Statistics:
- Location: ./.specprobe/index
- Status: healthy
- Total Indexed Operations: 5
- Unique Specifications: 2
  * Swagger Petstore (1.0.0): 3 operations
  * Composition Test API (3.1.0): 2 operations
- Vector Configurations:
  * dense: 384 dimensions (Cosine)
  * sparse: BM25 token weights
```

### Scenario D: Idempotent Re-indexing & Atomic Replacement
Re-index `valid_openapi_30.yaml`:
```bash
uv run specprobe chunk tests/fixtures/valid_openapi_30.yaml | uv run specprobe index
uv run specprobe index --stats
```
**Expected Outcome**:
- Spec-level replacement purges prior generation chunks matching `Swagger Petstore 1.0.0`.
- Total count remains 5 (no duplicates created).

---

## 3. Search & Retrieval Scenarios

### Scenario E: Default Hybrid Search (Compact JSON)
```bash
uv run specprobe search "find pet by identifier"
```
**Expected Outcome**:
Returns compact JSON array with top matches:
```json
[
  {
    "operationId": "showPetById",
    "path": "/pets/{petId}",
    "method": "GET",
    "score": 0.032258,
    "tags": ["pets"],
    "summary": "Info for a specific pet",
    "source_title": "Swagger Petstore",
    "source_version": "1.0.0"
  }
]
```

### Scenario F: Mode Comparison (`dense` vs `hybrid` vs `hybrid-rerank`)
Run search across the 3 retrieval modes against near-duplicate operations (`tests/fixtures/near_duplicate_operations.yaml`):

1. **Dense Vector Search**:
   ```bash
   uv run specprobe search "retrieve pet details" --mode dense
   ```
   Uses local semantic embeddings; scores reflect cosine similarity.

2. **Hybrid Search (Dense + BM25)**:
   ```bash
   uv run specprobe search "retrieve pet details" --mode hybrid
   ```
   Blends semantic similarity with exact lexical term matches; scores reflect RRF.

3. **Hybrid + Cross-Encoder Reranking**:
   ```bash
   uv run specprobe search "retrieve pet details" --mode hybrid-rerank
   ```
   Fetches top candidates via hybrid retrieval, applies MiniLM cross-encoder reranking; scores reflect token-level cross-attention relevance.

### Scenario G: Metadata Filtering
Narrow search candidates by method, tag, or spec:
```bash
uv run specprobe search "pet" --method POST --tag pets
```
**Expected Outcome**:
Only returns `POST` operations tagged with `pets` (e.g. `createPets`).

### Scenario H: Full Chunk Payload Inspection
Include complete parameters and pruned component schemas in search results:
```bash
uv run specprobe search "showPetById" --full
```
**Expected Outcome**:
Each match includes the `chunk` field containing parameters, responses, and pruned schemas.

---

## 4. Edge Cases & Error Handling

### Missing Index Directory
```bash
uv run specprobe search "test" --index-dir ./nonexistent/path
```
**Expected Outcome**: Exits with code 1; outputs `Error: Index not found at './nonexistent/path'. Run 'specprobe index' first.` to `stderr`.

### Empty Query Results
```bash
uv run specprobe search "completely_unrelated_concept_xyz" --method DELETE
```
**Expected Outcome**: Exits with code 0; outputs `[]` to `stdout`.
