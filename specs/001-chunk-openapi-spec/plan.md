# Implementation Plan: OpenAPI Operation Chunking CLI

**Branch**: `001-chunk-openapi-spec` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [`specs/001-chunk-openapi-spec/spec.md`](spec.md)

---

## Summary

The `specprobe chunk` command decomposes an OpenAPI 3.0 or 3.1 specification (YAML or JSON) into one discrete, self-contained chunk per operation, streamed to standard output as newline-delimited JSON (JSONL). The technical approach uses `prance` (with `openapi-spec-validator`) to parse and validate OpenAPI documents while rejecting legacy Swagger 2.0 specs. A dedicated `SchemaPruner` traverses references reachable by each operation, prunes unreferenced schemas from `components.schemas`, and employs a visited-set guard (`visited: set[str]`) to cleanly handle circular references by retaining local `$ref` pointers without infinite recursion. Path-level parameters are merged, security requirements are resolved with global fallbacks, token counts are estimated deterministically (~4 chars/token), and `--stats` / `--op` options enable high-level summaries and targeted spot-checking.

---

## Technical Context

**Language/Version**: Python 3.11+ (targeting modern typing, union syntax `|`, and pattern matching).

**Primary Dependencies**:
- `click`: CLI command definition, argument/option parsing, exit code handling.
- `prance` (with `openapi-spec-validator`): Maintained OpenAPI YAML/JSON parsing, schema validation, reference parsing.
- `pyyaml`: YAML decoding and streaming support.
- `pydantic`: Schema definitions and runtime validation for chunk metadata, configurations, and stats.

**Storage**: In-memory streaming. Standard output receives JSONL; temporary memory footprints scale with individual operations rather than full documents.

**Testing**: `pytest` for unit tests (isolated loaders, schema pruners, token estimators) and CLI integration tests. Test fixtures include minimal edge-case specs (composition, circular refs, external refs, Swagger 2.0) and a large-scale public spec (GitHub/Stripe).

**Target Platform**: Cross-platform (Windows, Linux, macOS).

**Project Type**: Standalone CLI tool.

**Performance Goals**:
- Stream and process standard specs (< 50 operations) in < 300ms.
- Stream and process large public specs (> 500 operations) in < 2.0s with bounded memory.
- Single operation lookup via `--op <id>` in < 500ms.

**Constraints**:
- Completely offline and local-first; 0 LLM calls, 0 remote API requests, 0 external embeddings.
- Standard exit code protocol (0 on success, 1 on fatal parse/validation error).
- External file references surfaced as non-fatal warnings (exit code 0).

**Scale/Scope**:
- 1 CLI command (`specprobe chunk`).
- Core modules: spec loader, operation extractor, schema pruner, token estimator, CLI formatters.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Gate | Requirement | Compliance Status | Notes |
|---|---|---|---|
| **Principle I: Clear Idiomatic Code** | Prefer clear idiomatic code over abstractions | **PASS** | Flat module structure (`loader.py`, `pruner.py`, `extractor.py`, `tokens.py`) without speculative class hierarchies or metaclasses. |
| **Principle II: Deterministic Artifacts** | Artifact generation is deterministic and never calls an LLM | **PASS** | 100% deterministic Python parsers and standard heuristics; zero LLM calls or probabilistic models. |
| **Principle III: Local-First Privacy** | Embeddings/reranking run locally | **PASS** | No embeddings or reranking involved; execution runs completely locally and offline. |
| **Principle IV: LLM Gateway & Caching** | All LLM calls route through LiteLLM | **PASS (N/A)** | No LLM calls in this feature. |
| **Principle V: Pydantic Validation** | Structured models validated with Pydantic | **PASS** | `ChunkMetadata` and `ChunkingStats` modeled and validated with Pydantic schemas; operation IDs explicitly named in all generated chunks. |
| **Principle VI: Comprehensive Testing** | Every feature ships with automated tests | **PASS** | Test plan includes unit, integration, edge-case, and scale checks with pytest. |
| **Tech Stack Standards** | Python 3.11+, Poetry, click, pytest | **PASS** | Standardized on Poetry 2.4+ and Click CLI. |

---

## Project Structure

### Documentation (this feature)

```text
specs/001-chunk-openapi-spec/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 research & technical decisions
├── data-model.md        # Phase 1 data entities and validation rules
├── quickstart.md        # Phase 1 runnable end-to-end validation scenarios
├── checklists/
│   └── requirements.md  # Spec quality validation checklist
└── contracts/
    └── cli.md           # CLI interface contract
```

### Source Code (repository root)

```text
pyproject.toml           # Poetry package and dependency configuration
src/
└── specprobe/
    ├── __init__.py
    ├── cli.py           # Click entrypoint and group definition
    ├── chunker/
    │   ├── __init__.py
    │   ├── loader.py    # Prance-backed spec loading, validation, Swagger 2.0 rejection
    │   ├── models.py    # Pydantic data models (ChunkMetadata, OperationChunk, ChunkingStats)
    │   ├── extractor.py # Operation extraction, path parameter merging, ID synthesis
    │   ├── pruner.py    # Schema pruning with visited-set cycle detection
    │   └── tokens.py    # Deterministic token estimation heuristic (~4 chars/token)
    └── formatters/
        ├── __init__.py
        ├── jsonl.py     # Newline-delimited JSON streaming serializer
        └── stats.py     # Terminal table summary formatter for --stats

tests/
├── conftest.py
├── fixtures/
│   ├── valid_openapi_30.yaml      # Baseline OpenAPI 3.0 spec
│   ├── composition_31.json        # OpenAPI 3.1 allOf/oneOf/anyOf spec
│   ├── circular_spec.yaml         # Self-referencing and mutual circular schema spec
│   ├── swagger_20.json            # Swagger 2.0 rejection fixture
│   ├── external_ref_spec.yaml     # Unsupported external file ref fixture
│   └── large_public_spec.json     # Large public spec (GitHub or Stripe) for scale checking
├── unit/
│   ├── test_loader.py             # Spec loading, format validation, Swagger rejection
│   ├── test_extractor.py          # Param merging, operationId synthesis, security fallback
│   ├── test_pruner.py             # Schema pruning, visited-set cycle guard, compositions
│   └── test_tokens.py             # Token estimation heuristic accuracy
└── integration/
    ├── test_cli_chunk.py          # CLI execution, JSONL streaming, stdout/stderr isolation
    ├── test_cli_stats.py          # Exclusive --stats table output
    ├── test_cli_op.py             # Single --op spot checking
    └── test_scale_streaming.py    # Scale check verifying sub-2s execution on large spec
```

**Structure Decision**: A single Python package structure under `src/specprobe/` with clean functional separation between CLI commands (`cli.py`), chunking core (`chunker/`), and output formatters (`formatters/`).

---

## Complexity Tracking

> **Constitution Check**: Zero violations. No unjustified architectural complexity. All gates pass.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| *None* | *N/A* | *N/A* |
