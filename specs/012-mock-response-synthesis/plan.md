# Implementation Plan: Higher-Fidelity Mock Response Synthesis

**Branch**: `012-mock-response-synthesis` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/.claude/worktrees/fix-stdin-streaming-test/specs/012-mock-response-synthesis/spec.md)

**Input**: Feature specification from [`specs/012-mock-response-synthesis/spec.md`](file:///C:/Users/mwalc/source/repos/specprobe/.claude/worktrees/fix-stdin-streaming-test/specs/012-mock-response-synthesis/spec.md)

---

## Summary

Extend `src/specprobe/mock/synth.py`'s existing deterministic, zero-LLM JSON Schema Draft 7 synthesizer with three additive value-selection rules, applied in this precedence order ahead of the existing `const`/`enum` checks staying first: (1) an `example`/`default` literal on a schema node short-circuits synthesis for that node when present; (2) a string node with a recognized `format` (`date-time`, `date`, `email`, `uuid`, `uri`/`url`, `ipv4`) emits a fixed, standards-based representative literal instead of `""`; (3) any other plain string node emits `sample_<key>`, where `<key>` is the nearest enclosing object property's key threaded through array/`items` recursion, or the fixed literal `sample_value` when no enclosing key exists at all (e.g. a bare root-level string schema). No new dependencies, no new files, no change to the required-properties-only object shape or to unconstrained-number synthesis (`0`).

---

## Technical Context

**Language/Version**: Python >= 3.11 (matches existing `synth.py`; standard library only — `re`, `typing`).

**Primary Dependencies**: None added. Implemented entirely with the standard library, consistent with the existing synthesizer (no `jsonschema`-style format validators — representative literals are fixed constants chosen to already be valid, so no runtime validation is needed to guarantee correctness).

**Storage**: N/A — pure function, no persistence.

**Testing**: `pytest>=8.0.0`, extending the existing `tests/unit/test_mock_synth.py` module in place (no new test file — same function, same module).

**Target Platform**: Cross-platform (Windows, Linux, macOS) — unaffected, since all new literals are fixed strings with no OS- or locale-dependent formatting.

**Project Type**: Developer CLI tool / Python module (single project; no new modules).

**Performance Goals**: No measurable change — adds only fixed dict/tuple lookups per string node, same O(schema size) synthesis cost as today (<1ms per schema).

**Constraints**:
- **Constitution Principle I (Clear Idiomatic Code Over Abstractions)**: All three additions land inside the existing `_synthesize` function and its private helpers; no new module, class, or framework layer for what remains a small, single-purpose recursive function.
- **Constitution Principle II (Zero-LLM Determinism)**: Every new literal (format samples, `sample_<key>` fallback, `example`/`default` echoing) is a fixed constant or a mechanical string interpolation of data already in the schema — no randomness, no wall-clock reads, no LLM calls.
- **Constitution Principle VI (Comprehensive Testing)**: Existing tests whose expected values change under the new behavior MUST be updated (not deleted), and new tests MUST cover each of the three additions plus their precedence interactions with `const`/`enum`.
- **Quality Gates**: Zero diagnostics on `uv run ty check src/`; clean `uv run ruff check .` / `uv run ruff format --check .`; all `pre-commit` hooks pass.

**Scale/Scope**: Unchanged — synthesis operates on individual OpenAPI response schemas, typically a handful of properties deep; no scale concerns.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Constitution Gate | Requirement | Status | Verification Plan |
|-------------------|-------------|--------|-------------------|
| **Principle I: Clear Idiomatic Code** | No unnecessary abstractions, speculative frameworks, or new modules for a small, single-purpose change. | **PASS** | All changes stay inside `synth.py`'s existing recursive `_synthesize` function and private helpers; one new module-level constant table for format samples. |
| **Principle II: Zero-LLM Determinism** | New value-selection logic MUST be 100% deterministic and MUST NEVER invoke an LLM or use randomness/wall-clock data. | **PASS** | Format samples are fixed string constants; `sample_<key>` is mechanical f-string interpolation of the schema's own property key; `example`/`default` echoing is a direct literal passthrough. |
| **Principle VI: Comprehensive Testing** | 100% automated test coverage with `pytest`; no code change ships without corresponding tests. | **PASS** | `tests/unit/test_mock_synth.py` extended: 3 existing tests updated for their new expected values (see research.md §3), plus new tests for format-aware synthesis, key threading through arrays/rootless schemas, and `example`/`default` precedence (including against `const`/`enum`). |
| **Quality Gate: Static Typing (`ty`)** | `uv run ty check src/` must pass with zero diagnostics. | **PASS** | New code fully type-annotated, consistent with existing `synth.py` style. |
| **Quality Gate: Lint & Formatting (`ruff`)** | `uv run ruff check .` and `uv run ruff format --check .` must pass cleanly. | **PASS** | Verified during development and pre-commit hook runs. |

No violations — Complexity Tracking table is empty.

**Post-Design Re-Check** (after Phase 1): The finalized design (research.md, data-model.md, contracts/synth-contract.md) introduced one new module-level constant table (format→literal) and one new optional function parameter (`key`) — no new files, dependencies, or abstractions beyond what was anticipated above. All gates remain **PASS**.

---

## Project Structure

### Documentation (this feature)

```text
specs/012-mock-response-synthesis/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output: format literal choices, key-threading design, precedence order, existing-test impact
├── data-model.md        # Phase 1 output: format→literal table, key-resolution state, precedence order
├── quickstart.md        # Phase 1 output: verification scenarios & run commands
├── contracts/           # Phase 1 output: synthesizer function contract
│   └── synth-contract.md
├── checklists/
│   └── requirements.md  # Quality validation checklist (from /speckit-specify)
└── tasks.md              # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/specprobe/mock/
└── synth.py              # MODIFIED: format-aware strings, key-based fallback (threaded through recursion), example/default honoring

tests/unit/
└── test_mock_synth.py    # MODIFIED: 3 existing expectations updated, new tests added for all three additions + precedence
```

**Structure Decision**: No new modules, packages, or test files. This feature is a targeted, additive change to a single existing ~90-line pure function and its existing unit test module, consistent with Principle I (no premature abstraction) and with the feature's own explicit non-goal of not restructuring the required-only synthesis design.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *None* | No constitutional violations or unwarranted complexity introduced. | N/A |
