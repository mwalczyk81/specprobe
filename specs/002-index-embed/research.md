# Research & Technical Decisions: Local Vector Indexing & Semantic Search

**Feature**: `002-index-embed`
**Date**: 2026-09-19
**Status**: Completed

---

## 1. Vector Database / Storage Engine

### Decision
Use **Qdrant in local embedded on-disk mode** (`qdrant_client.QdrantClient(path=str(index_path))`), storing the collection on disk at `./.specprobe/index` (or the directory specified by `--index-dir` / `SPECPROBE_INDEX_DIR`).

### Rationale
- **Zero-Process Architecture**: Runs embedded directly inside the Python process using local storage files. Requires no external Docker containers, background daemon services, or network listeners.
- **Native Dense + Sparse Vectors**: Qdrant natively supports named vectors with independent distance metrics within the same collection (e.g. `dense` using `Distance.COSINE` and `sparse` using `models.SparseVectorParams`).
- **Single-Query Hybrid Search**: Supports server-side / engine-side Reciprocal Rank Fusion (RRF) in a single query via `client.query_points(..., prefetch=[...], query=models.FusionQuery(fusion=models.Fusion.RRF))`. This eliminates manual ranking math or external two-stage fusion code.
- **Payload Indexing & Filtering**: Provides built-in boolean, keyword, and exact match filtering over payload fields (`source_title`, `source_version`, `method`, `tags`, `deprecated`, `generation_id`) executed alongside vector search.

### Alternatives Considered
- **SQLite + sqlite-vec**: Requires compiling C extensions or managing platform-specific prebuilt binaries; lacks native sparse vector / BM25 index support.
- **ChromaDB**: Higher dependency footprint, telemetry overhead, and lacks clean, single-query sparse/dense hybrid fusion.
- **LanceDB**: Capable on-disk format, but Qdrant and FastEmbed have first-class ecosystem synergy and simpler named-vector hybrid querying.

---

## 2. Dense & Sparse Vector Models (`fastembed`)

### Decision
Use **`fastembed`** for generating both dense embeddings and sparse BM25 vectors:
- **Dense Embedding Model**: `BAAI/bge-small-en-v1.5` (384 dimensions, cosine distance) via `fastembed.TextEmbedding`.
- **Sparse Vector Model**: `Qdrant/bm25` via `fastembed.SparseTextEmbedding`.

### Rationale
- **Lightweight CPU Inference**: `fastembed` uses ONNX Runtime (`onnxruntime`), eliminating heavy dependencies like PyTorch (~800MB–2GB), CUDA, or TensorFlow.
- **Fast Startup & Low Latency**: ONNX models initialize in milliseconds on CPU and process batch embeddings with high throughput.
- **Accuracy**: `bge-small-en-v1.5` is top-ranked on MTEB among small embedding models (~130MB weight footprint) and excels at technical and code-adjacent retrieval tasks.
- **Native BM25 Token Weighting**: `Qdrant/bm25` sparse embeddings directly emit token indices and weights matching Qdrant's sparse vector interface (`models.SparseVector(indices=..., values=...)`).

### Alternatives Considered
- **`sentence-transformers`**: Requires heavy PyTorch dependencies, slower cold-start times on CLI invocations.
- **Splade (`prithivida/Splade_PP_en_v1`)**: Stronger sparse representations, but significantly larger model size and 5–10x higher inference latency on CPU compared to BM25.

---

## 3. Local Reranking Cross-Encoder & Latency Targets

### Decision
Use **`fastembed.rerank.cross_encoder.TextCrossEncoder`** with model `Xenova/ms-marco-MiniLM-L-6-v2` for the `hybrid-rerank` retrieval mode.

