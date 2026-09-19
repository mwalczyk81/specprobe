# Implementation Tasks: Local Vector Indexing & Semantic Search

**Feature**: `002-index-embed`  
**Date**: 2026-09-19  
**Specification**: [specs/002-index-embed/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/002-index-embed/spec.md)  
**Implementation Plan**: [specs/002-index-embed/plan.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/002-index-embed/plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency management, and directory scaffolding.

- [x] T001 Configure runtime dependencies (`qdrant-client>=1.19.0`, `fastembed>=0.8.0`, `pydantic>=2.0.0`) and dev group (`pytest>=8.0.0`) in `pyproject.toml` and synchronize with `uv sync`.
- [x] T002 [P] Create package module directories `src/specprobe/index/` and `src/specprobe/search/` with `__init__.py` files.
- [x] T003 [P] Create test fixture `tests/fixtures/near_duplicate_operations.yaml` defining order management operations with closely-related summaries to evaluate dense vs. hybrid vs. hybrid-rerank mode ranking differences.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, natural-language document synthesizer, FastEmbed model wrappers, and embedded Qdrant store initialization that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 [P] Define Pydantic models for search results and statistics in `src/specprobe/models.py` (fields: `operationId: str`, `path: str`, `method: str`, `score: float`, `tags: list[str]`, `summary: str | None`, `source_title: str`, `source_version: str`, `chunk: dict | None`).
- [x] T005 Implement operational natural-language document synthesizer in `src/specprobe/index/synthesizer.py` to construct structured prose from `OperationChunk` (extracting HTTP method, path, summary, description, tags, parameter names/locations/types, request body descriptions/schemas, and response status codes/types, strictly avoiding raw JSON syntax noise).
- [x] T006 Implement FastEmbed engine wrapper in `src/specprobe/index/embedder.py` managing `TextEmbedding("BAAI/bge-small-en-v1.5")` for 384-dimensional dense vectors, `SparseTextEmbedding("Qdrant/bm25")` for sparse token weights, and `TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")` for reranking.
- [x] T007 Implement embedded on-disk Qdrant storage manager in `src/specprobe/index/store.py` initializing `QdrantClient(path=str(index_path))`, creating collection `specprobe_operations` with named vector configuration (`dense`: 384 Cosine, `sparse`: BM25 `SparseVectorParams`), and configuring keyword/boolean payload indices for `source_title`, `source_version`, `operation_id`, `method`, `tags`, `deprecated`, and `generation_id`.

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Idempotent Local Vector Indexing of Operation Chunks (Priority: P1) 🎯 MVP

**Goal**: Ingest JSONL operation chunks produced by `specprobe chunk` (via `stdin` or file argument), construct natural-language embedding text, compute dense and sparse vectors locally, and write generation-tagged points with atomic spec-level replacement to local on-disk Qdrant.

**Independent Test**: Stream `specprobe chunk tests/fixtures/valid_openapi_30.yaml | specprobe index`, verify that dense and sparse vectors are committed to `./.specprobe/index`, and confirm that re-indexing the same spec replaces existing chunks without creating duplicate records.

### Tests for User Story 1 🧪

- [x] T008 [P] [US1] Unit test for natural-language document synthesizer in `tests/unit/test_synthesizer.py` verifying extraction of method, path, parameters, request body, and responses without raw JSON artifacts.
- [x] T009 [P] [US1] Unit test for FastEmbed wrapper in `tests/unit/test_embedder.py` verifying dense vector dimensions (384), sparse BM25 indices/values, and cross-encoder score generation.
- [x] T010 [P] [US1] Unit test for Qdrant storage manager in `tests/unit/test_store.py` verifying collection creation, point batch upsert, and generation-tagged atomic deletion of prior specs.

### Implementation for User Story 1

- [x] T011 [US1] Implement atomic generation-tagged ingestion workflow in `src/specprobe/index/store.py`: generate unique UUID4 `generation_id`, upsert vectorized points with metadata payload (`source_title`, `source_version`, `operation_id`, `path`, `method`, `tags`, `deprecated`, `summary`, `embedding_text`, `generation_id`, and `raw_chunk`), and purge points matching `source_title == X AND source_version == Y AND generation_id != current_generation_id` only after full stream completion.
- [x] T012 [US1] Implement `specprobe index` CLI command in `src/specprobe/cli.py` accepting standard input or optional file argument, supporting `--index-dir` (defaulting to `./.specprobe/index` or `SPECPROBE_INDEX_DIR`), streaming chunk parsing, and emitting progress summaries to `stdout`.
- [x] T013 [US1] Add stream validation and error handling in `src/specprobe/cli.py` and `src/specprobe/index/store.py` for empty input streams, non-existent chunk files, malformed JSONL lines (reporting line numbers to `stderr`), and ensuring non-zero exit code 1 without corrupting existing data.
- [x] T014 [US1] Integration tests for `specprobe index` in `tests/integration/test_cli_index.py` verifying pipeline streaming (`specprobe chunk ... | specprobe index`), file argument ingestion, idempotent re-indexing, and mid-stream crash resilience.

**Checkpoint**: At this point, User Story 1 (MVP) is fully functional and independently testable. Operation chunks can be indexed persistently and idempotently.

---

## Phase 4: User Story 2 - Semantic and Filtered Search with Multi-Mode Retrieval (Priority: P2)

**Goal**: Query indexed operations using natural language with optional metadata filters across three retrieval modes (`dense`, `hybrid`, `hybrid-rerank`), returning results as compact JSON (or full chunk payload with `--full`).

**Independent Test**: Execute `specprobe search "<query>"` with `--mode dense`, `--mode hybrid`, and `--mode hybrid-rerank` against an index containing `valid_openapi_30.yaml` and `near_duplicate_operations.yaml`, verifying JSON output format, score validity, filter precision, and ranking differentiation across modes.

### Tests for User Story 2 🧪

- [x] T015 [P] [US2] Unit test for search retrieval engine in `tests/unit/test_search_engine.py` verifying pure dense cosine search, hybrid RRF fusion query execution, and cross-encoder candidate reranking.

### Implementation for User Story 2

- [x] T016 [US2] Implement multi-mode retrieval engine in `src/specprobe/search/engine.py` supporting:
  - `dense`: Single dense vector query against named vector `dense` with cosine similarity.
  - `hybrid`: Dual pre-fetch of dense (`bge-small-en-v1.5`) and sparse (`Qdrant/bm25`) vectors with Qdrant Reciprocal Rank Fusion (`models.FusionQuery(fusion=models.Fusion.RRF)`).
  - `hybrid-rerank`: Hybrid pre-fetch of top-20 candidate pool (`limit * 4`, max 20), token-level cross-attention scoring via `TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")`, and sorting by cross-encoder score.
- [x] T017 [US2] Implement metadata filter translation in `src/specprobe/search/engine.py` converting CLI options (`--tag`, `--method`, `--deprecated`, `--source-title`, `--source-version`) into Qdrant `models.Filter` match clauses.
- [x] T018 [US2] Implement `specprobe search` CLI command in `src/specprobe/cli.py` accepting `QUERY`, `--mode [dense|hybrid|hybrid-rerank]` (defaulting to `hybrid`), `-n/--limit` (defaulting to 5), filter flags, `--full` flag, and `--index-dir`, formatting results as a compact JSON array on `stdout`.
- [x] T019 [US2] Add search error handling and help text in `src/specprobe/cli.py`: validate uninitialized index (exit code 1 with descriptive `stderr` message), empty search results (emit `[]` with exit code 0), and document in `--mode` help text that scores are ordinal metrics valid only within a single invocation.
- [x] T020 [US2] Integration tests for `specprobe search` in `tests/integration/test_cli_search.py` verifying compact output, `--full` payload, metadata filters, exit codes, and mode ranking differences on `near_duplicate_operations.yaml`.

**Checkpoint**: At this point, User Stories 1 AND 2 are complete. Chunks can be indexed and retrieved across dense, hybrid, and reranked search strategies.

---

## Phase 5: User Story 3 - Index Health and Collection Diagnostics via `--stats` (Priority: P3)

**Goal**: Inspect collection size, unique specification chunk breakdowns, vector configuration, and store health status via `specprobe index --stats`.

**Independent Test**: Run `specprobe index --stats` against empty, single-spec, and multi-spec indexes, verifying that metrics are formatted clearly to `stdout` without attempting to read from `stdin`.

### Implementation for User Story 3

- [x] T021 [P] [US3] Implement collection diagnostic reporting in `src/specprobe/index/store.py` querying Qdrant point count, unique specification counts grouped by `source_title` and `source_version`, vector dimension specifications, and on-disk health status.
- [x] T022 [US3] Integrate `--stats` mode into `specprobe index` in `src/specprobe/cli.py` operating in exclusive diagnostic mode (mutually exclusive with stdin/file ingestion), formatting human-readable metrics to `stdout`.
- [x] T023 [US3] Integration tests for `specprobe index --stats` in `tests/integration/test_cli_stats.py` verifying empty index reporting (0 operations), multi-spec breakdowns, sub-100ms execution, and non-blocking CLI behavior.

**Checkpoint**: All three user stories are now independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, performance calibration, documentation, and final CLI polish.

- [x] T024 [P] Execute end-to-end quickstart validation against `specs/002-index-embed/quickstart.md`, running Scenarios A through H using `uv run specprobe` and verifying exact output alignment.
- [x] T025 [P] Update CLI documentation and docstrings across `src/specprobe/cli.py`, `src/specprobe/index/`, and `src/specprobe/search/`, documenting that scores are ordinal metrics not comparable across modes or queries.
- [x] T026 Benchmark query latencies across retrieval modes verifying dense/hybrid < 250ms and hybrid-rerank < 1000ms on multi-core CPU for up to 1,000 indexed operations in `tests/integration/test_scale_search.py`.

---

## Dependencies & Execution Order

### Phase Dependencies

```mermaid
flowchart TD
    Phase1[Phase 1: Setup] --> Phase2[Phase 2: Foundational Prerequisites]
    Phase2 --> Phase3[Phase 3: User Story 1 - Indexing Engine (MVP)]
    Phase3 --> Phase4[Phase 4: User Story 2 - Semantic Search & Modes]
    Phase2 --> Phase5[Phase 5: User Story 3 - Index Health & Stats]
    Phase4 --> Phase6[Phase 6: Polish & Cross-Cutting]
    Phase5 --> Phase6
```

- **Phase 1 (Setup)**: No dependencies — can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS** all user stories.
- **Phase 3 (User Story 1 - MVP)**: Depends on Phase 2. Delivers the foundational indexing capability.
- **Phase 4 (User Story 2)**: Depends on Phase 2 and Phase 3 (needs indexed data to search).
- **Phase 5 (User Story 3)**: Depends on Phase 2 and Phase 3 (needs storage manager and indexed data to report stats).
- **Phase 6 (Polish)**: Depends on completion of all user stories.

---

## Parallel Execution Examples

### User Story 1
```bash
# Run unit tests and foundational modules in parallel:
Task T008: "Unit test for natural-language document synthesizer in tests/unit/test_synthesizer.py"
Task T009: "Unit test for FastEmbed wrapper in tests/unit/test_embedder.py"
Task T010: "Unit test for Qdrant storage manager in tests/unit/test_store.py"
```

### User Story 2
```bash
# Implement search engine test while preparing CLI options:
Task T015: "Unit test for search retrieval engine in tests/unit/test_search_engine.py"
Task T017: "Implement metadata filter translation in src/specprobe/search/engine.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete **Phase 1: Setup** (T001–T003).
2. Complete **Phase 2: Foundational** (T004–T007).
3. Complete **Phase 3: User Story 1** (T008–T014).
4. **STOP and VALIDATE**: Stream `specprobe chunk tests/fixtures/valid_openapi_30.yaml | specprobe index` and verify points in `.specprobe/index`.

### Incremental Delivery
1. Foundation + US1 = Working persistent, idempotent local vector indexer (MVP).
2. Add US2 = Natural-language semantic search across dense, hybrid, and reranked modes.
3. Add US3 = Operational collection health and diagnostics (`--stats`).
4. Polish = End-to-end quickstart validation and latency benchmarking.
