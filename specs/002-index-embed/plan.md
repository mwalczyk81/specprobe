# Implementation Plan: Local Vector Indexing & Semantic Search

**Branch**: `002-index-embed` | **Date**: 2026-09-19 | **Spec**: [specs/002-index-embed/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/002-index-embed/spec.md)

**Input**: Feature specification from `specs/002-index-embed/spec.md`

---

## Summary

Implement the `specprobe index` and `specprobe search` CLI commands to enable persistent, local-first vector indexing and multi-mode semantic search over OpenAPI operation chunks produced by `specprobe chunk`.
- **Vector Database**: Embedded Qdrant running in local on-disk mode (`QdrantClient(path=...)`) at `./.specprobe/index` (or `--index-dir`).
- **Embedding & Sparse Engine**: `fastembed` using `BAAI/bge-small-en-v1.5` for dense vectors and `Qdrant/bm25` for sparse vectors, enabling native single-query hybrid search via Qdrant's Reciprocal Rank Fusion (`models.FusionQuery(fusion=models.Fusion.RRF)`).
- **Reranker**: `fastembed.rerank.cross_encoder.TextCrossEncoder` with `Xenova/ms-marco-MiniLM-L-6-v2` for CPU-efficient cross-attention reranking in `hybrid-rerank` mode.
- **Natural-Language Text Construction**: Synthesize information-dense operational summaries from HTTP method, path, summary/description, parameters, and response shapes before vectorization—avoiding raw JSON schema noise.
- **Generation-Tagged Atomic Writes**: Guarantee crash-resilient spec-level replacement by tagging incoming points with a unique `generation_id` and purging prior generations only after the ingestion stream completes cleanly.
- **Zero Cloud / Zero LLM**: Fully self-contained local execution with zero outbound network calls and zero LLM invocations.

---

## Technical Context

**Language/Version**: Python 3.11+ (verified on Python 3.14.7)
**Primary Dependencies**: `click>=8.1.0`, `pydantic>=2.0.0`, `qdrant-client>=1.19.0`, `fastembed>=0.8.0`
**Storage**: Embedded on-disk Qdrant storage (`./.specprobe/index`, configurable via `--index-dir` or `SPECPROBE_INDEX_DIR`)
**Testing**: `pytest>=8.0.0` with `uv run pytest`
**Target Platform**: Windows, Linux, macOS (CPU-based ONNX Runtime, no GPU required)
**Project Type**: CLI developer tool
**Performance Goals**:
- Dense and hybrid search latency < 250ms for collections up to 1,000 operations (SC-005).
- Hybrid-rerank search latency < 1000ms (1.0s) on multi-core CPU across top 20 candidate pool.
- Collection diagnostics (`--stats`) latency < 100ms (SC-007).
**Constraints**:
- 100% offline, zero network, zero cloud APIs, zero LLMs (Constitution Principle III).
- Idempotent spec-level replacement on `(source_title, source_version)` without orphaned operations.
- Scores are ordinal ranking values meaningful only within a single query; document non-comparability across modes and invocations.
**Scale/Scope**: Collections containing up to thousands of operations; real-world specs like Stripe (~600 operations).

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Gate | Compliance Analysis | Status |
|------------------|---------------------|--------|
| **I. Clear Idiomatic Code Over Abstractions** | Uses direct Python 3.11+ patterns. Uses `QdrantClient` and `fastembed` directly without introducing custom ORM layers or speculative vector database abstractions. | **PASS** |
| **II. Deterministic Artifact Generation (Zero-LLM)** | N/A to this feature (applies to Postman / .http export), but indexing and search pipelines are 100% deterministic/algorithmic and invoke zero LLMs. | **PASS** |
| **III. Local-First Privacy & Compute** | Both dense/sparse embedding (`fastembed`) and cross-encoder reranking (`TextCrossEncoder`) run self-contained on the local CPU via ONNX Runtime. Vector database runs embedded on disk. Zero remote sockets opened. | **PASS** |
| **IV. Unified Gateway, Local-Default LLM & Disk Caching** | No LLM calls used in indexing or retrieval. | **PASS** |
| **V. Strict Pydantic Validation & Traceability** | CLI models and entity payloads use Pydantic models. Every indexed point is keyed and traceable by `operationId`, `path`, and `method`. | **PASS** |
| **VI. Comprehensive Testing** | Every module (synthesizer, embedder, store, searcher, CLI commands) ships with automated unit and integration tests written in `pytest`. | **PASS** |

---

## Project Structure

### Documentation (this feature)

```text
specs/002-index-embed/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output (architectural & technical decisions)
├── data-model.md        # Phase 1 output (entities, schemas, lifecycle diagrams)
├── quickstart.md        # Phase 1 output (runnable end-to-end validation scenarios)
├── contracts/           # Phase 1 output
│   ├── cli-interface.md # CLI invocation contracts and score caveats
│   └── search-results.schema.json # JSON Schema for search output
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (generated by /speckit-tasks)
```

### Source Code (repository root)

```text
src/specprobe/
├── __init__.py
├── cli.py                  # Extended with 'index' and 'search' Click commands
├── models.py               # Shared Pydantic models (OperationChunk, SearchMatch)
├── chunker/                # Existing feature 001 modules
│   ├── extractor.py
│   ├── pruner.py
│   └── estimator.py
├── index/                  # Feature 002: Ingestion & Storage modules
│   ├── __init__.py
│   ├── synthesizer.py      # Natural language document builder (OperationChunk -> embedding text)
│   ├── embedder.py         # FastEmbed wrapper for dense, sparse, and cross-encoder models
│   └── store.py            # Local Qdrant embedded client, collection setup, atomic tagged writes
└── search/                 # Feature 002: Retrieval & Reranking modules
    ├── __init__.py
    └── engine.py           # Multi-mode search execution (dense, hybrid, hybrid-rerank), filtering

tests/
├── fixtures/
│   ├── valid_openapi_30.yaml        # Existing feature 001 fixture (reused)
│   ├── composition_31.json          # Existing feature 001 fixture (reused)
│   └── near_duplicate_operations.yaml # New fixture: near-duplicate summaries for mode ranking diffs
├── unit/
│   ├── test_extractor.py            # Existing unit tests
│   ├── test_pruner.py               # Existing unit tests
│   ├── test_synthesizer.py          # Unit tests for natural language embedding text construction
│   ├── test_embedder.py             # Unit tests for dense/sparse/cross-encoder wrappers
│   └── test_store.py                # Unit tests for Qdrant setup, generation writes, and stats
└── integration/
    ├── test_cli_chunk.py            # Existing CLI chunk tests
    ├── test_cli_op.py               # Existing CLI op tests
    ├── test_cli_validation.py       # Existing CLI validation tests
    ├── test_scale_streaming.py      # Existing scale tests
    ├── test_cli_index.py            # Integration tests for specprobe index (pipe, file, --stats, idempotency)
    └── test_cli_search.py           # Integration tests for specprobe search (modes, filters, --full, errors)
```

**Structure Decision**: Clean modular decomposition separating chunking (`specprobe.chunker`), indexing (`specprobe.index`), and retrieval (`specprobe.search`) under `src/specprobe/`, with all Click CLI commands unified in `src/specprobe/cli.py`.

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations. All design elements strictly comply with SpecProbe Constitution Principles I–VI.*
