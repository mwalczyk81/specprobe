# Tasks: LLM Test Generation & Filter-Only Search

**Feature**: `003-generate-llm-tests`  
**Date**: 2026-09-19  
**Specification**: [`specs/003-generate-llm-tests/spec.md`](file:///C:/Users/mwalc/source/repos/specprobe/specs/003-generate-llm-tests/spec.md)  
**Implementation Plan**: [`specs/003-generate-llm-tests/plan.md`](file:///C:/Users/mwalc/source/repos/specprobe/specs/003-generate-llm-tests/plan.md)  

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependency installation, package initialization, and test fixture directory layout.

- [x] T001 Add `litellm>=1.0.0` dependency to `pyproject.toml` and synchronize lockfile using `uv add litellm`
- [x] T002 Create package directory structure for generator in `src/specprobe/generator/__init__.py`
- [x] T003 [P] Create test directory structures `tests/fixtures/cache/` and `tests/fixtures/search_full_results.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core Pydantic data models, prompt builder, and LiteLLM gateway wrapper that all user stories depend on.

**⚠️ CRITICAL**: No user story implementation can begin until this foundational phase is complete.

- [x] T004 [P] Implement Pydantic models `RequestFixture`, `ResponseAssertion`, and `GeneratedTestCase` in `src/specprobe/generator/models.py` with verbatim constraints: `operation_id` non-empty string, `description` non-empty string, `status_code` integer between 100 and 599, and default factory dictionaries for headers and parameters
- [x] T005 [P] Implement unit tests for `GeneratedTestCase`, `RequestFixture`, and `ResponseAssertion` model validation in `tests/unit/test_generator_models.py`
- [x] T006 Implement `PromptBuilder` in `src/specprobe/generator/prompt.py` to synthesize natural-language system and user prompts from `OperationChunk` data and strip markdown code fences (`re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())`)
- [x] T007 [P] Implement unit tests for `PromptBuilder` and fence stripping in `tests/unit/test_generator_prompt.py`
- [x] T008 Implement `LLMGateway` client wrapper in `src/specprobe/generator/gateway.py` with local LM Studio default (`http://localhost:1234/v1`, model `openai/local-model`, dummy key `"lm-studio"`), resolving CLI options and `SPECPROBE_LLM_*` environment variables, and verifying opt-in credentials for cloud providers
- [x] T009 [P] Implement unit tests for `LLMGateway` endpoint resolution, credential checks, and LiteLLM completion dispatch in `tests/unit/test_generator_gateway.py`

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Generate Validated Test Cases from Operation Chunks (Priority: P1) 🎯 MVP

**Goal**: Read `OperationChunk`-bearing search results from `specprobe search --full` via stdin or file argument, generate schema-validated test cases via LiteLLM gateway, and stream JSON Lines (JSONL) to `stdout`.

**Independent Test**: Pipe `tests/fixtures/search_full_results.json` into `specprobe generate`, verify that valid JSONL test case objects are emitted to `stdout` containing the target `operation_id`, request fixtures, and response assertions, and confirm exit code 0.

### Tests for User Story 1
- [x] T010 [P] [US1] Create sample search results fixture with full chunk bodies in `tests/fixtures/search_full_results.json`
- [x] T011 [P] [US1] Write unit tests for single-operation test case generation in `tests/unit/test_generator_engine.py`

### Implementation for User Story 1
- [x] T012 [US1] Implement single-chunk generation in `GenerationEngine.generate_chunk()` in `src/specprobe/generator/engine.py` connecting `PromptBuilder`, `LLMGateway`, and Pydantic validation
- [x] T013 [US1] Implement search results input parser in `src/specprobe/generator/engine.py` to parse JSON array input, strictly validating that each element contains a valid `chunk` payload and rejecting non-conforming inputs
- [x] T014 [US1] Implement `specprobe generate` Click command in `src/specprobe/cli.py` accepting file path argument or stdin, streaming validated test cases as JSON Lines (JSONL) to `stdout` and diagnostic logs to `stderr`
- [x] T015 [P] [US1] Implement integration tests for `specprobe generate` CLI handling file input, stdin piping, and rejection of compact search results in `tests/integration/test_generate_cli.py`

**Checkpoint**: At this point, User Story 1 provides a functional, independently testable MVP test case generator.

---

## Phase 4: User Story 2 - Resilient Validation, Self-Correction Retry & Graceful Batch Processing (Priority: P2)

**Goal**: Implement Constitution Principle V: when initial model completion fails Pydantic validation, automatically trigger exactly one retry with schema error feedback; if the retry fails, log a descriptive error to `stderr` and continue processing remaining operations without aborting the batch.

**Independent Test**: Feed a batch of 3 operations where operation 1 succeeds on attempt 1, operation 2 fails attempt 1 but succeeds on attempt 2 (self-correction), and operation 3 fails both attempts; verify that operations 1 and 2 are streamed to `stdout`, operation 3's error is logged to `stderr`, and the batch exits with code 0.

### Tests for User Story 2
- [x] T016 [P] [US2] Write unit tests for single-retry self-correction and partial batch failure continuation in `tests/unit/test_generator_retry.py`

### Implementation for User Story 2
- [x] T017 [US2] Implement single-retry self-correction in `GenerationEngine.generate_chunk()` in `src/specprobe/generator/engine.py`, appending the invalid completion and specific Pydantic `e.errors()` schema validation feedback to the conversation turn
- [x] T018 [US2] Implement batch processing loop `GenerationEngine.generate_batch()` in `src/specprobe/generator/engine.py`, isolating per-operation failures, streaming valid test cases to `stdout`, logging descriptive diagnostic messages to `stderr`, and returning summary counts
- [x] T019 [US2] Update `specprobe generate` CLI command in `src/specprobe/cli.py` to use `generate_batch()`, exiting with code 0 if at least one test case succeeded (or 0 operations input) and exit code 1 if all operations failed
- [x] T020 [P] [US2] Implement integration tests for retry self-correction and resilient batch processing in `tests/integration/test_generate_resilience.py`

**Checkpoint**: At this point, User Stories 1 AND 2 are complete, delivering resilient unattended batch test generation.

---

## Phase 5: User Story 3 - Cryptographic Disk Caching for Repeatable, Zero-Cost Runs (Priority: P3)

**Goal**: Implement Constitution Principle IV: deterministically cache all LLM invocations to `.specprobe/cache/<cache_key>.json` keyed on SHA-256 hash of `(messages, model, temperature)` (excluding `api_base`), enabling instant cache hits and 100% offline automated test execution in CI.

**Independent Test**: Run `specprobe generate` on an input file, verify cache files are created in `.specprobe/cache/`; re-run with network disabled/mocked, verify execution completes instantly with 0 LLM inference calls; run with `--no-cache`, verify cache files are refreshed.

### Tests for User Story 3
- [x] T021 [P] [US3] Write unit tests for `DiskCache` in `tests/unit/test_generator_cache.py` testing key hashing determinism (verifying `api_base` does not alter key), cache hits, cache misses, atomic writes, and corrupted file recovery

### Implementation for User Story 3
- [x] T022 [US3] Implement `DiskCache` in `src/specprobe/generator/cache.py` with canonical JSON serialization (`sort_keys=True`, compact separators), SHA-256 key hashing on `(messages, model, temperature)`, atomic write via temporary file replacement, and metadata logging of `api_base`
- [x] T023 [US3] Integrate `DiskCache` into `LLMGateway` in `src/specprobe/generator/gateway.py` and `GenerationEngine` in `src/specprobe/generator/engine.py`, checking cache before dispatch and saving completions on miss
- [x] T024 [US3] Add `--cache-dir` and `--no-cache` CLI options and `SPECPROBE_CACHE_DIR` / `SPECPROBE_NO_CACHE` environment variable support to `specprobe generate` in `src/specprobe/cli.py`
- [x] T025 [P] [US3] Pre-record deterministic disk cache fixtures for test specs in `tests/fixtures/cache/` to support offline CI test execution
- [x] T026 [P] [US3] Implement integration tests in `tests/integration/test_generate_caching.py` verifying instant cache replay, zero network calls, and `--no-cache` invalidation

**Checkpoint**: At this point, User Stories 1, 2, and 3 are complete; all generation runs are cached, repeatable, and CI-ready.

---

## Phase 6: User Story 4 - Unranked Spec-Wide Retrieval via Filter-Only Search (Priority: P4)

**Goal**: Relax `specprobe search` query argument to optional (`required=False`); when query is omitted and metadata filters are present, retrieve all matching chunks unranked (`score=0.0`) via Qdrant scroll without default limit truncation, enabling spec-wide pipelining into `generate`.

**Independent Test**: Index a multi-operation specification, run `specprobe search --source-title "Petstore" --full` without a query string, verify all operations are returned unranked with `score: 0.0`, and pipe into `specprobe generate` to generate test cases for the entire specification.

### Tests for User Story 4
- [x] T027 [P] [US4] Write unit tests for unranked filter-only retrieval in `tests/unit/test_search_unranked.py`

### Implementation for User Story 4
- [x] T028 [US4] Implement `search_unranked()` in `src/specprobe/search/engine.py` using Qdrant `client.scroll()`, returning `SearchMatch` objects with `score=0.0` and unlimited pagination by default (or respecting explicit `limit` if provided)
- [x] T029 [US4] Update `search` command in `src/specprobe/cli.py` to make `query` optional (`required=False`, default `None`), validate that either query or at least one filter is supplied, default limit to unlimited when query is omitted, and route to `search_unranked()`
- [x] T030 [P] [US4] Implement integration tests in `tests/integration/test_search_filter_only.py` testing filter-only search, missing argument error reporting, and full pipeline `specprobe search ... --full | specprobe generate`

**Checkpoint**: All 4 user stories are fully implemented and integrated.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validation, linting, regression testing, and documentation.

- [x] T031 [P] Execute quickstart validation scenarios from `specs/003-generate-llm-tests/quickstart.md`
- [x] T032 [P] Run full linter and code style checks: `uv run ruff check .` and `uv run ruff format --check .`
- [x] T033 Run complete automated test suite: `uv run pytest` (verifying 100% tests pass offline)
- [x] T034 Update `README.md` with CLI documentation and pipeline examples for `specprobe generate` and filter-only `specprobe search`

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion.
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion.
- **User Story 3 (Phase 5)**: Depends on User Story 1 completion (can run in parallel with US2).
- **User Story 4 (Phase 6)**: Depends on Foundational completion (independent of US1-US3 generation engine; modifies search).
- **Polish (Phase 7)**: Depends on completion of all user story phases.

### User Story Dependencies
- **User Story 1 (P1)**: Core MVP generator. Can start as soon as Phase 2 finishes.
- **User Story 2 (P2)**: Extends `GenerationEngine` with single-retry and batch error handling.
- **User Story 3 (P3)**: Extends `LLMGateway` and `GenerationEngine` with disk caching.
- **User Story 4 (P4)**: Updates `specprobe search` retrieval. Independent of generator codebase; integrates via CLI pipeline.

### Parallel Opportunities
- In Phase 1: T003 can run in parallel with T001/T002.
- In Phase 2: T004/T005 (models), T006/T007 (prompt builder), and T008/T009 (gateway) can be developed and tested in parallel.
- Across Stories: User Story 4 (search engine changes) can be implemented in parallel with User Stories 1-3 (generator changes).
- Within User Stories: All test tasks marked `[P]` can be authored in parallel with or before their corresponding implementation tasks.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1: `specprobe generate`).
3. **Validate MVP**: Test `specprobe generate <search_results.json>` and verify valid JSONL streaming test cases.

### Incremental Delivery
1. Foundation Ready: Core schemas and LiteLLM gateway verified.
2. Increment 1 (MVP): Basic generation from search results (`stdout` JSONL streaming).
3. Increment 2: Single-retry self-correction and resilient batch continuation.
4. Increment 3: Cryptographic disk caching (instant hits, offline CI).
5. Increment 4: Filter-only unranked search (full spec extraction pipeline).
6. Polish: Ruff checks, full offline test suite pass, quickstart validation.
