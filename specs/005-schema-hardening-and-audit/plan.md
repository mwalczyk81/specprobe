# Implementation Plan: Schema Hardening & Artifact Audit

**Branch**: `005-schema-hardening-and-audit` | **Date**: 2026-09-20 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/005-schema-hardening-and-audit/spec.md)

**Input**: Feature specification from `specs/005-schema-hardening-and-audit/spec.md`

---

## Summary

This feature hardens API test case generation and export to guarantee valid JSON Schema Draft 7 contracts, and introduces an audit capability for spec-vs-artifact gap analysis:

1. **Part A (Schema Hardening)**: Enforce JSON Schema Draft 7 validation on `GeneratedTestCase.response.schema_shape` via `jsonschema.Draft7Validator.check_schema()` inside a Pydantic `@field_validator`. Invalid schemas or unresolvable `$ref` pointers trigger the existing single self-correcting retry loop with diagnostic error feedback. Upgrade the Postman exporter to emit `pm.response.to.have.jsonSchema(schema)` assertions and the REST Client exporter to emit `# Expected Schema: <type> (properties: ...)` signature comments. Update golden fixtures to maintain byte-identical determinism.
2. **Part B (Artifact Audit)**: Add `specprobe audit [ARTIFACT_FILE]` to evaluate test artifacts (Postman Collection JSON or `.http` files) against an API specification. The audit uses a hybrid pipeline: deterministic matching and structural diff (missing operations, unexercised status codes, omitted parameters) with zero LLM calls, paired with per-operation LLM critique of assertion depth and semantic edge cases via `prompts/audit.md` and the LiteLLM gateway with local LM Studio default and disk caching. Stream findings as `OperationCritique` JSONL on `stdout` and render optional `--summary` metrics on `stderr`.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Click, Rich, Pydantic (v2), LiteLLM, FastEmbed, Qdrant Client, jsonschema, prance, pyyaml

**Storage**: Local filesystem (`.specprobe/cache/audit` for LLM disk cache, `.specprobe/index` for Qdrant vector database)

**Testing**: pytest, hypothesis, offline disk cache fixtures, byte-identical golden regression fixtures

**Target Platform**: Cross-platform CLI (Windows, macOS, Linux)

**Project Type**: CLI tool and developer library (`specprobe`)

**Performance Goals**:
- Schema validation overhead < 5ms per test case
- Deterministic artifact parsing and structural diff < 200ms for 100 operations
- End-to-end audit execution with cached/local models < 30s for 50 operations

**Constraints**:
- Constitution Principle II: Postman/HTTP artifact parsing, path matching, and structural gap detection MUST be 100% deterministic with zero LLM calls
- Constitution Principle IV: All LLM critiques route through LiteLLM, default to local LM Studio, and cache to disk keyed on SHA-256 hash
- Constitution Principle V: Strict Pydantic model validation with single retry and explicit operation traceability
- Constitution Principle VI: 100% offline pytest execution with zero live network calls in standard CI test suites

**Scale/Scope**: OpenAPI 3.0/3.1 specifications up to 1,000 operations; Postman Collections v2.1 and RFC 7230 `.http` files

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Rule | Status | Evaluation & Evidence |
|---|---|---|
| **I. Clear Idiomatic Code Over Abstractions** | **PASS** | Straightforward, standard Python 3.11+ functions, Pydantic models, and Click commands. No speculative abstractions, inheritance towers, or dynamic metaclasses. |
| **II. Deterministic Artifact Generation (Zero-LLM)** | **PASS** | Postman and `.http` exporters remain 100% deterministic. Test artifact parsing (`ArtifactTestItem`) and structural gap detection (missing operations, unexercised status codes, unexercised parameters) are 100% algorithmic with zero LLM calls. |
| **III. Local-First Privacy & Compute** | **PASS** | Specification indexing and search continue to execute fully locally. Audit commands support local Qdrant indices and local YAML/JSON specifications. |
| **IV. Unified Gateway, Local-Default LLM & Disk Caching** | **PASS** | Per-operation LLM critique routes strictly through LiteLLM (`litellm`), defaults to local LM Studio, and caches all responses to `.specprobe/cache/audit` keyed on SHA-256 prompt hash. |
| **V. Strict Pydantic Validation, Single Retry & Traceability** | **PASS** | `ResponseAssertion.schema_shape` validated via Draft 7 meta-schema inside Pydantic validator, triggering the existing single self-correcting retry. Audit models (`CoverageGap`, `OperationCritique`, `AuditReport`) strictly validated through Pydantic. All audit findings explicitly link to `operation_id`. |
| **VI. Comprehensive Testing** | **PASS** | Dedicated unit tests for schema validator, updated Postman/HTTP exporters, artifact parsers, matchers, and analyzers. Offline integration tests with mocked/cached LLM replay fixtures. Golden fixtures updated for byte-identical determinism. |
| **Tooling: Static Typing & Hygiene** | **PASS** | Fully typed for `ty check src/`. Pre-commit hooks active (Ruff, formatting, hygiene, markdownlint-cli2). |

