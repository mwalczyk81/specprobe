# Implementation Plan: Negative Input & Resource Test Generation (400 & 404)

**Branch**: `008-negative-input-tests` | **Date**: 2026-09-20 | **Spec**: [specs/008-negative-input-tests/spec.md](spec.md)

**Input**: Feature specification from `/specs/008-negative-input-tests/spec.md`

## Summary

Extend SpecProbe's automated test generation to produce deterministic negative test cases asserting HTTP 404 Not Found (resource lookup failure via leaf path parameter mutation) and HTTP 400 Bad Request (request body schema violation via property omission or type inversion).

In strict adherence to SpecProbe Constitution Principle II (Deterministic Artifact Generation / Zero-LLM), both mutations are algorithmic transforms operating on validated happy-path `GeneratedTestCase` instances and OpenAPI `OperationChunk` metadata. Both generators default to enabled in `specprobe generate`, with independent CLI flag pairs (`--not-found/--no-not-found` and `--invalid-input/--no-invalid-input`), and export seamlessly into Postman collections (`[404]`, `[400]` item prefixes, status assertions) and REST Client `.http` files (`# @name <op>_404`, `# @name <op>_400`, `# Expected Status:` comments).

---

## Technical Context

**Language/Version**: Python 3.11+ (modern structural pattern matching, strict type annotations)

**Primary Dependencies**: Pydantic v2 (data modeling and schema validation), Click (CLI options and command execution), LiteLLM (positive test case generation gateway)

**Storage**: In-memory transforms, JSONL files (`GeneratedTestCase` streaming), existing disk cache

**Testing**: `pytest` (unit and integration tests), `hypothesis` (property-based test generation strategies)

**Target Platform**: Windows, Linux, macOS (cross-platform path resolution, zero OS-specific quirks)

**Project Type**: CLI tool & developer testing framework

**Performance Goals**: < 1ms per negative test case generated (pure Python dictionary/string transforms, zero network, zero LLM inference)

**Constraints**: Strict adherence to Constitution Principle II (Zero-LLM deterministic generation), zero diagnostics on `ty check src/`, 100% clean formatting and linting via `ruff`

**Scale/Scope**: All OpenAPI 3.0 and 3.1 operations defining path parameters or schema-constrained JSON request bodies

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evaluation & Architectural Evidence |
|:---|:---:|:---|
| **I. Clear Idiomatic Code Over Abstractions** | **PASS** | Implemented as straightforward, modular transform functions in `negative_input.py` without unnecessary framework abstractions or metaclass indirection. |
| **II. Deterministic Artifact Generation (Zero-LLM)** | **PASS** | 404 and 400 mutations are 100% algorithmic and deterministic, inspecting OpenAPI parameter and schema types without LLM inference. |
| **III. Local-First Privacy & Compute** | **PASS** | Executes completely offline on the host machine; no specs, schemas, or fixtures sent over external networks. |
| **IV. Unified Gateway, Local-Default LLM & Disk Caching** | **PASS** | Happy-path generation continues through LiteLLM gateway with disk caching; negative cases derive post-generation without additional LLM calls. |
| **V. Strict Pydantic Validation & Single Retry** | **PASS** | All negative test cases are modeled as strict `GeneratedTestCase` Pydantic models with explicit `test_type` and operation traceability. |
| **VI. Comprehensive Testing** | **PASS** | Dedicated unit test suites (`test_negative_input.py`, `test_negative_input_export.py`), extended Hypothesis property strategies, golden fixture reconciliation, and quickstart validation. |

*Quality Gates:*
- Static Type Checking: `uv run ty check src/` must produce 0 diagnostics.
- Linter & Formatter: `uv run ruff check .` and `uv run ruff format --check .` must pass clean.
- Pre-commit: `uv run pre-commit run --all-files` must pass all hooks.
- Test Suite: `uv run pytest` must pass 100% of tests.

---

## Project Structure

### Documentation (this feature)

```text
specs/008-negative-input-tests/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this document)
├── research.md          # Phase 0 research findings and technical decisions
├── data-model.md        # Phase 1 data models, mutator interfaces, and state diagrams
├── quickstart.md        # Phase 1 runnable validation scenarios
├── contracts/           # Phase 1 interface specifications
│   ├── cli-contract.md     # CLI options and JSONL output schema
│   └── export-contract.md  # Postman and REST Client export schemas
└── checklists/
    └── requirements.md  # Specification quality checklist
```

### Source Code Modifications

```text
src/specprobe/
├── cli.py                        # Add --not-found/--no-not-found & --invalid-input/--no-invalid-input
├── generator/
│   ├── models.py                 # Extend TestType with negative_not_found & negative_invalid_input
│   ├── negative_input.py         # NEW: PathParameterMutator, RequestBodyMutator, generation logic
│   └── engine.py                 # Pass not_found & invalid_input into generate_batch
└── exporter/
    ├── postman.py                # Serialize 404 & 400 items, assertions, keep variable parameterization
    └── http_client.py            # Serialize 404 & 400 blocks, comments, keep variable parameterization

tests/
├── unit/
│   ├── generator/
│   │   └── test_negative_input.py          # NEW: Unit tests for 404 & 400 parameter/body mutation
│   ├── exporter/
│   │   └── test_negative_input_export.py   # NEW: Unit tests for Postman & HTTP export of 404/400
│   ├── test_exporter_postman.py            # Update Hypothesis strategies for new TestType values
│   └── test_exporter_http.py               # Update Hypothesis strategies for new TestType values
├── integration/
│   ├── test_generate_cli.py                # Verify CLI flags (--no-not-found, --no-invalid-input)
│   └── test_export_golden.py               # Reconcile golden regression fixtures for new default negative cases
└── fixtures/golden/                        # Updated golden test case files
```

**Structure Decision**: Standard single-project SpecProbe package architecture. The new negative mutation logic is encapsulated in `src/specprobe/generator/negative_input.py`, directly paralleling `src/specprobe/generator/negative_auth.py` from Feature 007.

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No constitution violations. All architecture adheres strictly to core principles.*
