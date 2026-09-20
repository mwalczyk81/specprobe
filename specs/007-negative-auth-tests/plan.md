# Implementation Plan: Negative Authentication Test Case Generation (401/403)

**Branch**: `007-negative-auth-tests` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-negative-auth-tests/spec.md`

## Summary

Extend `specprobe generate` and `specprobe export` to automatically produce and serialize negative authentication test cases (HTTP 401 Unauthorized for missing/omitted credentials and HTTP 403 Forbidden for invalid/corrupted credentials) for OpenAPI operations declaring security requirements. The generation is 100% deterministic (zero-LLM per Constitution Principle II), reusing the scheme resolution and metadata mechanisms from Feature 006 (`SecurityResolver` and `security_schemes`). Negative auth generation is enabled by default in `specprobe generate` with an opt-out `--no-negative-auth` flag, and exported as self-contained sibling test items in Postman and `.http` artifacts with status assertions.

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Click, Pydantic, LiteLLM, jsonschema, rich
**Storage**: In-memory transformation / JSONL stream / local filesystem export
**Testing**: pytest, hypothesis
**Target Platform**: Windows / Linux / macOS (offline-capable)
**Project Type**: CLI tool & Python library
**Performance Goals**: < 5ms per operation for negative test case derivation; 0 extra LLM calls or token overhead
**Constraints**: Fully deterministic/zero-LLM (Principle II), strict operation traceability (Principle V), zero static type diagnostics under `ty check src/`
**Scale/Scope**: Linear in-memory transformation over batch search results; consistent 1:1:1 test case pattern per secured operation (happy path, 401, 403)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Clear Idiomatic Code Over Abstractions)**:
  - *Check*: PASS. Negative auth mutation logic is housed in a clean, focused module `src/specprobe/generator/negative_auth.py` with standard type annotations, structural pattern matching, and explicit functions. No speculative abstraction layers.
- **Principle II (Deterministic Artifact Generation / Zero-LLM)**:
  - *Check*: PASS. Negative test cases derive 100% algorithmically in memory by stripping or corrupting credentials from the validated happy-path fixture. Zero probabilistic LLM calls, zero network calls, zero prompt tokens consumed.
- **Principle III (Local-First Privacy & Compute)**:
  - *Check*: PASS. Operates completely locally and offline without outbound network connections.
- **Principle IV (Unified Gateway, Local-Default LLM & Disk Caching)**:
  - *Check*: PASS. Happy-path test cases continue using the LiteLLM gateway and disk cache. Negative test cases bypass the gateway entirely.
- **Principle V (Strict Pydantic Validation & Operation Traceability)**:
  - *Check*: PASS. Every negative test case preserves the exact `operation_id` of the target operation and is validated through `GeneratedTestCase` with explicit `test_type: str`.
- **Principle VI (Comprehensive Testing)**:
  - *Check*: PASS. Feature includes unit tests for mutation rules, batch generation tests, CLI flag tests, and byte-for-byte golden file export regressions.
- **Tooling Constraints**:
  - *Check*: PASS. Managed with `uv`, linted/formatted with `ruff`, type-checked with `ty check src/` (zero diagnostics), and tested with `pytest`.

---

## Project Structure

### Documentation (this feature)

```text
specs/007-negative-auth-tests/
├── spec.md              # Feature specification with clarifications
├── plan.md              # This file (Implementation Plan)
├── research.md          # Phase 0 technical decisions
├── data-model.md        # Phase 1 data entities and mutation specs
├── quickstart.md        # Phase 1 runnable validation scenarios
├── contracts/           # Phase 1 interface and CLI contracts
│   └── cli.md           # CLI options and artifact output contracts
└── checklists/
    └── requirements.md  # Quality checklist
```

### Source Code (repository root)

```text
src/specprobe/
├── generator/
│   ├── models.py        # Add test_type: str = "positive" to GeneratedTestCase
│   ├── negative_auth.py # NEW: generate_negative_auth_test_cases() & mutation rules
│   └── engine.py        # Integrate negative test generation in generate_batch()
├── cli.py               # Add --negative-auth / --no-negative-auth option to generate_command
└── exporter/
    ├── postman.py       # Support [401]/[403] sibling items & inline invalid literals
    └── http_client.py   # Support # @name <op>_401/403 & inline invalid literals

tests/
├── unit/
│   ├── generator/
│   │   └── test_negative_auth.py  # NEW: Unit tests for negative credential mutations
│   └── exporter/
│       └── test_negative_export.py # NEW: Unit tests for negative export rendering
├── integration/
│   └── test_generate_cli.py       # NEW/UPDATED: CLI tests for default vs --no-negative-auth
└── fixtures/
    └── golden/                     # Golden fixtures for negative auth export verification
```

**Structure Decision**: Single Python project within standard `src/specprobe` package and `tests/` directory layout, adhering strictly to established repository patterns.

---

## Complexity Tracking

> *No constitution violations. Complexity tracking table left empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| *(None)* | — | — |