### Candidate Pool & Latency Target (SC-005 Tradeoff)
- **Candidate Pool**: Initial candidate retrieval via hybrid search is capped at top 20 candidates (`limit * 4` up to max 20).
- **Latency Analysis**:
  - `dense` mode: Embedding query + cosine vector search takes ~15–40ms on CPU (<250ms target holds easily).
  - `hybrid` mode: Dense embedding + BM25 sparse tokenization + Qdrant RRF search takes ~30–75ms on CPU (<250ms target holds easily).
  - `hybrid-rerank` mode: Running cross-attention over 20 `(query, document)` pairs on CPU requires ~300ms–800ms depending on CPU core availability.
- **Target Calibration**: We explicitly document a relaxed latency target for `hybrid-rerank` of **<1000ms (1.0 second)** on modern multi-core CPUs for collections up to 1,000 operations, while maintaining the strict **<250ms** target for `dense` and `hybrid` modes.

### Alternatives Considered
- **`BAAI/bge-reranker-base`**: Noticeably higher accuracy, but larger model (~440MB) pushing CPU latency for 20 pairs to 1.5s–2.5s.
- **`jinaai/jina-reranker-v1-tiny-en`**: Ultra-lightweight (~33MB), but lower domain generalizability across varied API terminology.

---

## 4. Critical Natural-Language Embedding Text Construction

### Decision
**Do NOT embed raw chunk JSON.** Construct a synthesized, information-dense natural-language document per operation chunk prior to vectorization.

### Structured Text Template
```text
{METHOD} {path} — {summary or description}
Summary: {summary}
Description: {description}
Tags: {comma-separated tags}
Parameters:
  - {name} ({in}, {required|optional}): {description} (type: {schema_type})
Request Body:
  - {description} ({content_types}): {schema_title or schema_type}
Responses:
  - {status_code} ({content_types}): {description} ({schema_type})
```

### Rationale
- OpenAPI JSON contains structural syntax noise (`"$ref"`, `"type": "string"`, curly braces, quotes) that pollutes token distributions and severely degrades dense semantic retrieval.
- API developers search with natural language intent (e.g. *"find user by email"*, *"cancel pending subscription"*). Embedding human-readable prose that connects the HTTP method, path, purpose, parameter names, and return types directly bridges the semantic gap.

### Alternatives Considered
- **Raw JSON dump**: Extremely noisy, dilutes embeddings, wastes context tokens.
- **Path + Method only**: Fails to capture parameters, request schemas, or semantic summaries.

---

## 5. Generation-Tagged Atomic Writes (Crash Resiliency)

### Decision
Each `specprobe index` execution tags newly indexed points with a unique `generation_id` (UUID4 string).
1. Collect and embed all operation chunks in the incoming batch.
2. Upsert all points into Qdrant with `generation_id` and spec metadata (`source_title`, `source_version`, `operation_id`).
3. Only after the entire stream or file is processed and committed without error, issue a deletion query for all points matching:
   `source_title == current_title AND source_version == current_version AND generation_id != current_generation_id`.

### Rationale
- Satisfies **Clarification 1** (spec-level replacement: deleting removed or renamed operations so they don't linger as orphans).
- Satisfies crash resiliency: If the process is terminated mid-stream (SIGINT, crash, malformed JSONL line), previous points for that spec remain untouched and searchable.

### Alternatives Considered
- **Purge before write**: Leaves the index empty or half-populated if ingestion fails midway.
- **Per-operation upsert without purge**: Fails to remove deleted endpoints when an API specification is updated.

---

## 6. Score Interpretation Across Retrieval Modes

### Decision
Document explicitly that `score` in search output is an **ordinal ranking metric meaningful only within a single search call**.
- `dense`: Cosine similarity score (typically `0.0` to `1.0`).
- `hybrid`: Reciprocal Rank Fusion (RRF) score (typically `0.01` to `0.05`).
- `hybrid-rerank`: Cross-encoder relevance logit/score (typically uncalibrated float, e.g. `-12.0` to `+5.0`).

### Documentation Locations
1. CLI `--help` text for `--mode`.
2. Specification (`spec.md`) and Plan (`plan.md`).
3. `contracts/cli-interface.md` and `contracts/search-results.json`.
4. `quickstart.md`.
