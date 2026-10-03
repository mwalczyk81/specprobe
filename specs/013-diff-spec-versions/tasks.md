# Implementation Tasks: OpenAPI Structural Diff (`specprobe diff`)

**Feature Branch**: `013-diff-spec-versions`
**Feature Spec**: [`specs/013-diff-spec-versions/spec.md`](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)
**Implementation Plan**: [`specs/013-diff-spec-versions/plan.md`](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize package module and define data structures per design artifacts.

- [X] T001 Initialize diff package module with exports in `src/specprobe/diff/__init__.py`
- [X] T002 [P] Implement data models `ChangeType` (`operation_added`, `operation_removed`, `required_request_property_added`, `response_property_removed`, `response_status_removed`, `type_changed`, `enum_value_removed`), `DiffChangeRecord` (`change_type`, `breaking`, `method`, `path`, `location`, `description`, `old_value`, `new_value`), and `DiffSummary` in `src/specprobe/diff/models.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core model validation and OpenAPI extraction foundation required by all user stories.

- [X] T003 [P] Implement unit tests for data models and enum validation in `tests/unit/test_diff_models.py`
- [X] T004 Implement path template structural normalizer (converting `{param}` to `{}`) and operation extraction helper in `src/specprobe/diff/engine.py` reusing `load_openapi_spec` and `OperationExtractor` with `schema_depth=None`

---

## Phase 3: User Story 1 - Operation-Level Change Detection (Priority: P1) 🎯 MVP

**Goal**: Identify newly added operations (`breaking: false`) and removed operations (`breaking: true`) keyed on HTTP method and normalized path template string, ignoring `operationId` modifications and path parameter token renames.

**Independent Test**: Execute `diff_operations` on two synthetic specifications where endpoints are added, deleted, or have `operationId`/parameter tokens renamed. Verify added/removed records match expectations with zero false positives.

### Tests for User Story 1

- [X] T005 [P] [US1] Write unit tests for operation-level addition, removal, and parameter token rename normalization in `tests/unit/test_diff_engine.py`
- [X] T006 [P] [US1] Write CLI integration test for operation addition/removal and stdout JSONL streaming in `tests/integration/test_cli_diff.py`

### Implementation for User Story 1

- [X] T007 [US1] Implement operation matching and addition/removal comparison logic in `src/specprobe/diff/engine.py`
- [X] T008 [US1] Implement initial Click CLI command skeleton for `specprobe diff` in `src/specprobe/cli.py` executing operation diff and streaming JSONL lines to stdout

**Checkpoint**: User Story 1 is functional as an MVP — operation additions and removals are accurately detected and streamed.

---

## Phase 4: User Story 2 - Breaking Schema and Response Change Detection (Priority: P2)

**Goal**: Mechanically detect the 5 breaking change rules across shared operations: (1) required request property added, (2) response property removed, (3) 2xx success response status code removed, (4) field data type changed, and (5) enum value removed, while excluding non-breaking/cosmetic edits.

**Independent Test**: Execute diff against test specs isolating each of the five breaking conditions across request bodies, parameters, and responses. Verify breaking records are generated with exact location pointers and non-breaking changes are excluded.

### Tests for User Story 2

- [X] T009 [P] [US2] Write unit tests for schema dereferencing (`$ref`), nested object/array traversal, and circular reference guards in `tests/unit/test_diff_engine.py`
- [X] T010 [P] [US2] Write unit tests for all 5 breaking change rules and exclusion of non-breaking edits (optional params added, 4xx/5xx removed, descriptions changed) in `tests/unit/test_diff_engine.py`

### Implementation for User Story 2

- [X] T011 [US2] Implement schema dereferencer and cycle-guarded recursive schema traverser in `src/specprobe/diff/engine.py`
- [X] T012 [US2] Implement required request property addition detector (`required_request_property_added`) for request body and parameter schemas in `src/specprobe/diff/engine.py`
- [X] T013 [US2] Implement response property removal detector (`response_property_removed`) and 2xx response status code removal detector (`response_status_removed`, ignoring 4xx/5xx) in `src/specprobe/diff/engine.py`
- [X] T014 [US2] Implement field data type change detector (`type_changed`) and enum value removal detector (`enum_value_removed`) in `src/specprobe/diff/engine.py`
- [X] T015 [US2] Integrate schema diff evaluators into `DiffEngine.diff_operations()` in `src/specprobe/diff/engine.py`

**Checkpoint**: User Story 2 is functional — all five breaking schema/response changes are detected deterministically without false positives on non-breaking edits.

---

## Phase 5: User Story 3 - Machine-Readable Streaming Output, Summary Tables, and CI Exit Codes (Priority: P3)

**Goal**: Deliver a polished CLI experience with line-delimited JSON on `stdout`, a human-readable Rich summary table on `stderr` via `--summary`, and standard CI-friendly exit codes (`0` clean, `1` breaking changes, `2` error).

**Independent Test**: Run CLI with combinations of breaking and non-breaking specs, verify stdout contains strictly valid JSONL, stderr contains Rich table if and only if `--summary` is passed, and exit codes match 0/1/2.

### Tests for User Story 3

- [X] T016 [P] [US3] Write CLI integration tests for stdout JSONL formatting, stderr `--summary` table rendering, and exit codes (0, 1, 2) in `tests/integration/test_cli_diff.py`

### Implementation for User Story 3

- [X] T017 [P] [US3] Implement JSONL streaming serializer (`stream_diff_as_jsonl`) and Rich summary table renderer (`render_diff_summary`) to `stderr` in `src/specprobe/diff/formatter.py`
- [X] T018 [US3] Complete `specprobe diff` Click CLI command in `src/specprobe/cli.py` wiring `--summary`, exit code signaling (0 for clean, 1 for breaking, 2 for error), and error reporting for missing/invalid specification files

**Checkpoint**: All three user stories are complete and integrated into the `specprobe diff` command.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Quality verification, type safety, code hygiene, and regression test validation.

- [X] T019 [P] Verify static type checking with zero diagnostics using `uv run ty check src/`
- [X] T020 [P] Verify code quality and formatting using `uv run ruff check .` and `uv run ruff format --check .`
- [X] T021 Execute full test suite with `uv run pytest` and validate quickstart scenarios from `specs/013-diff-spec-versions/quickstart.md`
- [X] T022 Run commit hygiene validation using `uv run pre-commit run --all-files`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — BLOCKS all user stories.
- **Phase 3 (User Story 1 - MVP)**: Depends on Phase 2 completion.
- **Phase 4 (User Story 2)**: Depends on Phase 3 completion (extends diff engine to inspect schemas of matched operations).
- **Phase 5 (User Story 3)**: Depends on Phase 4 completion (formats all emitted records and computes final summary metrics).
- **Phase 6 (Polish)**: Depends on all user story phases being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Foundational operation matching and addition/removal detection. Delivers standalone MVP value.
- **User Story 2 (P2)**: Builds upon matched shared operations from US1 to run detailed schema and response comparison.
- **User Story 3 (P3)**: Consumes records produced by US1 and US2, formatting output and controlling process exit status.

### Parallel Opportunities

- Within Phase 1: T002 can run in parallel with T001.
- Within Phase 2: T003 can run in parallel with T004.
- Within Phase 3: T005 and T006 (tests) can be authored in parallel before implementation tasks T007-T008.
- Within Phase 4: T009 and T010 (tests) can be authored in parallel.
- Within Phase 5: T016 and T017 can run in parallel.
- Within Phase 6: T019 and T020 can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Launch test creation for User Story 1 together:
Task: "Write unit tests for operation-level addition, removal, and parameter token rename normalization in tests/unit/test_diff_engine.py"
Task: "Write CLI integration test for operation addition/removal and stdout JSONL streaming in tests/integration/test_cli_diff.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup: models and package init).
2. Complete Phase 2 (Foundational: extraction helper and model tests).
3. Complete Phase 3 (User Story 1: operation addition/removal diffing and basic JSONL streaming).
4. **STOP and VALIDATE**: Verify that `specprobe diff old.yaml new.yaml` correctly detects added and removed operations.

### Incremental Delivery

1. Setup + Foundational -> Foundation ready.
2. User Story 1 -> MVP delivery (operation additions & removals).
3. User Story 2 -> Breaking schema & 2xx response changes (5 rules).
4. User Story 3 -> Rich summary tables & CI exit codes (0/1/2).
5. Polish -> Static typing (`ty`), linting (`ruff`), and pre-commit checks pass cleanly.
