# Interface Contract: CLI Options for LLM Commands

**Component**: `specprobe.cli` (`generate` and `audit` commands)
**Feature**: `009-bedrock-llm-backend`
**Date**: 2026-09-21

---

## 1. `specprobe generate` Command Contract

### Signature & Relevant Options

```shell
specprobe generate [RESULTS_FILE] [OPTIONS]
```

| Option | Flag | Type | Click Default | Description |
|---|---|---|---|---|
| Model | `--model` | `str` | `lambda: os.environ.get("SPECPROBE_LLM_MODEL", "openai/local-model")` | Model identifier string passed to LiteLLM. |
| Base URL | `--api-base` | `str \| None` | `None` | Base endpoint URL for model requests (defaults to `http://localhost:1234/v1` for local models; omitted for Bedrock). |
| Temperature | `--temperature` | `float` | `lambda: float(os.environ.get("SPECPROBE_LLM_TEMPERATURE", "0.0"))` | Sampling temperature for model completions. |
| Cache Dir | `--cache-dir` | `Path` | `lambda: os.environ.get("SPECPROBE_CACHE_DIR", ".specprobe/cache")` | Directory where LLM call cache files are stored. |
| No Cache | `--no-cache` | `bool` | `lambda: os.environ.get("SPECPROBE_NO_CACHE", "false") ...` | Bypass disk cache entries. |

### Endpoint Resolution Precedence for `generate`

1. Explicit `--api-base <url>` CLI option.
2. `SPECPROBE_LLM_API_BASE` environment variable.
3. If `--model` (or `SPECPROBE_LLM_MODEL`) begins with `bedrock/`: `None` (omitted from LiteLLM call).
4. Otherwise (local/default model): `http://localhost:1234/v1`.

### Exit Codes & Error Reporting

- **Exit Code 0**: Successful test generation (or empty input).
- **Exit Code 1**:
  - Cloud opt-in validation failure (e.g. `bedrock/*` model specified without `AWS_REGION` or `AWS_DEFAULT_REGION`).
    Output on `stderr`:
    ```text
    Error initializing LLM gateway: Cloud model 'bedrock/<model-id>' requires AWS_REGION or AWS_DEFAULT_REGION environment variable. Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV.
    ```
  - Unreachable endpoint / invalid input / missing files.

---

## 2. `specprobe audit` Command Contract

### Signature & Relevant Options

```shell
specprobe audit [ARTIFACT_FILE] [OPTIONS]
```

| Option | Flag | Type | Click Default | Description |
|---|---|---|---|---|
| Model | `--model` | `str \| None` | `None` | Model identifier string passed to LiteLLM (or `SPECPROBE_LLM_MODEL`). |
| Base URL | `--api-base` | `str \| None` | `None` | Base endpoint URL for model requests (or `SPECPROBE_LLM_API_BASE`). |
| Summary | `--summary` | `bool` | `False` | Render human-readable summary table to stderr. |
| Cache Dir | `--cache-dir` | `Path` | `None` | Directory for audit cache (defaults to `SPECPROBE_AUDIT_CACHE_DIR` or `.specprobe/cache/audit`). |
| No Cache | `--no-cache` | `bool` | `False` | Bypass LLM disk cache. |

### Endpoint Resolution Precedence for `audit`

1. Explicit `--api-base <url>` CLI option.
2. `SPECPROBE_LLM_API_BASE` environment variable.
3. If `--model` (or `SPECPROBE_LLM_MODEL`) begins with `bedrock/`: `None` (omitted from LiteLLM call).
4. Otherwise: `http://localhost:1234/v1`.

### Exit Codes & Error Reporting

- **Exit Code 0**: Audit completed successfully.
- **Exit Code 1**:
  - Cloud opt-in validation failure (e.g. `bedrock/*` model specified without `AWS_REGION` or `AWS_DEFAULT_REGION`).
    Output on `stderr`:
    ```text
    Error initializing LLM gateway: Cloud model 'bedrock/<model-id>' requires AWS_REGION or AWS_DEFAULT_REGION environment variable. Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV.
    ```
  - Specification or artifact file loading error / execution failure.

---

## 3. Behavior Matrix

| Command | Model Specified | Region Env Set? | Explicit `--api-base`? | Resulting `api_base` Passed to LiteLLM | Expected Behavior |
|---|---|---|---|---|---|
| `generate` | `openai/local-model` | N/A | No | `"http://localhost:1234/v1"` | Connects to local LM Studio server. |
| `generate` | `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` | No | No | N/A | Exits with code 1; opt-in error on stderr. |
| `generate` | `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` | Yes (`us-east-1`) | No | `None` (omitted) | LiteLLM resolves AWS SDK endpoint via boto3. |
| `generate` | `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` | Yes (`us-east-1`) | Yes (`https://aitrium.internal.proxy/v1`) | `"https://aitrium.internal.proxy/v1"` | LiteLLM routes through custom proxy endpoint. |
| `audit` | `bedrock/amazon.nova-pro-v1:0` | No | No | N/A | Exits with code 1; opt-in error on stderr. |
| `audit` | `bedrock/amazon.nova-pro-v1:0` | Yes (`us-west-2`) | No | `None` (omitted) | LiteLLM completes critique via Bedrock; cache records model. |
