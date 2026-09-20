# Implementation Plan: LLM Test Generation & Filter-Only Search

**Branch**: `003-generate-llm-tests` | **Date**: 2026-09-19 | **Spec**: [specs/003-generate-llm-tests/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/003-generate-llm-tests/spec.md)

**Input**: Feature specification from `specs/003-generate-llm-tests/spec.md`

---

## Summary

Implement the `specprobe generate` CLI command and companion unranked filter-only search in `specprobe search` to produce structured, schema-validated test cases from `OperationChunk`-bearing search results using a local-default language model.
- **Unified Gateway**: LiteLLM (`litellm`) as the single unified gateway, defaulting to a local LM Studio endpoint (`http://localhost:1234/v1`, model `openai/local-model`) with zero cloud transmissions unless explicit credentials/flags are provided.
- **Cryptographic Disk Caching**: Persistent JSON cache stored in `.specprobe/cache` keyed on a deterministic SHA-256 hash of the canonical prompt payload and model configuration (strictly excluding transport routing URLs like `api_base`), enabling instant replay and 100% offline automated test runs in CI.
- **Strict Pydantic Validation & Traceability**: Validate every generated test case against `GeneratedTestCase`, guaranteeing explicit `operationId` linkage, concrete request fixtures, and 2xx expected response assertions.
- **Single-Retry Self-Correction**: Automatically retry validation failures exactly once by feeding specific schema validation error feedback back to the model.
- **Resilient Batch Processing**: Per-operation error containment: operations failing after retry log a descriptive error to `stderr` and are skipped without aborting the batch.
- **Streaming JSONL Output**: Stream validated test cases line-by-line to `stdout` for downstream consumption by Postman and REST Client exporters.
- **Unranked Filter-Only Search**: Make `specprobe search`'s query argument optional; when omitted with metadata filters, scroll unranked points directly from Qdrant without vector inference or default limit truncation.

---

## Technical Context

**Language/Version**: Python 3.11+ (tested on Python 3.14.7)
**Primary Dependencies**: `click>=8.1.0`, `pydantic>=2.0.0`, `litellm>=1.0.0`, `qdrant-client>=1.19.0`, `fastembed>=0.8.0`
**Storage**: File-based JSON disk cache (`.specprobe/cache/`, configurable via `--cache-dir` or `SPECPROBE_CACHE_DIR`)
**Testing**: `pytest>=8.0.0` with `uv run pytest`
**Target Platform**: Windows, Linux, macOS
**Project Type**: CLI developer tool
**Performance Goals**:
- Cache-hit generation latency < 1 second for batches up to 50 operations (SC-002).
- Filter-only unranked search retrieval < 100ms for collections up to 1,000 operations.
- Single happy-path test case per operation to minimize local inference token consumption and runtime.
**Constraints**:
- 100% local-first privacy: LM Studio default, no remote outbound sockets opened without explicit opt-in env vars (Principle III & IV).
- Exactly one retry on schema validation failure; fail-safe batch execution (Principle V).
- Complete traceability to source specification `operationId` (Principle V).
- Downstream artifact generators remain zero-LLM consumers of the emitted JSONL test cases (Principle II).
**Scale/Scope**: Specification batches from single operations up to hundreds of endpoints across complex enterprise APIs.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Gate | Compliance Analysis | Status |
| :--- | :--- | :---: |
| **I. Clear Idiomatic Code Over Abstractions** | Implements straightforward modules (`gateway.py`, `cache.py`, `prompt.py`, `engine.py`) using direct Python 3.11+ patterns. No speculative abstraction layers or framework wrappers around LiteLLM. | **PASS** |
| **II. Deterministic Artifact Generation (Zero-LLM)** | Generation command emits structured JSONL test cases that serve as the input fixtures for downstream deterministic Postman and `.http` exporters. No LLMs are introduced into artifact serialization. | **PASS** |
| **III. Local-First Privacy & Compute** | Default target is local LM Studio (`http://localhost:1234/v1`). Cloud providers strictly opt-in via explicit environment variables. Offline test execution supported via disk cache. | **PASS** |
| **IV. Unified Gateway, Local-Default LLM & Disk Caching** | All LLM interactions route through LiteLLM. All calls are cached to local disk keyed deterministically on SHA-256 hash of prompt payload (messages, model, temperature; strictly excluding endpoint routing URL). Cache hits return immediately with zero inference, enabling offline CI replay against pre-recorded fixtures. | **PASS** |
| **V. Strict Pydantic Validation & Single Retry** | Output validated against `GeneratedTestCase` Pydantic model. Exactly one retry with schema validation error feedback. Operation traceability enforced. Batch processing continues on single-operation failure. | **PASS** |
| **VI. Comprehensive Testing** | Every module and CLI command ships with automated unit and integration tests written in `pytest`. Test suites run offline in CI using pre-recorded disk cache fixtures. | **PASS** |

---

## Project Structure

### Documentation (this feature)

```text
specs/003-generate-llm-tests/
├── spec.md              # Feature specification (clarified & validated)
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output (architectural & technical decisions)
├── data-model.md        # Phase 1 output (entities, schemas, lifecycle diagrams)
├── quickstart.md        # Phase 1 output (runnable end-to-end validation scenarios)
├── contracts/           # Phase 1 output
│   ├── cli-interface.md # CLI invocation contracts and pipeline definitions
│   └── generated-test-case.schema.json # JSON Schema for generated test case
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (generated by /speckit-tasks)
```

### Source Code (repository root)

```text
src/specprobe/
├── __init__.py
├── cli.py                  # Extended with 'generate' command and relaxed 'search' argument
├── models.py               # Shared Pydantic models (OperationChunk, SearchMatch)
├── chunker/                # Existing feature 001 modules
├── index/                  # Existing feature 002 modules
├── search/                 # Feature 002: updated with unranked scroll retrieval
│   ├── __init__.py
│   └── engine.py           # Updated search() with unranked scroll branch
└── generator/              # Feature 003: LLM test generation modules
    ├── __init__.py
    ├── models.py           # GeneratedTestCase, RequestFixture, ResponseAssertion
    ├── gateway.py          # LiteLLM client wrapper, endpoint resolution, cloud opt-in check
    ├── cache.py            # SHA-256 disk cache with atomic file replacement
    ├── prompt.py           # OperationChunk to structured prompt synthesis
    └── engine.py           # Generation orchestrator, retry protocol, batch processing

tests/
├── fixtures/
│   ├── valid_openapi_30.yaml        # Existing spec fixture
│   ├── composition_31.json          # Existing spec fixture
│   ├── search_full_results.json     # Search results fixture with full chunk bodies
│   └── cache/                       # Pre-recorded LLM disk cache fixtures for offline CI
│       └── *.json
├── unit/
│   ├── test_generator_models.py     # Pydantic schema validation tests
│   ├── test_generator_cache.py      # Cache hit/miss/bypass/atomic write tests
│   ├── test_generator_gateway.py    # LiteLLM routing and local/cloud resolution tests
│   ├── test_generator_prompt.py     # Prompt synthesis and Markdown fence stripping tests
│   └── test_generator_engine.py     # Retry loop, self-correction, and batch failure tests
└── integration/
    ├── test_search_unranked.py      # Filter-only unranked search tests
    └── test_generate_cli.py         # End-to-end generate CLI tests (stdin, file, piping)
```

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No constitutional violations. All implementations adhere strictly to Principles I through VI.*
