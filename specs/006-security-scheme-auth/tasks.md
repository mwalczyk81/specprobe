# Implementation Tasks: Security-Scheme-Aware Authentication

**Feature Branch**: `006-security-scheme-auth`  
**Date**: 2026-09-20  
**Spec**: [specs/006-security-scheme-auth/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/006-security-scheme-auth/spec.md)  
**Plan**: [specs/006-security-scheme-auth/plan.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/006-security-scheme-auth/plan.md)  

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test fixtures and environment setup for security scheme authentication

- [x] T001 Create multi-scheme OpenAPI test fixture in `tests/fixtures/specs/security_schemes.json` covering HTTP Bearer, HTTP Basic, API Key (header), API Key (query), OAuth2 with scopes, optional security (`{}`), and compound security requirements
- [x] T002 [P] Create initial golden file regression directory structure for security exports in `tests/fixtures/golden/security/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and resolver infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 [P] Add optional backward-compatible security fields `security: list[dict[str, list[str]]] = Field(default_factory=list)` and `security_schemes: dict[str, Any] = Field(default_factory=dict)` to `GeneratedTestCase` in `src/specprobe/generator/models.py`
- [x] T004 Update `OperationChunk.components` docstrings and schema definition in `src/specprobe/chunker/models.py` to document `"securitySchemes"` preservation alongside `"schemas"`
- [x] T005 Implement `SecurityResolver` and `ResolvedCredential` in `src/specprobe/exporter/security.py` with name sanitization to `[a-zA-Z0-9_]`, priority order (`http` bearer / `oauth2` > `apiKey` header > `apiKey` query > `http` basic), compound requirement resolution, and deterministic substring fallback heuristics (`FR-005`, `FR-006`, `FR-011`, `FR-013`)
- [x] T006 [P] Create unit tests for `SecurityResolver` in `tests/unit/test_security_resolver.py` testing priority sorting, variable sanitization, compound requirements, optional `{}` detection, and unresolvable scheme fallback heuristics

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Security Credential Placeholders in Generated Test Cases (Priority: P1) 🎯 MVP

**Goal**: Chunker extracts and preserves `components.securitySchemes`; prompt builder instructs model on security requirements; generation engine preserves security metadata and ensures credential placeholders are present in request fixtures.

**Independent Test**: Chunk an operation with auth requirement and assert `OperationChunk.components["securitySchemes"]` is populated; run generator and assert emitted `GeneratedTestCase` contains `Authorization: Bearer <token>` or API key placeholder, with `security` and `security_schemes` fields populated.

### Tests for User Story 1 (Mandatory per Constitution Principle VI) ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T007 [P] [US1] Unit test for chunker security extraction in `tests/unit/test_security_chunker.py` verifying referenced `components.securitySchemes` are pruned and preserved in `OperationChunk.components["securitySchemes"]`
- [x] T008 [P] [US1] Unit test for generator security prompt construction and model output in `tests/unit/test_security_generator.py` verifying placeholder headers/query params and metadata propagation into `GeneratedTestCase`

### Implementation for User Story 1

- [x] T009 [US1] Update `OperationExtractor` in `src/specprobe/chunker/extractor.py` to prune and copy referenced `components.securitySchemes` into `OperationChunk.components["securitySchemes"]`
- [x] T010 [US1] Update `SYSTEM_PROMPT` and `PromptBuilder.build_user_prompt` in `src/specprobe/generator/prompt.py` to format active security requirements and instruct the model on credential placeholders (`<token>`, `<api_key>`, `<credentials>`)
- [x] T011 [US1] Update `GenerationEngine._validate_completion` in `src/specprobe/generator/engine.py` to propagate `chunk.metadata.security` and `chunk.components.get("securitySchemes", {})` into `GeneratedTestCase.security` and `GeneratedTestCase.security_schemes`, ensuring the credential placeholder is present in `request.headers` or `request.query_params`


**Checkpoint**: At this point, User Story 1 is fully functional and testable independently.

---

## Phase 4: User Story 2 - Collection-Level Variable Parameterization in Postman Export (Priority: P1)

**Goal**: Parameterize credentials into top-level Postman collection variables (`{{<sanitizedSchemeName>}}`) with default placeholder values and wire request headers and query parameters.

**Independent Test**: Export test cases requiring Bearer and API Key to Postman collection JSON; verify collection `variable` array contains `{"key": "<schemeName>", "value": "<token>" | "<api_key>", "type": "string"}` and request items reference `{{<schemeName>}}`.

### Tests for User Story 2 (Mandatory per Constitution Principle VI) ⚠️

- [x] T012 [P] [US2] Unit tests for Postman security variable parameterization in `tests/unit/test_security_postman.py` verifying collection `variable` array declarations and request item header/query references

### Implementation for User Story 2

- [x] T013 [US2] Update `_build_postman_item` in `src/specprobe/exporter/postman.py` to resolve credentials via `src/specprobe/exporter/security.py`, replacing credential values with `{{<sanitizedSchemeName>}}` placeholders in headers and query parameters
- [x] T014 [US2] Update `generate_postman_collection` in `src/specprobe/exporter/postman.py` to aggregate all unique `ResolvedCredential` instances across test cases and append them to the collection's `variable` array (sorted alphabetically by `key` after `baseUrl`, with no duplicate declarations per `FR-010`)


**Checkpoint**: At this point, User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Top-Level File Variable Parameterization in REST Client (.http) Export (Priority: P1)

**Goal**: Parameterize credentials into top-level file variables (`@<sanitizedSchemeName> = <placeholder>`) in `.http` export and reference them in request blocks.

**Independent Test**: Export test cases requiring Bearer and API Key to `.http` format; verify header declares `@bearerAuth = <token>` directly following `@baseUrl` and request blocks reference `{{bearerAuth}}`.

### Tests for User Story 3 (Mandatory per Constitution Principle VI) ⚠️

- [x] T015 [P] [US3] Unit tests for REST Client security file variable parameterization in `tests/unit/test_security_http.py` verifying top-level `@variable = ...` declarations and `{{variable}}` request references

### Implementation for User Story 3

- [x] T016 [US3] Update `_build_request_block` in `src/specprobe/exporter/http_client.py` to resolve credentials via `src/specprobe/exporter/security.py` and replace credential headers and query parameters with `{{<sanitizedSchemeName>}}` references
- [x] T017 [US3] Update `generate_http_document` in `src/specprobe/exporter/http_client.py` to aggregate all unique `ResolvedCredential` instances across test cases and declare them as top-level file variables (`@<sanitizedSchemeName> = <placeholder>`) directly below `@baseUrl` (sorted alphabetically, with zero duplicates per `FR-010`)


**Checkpoint**: At this point, User Stories 1, 2, and 3 are independently functional.

---

## Phase 6: User Story 4 - Deterministic Selection, Scopes, and Traceability for Multiple Security Schemes (Priority: P2)

**Goal**: Resolve multiple alternative schemes deterministically, support compound security requirements, format `# Security: ...`, `# Scopes: ...`, `# Alternatives: ...`, and `(optional)` annotations in both `.http` comments and Postman descriptions.

