# Tasks: AWS Bedrock LLM Gateway Support

**Feature Branch**: `009-bedrock-llm-backend`
**Specification**: [specs/009-bedrock-llm-backend/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/009-bedrock-llm-backend/spec.md)
**Implementation Plan**: [specs/009-bedrock-llm-backend/plan.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/009-bedrock-llm-backend/plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project dependency verification and test setup.

- [X] T001 Inspect and verify environment dependencies for AWS Bedrock support via LiteLLM in `pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared test harnesses and mock fixtures required by all user stories.

**⚠️ CRITICAL**: Must complete before user story testing and implementation can proceed.

- [X] T002 Create shared test fixtures and helpers for Bedrock mocking and environment isolation in `tests/unit/generator/conftest.py`

**Checkpoint**: Foundation ready — user story implementation can begin.

---

## Phase 3: User Story 1 - Bedrock Model Routing & Cloud Opt-In Enforcement (Priority: P1) 🎯 MVP

**Goal**: Identify models starting with `bedrock/` as cloud models and strictly enforce SpecProbe Constitution Principle IV by requiring `AWS_REGION` or `AWS_DEFAULT_REGION` before initiating inference.

**Independent Test**: Initialize `LLMGateway(model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0")` with and without AWS environment variables; verify descriptive `ValueError` on missing region and successful initialization when present.

### Tests for User Story 1 🧪

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T003 [P] [US1] Write unit tests for Bedrock cloud opt-in validation verifying rejection when `AWS_REGION` and `AWS_DEFAULT_REGION` are unset and acceptance when either is set in `tests/unit/generator/test_bedrock_gateway.py`

### Implementation for User Story 1

- [X] T004 [US1] Implement Bedrock cloud opt-in verification in `LLMGateway._validate_cloud_opt_in()` checking `AWS_REGION` or `AWS_DEFAULT_REGION` with exact error message `"Cloud model '{self.model}' requires AWS_REGION or AWS_DEFAULT_REGION environment variable. Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV."` in `src/specprobe/generator/gateway.py`

**Checkpoint**: User Story 1 complete — Bedrock opt-in enforcement is active and testable independently.

---

## Phase 4: User Story 2 - Provider-Aware Endpoint Resolution & api_base Handling (Priority: P1)

**Goal**: Omit `api_base` (pass `None` to LiteLLM) for `bedrock/*` models by default to enable native AWS SDK/boto3 regional routing, while preserving explicit `--api-base` / `SPECPROBE_LLM_API_BASE` proxy endpoints (such as Fiserv Aitrium) and retaining `"http://localhost:1234/v1"` for local models.

**Independent Test**: Inspect arguments forwarded to `litellm.completion()`: verify `api_base` is omitted (`None`) for default Bedrock calls, forwarded when explicitly provided, and defaulted to `"http://localhost:1234/v1"` for local models. Verify disk cache serialization persists `api_base: null` for Bedrock.

### Tests for User Story 2 🧪

- [X] T005 [P] [US2] Write unit tests for provider-aware `api_base` resolution verifying `api_base is None` for `bedrock/*`, explicit `--api-base` preservation, and `http://localhost:1234/v1` default for local models in `tests/unit/generator/test_bedrock_gateway.py`
- [X] T006 [P] [US2] Write unit tests for `LLMGateway.complete()` call dispatch verifying `litellm.completion(..., api_base=None)` and disk cache record persistence with `api_base: null` in `tests/unit/generator/test_bedrock_gateway.py`

### Implementation for User Story 2

- [X] T007 [US2] Implement provider-aware `api_base` resolution in `LLMGateway.__init__()` and pass-through in `LLMGateway.complete()` in `src/specprobe/generator/gateway.py`
- [X] T008 [US2] Verify and enforce disk cache serialization with `api_base=None` for Bedrock completions in `src/specprobe/generator/cache.py`

**Checkpoint**: User Stories 1 and 2 complete — Bedrock completions resolve endpoints correctly and cache deterministically.

---

## Phase 5: User Story 3 - End-to-End CLI Integration in `generate` and `audit` (Priority: P2)

**Goal**: Support `--model bedrock/<model-id>` and `--api-base` in both `specprobe generate` and `specprobe audit` CLI commands, decoupling Click default URL assignment so `LLMGateway` dynamically handles endpoint defaults.

**Independent Test**: Execute CLI integration tests for `specprobe generate` and `specprobe audit` targeting Bedrock models with mocked completions and replay cache fixtures, verifying opt-in rejection when region is missing and successful execution when present.

### Tests for User Story 3 🧪

- [X] T009 [P] [US3] Write CLI integration tests for `specprobe generate` with Bedrock models verifying opt-in failure and mock completion in `tests/integration/test_bedrock_cli.py`
- [X] T010 [P] [US3] Write CLI integration tests for `specprobe audit` with Bedrock models verifying opt-in failure and mock completion in `tests/integration/test_bedrock_cli.py`

### Implementation for User Story 3

- [X] T011 [US3] Update `generate_command` Click options in `src/specprobe/cli.py` to decouple `--api-base` default to `None`
- [X] T012 [US3] Update `audit_command` Click options in `src/specprobe/cli.py` to add `--model` and `--api-base` options and pass them to `LLMGateway`

**Checkpoint**: All user stories complete — Bedrock LLM backend is fully operational across `generate` and `audit` CLI commands.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation updates, quickstart verification, and repo-wide quality gates.

- [X] T013 [P] Update CLI reference and documentation for Bedrock LLM backend in `README.md`
- [X] T014 Execute full offline verification suite against quickstart scenarios in `specs/009-bedrock-llm-backend/quickstart.md`
- [X] T015 Run pre-commit hooks and type checks (`ruff check`, `ruff format --check`, `ty check src/`, `pre-commit run --all-files`) across all files

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — blocks all user stories.
- **User Story 1 (Phase 3 - P1)**: Depends on Foundational completion.
- **User Story 2 (Phase 4 - P1)**: Depends on User Story 1 (gateway structure established).
- **User Story 3 (Phase 5 - P2)**: Depends on User Story 2 (gateway provider-aware logic ready).
- **Polish (Phase 6)**: Depends on all user story phases being complete.

### Within Each User Story

- Test tasks (`tests/`) MUST be written and fail before implementation tasks (`src/`).
- Core logic before integration.
- Story complete before moving to next priority.

### Parallel Opportunities

- Within Phase 3: T003 can run in parallel with foundational test planning.
- Within Phase 4: T005 and T006 can run in parallel (different test scenarios in `tests/unit/generator/test_bedrock_gateway.py`).
- Within Phase 5: T009 and T010 can run in parallel (separate CLI command test functions in `tests/integration/test_bedrock_cli.py`).
- Within Phase 6: T013 (`README.md`) can run in parallel with verification tasks.

---

## Parallel Example: User Story 2

```bash
# Launch both unit test tasks for User Story 2 in parallel:
Task: "Write unit tests for provider-aware api_base resolution in tests/unit/generator/test_bedrock_gateway.py"
Task: "Write unit tests for LLMGateway.complete() call dispatch in tests/unit/generator/test_bedrock_gateway.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (`T001`).
2. Complete Phase 2: Foundational (`T002`).
3. Complete Phase 3: User Story 1 (`T003`, `T004`).
4. **STOP and VALIDATE**: Verify opt-in validation passes with `AWS_REGION` and fails without it.

### Incremental Delivery

1. Setup + Foundation $\rightarrow$ Ready.
2. Add User Story 1 $\rightarrow$ Cloud opt-in enforced per Principle IV (MVP).
3. Add User Story 2 $\rightarrow$ Provider-aware `api_base` omission + cache persistence.
4. Add User Story 3 $\rightarrow$ CLI integration in `generate` and `audit`.
5. Polish $\rightarrow$ README updates, quickstart scenarios, and pre-commit checks.
