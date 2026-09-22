# Implementation Plan: Environment File Export for Postman and REST Client

**Branch**: `010-env-file-export` | **Date**: 2026-09-21 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/010-env-file-export/spec.md)

**Input**: Feature specification from [`specs/010-env-file-export/spec.md`](file:///C:/Users/mwalc/source/repos/specprobe/specs/010-env-file-export/spec.md)

---

## Summary

Decouple target server URLs and security credentials from exported Postman collection (`collection.json`) and VS Code REST Client (`requests.http`) files by emitting native environment files. The export command supports multiple named environments via repeatable `--env <name>=<url>` CLI options and an optional `--env-file <path>` configuration file (supporting JSON and YAML). The primary collection and `.http` files drop baked-in values and header declarations, referencing `{{baseUrl}}` and `{{schemeName}}` dynamically. Postman exports emit native `<env>.postman_environment.json` files; REST Client exports emit `http-client.env.json`. Supplying legacy `--base-url <url>` without explicit environment flags acts as shorthand for `--env default=<url>`.

---

## Technical Context

**Language/Version**: Python >= 3.11 (utilizing modern type annotations, built-in string/path utilities, and match/case where appropriate).

**Primary Dependencies**: `click>=8.1.0` (CLI flags, validation, error messages), `pydantic>=2.0.0` (schema validation for environment configurations), `pyyaml>=6.0.0` (YAML `--env-file` parsing), standard library `uuid`, `json`, `pathlib`.

**Storage**: Local filesystem files (`collection.json`, `requests.http`, `*.postman_environment.json`, `http-client.env.json`).

**Testing**: `pytest>=8.0.0` (unit tests for models/generators, integration tests for CLI export).

**Target Platform**: Cross-platform (Windows, Linux, macOS). File paths normalized for cross-platform execution.

**Project Type**: Developer CLI tool and Python library.

**Performance Goals**: Sub-second execution (< 500ms) for exporting hundreds of test cases across multiple environments.

**Constraints**:
- Constitution Principle II: 100% deterministic, zero-LLM generation.
- Constitution Principle VI: Every feature ships with comprehensive tests; all test cases pass without live LLM or external network access.
- Code quality gates: `ruff check`, `ruff format --check`, `ty check src/`, `pre-commit run --all-files`, `pytest`.

**Scale/Scope**: Exporting 1 to 20+ environments across Postman and REST Client in a single invocation.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Constitution Gate | Requirement | Status | Verification Plan |
|-------------------|-------------|--------|-------------------|
| **Principle I: Clear Idiomatic Code** | No unnecessary abstractions, speculative framework layers, or generic indirection. | **PASS** | Simple dataclasses/Pydantic models, direct file writes, standard Python dictionary manipulation. |
| **Principle II: Zero-LLM Determinism** | Export generation MUST be fully deterministic and NEVER invoke an LLM. | **PASS** | Entire export pipeline is pure Python algorithms, standard JSON serialization, and deterministic UUIDv5 generation. |
| **Principle III: Local-First Privacy** | No external cloud network calls or sensitive schema leakage. | **PASS** | All operations execute strictly on the local filesystem. |
| **Principle V: Pydantic Validation** | Configuration and environment data structures validated via Pydantic. | **PASS** | `ExportEnvironment`, `ExportConfig`, and environment schemas defined with strict Pydantic models. |
| **Principle VI: Comprehensive Testing** | 100% automated test coverage with `pytest`. | **PASS** | Unit tests for environment serializers, CLI parsing tests, backward-compatibility tests, and golden file validations. |
| **Quality Gate: Static Typing (`ty`)** | `uv run ty check src/` must pass with zero diagnostics. | **PASS** | Explicit type annotations across all new models, functions, and CLI callbacks. |
| **Quality Gate: Lint & Formatting (`ruff`)**| `uv run ruff check .` and `uv run ruff format --check .` must pass cleanly. | **PASS** | Ruff standards verified during development and pre-commit hooks. |

---

## Project Structure

### Documentation (this feature)

```text
specs/010-env-file-export/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output: decisions, schema details, format specs
├── data-model.md        # Phase 1 output: ExportEnvironment, Postman & REST Client models
├── quickstart.md        # Phase 1 output: validation scenarios & verification commands
├── contracts/           # Phase 1 output: interface & schema contracts
│   ├── cli-contract.md
│   └── environment-schemas.md
├── checklists/
│   └── requirements.md  # Quality validation checklist
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/specprobe/
├── cli.py                     # Add --env, --env-file options, input validation, output checks
└── exporter/
    ├── __init__.py            # Expose public exports
    ├── models.py              # ExportEnvironment, updated ExportConfig
    ├── postman.py             # generate_postman_environment, variable suppression in collection
    ├── http_client.py         # generate_rest_client_environments, header omission
    ├── engine.py              # Orchestrate environment file serialization (single & dual format)
    ├── security.py            # Existing SecurityResolver (reuse default_placeholder)
    └── utils.py               # File sanitization & path helpers

tests/
├── unit/
│   ├── test_exporter_models.py       # Unit tests for ExportEnvironment & ExportConfig
│   ├── test_exporter_postman.py      # Unit tests for Postman environment generation
│   ├── test_exporter_http_client.py  # Unit tests for http-client.env.json generation
│   └── test_exporter_engine.py       # Unit tests for batch export with environments
└── integration/
    └── test_cli_export.py            # CLI integration tests for --env, --env-file, --base-url compat
```

**Structure Decision**: Enhances existing `specprobe.exporter` package and `specprobe.cli` without adding new top-level directories or breaking public interfaces.

---

## Complexity Tracking

> **No constitutional violations detected. Table left empty.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *None* | N/A | N/A |
