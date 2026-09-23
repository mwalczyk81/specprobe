# Tasks: Higher-Fidelity Mock Response Synthesis

**Branch**: `012-mock-response-synthesis` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/.claude/worktrees/fix-stdin-streaming-test/specs/012-mock-response-synthesis/spec.md) | **Plan**: [plan.md](file:///C:/Users/mwalc/source/repos/specprobe/.claude/worktrees/fix-stdin-streaming-test/specs/012-mock-response-synthesis/plan.md)

---

## Phase 1: Setup

**Purpose**: Establish a known-good baseline before touching the synthesizer (no new dependencies, directories, or scaffolding are needed for this feature).

- [X] T001 Run `uv run pytest tests/unit/test_mock_synth.py tests/unit/test_mock_router.py tests/integration/test_cli_mock.py -v` to confirm the current (pre-change) baseline passes, before modifying `src/specprobe/mock/synth.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the key-threading plumbing that both User Story 1 (its own AC5 fallback) and User Story 2 (its primary case) depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Add an optional `key: str | None = None` parameter to `_synthesize` in `src/specprobe/mock/synth.py`; have `_synthesize_object` pass `key=<property name>` when recursing into each `properties[<name>]` value, and have `_synthesize_array` pass its own `key` through unchanged when recursing into `items` (per data-model.md §2). This is pure plumbing — no observable behavior change yet; the string branch still returns `""` until Phase 3.

**Checkpoint**: Key-threading plumbing in place (verified indirectly once Phase 3 makes it observable) — user story implementation can begin.

---

## Phase 3: User Story 1 - Recognizable placeholder values for well-known string formats (Priority: P1) 🎯 MVP

**Goal**: String fields with a recognized JSON Schema `format` (`date-time`, `date`, `email`, `uuid`, `uri`/`url`, `ipv4`) synthesize to a valid, fixed representative literal instead of `""`.

**Independent Test**: Call `synthesize_sample_from_schema` on a schema with a `"format": "date-time"` string property (and separately `"uuid"`, `"email"`); confirm each returns its fixed literal from data-model.md §1, not `""`, and that repeated calls return identical output.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T003 [P] [US1] Rewrite `test_synthesize_string_format_is_ignored` in `tests/unit/test_mock_synth.py` (its premise is reversed by this feature) to assert format-aware output for all seven supported `format` values (`date-time`, `date`, `email`, `uuid`, `uri`, `url`, `ipv4`) against the literals in data-model.md §1
- [X] T004 [P] [US1] Add a test in `tests/unit/test_mock_synth.py` asserting an unrecognized `format` (e.g. `"hostname"`) falls back to the generic `sample_<key>` value rather than `""` (FR-003)
- [X] T005 [P] [US1] Add a test in `tests/unit/test_mock_synth.py` asserting that synthesizing the same format-aware schema node repeatedly produces byte-identical output every time (FR-002, SC-004)

### Implementation for User Story 1

- [X] T006 [US1] Add a module-level `_FORMAT_SAMPLES` constant dict in `src/specprobe/mock/synth.py` mapping `date-time` → `"2024-01-01T00:00:00Z"`, `date` → `"2024-01-01"`, `email` → `"user@example.com"`, `uuid` → `"3fa85f64-5717-4562-b3fc-2c963f66afa6"`, `uri` and `url` → `"https://example.com/sample"`, `ipv4` → `"203.0.113.1"` (data-model.md §1)
- [X] T007 [US1] Update the `string`-type branch of `_synthesize` in `src/specprobe/mock/synth.py`: if the node's `format` is a key in `_FORMAT_SAMPLES`, return that literal; otherwise return `f"sample_{key}"` if `key is not None`, else the fixed literal `"sample_value"` (depends on T002, T006)

**Checkpoint**: User Story 1 complete and independently testable. Because US1's own acceptance scenario (AC5) requires the unsupported-format case to fall back to the generic key-based value, T007 necessarily implements that fallback too — this is expected and is what makes User Story 2 (below) a thin, test-only phase.

---

## Phase 4: User Story 2 - Self-identifying placeholder values for unformatted strings (Priority: P2)

**Goal**: Plain string fields (no `format`/`enum`/`const`) synthesize to `sample_<key>` (or `sample_value` with no enclosing key), including through array `items` nesting.

**Independent Test**: Call `synthesize_sample_from_schema` on a schema with two different plain string properties; confirm each value is derived from its own property key and the two differ from each other, and that an array-of-plain-strings property inherits its own key.

**Note**: T007 (Phase 3) already implements this behavior in full, because User Story 1's own AC5 depends on it. This phase's tasks are User Story 2's dedicated test coverage, plus updates to every existing assertion this behavior change invalidates.

### Tests for User Story 2

> **NOTE: Write these tests FIRST if not already covered; here they primarily fix existing expectations**

- [X] T008 [P] [US2] Update `test_synthesize_string_type` in `tests/unit/test_mock_synth.py`: a bare root `{"type": "string"}` schema (no enclosing property) now expects `"sample_value"`, not `""` (FR-004a)
- [X] T009 [P] [US2] Update `test_synthesize_object_required_only` in `tests/unit/test_mock_synth.py`: expect `{"id": 0, "name": "sample_name"}`, not `{"id": 0, "name": ""}`
- [X] T010 [P] [US2] Update `test_synthesize_array_of_objects` in `tests/unit/test_mock_synth.py`: expect `[{"id": 0, "name": "sample_name"}]`, not `[{"id": 0, "name": ""}]`
- [X] T011 [P] [US2] Update `test_synthesize_resolves_local_definitions_ref` in `tests/unit/test_mock_synth.py`: a root-level array of plain strings resolved via `$ref` has no enclosing property key, so expect `["sample_value"]`, not `[""]`
- [X] T012 [P] [US2] Update `test_response_body_synthesized_from_schema_shape` in `tests/unit/test_mock_router.py`: expect `{"id": 0, "name": "sample_name"}`, not `{"id": 0, "name": ""}`
- [X] T013 [P] [US2] Update `test_cli_mock_custom_port_and_host` in `tests/integration/test_cli_mock.py`: expect `[{"id": 0, "name": "sample_name"}]`, not `[{"id": 0, "name": ""}]`
- [X] T014 [P] [US2] Add a test in `tests/unit/test_mock_synth.py` asserting two different plain string properties (e.g. `"description"`, `"notes"`) synthesize to different values (`"sample_description"`, `"sample_notes"`) derived from their own keys
- [X] T015 [P] [US2] Add a test in `tests/unit/test_mock_synth.py` asserting a plain-string array item inherits its enclosing property's key — `{"type": "object", "required": ["tags"], "properties": {"tags": {"type": "array", "items": {"type": "string"}}}}` synthesizes to `{"tags": ["sample_tags"]}`

### Implementation for User Story 2

*(None — already delivered by T002 and T007. This phase exists to prove User Story 2's acceptance scenarios independently, per the coupling noted above.)*

**Checkpoint**: User Stories 1 AND 2 both independently verifiable; every existing test that encoded the old all-placeholder behavior is now updated to match.

---

## Phase 5: User Story 3 - Schema-declared example/default values take priority (Priority: P3)

**Goal**: A schema node declaring `example` (or `default`, when `example` is absent) synthesizes to that literal verbatim, ahead of format-aware/key-based string synthesis, but still behind `const`/`enum`.

**Independent Test**: Call `synthesize_sample_from_schema` on a node with `"example": "widget-42"` and confirm the output is exactly `"widget-42"` regardless of type/format/key; separately confirm a conflicting `const`/`enum` still wins over a present `example`.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T016 [P] [US3] Add a test in `tests/unit/test_mock_synth.py` asserting a node with `"example"` returns it verbatim regardless of declared `type` (cover string, object, array, and integer example values)
- [X] T017 [P] [US3] Add a test in `tests/unit/test_mock_synth.py` asserting a node with only `"default"` (no `"example"`) returns it verbatim
- [X] T018 [P] [US3] Add a test in `tests/unit/test_mock_synth.py` asserting a node declaring both `"example"` and a different `"default"` returns the `"example"` value
- [X] T019 [P] [US3] Add a test in `tests/unit/test_mock_synth.py` asserting a node with `"const"` (and separately `"enum"`) plus a conflicting `"example"` still returns the `const`/`enum` value, not the `example` (FR-008)
- [X] T020 [P] [US3] Add a test in `tests/unit/test_mock_synth.py` asserting an `"example"`/`"default"` on an object- or array-typed node replaces that node's entire synthesized subtree rather than being merged into its properties/items

### Implementation for User Story 3

- [X] T021 [US3] Insert `example`/`default` precedence checks into `_synthesize` in `src/specprobe/mock/synth.py` immediately after the existing `const`/`enum` checks and before the `type`-based dispatch: return `node["example"]` if present, else `node["default"]` if present, per data-model.md §3 (independent of T002/T006/T007)

**Checkpoint**: All three user stories independently functional. Full precedence chain — `$ref` → `const` → `enum` → `example` → `default` → type dispatch (format-aware/key-based strings, unchanged numbers/booleans) — is in place.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Quality gate verification and end-to-end validation.

- [X] T022 [P] Run static type verification with `uv run ty check src/` and confirm zero diagnostics
- [X] T023 [P] Run code quality verification with `uv run ruff check .` and `uv run ruff format --check .`
- [X] T024 Execute the end-to-end quickstart validation scenarios in `specs/012-mock-response-synthesis/quickstart.md` (Scenarios 1–4)
- [X] T025 Run the full automated test suite with `uv run pytest` and confirm 100% of tests pass cleanly (429 passed, 1 skipped; 3 pre-existing unrelated failures — terminal-width rendering in `test_cli_stats.py` and Hypothesis input-generation timing in `test_exporter_http.py` — confirmed present without this feature's changes)
- [X] T026 Run pre-commit verification with `uv run pre-commit run --all-files` and confirm all hooks pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion (T002). Delivers the MVP and, as a side effect of its own AC5, the User Story 2 fallback logic.
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion (T006, T007) — its tests exercise behavior T007 already implements.
- **User Story 3 (Phase 5)**: Depends only on Foundational (T002 is untouched by this story) — can be implemented in parallel with Phases 3–4 if staffed separately, since its precedence checks are inserted independently of the string branch.
- **Polish (Phase 6)**: Depends on all user stories (Phases 3–5) being complete.

### Parallel Opportunities

- Within Phase 3: T003, T004, T005 (tests) can be written in parallel; T006 and T007 are sequential (T007 depends on T006).
- Within Phase 4: T008–T015 are all test-only edits to independent test functions across three files and can all run in parallel.
- Within Phase 5: T016–T020 (tests) can be written in parallel, before T021 (implementation).
- Phase 5 as a whole can proceed in parallel with Phases 3–4 by a second contributor, since `example`/`default` precedence is inserted independently of the string-branch changes.
- Within Phase 6: T022 and T023 can run in parallel; T024–T026 should run after them, in order.

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Rewrite test_synthesize_string_format_is_ignored for format-aware output in tests/unit/test_mock_synth.py"
Task: "Add unsupported-format fallback test in tests/unit/test_mock_synth.py"
Task: "Add determinism/repeatability test in tests/unit/test_mock_synth.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (baseline confirmation).
2. Complete Phase 2: Foundational (`key` parameter threading).
3. Complete Phase 3: User Story 1 (`_FORMAT_SAMPLES` table + format-aware/fallback string branch).
4. **Validate MVP**: Run `uv run pytest tests/unit/test_mock_synth.py -v` and confirm format-aware fields no longer read as `""`.

### Incremental Delivery

1. Add User Story 2: dedicated tests proving the key-based fallback (already shipped by US1's T007) meets its own bar, plus fixing every existing test the behavior change invalidates.
2. Add User Story 3: `example`/`default` precedence, independent of the string-branch work.
3. Polish: static typing, lint, quickstart validation, full test suite, pre-commit.