**Independent Test**: Export operations declaring OAuth2 with scopes, optional security `{}`, and multiple alternatives; verify correct primary scheme selection, scope comments, alternative lists, and `(optional)` annotations in exported `.http` comments and Postman request descriptions.

### Tests for User Story 4 (Mandatory per Constitution Principle VI) ⚠️

- [x] T018 [P] [US4] Unit tests in `tests/unit/test_security_multi_scheme.py` verifying alternative scheme priority, compound security requirements, OAuth2 scope documentation, and optional security handling

### Implementation for User Story 4

- [x] T019 [US4] Enhance `src/specprobe/exporter/security.py` to format documentation comment lines (`# Security: <scheme>`, `# Scopes: <scopes>`, `# Alternatives: <alts>`) and Postman description text for multi-scheme alternatives, compound requirements, and optional security (`FR-006`, `FR-009`, `FR-013`, `FR-014`)
- [x] T020 [US4] Update `_build_request_block` in `src/specprobe/exporter/http_client.py` to inject `# Security: ...`, `# Scopes: ...`, and `# Alternatives: ...` comment lines directly above the request line
- [x] T021 [US4] Update `_build_postman_item` in `src/specprobe/exporter/postman.py` to append security schemes, scopes, and alternatives metadata to `request.description`


**Checkpoint**: All user stories are now fully implemented and testable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Golden file regressions, end-to-end integration, quickstart validation, and quality gates

