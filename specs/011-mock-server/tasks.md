# Tasks: Minimal Local Mock Server (`specprobe mock`)

**Branch**: `011-mock-server` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/011-mock-server/spec.md) | **Plan**: [plan.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/011-mock-server/plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize mock package layout and directory structure.

- [X] T001 Create `src/specprobe/mock/` directory and initialize empty `src/specprobe/mock/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and schema synthesis utilities that MUST be complete before user stories can be implemented.

**⚠️ CRITICAL**: Foundational models and schema synthesis must be complete and tested before user story implementation begins.

- [X] T002 [P] Define `MockResponse`, `MockRoute`, `MockServerConfig`, and `MockAccessLogEntry` Pydantic models in `src/specprobe/mock/models.py` per data-model.md
- [X] T003 [P] Implement deterministic Draft 7 JSON Schema synthesizer `synthesize_sample_from_schema(schema: dict[str, Any] | None) -> Any` in `src/specprobe/mock/synth.py` supporting `object`, `array`, `string` (with format & enum), `integer`/`number` (with minimum & enum), `boolean`, `null`, and local `$defs`/`definitions` resolution
- [X] T004 [P] Add unit tests for `MockRoute`, `MockResponse`, and `MockServerConfig` validation in `tests/unit/test_mock_models.py`
- [X] T005 [P] Add unit tests for `synthesize_sample_from_schema` in `tests/unit/test_mock_synth.py` covering all Draft 7 types, enums, formats, required properties, and local `$defs` resolution

**Checkpoint**: Foundational models and deterministic schema synthesis verified; user story implementation can begin.

---

## Phase 3: User Story 1 - Serve Positive Canned Responses for Exported Test Artifacts (Priority: P1) 🎯 MVP

**Goal**: Match incoming HTTP requests by HTTP method and normalized path against positive `GeneratedTestCase` fixtures, returning recorded status codes, headers, and canned or synthesized response bodies so exported Postman and `.http` artifacts execute and pass locally.

**Independent Test**: Start mock server on port 8000 using `tests/fixtures/generated_tests.jsonl`. Send HTTP requests to `GET /pets?limit=10`, `POST /pets`, `GET /pets/42`, and `DELETE /pets/42`. Verify that status codes (200, 201, 200, 204), response headers, and bodies matching schema are returned, and 204 returns an empty body.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T006 [P] [US1] Add unit tests for `MockRouter` in `tests/unit/test_mock_router.py` verifying positive test case filtering (`test_type == "positive"` or 2xx), path parameter substitution (`/pets/{petId}` + `{"petId": "42"}` -> `/pets/42`), trailing slash normalization, and response body synthesis
- [X] T007 [P] [US1] Add unit tests for `MockServer` HTTP request serving in `tests/unit/test_mock_server.py` verifying matched `GET`, `POST`, and `DELETE 204` responses, query parameter ignoring, and `Content-Type`/`Content-Length` headers

### Implementation for User Story 1

- [X] T008 [US1] Implement `MockRouter` in `src/specprobe/mock/router.py` with `load_test_cases` (filtering positive cases, resolving path parameters, stripping trailing slashes except root `/`, synthesizing canned bodies or empty body for 204), and `match_route(method: str, path: str) -> MockRoute | None`
- [X] T009 [US1] Implement multi-threaded HTTP request handler subclassing `http.server.BaseHTTPRequestHandler` and `MockServer` subclassing `http.server.ThreadingHTTPServer` in `src/specprobe/mock/server.py` to dispatch matched routes and return canned status, headers, and body bytes
- [X] T010 [US1] Implement basic `specprobe mock` CLI command in `src/specprobe/cli.py` accepting `TEST_CASES_FILE` (or `-` for stdin) and launching `MockServer`

**Checkpoint**: User Story 1 complete and independently testable as an MVP mock server.

---

## Phase 4: User Story 2 - Configurable Port, Host, and Process Lifecycle (Priority: P2)

**Goal**: Provide configurable `--port` and `--host` options, display a rich startup banner with loaded route summary, print concise single-line access logs per request, and cleanly terminate on SIGINT/Ctrl+C without socket leakage.

**Independent Test**: Run `specprobe mock tests/fixtures/generated_tests.jsonl --port 9090 --host 127.0.0.1`. Verify custom host/port binding, inspect startup route banner, send requests and observe access logs `[HH:MM:SS] METHOD PATH -> STATUS (LATENCYms)`, send Ctrl+C and verify clean exit code 0 and socket release.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T011 [P] [US2] Add unit tests for `MockServer` lifecycle in `tests/unit/test_mock_server.py` verifying custom host/port binding, `allow_reuse_address = True`, multi-threaded concurrent request dispatch, and `shutdown()`
- [X] T012 [P] [US2] Add integration tests in `tests/integration/test_cli_mock.py` verifying CLI options `--port` and `--host`, stdin streaming via `-`, port conflict handling (exit code 1 with stderr diagnostic), and missing/empty file error handling

### Implementation for User Story 2

- [X] T013 [US2] Implement rich startup banner and loaded route table rendering using `rich.console.Console` and `rich.table.Table` in `src/specprobe/mock/server.py`
- [X] T014 [US2] Implement concise per-request access logging in `src/specprobe/mock/server.py` printing `[HH:MM:SS] METHOD PATH -> STATUS (LATENCYms)`
- [X] T015 [US2] Implement signal handling for `SIGINT`, `SIGTERM`, and `KeyboardInterrupt` with clean socket shutdown, along with port collision error handling in `src/specprobe/mock/server.py`
- [X] T016 [US2] Update `specprobe mock` CLI command in `src/specprobe/cli.py` with `--port` (`-p`, default 8000) and `--host` (`-h`, default `127.0.0.1`) options, stdin buffering, and informative error handling

**Checkpoint**: User Stories 1 AND 2 complete and independently verifiable.

---

## Phase 5: User Story 3 - Diagnostic Handling for Unmatched Routes (Priority: P3)

**Goal**: Return HTTP 404 with structured JSON diagnostics listing available routes when an endpoint is unmatched, and return HTTP 405 with `Allow` header when the path matches but the method is unsupported.

**Independent Test**: Request `GET http://localhost:8000/unregistered/path` and verify response is HTTP 404 with JSON listing registered routes. Request `PATCH http://localhost:8000/pets` and verify response is HTTP 405 with `Allow: GET, POST` header and diagnostic JSON.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T017 [P] [US3] Add unit tests in `tests/unit/test_mock_router.py` verifying `find_allowed_methods(path: str)` and generation of structured 404 and 405 diagnostic dictionaries per http-mock-contract.md
- [X] T018 [P] [US3] Add integration tests in `tests/integration/test_cli_mock.py` verifying HTTP 404 and 405 responses from the running mock server

### Implementation for User Story 3

- [X] T019 [US3] Implement `build_not_found_response(method: str, path: str)` and `build_method_not_allowed_response(method: str, path: str, allowed_methods: list[str])` in `src/specprobe/mock/router.py` per http-mock-contract.md
- [X] T020 [US3] Integrate 404/405 diagnostic response dispatch and `[UNMATCHED]` access log highlighting into the request handler in `src/specprobe/mock/server.py`

**Checkpoint**: All user stories complete with full route matching, lifecycle management, and diagnostic handling.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Package exports, quickstart verification, type checking, and code quality verification.

- [X] T021 [P] Expose public symbols `MockServer`, `MockRouter`, `MockRoute`, `MockResponse`, `MockServerConfig` in `src/specprobe/mock/__init__.py`
- [X] T022 Execute end-to-end quickstart validation scenarios from `specs/011-mock-server/quickstart.md` using `tests/fixtures/generated_tests.jsonl`
- [X] T023 Run static type verification with `uv run ty check src/` and ensure zero diagnostics
- [X] T024 Run code quality verification with `uv run ruff check .` and `uv run ruff format --check .`
- [X] T025 Run full automated test suite with `uv run pytest` and verify 100% of tests pass cleanly
- [X] T026 Run pre-commit verification with `uv run pre-commit run --all-files` and verify all hooks pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion (T002-T005) — Delivers MVP.
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion (T008-T010).
- **User Story 3 (Phase 5)**: Depends on User Story 1 completion (T008-T010); can run concurrently with US2.
- **Polish (Phase 6)**: Depends on all user stories (Phases 3-5) being complete.

### Parallel Opportunities

- Within Phase 2: T002, T003, T004, and T005 can all be written/tested in parallel across distinct files.
- Within Phase 3: Tests T006 and T007 can be written in parallel before implementation tasks T008, T009, T010.
- Within Phase 4: Tests T011 and T012 can be written in parallel.
- Within Phase 5: Tests T017 and T018 can be written in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1: Setup (`src/specprobe/mock/`).
2. Complete Phase 2: Foundational (`models.py`, `synth.py`, tests).
3. Complete Phase 3: User Story 1 (`router.py`, `server.py`, basic `cli.py` command).
4. **Validate MVP**: Test `specprobe mock tests/fixtures/generated_tests.jsonl` and send HTTP requests to verify canned status codes and bodies.

### Incremental Delivery
1. Add User Story 2: Configurable port/host, rich startup table, access logging, and graceful Ctrl+C shutdown.
2. Add User Story 3: Unmatched 404 diagnostics with route listing and 405 Method Not Allowed handling.
3. Polish: Export symbols, validate quickstart scenarios, run `ty check`, `ruff`, and `pytest`.
