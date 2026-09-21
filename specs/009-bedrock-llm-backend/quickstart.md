# Quickstart Validation Guide: AWS Bedrock LLM Gateway Support

**Feature**: `009-bedrock-llm-backend`
**Date**: 2026-09-21
**Status**: Ready for Validation

This guide outlines runnable end-to-end scenarios to validate AWS Bedrock support in `specprobe generate` and `specprobe audit`. All automated tests and offline scenarios comply with SpecProbe Constitution Principles II, IV, and VI (zero external network calls during testing).

---

## Prerequisites & Setup

Ensure test environment has dependencies installed:

```powershell
uv sync
```

Verify baseline test suite and linters pass:

```powershell
uv run pytest
uv run ruff check
uv run ty check src/
```

---

## Validation Scenarios

### Scenario 1: Cloud Opt-In Rejection on Missing AWS Region (Principle IV)

**Objective**: Verify that targeting a Bedrock model without setting `AWS_REGION` or `AWS_DEFAULT_REGION` fails immediately with an informative error before initiating inference.

**Execution**:

```powershell
# Ensure AWS region variables are unset
Remove-Item Env:\AWS_REGION -ErrorAction SilentlyContinue
Remove-Item Env:\AWS_DEFAULT_REGION -ErrorAction SilentlyContinue

# Attempt test generation with a Bedrock model
uv run specprobe generate tests/fixtures/search_full_results.json --model "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
```

**Expected Outcome**:
- Process exits with non-zero exit code (`1`).
- Error output on stderr:
  `Error: Gateway initialization failed: Cloud model 'bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0' requires AWS_REGION or AWS_DEFAULT_REGION environment variable. Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV.`

---

### Scenario 2: Successful Opt-In and `api_base` Omission (boto3 Native Routing)

**Objective**: Verify that when `AWS_REGION` is present, `LLMGateway` accepts the Bedrock model and omits `api_base` (passing `None` to LiteLLM) rather than defaulting to `http://localhost:1234/v1`.

**Execution (Automated Unit Test)**:

```powershell
uv run pytest tests/unit/generator/test_bedrock_gateway.py -k "test_bedrock_api_base_omitted"
```

**Expected Outcome**:
- Test passes.
- Inspected LiteLLM call arguments verify `api_base=None` (or not present in kwargs).

---

### Scenario 3: Custom Proxy / Aitrium `--api-base` Passthrough

**Objective**: Verify that when a user explicitly supplies `--api-base` (or `SPECPROBE_LLM_API_BASE`) for an enterprise proxy (such as Fiserv Aitrium), the gateway preserves and forwards the explicit URL.

**Execution (Automated Unit Test)**:

```powershell
uv run pytest tests/unit/generator/test_bedrock_gateway.py -k "test_bedrock_explicit_api_base_preserved"
```

**Expected Outcome**:
- Test passes.
- Inspected LiteLLM call arguments verify `api_base="https://aitrium.internal.proxy/v1"`.

---

### Scenario 4: Local Model Defaults Preserved (Backward Compatibility)

**Objective**: Verify that omitting `--api-base` for standard local models (`openai/local-model`) continues to resolve to `http://localhost:1234/v1`.

**Execution (Automated Unit Test)**:

```powershell
uv run pytest tests/unit/generator/test_gateway.py -k "test_local_default_api_base"
```

**Expected Outcome**:
- Test passes.
- Gateway `api_base` is `"http://localhost:1234/v1"`.

---

### Scenario 5: End-to-End Disk Cache Persistence with Bedrock Identifier

**Objective**: Verify that responses for Bedrock completions are cached to disk using the canonical hash of the prompt, Bedrock model ID, and temperature, and that cache hits replay without invoking the LLM.

**Execution**:

```powershell
uv run pytest tests/unit/generator/test_bedrock_gateway.py -k "test_bedrock_disk_cache_replay"
```

**Expected Outcome**:
- Test passes.
- First invocation records cache file in cache directory with `model: "bedrock/..."` and `api_base: null`.
- Second invocation returns cached completion with zero calls to LiteLLM.

---

### Scenario 6: End-to-End `audit` Integration with Bedrock Model

**Objective**: Verify that `specprobe audit` accepts `--model bedrock/...`, validates AWS opt-in, and completes critique using mock/cached responses.

**Execution**:

```powershell
uv run pytest tests/integration/test_bedrock_cli.py -k "test_audit_with_bedrock_model"
```

**Expected Outcome**:
- Test passes.
- Command completes with exit code 0 and emits valid JSONL critique records.

---

## Full Quality Gate Checklist

Run the complete verification suite across linting, type-checking, and offline tests:

```powershell
# 1. Formatting and lint checks
uv run ruff check
uv run ruff format --check
uv run pre-commit run --all-files

# 2. Static type checks
uv run ty check src/

# 3. Full automated test suite
uv run pytest
```

All commands must exit cleanly with code 0 and zero warnings/errors.