*Constitution Gate Status*: **ALL GATES PASS**. No exceptions or complexity tracking entries required.

---

## Project Structure

### Documentation (this feature)

```text
specs/005-schema-hardening-and-audit/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output: decisions, rationale, alternatives
├── data-model.md        # Phase 1 output: Pydantic schemas, entities, mappings
├── contracts/           # Phase 1 output: CLI interface contracts
│   └── cli-audit.md     # Command-line contract for `specprobe audit`
├── quickstart.md        # Phase 1 output: step-by-step validation scenarios
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/specprobe/
├── audit/                          # [NEW] Test artifact audit and gap analysis
│   ├── __init__.py
│   ├── analyzer.py                 # Structural diff + critique prompt assembly
│   ├── engine.py                   # Audit orchestration, caching & JSONL streaming
│   ├── matcher.py                  # Method & path template matching algorithms
│   ├── models.py                   # Pydantic domain models for audit findings
│   └── parser.py                   # Deterministic Postman v2.1 & .http parsers
├── exporter/
│   ├── http_client.py              # [UPDATED] Emits # Expected Schema: signature
│   ├── postman.py                  # [UPDATED] Emits pm.response.to.have.jsonSchema
│   └── utils.py                    # [UPDATED] Helper for schema signature formatting
├── generator/
│   ├── engine.py                   # Existing single-retry generation engine
│   └── models.py                   # [UPDATED] ResponseAssertion Draft 7 validator
├── cli.py                          # [UPDATED] Registers `audit` command group
└── ...

prompts/
├── generate.md                     # [UPDATED] Explicit Draft 7 JSON Schema requirement
└── audit.md                        # [NEW] Per-operation assertion critique prompt

tests/
├── fixtures/
│   ├── audit_postman_collection.json # Sample Postman artifact with known gaps
│   ├── audit_sample_requests.http    # Sample .http artifact with known gaps
│   └── golden/                     # [UPDATED] Golden test fixtures for exporter
├── unit/
│   ├── test_audit_analyzer.py      # Tests for deterministic gap detection
│   ├── test_audit_matcher.py       # Tests for path/method normalization
│   ├── test_audit_parser.py        # Tests for Postman and .http parsers
│   ├── test_exporter_http.py       # [UPDATED] Tests for # Expected Schema: comment
│   ├── test_exporter_postman.py    # [UPDATED] Tests for pm.response.to.have.jsonSchema
│   └── test_schema_hardening.py    # [NEW] Tests for Draft 7 validation & retry
└── integration/
    └── test_cli_audit.py           # [NEW] Integration tests for `specprobe audit` CLI
```

**Structure Decision**:
- Core generator models are updated in-place at `src/specprobe/generator/models.py`.
- Exporter improvements are updated in-place at `src/specprobe/exporter/postman.py`, `http_client.py`, and `utils.py`.
- All audit capabilities reside in a cohesive new package `src/specprobe/audit/`, mirroring the modular pattern established by `chunk/`, `index/`, `search/`, `generator/`, and `exporter/`.

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations. All principles and constraints are strictly satisfied.*
