# Implementation Plan: AWS Bedrock LLM Gateway Support

**Branch**: `009-bedrock-llm-backend` | **Date**: 2026-09-21 | **Spec**: [specs/009-bedrock-llm-backend/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/009-bedrock-llm-backend/spec.md)

**Input**: Feature specification from [specs/009-bedrock-llm-backend/spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/009-bedrock-llm-backend/spec.md)

---

## Summary

Add AWS Bedrock support as an LLM backend for `specprobe generate` and `specprobe audit` via the unified LiteLLM gateway (`src/specprobe/generator/gateway.py`).

The technical approach comprises four key enhancements:
1. **Cloud Opt-In Enforcement (Principle IV)**: Update `LLMGateway._validate_cloud_opt_in()` to detect `bedrock/*` models and verify that either `AWS_REGION` or `AWS_DEFAULT_REGION` is set in the environment. If missing, fail fast with a descriptive error before initiating inference.
2. **Provider-Aware `api_base` Resolution**: In `LLMGateway.__init__`, omit `api_base` (`None`) when targeting `bedrock/*` models unless the user explicitly provided an endpoint via CLI `--api-base` or `SPECPROBE_LLM_API_BASE` (e.g. for Fiserv Aitrium proxy). Local models (`openai/local-model` or private endpoints) continue to default to `http://localhost:1234/v1`.
3. **CLI Default Decoupling**: Update Click option `--api-base` in `src/specprobe/cli.py` for `generate` to default to `None` rather than eagerly injecting `http://localhost:1234/v1`. Add `--model` and `--api-base` options to `audit_command` with default `None`, establishing parity across both LLM-powered commands.
4. **Offline CI & Test Coverage (Principle VI)**: Deliver comprehensive unit and integration tests using monkeypatched environment variables, mocked `litellm.completion`, and disk cache replay fixtures with zero external network calls.

---

## Technical Context

**Language/Version**: Python >= 3.11, < 4.0 (Dev on Python 3.14.7, CI on Python 3.11 and 3.12)

**Primary Dependencies**: `litellm`, `click`, `pydantic`, `rich`, `boto3` (transitive via LiteLLM Bedrock extras)

**Storage**: File-based canonical JSON disk cache in `.specprobe/cache` and `.specprobe/cache/audit`

**Testing**: `pytest`, `hypothesis`

**Target Platform**: Windows 11 (dev workstation), Linux (Ubuntu CI runner)

**Project Type**: Developer CLI tool and Python library

**Performance Goals**: Negligible latency impact (< 2ms overhead during gateway initialization and endpoint resolution); zero network latency in offline CI.

**Constraints**:
- SpecProbe Constitution Principle IV: Cloud providers strictly opt-in; Bedrock models MUST NOT execute without explicit AWS region configuration.
- SpecProbe Constitution Principles II & VI: Zero external network calls during automated testing; mock `litellm.completion` and test disk cache replay.
- Backward compatibility: Existing local LM Studio defaults (`openai/local-model` with `http://localhost:1234/v1`) must remain completely undisturbed.

**Scale/Scope**: Two existing source files modified (`src/specprobe/generator/gateway.py`, `src/specprobe/cli.py`), two dedicated test files added (`tests/unit/generator/test_bedrock_gateway.py`, `tests/integration/test_bedrock_cli.py`).

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Plan Compliance | Status |
|---|---|---|---|
| **I. Clear Idiomatic Code** | Clean, readable Python 3.11+ without speculative abstractions | Minimal, idiomatic additions to existing gateway resolution logic and Click options | PASS |
| **II. Deterministic Artifact Generation** | Zero-LLM deterministic export; canonical hashing | Exporters unaffected; Bedrock cache keys deterministically hashed from prompt, model, and temperature | PASS |
| **III. Local-First Privacy & Compute** | Local compute default; external calls strictly opt-in | Default model remains `openai/local-model` at `http://localhost:1234/v1`; Bedrock requires explicit model flag AND AWS region | PASS |
| **IV. Unified Gateway & Opt-In** | All LLM calls through LiteLLM; cloud strictly opt-in | LiteLLM gateway routes Bedrock calls; opt-in gate strictly verified via `AWS_REGION` / `AWS_DEFAULT_REGION` | PASS |
| **V. Strict Pydantic Validation** | Structured LLM output validated against Pydantic models with single retry | Generation and audit output validation loops unchanged | PASS |
| **VI. Comprehensive Testing** | Every feature ships with automated tests; zero live external calls in CI | Dedicated offline test suites for gateway opt-in, endpoint omission, Aitrium proxy passthrough, and CLI integration | PASS |

*All gates pass with zero constitutional violations.*

---

## Project Structure

### Documentation (this feature)

```text
specs/009-bedrock-llm-backend/
├── plan.md              # This implementation plan
├── research.md          # Phase 0: Bedrock opt-in signal, api_base resolution, and CLI decoupling
├── data-model.md        # Phase 1: LLMGatewayConfig, cache record, and CLI options entities
├── quickstart.md        # Phase 1: Runnable validation scenarios and quality gates
├── contracts/
│   ├── gateway.contract.md  # LLMGateway interface contract
│   └── cli.contract.md      # CLI options contract for generate and audit
└── checklists/
    └── requirements.md  # Requirements verification checklist
```

### Source Code (repository root)

```text
src/specprobe/
├── cli.py                     # Decouple --api-base default to None; add --model/--api-base to audit
└── generator/
    └── gateway.py             # Add Bedrock opt-in check and model-aware api_base resolution

tests/
├── unit/
│   └── generator/
│       ├── test_gateway.py           # Existing local & cloud provider tests
│       └── test_bedrock_gateway.py   # Dedicated unit tests for Bedrock opt-in and api_base resolution
└── integration/
    ├── test_cli.py                   # Existing CLI integration tests
    └── test_bedrock_cli.py           # Dedicated CLI integration tests for generate and audit with Bedrock
```

**Structure Decision**: Single project layout matching SpecProbe existing standard conventions. Core changes are localized to `src/specprobe/generator/gateway.py` and `src/specprobe/cli.py`, with corresponding unit and integration test suites.

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No constitutional violations identified.*