- [x] T022 [P] Create end-to-end integration test in `tests/integration/test_security_pipeline.py` verifying full pipeline execution (`specprobe chunk | specprobe generate | specprobe export`) on multi-auth specifications
- [x] T023 [P] Generate byte-identical golden file fixtures for Postman and `.http` in `tests/fixtures/golden/security/` and add golden regression tests in `tests/unit/test_security_golden.py`
- [x] T024 Run quickstart validation scenarios from `specs/006-security-scheme-auth/quickstart.md` and verify all CLI commands
- [x] T025 Run code hygiene and static verification gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check src/`, `uv run pytest`, and `uv run pre-commit run --all-files`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Stories (Phase 3+)**: All depend on Foundational phase completion.
  - User Story 1 (P1): Chunk and test generation security support.
  - User Story 2 (P1): Postman export parameterization (depends on US1 models).
  - User Story 3 (P1): REST Client export parameterization (depends on US1 models; can run in parallel with US2).
  - User Story 4 (P2): Advanced multi-scheme priority, scopes, and comment annotations (builds upon US2 & US3 exporters).
- **Polish (Phase 7)**: Depends on all user stories being complete.

### Parallel Opportunities

- **Setup Phase**: T001 and T002 can run in parallel.
- **Foundational Phase**: T003 and T006 can run in parallel with T004 and T005.
- **User Story 1**: T007 and T008 (tests) can run in parallel before implementation.
- **User Story 2 & 3**: Once User Story 1 completes, US2 (`postman.py`) and US3 (`http_client.py`) touch separate exporter files and can run in parallel.
- **Polish Phase**: T022 and T023 can run in parallel.

---

## Parallel Example: Exporter Implementation (US2 & US3)

```bash
# Developer / Agent A works on Postman Collection export (US2):
Task: "T012 [P] [US2] Unit tests for Postman security variable parameterization in tests/unit/test_security_postman.py"
Task: "T013 [US2] Update _build_postman_item in src/specprobe/exporter/postman.py"
Task: "T014 [US2] Update generate_postman_collection in src/specprobe/exporter/postman.py"

# Developer / Agent B works in parallel on REST Client (.http) export (US3):
Task: "T015 [P] [US3] Unit tests for REST Client security file variable parameterization in tests/unit/test_security_http.py"
Task: "T016 [US3] Update _build_request_block in src/specprobe/exporter/http_client.py"
Task: "T017 [US3] Update generate_http_document in src/specprobe/exporter/http_client.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003, T004, T005, T006)
3. Complete Phase 3: User Story 1 (T007, T008, T009, T010, T011)
4. **VALIDATE MVP**: Verify `specprobe chunk | specprobe generate` produces valid credential placeholders in `request.headers` / `request.query_params` and carries `security` / `security_schemes` in `GeneratedTestCase`.

### Incremental Delivery

1. Setup + Foundational -> Foundation ready.
2. User Story 1 -> Runnable test fixtures with auth placeholders (MVP).
3. User Story 2 -> Parameterized Postman collections with collection variables (`{{...}}`).
4. User Story 3 -> Parameterized REST Client files with top-level variables (`@... =`).
5. User Story 4 -> Full multi-scheme priority resolution, compound security, OAuth2 scopes, and comment annotations.
6. Polish -> Golden file regressions, end-to-end integration tests, static type verification (`ty check src/`), and pre-commit checks.
