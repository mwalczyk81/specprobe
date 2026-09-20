# Implementation Plan: Deterministic Export for Runnable Test Artifacts (Postman & REST Client)

**Branch**: `004-export-test-artifacts` | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-export-test-artifacts/spec.md`

---

## Summary

Implement the `specprobe export` CLI command to deterministically transform `GeneratedTestCase` JSONL records into runnable test artifacts: Postman Collection v2.1.0 JSON (with folder tag grouping and embedded `pm.test` scripts) and VS Code REST Client `.http` files (with `###` request blocks and metadata documentation). In strict adherence to Constitution Principle II, artifact generation is 100% deterministic, zero-LLM, zero-network, and produces byte-identical output across repeated runs.

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Click (CLI framework), Pydantic v2 (domain validation & schemas), standard library `json`, `urllib.parse`, `uuid`
**Storage**: Local filesystem (`collection.json`, `requests.http`) and standard output (`stdout`)
**Testing**: pytest (unit tests, integration tests, golden-file structural regression tests)
**Target Platform**: Cross-platform (Windows, Linux, macOS)
**Project Type**: CLI command (`specprobe export`) & export engine
**Performance Goals**: < 200ms latency to export 50 test cases to both formats
**Constraints**: 100% deterministic byte-for-byte reproducibility across runs; Zero-LLM (Constitution Principle II); 100% offline with zero outbound network calls (Principle III)
**Scale/Scope**: Batches from 0 up to 1,000+ operations; supports single format to `stdout` or dual format to disk

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance Assessment | Gate Status |
|---|---|---|
| **I. Clear Idiomatic Code Over Abstractions** | Direct formatter functions and simple Pydantic models in `src/specprobe/exporter/`. No complex abstract visitor hierarchies or speculative template engines. | **PASS** |
| **II. Deterministic Artifact Generation (Zero-LLM)** | The entire export pipeline is pure Python parsing and string/JSON serialization. Strictly zero LLM invocations and zero probabilistic drift. Same inputs produce byte-identical output every time. | **PASS** |
| **III. Local-First Privacy & Compute** | Exporters execute 100% locally on the host machine. Zero network transmissions or remote API calls. | **PASS** |
| **IV. Unified Gateway, Local-Default LLM & Disk Caching** | Not applicable — no LLM calls are executed in this feature. | **PASS (N/A)** |
| **V. Strict Pydantic Validation & Operation Traceability** | Input lines are validated against `GeneratedTestCase`. Every exported request explicitly embeds `operation_id` in request descriptions and REST Client headers. | **PASS** |
| **VI. Comprehensive Testing** | Shipping with unit tests, integration tests, and golden-file structural regression tests comparing output against static reference fixtures for OpenAPI specs. | **PASS** |

---

## Project Structure

### Documentation (this feature)

```text
specs/004-export-test-artifacts/
├── plan.md              # Implementation plan
├── research.md          # Phase 0 research decisions
├── data-model.md        # Data models & Postman/HTTP schemas
├── quickstart.md        # Validation scenarios guide
├── checklists/
│   └── requirements.md  # Quality checklist
├── contracts/
│   └── cli-export.md    # CLI specification & interface contract
└── tasks.md             # Tasks (generated via /speckit-tasks)
```

### Source Code Layout

```text
src/specprobe/
├── exporter/
│   ├── __init__.py      # Package export definitions
│   ├── models.py        # ExportFormat, ExportConfig models
│   ├── postman.py       # Postman Collection v2.1.0 serializer
│   ├── http_client.py   # VS Code REST Client (.http) serializer
│   └── engine.py        # Stream parser & batch export orchestrator
├── cli.py               # Adds 'export' click command
└── ...

tests/
├── fixtures/
│   ├── generated_tests.jsonl      # Valid test case fixture
│   └── golden/                    # Static reference golden files
│       ├── petstore.postman.json  # Reference Postman collection
│       └── petstore.requests.http # Reference REST Client file
├── unit/
│   ├── test_exporter_postman.py   # Unit tests for Postman serializer
│   └── test_exporter_http.py      # Unit tests for .http serializer
└── integration/
    ├── test_export_cli.py         # CLI invocation & options tests
    └── test_export_golden.py      # Exact byte/structural regression tests
```

**Structure Decision**:
Keep export logic modularized in `src/specprobe/exporter/` with clean separation between the Postman formatter (`postman.py`), REST Client formatter (`http_client.py`), and batch orchestrator (`engine.py`), wired directly into `src/specprobe/cli.py`.

---

## Complexity Tracking

*No constitutional violations; no complex abstractions required.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| None | N/A | N/A |
