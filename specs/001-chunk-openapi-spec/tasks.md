# Tasks: OpenAPI Operation Chunking CLI

**Feature**: OpenAPI Operation Chunking CLI
**Feature Directory**: `specs/001-chunk-openapi-spec`
**Spec**: [`specs/001-chunk-openapi-spec/spec.md`](spec.md)
**Plan**: [`specs/001-chunk-openapi-spec/plan.md`](plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, Poetry dependency setup, directory skeleton, and test fixture provisioning.

- [X] T001 Initialize Poetry package configuration in `pyproject.toml` with dependencies (`click>=8.1`, `prance[osv]>=26.7`, `pyyaml>=6.0`, `pydantic>=2.0`) and development dependencies (`pytest>=8.0`).
- [X] T002 Create package and test directory layout per implementation plan (`src/specprobe/chunker/`, `src/specprobe/formatters/`, `tests/fixtures/`, `tests/unit/`, `tests/integration/`).
- [X] T003 [P] Provision test fixtures in `tests/fixtures/`:
  - `tests/fixtures/valid_openapi_30.yaml`: Baseline OpenAPI 3.0 document with multiple HTTP verbs (`GET`, `POST`, `DELETE`), status responses, and component schemas.
  - `tests/fixtures/composition_31.json`: OpenAPI 3.1 document testing polymorphic compositions (`allOf`, `oneOf`, `anyOf`, `not`) and path-level shared parameters.
  - `tests/fixtures/circular_spec.yaml`: Document with direct self-referencing (`Node` -> `Node`) and mutual circular references (`User` -> `Team` -> `User`).
  - `tests/fixtures/swagger_20.json`: Legacy Swagger 2.0 file containing `"swagger": "2.0"` for rejection verification.
  - `tests/fixtures/external_ref_spec.yaml`: Document with external `$ref` pointers (e.g., `$ref: "common.yaml#/components/schemas/Error"`).
  - `tests/fixtures/large_public_spec.json`: Real public Stripe OpenAPI 3.0 specification (594 operations, 1,454 schemas) for scale and real-world schema benchmarking.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, token estimation heuristic, spec loader, and CLI framework that MUST be complete before ANY user story can be implemented.

- [X] T004 [P] Implement core Pydantic domain models in `src/specprobe/chunker/models.py`:
  - `ChunkMetadata`: fields `path: str`, `method: str` (uppercase HTTP verb: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`, `TRACE`), `tags: list[str]`, `operationId: str`, `security: list[dict[str, list[str]]]`, `deprecated: bool = False`, `source_title: str = "Untitled API"`, `source_version: str = "0.0.0"`, `estimated_tokens: int = 0`, `warnings: list[str] = Field(default_factory=list)`.
  - `OperationChunk`: fields `metadata: ChunkMetadata`, `operation: dict[str, Any]`, `components: dict[str, Any]`.
  - `ChunkingStats`: fields `total_operations: int`, `min_tokens: int`, `max_tokens: int`, `median_tokens: float`, `avg_tokens: float`, `oversized_chunks: int`, `warnings: list[str]`.
- [X] T005 [P] Implement deterministic token estimation heuristic in `src/specprobe/chunker/tokens.py` using standard character calculation: `max(1, round(len(canonical_json) / 4))`.
- [X] T006 Implement OpenAPI specification loader and validation in `src/specprobe/chunker/loader.py` using `prance.BaseParser`: validate file existence, parse YAML/JSON, reject legacy Swagger 2.0 specifications upfront with `Error: Swagger 2.0 is not supported. SpecProbe requires OpenAPI 3.0 or 3.1.`, and return root specification dictionary.
- [X] T007 [P] Implement Click CLI root group and command entrypoint in `src/specprobe/cli.py` and expose CLI executable script via `src/specprobe/__init__.py`.

**Checkpoint**: Foundation ready - all core data models, spec loading, and CLI harness verified.

---

## Phase 3: User Story 1 - Core Operation Chunking with Schema Trimming (Priority: P1) [MVP]

**Goal**: Split an OpenAPI 3.0 or 3.1 specification into one discrete, self-contained chunk per operation streamed to `stdout` as newline-delimited JSON (JSONL), with path-level parameters merged, metadata attached, unreferenced schemas pruned, and circular references handled cleanly via local `$ref` pointers.

**Independent Test**: Execute `specprobe chunk tests/fixtures/valid_openapi_30.yaml`, verify `stdout` outputs valid JSONL with exactly one chunk per operation, path parameters merged, metadata populated, and `components.schemas` trimmed to only referenced definitions. Execute on `tests/fixtures/circular_spec.yaml` and verify no infinite recursion occurs.

### Tests for User Story 1

- [X] T008 [P] [US1] Unit test for schema pruning and visited-set cycle guard in `tests/unit/test_pruner.py` testing unreferenced schema removal, `allOf`/`oneOf`/`anyOf` resolution, and circular references.
- [X] T009 [P] [US1] Unit test for operation extraction and parameter merging in `tests/unit/test_extractor.py` testing path-level parameter inheritance, operation override rules, security fallback, and operationId synthesis.
- [X] T010 [P] [US1] Integration test for baseline JSONL chunking in `tests/integration/test_cli_chunk.py` testing CLI invocation, exit code 0, and JSONL format conformance.

### Implementation for User Story 1

- [X] T011 [US1] Implement `SchemaPruner` in `src/specprobe/chunker/pruner.py` using a `visited: set[str]` guard: starting from operation roots (parameters, request body, responses, callbacks, headers), transitively collect referenced component schemas, retain local internal `$ref` pointers (`#/components/schemas/<Name>`), terminate recursion at cycle boundaries, and omit unreferenced schemas.
- [X] T012 [US1] Implement `OperationExtractor` in `src/specprobe/chunker/extractor.py`: iterate over all path items and standard HTTP methods, merge path-level parameters into operation parameters (operation-level overriding matching name and `in`), resolve security (operation-level or global fallback, respecting `security: []`), and synthesize unique deterministic `operationId` (`{method}_{normalized_path}`) when omitted.
- [X] T013 [US1] Implement JSONL streaming serializer in `src/specprobe/formatters/jsonl.py`: serialize each `OperationChunk` into a single-line JSON string (`ensure_ascii=False`) terminated by a newline.
- [X] T014 [US1] Implement the `chunk` subcommand in `src/specprobe/cli.py` wiring `loader`, `extractor`, `pruner`, and `jsonl` formatter to stream chunks to `stdout`.

**Checkpoint**: User Story 1 is fully functional and delivers the core MVP capability.

---

## Phase 4: User Story 2 - Token Counting, Budget Alerts, and Statistics Summary (Priority: P2)

**Goal**: Calculate estimated tokens for each operation chunk, emit overage warnings for chunks exceeding a configurable budget (default: 2000), and provide an exclusive summary table via `--stats`.

**Independent Test**: Execute `specprobe chunk tests/fixtures/valid_openapi_30.yaml --max-tokens 100` and verify warning attached in chunk metadata and printed to stderr. Execute `specprobe chunk tests/fixtures/valid_openapi_30.yaml --stats` and verify exclusive formatted summary table printed to stdout without streaming JSONL.

### Tests for User Story 2

- [ ] T015 [P] [US2] Unit test for token estimator and budget overage warning in `tests/unit/test_tokens.py`.
- [ ] T016 [P] [US2] Integration test for `--stats` exclusive mode and `--max-tokens` CLI option in `tests/integration/test_cli_stats.py`.

### Implementation for User Story 2

- [ ] T017 [US2] Implement summary statistics calculator and text table formatter in `src/specprobe/formatters/stats.py`: compute total operations, min, max, median, average token counts, oversized chunk count, and format a human-readable summary table with warning lists.
- [ ] T018 [US2] Add `--max-tokens` (default 2000) and `--stats` options to `specprobe chunk` in `src/specprobe/cli.py`: evaluate token budget overages during chunking, emit warnings to stderr, and route exclusive table output to `stdout` when `--stats` is set.

**Checkpoint**: User Stories 1 and 2 operate independently and in combination.

---

## Phase 5: User Story 3 - Targeted Spot Checking for Single Operations (Priority: P3)

**Goal**: Filter output to a single targeted operation chunk using `--op <operationId>`, printing formatted JSON to `stdout` or exiting with code 1 if not found.

**Independent Test**: Execute `specprobe chunk tests/fixtures/valid_openapi_30.yaml --op <validId>` and assert single pretty-printed JSON chunk returned. Execute with `--op <invalidId>` and assert exit code 1 with error on stderr.

### Tests for User Story 3

- [X] T019 [P] [US3] Integration test for `--op <operationId>` in `tests/integration/test_cli_op.py` covering found operation (exit code 0, formatted JSON) and not-found operation (exit code 1, stderr error).

### Implementation for User Story 3

- [X] T020 [US3] Add `--op` option to `specprobe chunk` in `src/specprobe/cli.py`: filter chunk stream by `operationId` (explicit or synthesized), format matching chunk as pretty-printed JSON to `stdout`, and exit with code 1 and descriptive error message on `stderr` if no matching operation exists.

**Checkpoint**: User Stories 1, 2, and 3 are all functional and independently testable.

---

## Phase 6: User Story 4 - Specification Validation & Unsupported Reference Guardrails (Priority: P4)

**Goal**: Explicitly reject Swagger 2.0 specifications with an informative error message, and detect external file references as non-fatal warnings that preserve raw `$ref` strings with exit code 0.

**Independent Test**: Execute `specprobe chunk tests/fixtures/swagger_20.json` and assert exit code 1 with rejection message. Execute `specprobe chunk tests/fixtures/external_ref_spec.yaml` and assert exit code 0 with warning on stderr and preserved raw `$ref` in output chunk.

### Tests for User Story 4

- [X] T021 [P] [US4] Integration test in `tests/integration/test_cli_validation.py` asserting Swagger 2.0 rejection (exit code 1) and external file reference non-fatal warning handling (exit code 0).

### Implementation for User Story 4

- [X] T022 [US4] Enhance `SchemaPruner` in `src/specprobe/chunker/pruner.py` to identify external file `$ref` patterns (relative or remote URI references outside `#/components/schemas/`), attach non-fatal warning notices, preserve the raw `$ref` string in the chunk schema, and write advisory warnings to `stderr`.

**Checkpoint**: All 4 user stories are fully implemented, robust, and validated.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Scale performance verification, end-to-end quickstart validation, and test suite verification.

- [X] T023 [P] Implement scale check integration test in `tests/integration/test_scale_streaming.py` asserting that streaming chunking on `tests/fixtures/large_public_spec.json` (> 500 operations) completes in < 2.0 seconds with bounded memory (verified during schema-depth benchmark: 594 ops in 0.275s).
- [X] T024 Execute and verify all quickstart validation scenarios documented in `specs/001-chunk-openapi-spec/quickstart.md`.
- [X] T025 Run full automated test suite (`poetry run pytest -v`) and verify 100% test pass rate across unit and integration tests.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3+)**: All depend on Foundational phase completion.
  - User stories can proceed sequentially in priority order (P1 -> P2 -> P3 -> P4).
- **Polish (Phase 7)**: Depends on all user stories (Phases 3-6) being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational (Phase 2). No dependencies on subsequent stories.
- **User Story 2 (P2)**: Depends on User Story 1 (uses chunks generated by US1).
- **User Story 3 (P3)**: Depends on User Story 1 (filters chunks generated by US1).
- **User Story 4 (P4)**: Depends on User Story 1 (adds reference guardrails to US1 pruner).

### Within Each User Story

- Tests MUST be written and verified to fail before implementation.
- Pruners / extractors before CLI wiring.
- Core capability verified before advancing to subsequent user stories.

---

## Parallel Execution Opportunities

- **Phase 1 (Setup)**: `T003` fixture creation can run in parallel with project directory setup.
- **Phase 2 (Foundational)**: `T004` (models), `T005` (tokens), and `T007` (CLI stub) can all be implemented in parallel.
- **Phase 3 (User Story 1)**: Tests `T008`, `T009`, and `T010` can all be written concurrently before implementation.
- **Phase 4 (User Story 2)**: Tests `T015` and `T016` can be written concurrently.
- **Phase 5 (User Story 3)**: Test `T019` can be written concurrently.
- **Phase 6 (User Story 4)**: Test `T021` can be written concurrently.
- **Phase 7 (Polish)**: `T023` scale test can be authored concurrently with quickstart verification.

---

## Parallel Example: User Story 1

```bash
# Launch test creation for User Story 1 in parallel:
Task: "T008 [P] [US1] Unit test for schema pruning and visited-set cycle guard in tests/unit/test_pruner.py"
Task: "T009 [P] [US1] Unit test for operation extraction and parameter merging in tests/unit/test_extractor.py"
Task: "T010 [P] [US1] Integration test for baseline JSONL chunking in tests/integration/test_cli_chunk.py"

# After tests are written and failing, launch core components:
Task: "T011 [US1] Implement SchemaPruner in src/specprobe/chunker/pruner.py"
Task: "T012 [US1] Implement OperationExtractor in src/specprobe/chunker/extractor.py"
Task: "T013 [US1] Implement JSONL streaming serializer in src/specprobe/formatters/jsonl.py"
```

---

## Implementation Strategy (MVP First)

1. **MVP Delivery (User Story 1)**:
   - Complete Setup (Phase 1) and Foundational (Phase 2).
   - Implement Phase 3 (User Story 1: core chunking, schema pruning with cycle guard, JSONL streaming).
   - **Stop and Validate**: Verify baseline chunking works on standard and circular OpenAPI specs.
2. **Incremental Delivery (Phases 4-6)**:
   - Add User Story 2 (token counts and `--stats` exclusive dashboard).
   - Add User Story 3 (`--op` spot check).
   - Add User Story 4 (Swagger 2.0 rejection and external file reference warnings).
3. **Hardening & Scale (Phase 7)**:
   - Verify performance benchmark on large public spec (< 2s).
   - Run quickstart validation scenarios and complete full test suite pass.
