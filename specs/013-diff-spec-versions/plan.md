# Implementation Plan: OpenAPI Structural Diff (`specprobe diff`)

**Branch**: `013-diff-spec-versions` | **Date**: 2026-10-03 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)

**Input**: Feature specification from [`specs/013-diff-spec-versions/spec.md`](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)

---

## Summary

Implement the `specprobe diff <old_spec> <new_spec>` CLI command to deterministically detect and report changes between two OpenAPI 3.0/3.1 specification versions at the operation and schema levels. The feature operates 100% offline with zero LLMs (Constitution Principle II), reusing the existing chunker's parsing and normalization logic (`load_openapi_spec` and `OperationExtractor`) rather than implementing redundant OpenAPI loading. Operations are keyed by normalized uppercase HTTP method and structurally normalized URL path template (normalizing parameter tokens like `{petId}` and `{id}` to positional `{}` to prevent false removals on parameter renames, and disregarding `operationId` modifications). In v1, the engine detects operation-level changes (operations added as non-breaking, operations removed as breaking) and five specific mechanical breaking changes: (1) request body or parameter schema gains a new required field, (2) response schema loses a previously declared property, (3) existing 2xx success response status code is removed, (4) field data type changes, and (5) enum definition loses an allowable value. Results stream as JSONL to `stdout`, an optional `--summary` flag prints a Rich summary table to `stderr`, and the process returns exit code `0` on clean/non-breaking runs, `1` on breaking changes, and `2` on execution/parsing errors.

---

## Technical Context

**Language/Version**: Python >= 3.11 (modern structural pattern matching, union types, built-in string/collection utilities).

**Primary Dependencies**:
- `click>=8.1.0` (CLI argument parsing, validation, and exit code handling)
- `rich>=13.0.0` (human-readable table rendering to `stderr` for `--summary`)
- `pydantic>=2.0.0` (data modeling for `DiffChangeRecord`, `ChangeType`, `DiffSummary`)
- Standard library: `sys`, `json`, `pathlib`, `typing`, `collections`.

**Storage**: In-memory dictionary indexing of operations and schemas; zero external database or disk persistence required.

**Testing**: `pytest>=8.0.0`, `hypothesis>=6.0.0` (unit and integration tests with synthetic specification fixtures).

**Target Platform**: Cross-platform (Windows, Linux, macOS).

**Project Type**: Developer CLI tool and Python module.

**Performance Goals**:
- Comparison of two 1,000-operation OpenAPI specifications completes in under 2 seconds.
- Memory overhead < 50MB for standard specs.

**Constraints**:
- **Constitution Principle I (Clear Idiomatic Code Over Abstractions)**: Straightforward comparison functions, explicit dictionary lookups, no bloated diff abstractions or generic AST frameworks.
- **Constitution Principle II (Zero-LLM Determinism)**: 100% deterministic, zero-LLM execution. Identical inputs yield identical outputs.
- **Constitution Principle VI (Comprehensive Testing)**: 100% automated test coverage in `pytest` with unit tests for each breaking change rule and end-to-end CLI integration tests.
- **Quality Gates**: Zero diagnostics on `uv run ty check src/`, clean pass on `uv run ruff check .` and `uv run ruff format --check .`, all pre-commit hooks passing.

**Scale/Scope**: Comparing OpenAPI 3.0 and 3.1 specifications of any size (up to thousands of operations).

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Constitution Gate | Requirement | Status | Verification Plan |
|---|---|---|---|
| **Principle I: Clear Idiomatic Code** | Prioritize clarity and idiomatic Python over unnecessary abstractions. Reintroduce logic only when duplication exists. | **PASS** | Reuses existing `load_openapi_spec` and `OperationExtractor`. Implementation structured as clean comparison engine functions without unnecessary layers. |
| **Principle II: Zero-LLM Determinism** | Diff generation MUST be fully deterministic and MUST NEVER invoke an LLM. | **PASS** | 100% algorithmic rules; zero LLM gateway dependencies or prompt calls. |
| **Principle III: Local-First Privacy** | No external network calls, cloud APIs, or spec data leakage. | **PASS** | Entire diff executes locally in-memory; zero network sockets or telemetry. |
| **Principle V: Pydantic Validation** | Models and records validated via Pydantic. | **PASS** | `DiffChangeRecord`, `ChangeType`, and `DiffSummary` defined as strict Pydantic models. |
| **Principle VI: Comprehensive Testing** | 100% automated test coverage with `pytest`. | **PASS** | Comprehensive unit test suite covering all five breaking change rules, operation addition/removal, parameter token renames, and CLI integration tests with stdout/stderr assertions. |
| **Quality Gate: Static Typing (`ty`)** | `uv run ty check src/` must pass with zero diagnostics. | **PASS** | Fully typed module signatures across `src/specprobe/diff/` and CLI callbacks. |
| **Quality Gate: Lint & Formatting (`ruff`)** | `uv run ruff check .` and `uv run ruff format --check .` must pass cleanly. | **PASS** | Continuous verification during development and pre-commit hook runs. |

---

## Project Structure

### Documentation (this feature)

```text
specs/013-diff-spec-versions/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output: chunker reuse, operation keying, breaking rules
├── data-model.md        # Phase 1 output: DiffChangeRecord, DiffSummary, ChangeType
├── quickstart.md        # Phase 1 output: runnable verification scenarios & commands
├── contracts/           # Phase 1 output: interface & protocol contracts
│   ├── cli-contract.md
│   └── diff-record-contract.md
├── checklists/
│   └── requirements.md  # Quality validation checklist
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/specprobe/
├── cli.py                     # Add `specprobe diff` Click command
└── diff/
    ├── __init__.py            # Public package exports (DiffEngine, DiffSummary, DiffChangeRecord, ChangeType)
    ├── models.py              # Pydantic models: DiffChangeRecord, ChangeType, DiffSummary
    ├── engine.py              # Core comparison engine: operation matching, schema traversal, 5 breaking rule evaluators
    └── formatter.py           # Output formatters: JSONL stdout streaming, Rich stderr summary table

tests/
├── unit/
│   ├── test_diff_models.py    # Unit tests for DiffChangeRecord, ChangeType, DiffSummary
│   └── test_diff_engine.py    # Unit tests for operation diffing, schema traversal, and breaking rules
└── integration/
    └── test_cli_diff.py       # Integration tests for `specprobe diff` CLI (stdout JSONL, stderr table, exit codes)
```

**Structure Decision**: Add dedicated module `src/specprobe/diff/` matching the established repository architecture (`chunker`, `indexer`, `generator`, `exporter`, `audit`, `mock`). CLI command `diff` wired cleanly into `src/specprobe/cli.py`.

---

## Complexity Tracking

*No constitutional violations. Zero unjustified abstractions.*
