# Implementation Plan: Minimal Local Mock Server (`specprobe mock`)

**Branch**: `011-mock-server` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/011-mock-server/spec.md)

**Input**: Feature specification from [`specs/011-mock-server/spec.md`](file:///C:/Users/mwalc/source/repos/specprobe/specs/011-mock-server/spec.md)

---

## Summary

Implement the `specprobe mock` CLI command that reads `GeneratedTestCase` records from a JSONL file or standard input (`-`), registers positive test fixtures (`test_type == "positive"` or 2xx), and launches a local HTTP mock server. The server matches incoming requests by HTTP method and normalized path (with path parameters resolved and trailing slashes stripped, ignoring extra headers, query strings, and body payloads), serving canned HTTP status codes, headers, and deterministic response bodies (either explicit or synthesized from `response.schema_shape` conforming to JSON Schema Draft 7). Built on Python's standard library `http.server.ThreadingHTTPServer` to guarantee zero heavy dependencies (Constitution Principle I) and 100% deterministic zero-LLM operation (Principle II). Unknown routes return HTTP 404 with structured JSON diagnostics listing available routes; method mismatches return HTTP 405. The server runs interactively in the foreground with startup route banners and single-line access logs, shutting down cleanly on SIGINT/Ctrl+C.

---

## Technical Context

**Language/Version**: Python >= 3.11 (modern type hints, structural pattern matching, built-in string/path utilities).

**Primary Dependencies**:
- `click>=8.1.0` (CLI arguments, validation, error handling)
- `rich>=13.0.0` (startup banners, formatted route tables, colorized access logging)
- `pydantic>=2.0.0` (data modeling for `MockRoute`, `MockResponse`, `MockServerConfig`)
- `jsonschema>=4.20.0` (schema validation guarantees)
- Standard library: `http.server`, `socketserver`, `json`, `signal`, `urllib.parse`, `threading`, `time`, `datetime`.

**Storage**: In-memory route dictionary keyed on `(normalized_method, normalized_path)`.

**Testing**: `pytest>=8.0.0`, `hypothesis>=6.0.0`, and standard library `urllib.request` / `http.client` (for local socket verification).

**Target Platform**: Cross-platform (Windows, Linux, macOS). Native signal handling for `SIGINT`/`SIGTERM` with clean socket release across platforms.

**Project Type**: Developer CLI tool and Python module.

**Performance Goals**:
- Startup and route population: < 1 second for 1,000 endpoint fixtures.
- Response latency: < 10 milliseconds under local execution.
- Graceful shutdown: < 500 milliseconds on SIGINT/Ctrl+C.

**Constraints**:
- **Constitution Principle I (Clear Idiomatic Code Over Abstractions)**: Standard library `http.server.ThreadingHTTPServer`; no external web framework dependencies (`starlette`, `fastapi`, `flask`, `uvicorn`).
- **Constitution Principle II (Zero-LLM Determinism)**: 100% deterministic, zero-LLM response serving and schema payload synthesis.
- **Constitution Principle VI (Comprehensive Testing)**: 100% automated test coverage in `pytest` with zero external network or cloud calls.
- **Quality Gates**: Zero diagnostics on `uv run ty check src/`, clean pass on `uv run ruff check .` and `uv run ruff format --check .`, and all pre-commit hooks passed.

**Scale/Scope**: Serving up to 1,000+ mock routes concurrently with multi-threaded request dispatch.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Constitution Gate | Requirement | Status | Verification Plan |
|-------------------|-------------|--------|-------------------|
| **Principle I: Clear Idiomatic Code** | No unnecessary abstractions, speculative frameworks, or deep inheritance hierarchies. | **PASS** | Standard library `http.server.ThreadingHTTPServer` + simple dictionary route lookup; zero heavy dependencies. |
| **Principle II: Zero-LLM Determinism** | Canned mock serving MUST be fully deterministic and NEVER invoke an LLM. | **PASS** | Entire serving pipeline is pure deterministic Python dictionary lookups and rule-based JSON Schema Draft 7 payload synthesis. |
| **Principle III: Local-First Privacy** | No external cloud network calls or schema leakage. | **PASS** | Binds exclusively to local interface (`127.0.0.1` / `localhost` by default); zero outbound sockets. |
| **Principle V: Pydantic Validation** | Models and configurations validated via Pydantic. | **PASS** | `MockRoute`, `MockResponse`, and `MockServerConfig` defined with strict Pydantic models. |
| **Principle VI: Comprehensive Testing** | 100% automated test coverage with `pytest`. | **PASS** | Unit tests for models, schema synthesis, router, and server lifecycle; CLI integration tests against live local sockets. |
| **Quality Gate: Static Typing (`ty`)** | `uv run ty check src/` must pass with zero diagnostics. | **PASS** | Full type annotations across all new modules in `src/specprobe/mock/` and CLI callbacks. |
| **Quality Gate: Lint & Formatting (`ruff`)** | `uv run ruff check .` and `uv run ruff format --check .` must pass cleanly. | **PASS** | Verified during development and pre-commit hook runs. |

---

## Project Structure

### Documentation (this feature)

```text
specs/011-mock-server/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output: server runtime, router design, synthesis
├── data-model.md        # Phase 1 output: MockRoute, MockResponse, MockServerConfig
├── quickstart.md        # Phase 1 output: verification scenarios & run commands
├── contracts/           # Phase 1 output: interface & protocol contracts
│   ├── cli-contract.md
│   └── http-mock-contract.md
├── checklists/
│   └── requirements.md  # Quality validation checklist
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/specprobe/
├── cli.py                     # Add `specprobe mock` Click command
└── mock/
    ├── __init__.py            # Public package exports (MockServer, MockRouter, MockRoute, MockResponse)
    ├── models.py              # Pydantic models: MockRoute, MockResponse, MockServerConfig, MockAccessLogEntry
    ├── synth.py               # Deterministic JSON Schema Draft 7 mock payload synthesizer
    ├── router.py              # MockRouter: route registration, path resolution, trailing slash strip, 404/405 builder
    └── server.py              # MockServer: ThreadingHTTPServer, BaseHTTPRequestHandler, lifecycle, rich logs

tests/
├── unit/
│   ├── test_mock_models.py    # Unit tests for MockRoute, MockResponse, MockServerConfig
│   ├── test_mock_synth.py     # Unit tests for synthesize_sample_from_schema
│   ├── test_mock_router.py    # Unit tests for MockRouter (matching, normalization, 404/405 diagnostics)
│   └── test_mock_server.py    # Unit tests for MockServer (socket binding, threading, lifecycle, shutdown)
└── integration/
    └── test_cli_mock.py       # Integration tests for `specprobe mock` CLI (file, stdin, port/host, error cases)
```

**Structure Decision**: Introduces a dedicated `specprobe.mock` package consistent with other core modules (`specprobe.chunk`, `specprobe.indexer`, `specprobe.generator`, `specprobe.exporter`, `specprobe.audit`), maintaining high cohesion and separation of concerns.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *None* | No constitutional violations or unwarranted complexity introduced. | Standard library `http.server` selected over third-party frameworks. |
