# Implementation Plan: Security-Scheme-Aware Authentication

**Branch**: `006-security-scheme-auth` | **Date**: 2026-09-20 | **Spec**: [specs/006-security-scheme-auth/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/006-security-scheme-auth/spec.md)

**Input**: Feature specification from `specs/006-security-scheme-auth/spec.md`

---

## Summary

This feature enhances SpecProbe to recognize, propagate, and export OpenAPI security requirements end-to-end (`chunk` -> `search` -> `generate` -> `export`). 

Currently, `specprobe chunk` extracts `metadata.security` for each operation, but `components.securitySchemes` is dropped, and downstream commands (`generate`, `export`) omit authentication credentials entirely. When exported Postman collections or `.http` files are executed against real protected APIs, every request fails with HTTP 401 Unauthorized or 403 Forbidden.

The implementation:
1. **Preserves Security Scheme Definitions**: Updates `OperationExtractor` to prune and preserve referenced `components.securitySchemes` in `OperationChunk.components`.
2. **Guides Test Generation**: Informs `PromptBuilder` of active security requirements so generated request fixtures include appropriate credential placeholders (`Authorization: Bearer <token>`, `<api_key>`, etc.), carrying `security` and `security_schemes` metadata in `GeneratedTestCase`.
3. **Encapsulates Resolution Logic**: Introduces `specprobe.exporter.security` to provide deterministic multi-scheme priority selection (`Bearer/OAuth2` > `API Key header` > `API Key query` > `Basic`), variable name sanitization, and fallback heuristics for unresolvable schemes.
4. **Parameterizes Exporters (Zero-LLM)**:
   - **Postman**: Declares collection-level variables (`{{<sanitizedSchemeName>}}`) with placeholder default values in the root `variable` array and references them across requests, annotating request descriptions with security schemes, scopes, and alternatives.
   - **VS Code REST Client**: Declares top-level `@<sanitizedSchemeName> = <placeholder>` file variables directly below `@baseUrl` and references them in request blocks, annotating requests with `# Security: ...`, `# Scopes: ...`, and `# Alternatives: ...`.

---

## Technical Context

**Language/Version**: Python >= 3.11  
**Primary Dependencies**: Click, Rich, Pydantic, LiteLLM, jsonschema, pytest, hypothesis, uv, ruff, ty  
**Storage**: Local file system (JSONL test cases, Postman JSON collections, `.http` documents)  
**Testing**: pytest, hypothesis (unit tests, integration pipeline tests, byte-identical golden regression tests)  
**Target Platform**: Cross-platform (Windows, Linux, macOS)  
**Project Type**: CLI tool & library (`specprobe chunk`, `specprobe search`, `specprobe generate`, `specprobe export`)  
**Performance Goals**: < 50ms per operation chunking/export; byte-for-byte deterministic reproducibility  
**Constraints**: Fully offline-capable; zero external network requests during export (Constitution Principle II); strict Pydantic validation (Principle V); zero static type diagnostics (`ty check src/`)  
**Scale/Scope**: Operations spanning diverse security schemes (Bearer, Basic, API Key in header/query, OAuth2 with scopes, optional security, compound security)  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Status | Verification & Justification |
|---|---|---|---|
| **I. Clear Idiomatic Code** | Straightforward Python 3.11+, no unnecessary abstractions | **PASS** | Centralizes security resolution into a single straightforward helper module (`src/specprobe/exporter/security.py`) reused by both exporters. No deep inheritance or speculative wrapper layers. |
| **II. Deterministic Artifact Generation (Zero-LLM)** | Postman and `.http` exports MUST NEVER call an LLM; 100% deterministic | **PASS** | Exporter resolution, variable parameterization, and comment formatting execute purely in deterministic Python. Zero LLMs invoked during export. |
| **III. Local-First Privacy & Compute** | Local embeddings, no external cloud queries | **PASS** | Auth placeholders and spec parsing execute purely locally without outbound network calls. |
| **IV. Unified Gateway & Disk Caching** | All LLM calls route through LiteLLM with disk caching | **PASS** | Prompt enhancements route through `PromptBuilder` and existing `LLMGateway`; caching remains keyed on cryptographic hashes. |
| **V. Strict Pydantic Validation & Traceability** | Strict Pydantic models, single retry, operation traceability | **PASS** | `GeneratedTestCase` and `OperationChunk` validate all fields strictly; `operation_id` traceability and security scheme bindings preserved. |
| **VI. Comprehensive Testing** | Every feature ships with automated tests; golden regressions | **PASS** | Unit tests cover all scheme types, fallbacks, and multi-scheme edge cases; golden-file regression tests verify byte-identical output. |

*Post-Design Evaluation*: All gates **PASS**. No constitutional violations exist.

---

## Project Structure

### Documentation (this feature)

```text
specs/006-security-scheme-auth/
├── plan.md              # This implementation plan
├── research.md          # Phase 0 architectural decisions and rationale
├── data-model.md        # Phase 1 entities, relationships, and transformation lifecycle
├── quickstart.md        # Phase 1 end-to-end runnable validation scenarios
├── contracts/           # Phase 1 contract specifications
│   ├── generated-test-case.contract.md
│   ├── postman-collection.contract.md
│   └── rest-client.contract.md
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code Layout

```text
src/specprobe/
├── chunker/
│   ├── extractor.py     # Extract and prune components.securitySchemes into chunks
│   └── models.py        # ChunkMetadata and OperationChunk definitions
├── generator/
│   ├── models.py        # GeneratedTestCase with security and security_schemes
│   ├── prompt.py        # PromptBuilder formatting security requirements into prompt
│   └── engine.py        # GenerationEngine propagating security metadata to test case
└── exporter/
    ├── security.py      # NEW: Shared resolver, sanitization, priority & placeholder formatting
    ├── postman.py       # Postman Collection serializer with collection variables
    ├── http_client.py   # REST Client (.http) serializer with file variables
    └── utils.py         # Formatting utilities

tests/
├── unit/
│   ├── test_security_resolver.py   # Unit tests for priority, sanitization, fallbacks
│   ├── test_security_chunker.py    # Unit tests for chunker security scheme extraction
│   ├── test_security_generator.py  # Unit tests for generator security prompt & model
│   ├── test_security_postman.py    # Unit tests for Postman collection variable export
│   └── test_security_http.py       # Unit tests for REST Client file variable export
├── integration/
│   └── test_security_pipeline.py   # End-to-end pipeline: chunk -> generate -> export
└── fixtures/
    ├── specs/                      # OpenAPI test fixtures with various securitySchemes
    └── golden/                     # Byte-identical Postman and .http golden fixtures
```

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No constitutional violations. Table is clean.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| None | N/A | N/A |
