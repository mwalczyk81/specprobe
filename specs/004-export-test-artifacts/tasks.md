# Tasks: Deterministic Export for Runnable Test Artifacts (Postman & REST Client)

**Feature Branch**: `004-export-test-artifacts`
**Specification**: [`specs/004-export-test-artifacts/spec.md`](spec.md)
**Implementation Plan**: [`specs/004-export-test-artifacts/plan.md`](plan.md)
**Status**: Complete

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize package structure and test fixture directories for the exporter.

- [x] T001 Create exporter package directory and module exports in `src/specprobe/exporter/__init__.py`
- [x] T002 [P] Create golden fixture directory `tests/fixtures/golden/` and add sample test cases fixture in `tests/fixtures/generated_tests.jsonl`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, URL parameter substitution utilities, and stream parsing that all user stories depend on.

**CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T003 [P] Implement export configuration and format enums in `src/specprobe/exporter/models.py` (`ExportFormat`, `ExportConfig`)
- [x] T004 [P] Implement RFC 3986 path parameter substitution and URL-encoding utility in `src/specprobe/exporter/utils.py`
- [x] T005 Implement input JSONL parser and validation reader in `src/specprobe/exporter/engine.py` (parsing lines into `list[GeneratedTestCase]`, with line-numbered error reporting on malformed JSONL)

**Checkpoint**: Core data models and utilities ready — user story implementations can now proceed.

---

## Phase 3: User Story 1 - Export Runnable Postman Collection v2.1 (Priority: P1) 🎯 MVP

**Goal**: Transform validated `GeneratedTestCase` records into a standard Postman Collection v2.1.0 JSON artifact with primary tag folders, substituted request URLs, and embedded `pm.test` assertions for status code, headers, and schema shape properties.

**Independent Test**: Feed `GeneratedTestCase` JSONL into `specprobe export --format postman`, verify output adheres to Schema v2.1.0, groups requests into tag folders, substitutes `{{baseUrl}}` and path parameters, and includes executable test scripts.

### Tests for User Story 1
- [x] T006 [P] [US1] Write unit tests for Postman Collection serialization in `tests/unit/test_exporter_postman.py` (verifying `_postman_id` UUIDv5 determinism, `baseUrl` variable, primary tag folder grouping, path substitution & URL encoding, body payloads, `pm.test` assertions, and `operation_id` traceability)

### Implementation for User Story 1
- [x] T007 [US1] Implement Postman Collection v2.1.0 generator in `src/specprobe/exporter/postman.py` (`generate_postman_collection(test_cases, collection_name, base_url) -> dict`)
- [x] T008 [US1] Integrate Postman collection generation into `export_batch()` in `src/specprobe/exporter/engine.py`
- [x] T009 [US1] Wire basic `specprobe export --format postman` CLI command in `src/specprobe/cli.py` supporting file and stdin input, streaming formatted JSON to stdout or output file

**Checkpoint**: At this point, User Story 1 is fully functional and delivers an independently runnable Postman MVP.

---

## Phase 4: User Story 2 - Export Runnable REST Client (.http) File (Priority: P2)

**Goal**: Transform validated `GeneratedTestCase` records into a plain-text REST Client (`.http`) document formatted with a top-level `@baseUrl` variable, `###` block delimiters, human-readable documentation comments, target method/URL, headers, and formatted JSON bodies.

**Independent Test**: Feed `GeneratedTestCase` JSONL into `specprobe export --format http`, verify output contains valid RFC 7230 syntax, `@baseUrl` declaration, `# @name` and metadata comment headers, and clean separation between blocks.

### Tests for User Story 2
- [x] T010 [P] [US2] Write unit tests for REST Client `.http` serialization in `tests/unit/test_exporter_http.py` (verifying `@baseUrl` header, `###` delimiters, `# @name`, `# Operation:`, `# Expected Status:`, `# Expected Properties:`, request lines, headers, blank line separators, and JSON request bodies)

### Implementation for User Story 2
- [x] T011 [US2] Implement REST Client `.http` serializer in `src/specprobe/exporter/http_client.py` (`generate_http_document(test_cases, base_url) -> str`)
- [x] T012 [US2] Integrate REST Client generation into `export_batch()` in `src/specprobe/exporter/engine.py`
- [x] T013 [US2] Wire `--format http` option into `specprobe export` in `src/specprobe/cli.py` streaming `.http` text to stdout or output file

**Checkpoint**: Both Postman and REST Client exporters work independently with single-format output.

---

## Phase 5: User Story 3 - Dual-Format Export & Output Destination Management (Priority: P3)

**Goal**: Support exporting both Postman and REST Client formats simultaneously to a designated directory (`--format both --output <dir>`), validate CLI option constraints (failing if `--output` omitted for dual format), support `--collection-name` and `--base-url`, and handle empty input streams cleanly.

**Independent Test**: Execute `specprobe export --format both --output ./exported/` on a test case file, verifying both `collection.json` and `requests.http` are written to the target directory with custom collection name and base URL; verify `--format both` without `--output` fails with exit code 1; verify 0 test cases produces valid empty artifacts with exit code 0.

### Tests for User Story 3
- [x] T014 [P] [US3] Write integration tests for CLI export options and destination routing in `tests/integration/test_export_cli.py` (verifying `--format both`, `--output <dir>`, stdout default for single formats, missing `--output` guardrail, `--collection-name`, `--base-url`, automatic directory creation, and 0 test cases edge case)

