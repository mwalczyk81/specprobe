# Phase 0 Research: AWS Bedrock LLM Gateway Support

**Feature**: `009-bedrock-llm-backend`
**Date**: 2026-09-21
**Status**: Completed

---

## 1. Bedrock Cloud Opt-In Validation

### Context
Under SpecProbe Constitution Principle IV:
> "Cloud providers (e.g., OpenAI, Anthropic, Gemini) are strictly opt-in and MUST ONLY be activated when explicit API key environment variables are set by the user."

Currently, `LLMGateway._validate_cloud_opt_in()` checks:
- `openai/` or `gpt-` $\rightarrow$ `OPENAI_API_KEY` (or `self.api_key`)
- `anthropic/` or `claude-` $\rightarrow$ `ANTHROPIC_API_KEY` (or `self.api_key`)
- `gemini/` $\rightarrow$ `GEMINI_API_KEY` (or `self.api_key`)

Any model with prefix `bedrock/` falls through with no check, bypassing cloud opt-in verification completely.

### Decision
Add a `bedrock/` check in `_validate_cloud_opt_in()` that verifies an AWS region environment variable is present:
```python
elif model_lower.startswith("bedrock/"):
    if not (os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")):
        raise ValueError(
            f"Cloud model '{self.model}' requires AWS_REGION or AWS_DEFAULT_REGION environment variable. "
            "Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV."
        )
```

### Rationale
- Every AWS Bedrock API invocation via boto3 requires a target AWS region (e.g., `us-east-1`, `us-west-2`) to construct the regional service endpoint.
- Requiring `AWS_REGION` or `AWS_DEFAULT_REGION` confirms the user intentionally configured their AWS environment for Bedrock.
- Unlike static keys (`AWS_ACCESS_KEY_ID`), an AWS region is present in all valid deployment modes (static keys, named AWS profiles, AWS SSO, and IAM instance/task/pod roles).

### Alternatives Considered
- **Require `AWS_ACCESS_KEY_ID`**: Rejected because modern enterprise and container environments (ECS task roles, EKS pod identities, EC2 instance profiles, AWS IAM Identity Center SSO) do not set static `AWS_ACCESS_KEY_ID` in environment variables.
- **Require a dedicated `SPECPROBE_ALLOW_BEDROCK` flag**: Rejected as non-idiomatic; all other cloud providers rely on their standard cloud configuration environment variables.

---

## 2. Provider-Aware `api_base` Resolution & Passing

### Context
`LLMGateway` currently resolves `api_base` to:
`api_base or os.environ.get("SPECPROBE_LLM_API_BASE") or DEFAULT_LOCAL_API_BASE` (where `DEFAULT_LOCAL_API_BASE = "http://localhost:1234/v1"`).
This value is passed unconditionally to `litellm.completion(api_base=self.api_base, ...)`.

For Bedrock, LiteLLM routes requests to `bedrock-runtime.<region>.amazonaws.com` through boto3 SigV4 signing. Passing `api_base="http://localhost:1234/v1"` overrides LiteLLM's regional endpoint routing, causing calls to fail or attempt connecting to LM Studio.

### Decision
1. In `LLMGateway.__init__`:
   - If `api_base` is provided explicitly by the caller, use it.
   - Else if `os.environ.get("SPECPROBE_LLM_API_BASE")` is set, use that.
   - Else if `model.lower().startswith("bedrock/")`: set `api_base = None`.
   - Else: set `api_base = DEFAULT_LOCAL_API_BASE` (`"http://localhost:1234/v1"`).
2. In `LLMGateway.complete()`:
   - Call `litellm.completion()` passing `api_base=self.api_base`. When `self.api_base is None`, LiteLLM omits `api_base` from its underlying provider dispatch and uses native AWS SDK endpoint resolution.
   - In cache persistence, `cache.set(..., api_base=self.api_base)` persists `api_base: null` (JSON `null`) for Bedrock entries where `api_base` was omitted.

### Rationale
- Allows standard Bedrock invocations to use AWS SDK regional routing out of the box.
- Preserves full support for enterprise reverse proxies and VPC private endpoints (e.g. Fiserv Aitrium at `https://aitrium.internal.proxy/v1`) when `--api-base` or `SPECPROBE_LLM_API_BASE` is explicitly supplied.
- Completely backwards-compatible with local LM Studio workflows (`openai/local-model`), which continue to default to `"http://localhost:1234/v1"`.

---

## 3. CLI Option Defaults in `src/specprobe/cli.py`

### Context
In `src/specprobe/cli.py`, the Click option definition for `--api-base` on `generate`:
```python
@click.option(
    "--api-base",
    type=str,
    default=lambda: os.environ.get("SPECPROBE_LLM_API_BASE", "http://localhost:1234/v1"),
    show_default=True,
    ...
)
```
Click executes this default before invoking `generate_command`. As a result, `api_base` is *never* `None` inside `generate_command`, making it impossible for `LLMGateway` to know whether `--api-base` was explicitly passed or came from Click's fallback.

### Decision
Update the Click option definition in `src/specprobe/cli.py`:
```python
@click.option(
    "--api-base",
    type=str,
    default=None,
    show_default=False,
    help="Base endpoint URL for model requests (defaults to http://localhost:1234/v1 for local models; omitted for Bedrock).",
)
```
Also add optional `--model` and `--api-base` options to `audit_command` in `src/specprobe/cli.py` (both defaulting to `None`), passing them into `LLMGateway(model=model, api_base=api_base, ...)`.

### Rationale
- Defers default URL assignment to `LLMGateway`, where model-aware logic can determine the appropriate default (`None` for Bedrock, `http://localhost:1234/v1` for local models).
- Aligns `generate` and `audit` commands so both can target Bedrock models via CLI flags or environment variables identically.

---

## 4. Offline Testing & CI Determinism

### Context
Constitution Principle VI requires all CI and automated test suites to run completely offline without requiring live LLM instances or external network requests.

### Decision
- **Opt-In Unit Tests**: Test `LLMGateway._validate_cloud_opt_in()` with monkeypatched `os.environ` to verify:
  - Missing `AWS_REGION` and `AWS_DEFAULT_REGION` $\rightarrow$ `ValueError` containing descriptive error message.
  - Presence of `AWS_REGION` $\rightarrow$ passes.
  - Presence of `AWS_DEFAULT_REGION` $\rightarrow$ passes.
- **`api_base` Resolution Tests**:
  - Bedrock model without `api_base` $\rightarrow$ `gateway.api_base is None`.
  - Bedrock model with explicit `api_base` $\rightarrow$ `gateway.api_base == "https://custom.endpoint"`.
  - Bedrock model with `SPECPROBE_LLM_API_BASE` $\rightarrow$ `gateway.api_base == "https://custom.endpoint"`.
  - Local model without `api_base` $\rightarrow$ `gateway.api_base == "http://localhost:1234/v1"`.
- **Completion Call Mocking**:
  - Mock `litellm.completion` to verify that `litellm.completion(model="bedrock/...", api_base=None, ...)` is called.
- **Cache Persistence & Retrieval**:
  - Verify disk cache records a Bedrock completion and hits cache on repeat call without invoking `litellm.completion`.
- **CLI Integration Tests**:
  - Test `specprobe generate` with `--model bedrock/...` and mocked completion, verifying output test cases and error messaging when region is missing.