### Implementation for User Story 3
- [x] T015 [US3] Implement dual-format directory export in `src/specprobe/exporter/engine.py` writing `collection.json` and `requests.http` to target directory with parent directory creation and progress output to `stderr`
- [x] T016 [US3] Update `specprobe export` CLI command in `src/specprobe/cli.py` to enforce `--format both` requires `--output <dir>` (exiting with code 1 and descriptive error on `stderr`), and support `--collection-name` and `--base-url`
- [x] T017 [US3] Implement empty input handling in `src/specprobe/exporter/engine.py` and `cli.py` (0 test cases emits valid empty collection `{"info": ..., "item": []}` or empty `.http` file, logs informational message to `stderr`, and exits code 0)

**Checkpoint**: All three export modes (`postman`, `http`, `both`) and CLI destination routing are fully functional.

---

## Phase 6: User Story 4 - End-to-End Pipeline & Golden Structural Regression (Priority: P4)

**Goal**: Verify seamless Unix pipeline composition (`specprobe search --full | specprobe generate | specprobe export`) and establish 100% byte-identical golden-file regression tests comparing output against static reference fixtures for OpenAPI sample specs (Constitution Principle VI).

**Independent Test**: Execute pipeline `specprobe search --source-title "Petstore Probe API" --full | specprobe generate | specprobe export --format both --output <dir>`, confirm valid artifacts generated without manual intermediate steps, and run automated regression tests asserting exact structural match with golden files.

### Tests for User Story 4
- [x] T018 [P] [US4] Create static reference golden fixtures in `tests/fixtures/golden/` (`petstore.postman.json` and `petstore.requests.http`) generated from `tests/fixtures/valid_openapi_30.yaml` test cases
- [x] T019 [P] [US4] Implement golden-file structural regression tests in `tests/integration/test_export_golden.py` asserting character-for-character / byte-identical equality against reference fixtures per Constitution Principle VI
- [x] T020 [P] [US4] Implement end-to-end pipeline integration test in `tests/integration/test_export_pipeline.py` verifying `specprobe search ... --full | specprobe generate | specprobe export` via stdin

**Checkpoint**: All user stories and constitutional regression requirements are completely implemented and verified.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validation, linting, regression testing, and documentation.

- [x] T021 [P] Execute quickstart validation scenarios from `specs/004-export-test-artifacts/quickstart.md`
- [x] T022 [P] Run full linter and code style checks: `uv run ruff check .` and `uv run ruff format --check .`
- [x] T023 Run complete automated test suite: `uv run pytest` (verifying 100% tests pass offline with zero network requests)
- [x] T024 Update `README.md` with `specprobe export` CLI documentation, options reference, and pipeline examples

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion.
- **User Story 2 (Phase 4)**: Depends on Foundational completion (can run in parallel with US1).
- **User Story 3 (Phase 5)**: Depends on User Story 1 and 2 completion (integrates dual format and CLI options).
- **User Story 4 (Phase 6)**: Depends on User Story 3 completion (golden files and pipeline integration).
- **Polish (Phase 7)**: Depends on completion of all user story phases.

### User Story Dependencies
- **User Story 1 (P1)**: Core MVP Postman exporter. Can start as soon as Phase 2 finishes.
- **User Story 2 (P2)**: REST Client exporter. Can start as soon as Phase 2 finishes.
- **User Story 3 (P3)**: Dual format and CLI destination options. Depends on both serializers (US1 & US2).
- **User Story 4 (P4)**: Pipeline integration and golden-file regression tests. Depends on US3.

### Parallel Opportunities
- In Phase 1: T002 can run in parallel with T001.
- In Phase 2: T003 and T004 can run in parallel.
- Across Stories: User Story 1 (Postman) and User Story 2 (REST Client) can be implemented in parallel once Foundational (Phase 2) completes.
- Within User Stories: All test tasks marked `[P]` (T006, T010, T014, T018, T019, T020) can be authored in parallel with or before their corresponding implementation tasks.

---

## Parallel Example: User Story 1 & User Story 2

```bash
# Once Foundational (Phase 2) is complete, work on US1 and US2 can run concurrently:
Developer A:
  - T006: Unit tests for Postman Collection serializer (tests/unit/test_exporter_postman.py)
  - T007: Implement Postman serializer (src/specprobe/exporter/postman.py)

Developer B:
  - T010: Unit tests for REST Client serializer (tests/unit/test_exporter_http.py)
  - T011: Implement REST Client serializer (src/specprobe/exporter/http_client.py)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1: Postman Collection exporter).
3. **Validate MVP**: Test `specprobe export generated_tests.jsonl --format postman` and verify valid Postman Collection v2.1 JSON with test scripts.

### Incremental Delivery
1. Foundation Ready: Core models, URL substitution utility, and JSONL reader verified.
2. Increment 1 (MVP): Postman Collection v2.1 JSON output to stdout or file.
3. Increment 2: VS Code REST Client `.http` output to stdout or file.
4. Increment 3: Dual-format export (`--format both --output <dir>`), custom collection name, `--base-url`, and empty input guardrails.
5. Increment 4: End-to-end pipeline composition and golden-file regression tests.
6. Polish: Quickstart validation, Ruff linter/formatter clean, full test suite pass, and `README.md` documentation.
