# Data Model: AWS Bedrock LLM Gateway Support

**Feature**: `009-bedrock-llm-backend`
**Date**: 2026-09-21
**Status**: Ready for Implementation

---

## 1. Gateway Configuration & State Entities

### `LLMGatewayConfig` (Conceptual Configuration Entity)

Represents the resolved runtime configuration used by `LLMGateway` for dispatching completion requests to LiteLLM.

| Field | Type | Optional | Default | Description |
|---|---|---|---|---|
| `model` | `str` | No | `"openai/local-model"` | Model identifier passed to LiteLLM. For Bedrock, starts with `bedrock/` (e.g. `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`). |
| `api_base` | `str \| None` | Yes | `None` for Bedrock; `"http://localhost:1234/v1"` for local models | Endpoint URL passed to `litellm.completion()`. Omitted (`None`) for Bedrock unless explicitly specified. |
| `api_key` | `str \| None` | Yes | `None` (or `"lm-studio"` for local endpoints) | API credential string. Not required for Bedrock (which uses AWS IAM/SigV4 via boto3). |
| `temperature` | `float` | No | `0.0` | Sampling temperature for model completions. |

### Validation & Resolution Rules

1. **Provider Classification**:
   - `model.lower().startswith("bedrock/")`: Classified as AWS Bedrock cloud provider.
   - `is_local_endpoint(api_base)`: Classified as local/private endpoint.
   - `openai/`, `gpt-`, `anthropic/`, `claude-`, `gemini/`: Classified as respective commercial cloud providers.
2. **Opt-In Validation**:
   - For `bedrock/`:
     - Checks `os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")`.
     - If neither is present, raises `ValueError`:
       `"Cloud model '{model}' requires AWS_REGION or AWS_DEFAULT_REGION environment variable. Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV."`
3. **Endpoint Resolution Logic**:
   ```python
   if api_base is not None:
       resolved_api_base = api_base
   elif os.environ.get("SPECPROBE_LLM_API_BASE"):
       resolved_api_base = os.environ["SPECPROBE_LLM_API_BASE"]
   elif resolved_model.lower().startswith("bedrock/"):
       resolved_api_base = None
   else:
       resolved_api_base = DEFAULT_LOCAL_API_BASE
   ```

---

## 2. Disk Cache Record Entity

Stored in `.specprobe/cache/<sha256>.json` as defined in `DiskCache`.

| Field | Type | Description |
|---|---|---|
| `cache_key` | `str` | SHA-256 hash of canonical JSON `[messages, model, temperature]`. |
| `model` | `str` | Exact model identifier (e.g. `"bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"`). |
| `api_base` | `str \| None` | Endpoint URL or `null` if omitted. |
| `messages` | `list[dict[str, str]]` | Prompt messages array. |
| `temperature` | `float` | Sampling temperature. |
| `completion_text` | `str` | Raw completion output text. |
| `created_at` | `str` | ISO 8601 UTC timestamp. |

---

## 3. CLI Command Options Entity (Click Interface)

### `specprobe generate` / `specprobe audit` CLI Options

| Option | Flag | Type | Default | Precedence |
|---|---|---|---|---|
| Model | `--model` | `str` | `"openai/local-model"` | CLI flag > `SPECPROBE_LLM_MODEL` > Default |
| Base URL | `--api-base` | `str \| None` | `None` | CLI flag > `SPECPROBE_LLM_API_BASE` > Model-aware fallback (`None` for Bedrock, `"http://localhost:1234/v1"` for local) |
| Temperature | `--temperature` | `float` | `0.0` | CLI flag > `SPECPROBE_LLM_TEMPERATURE` > Default |
| Cache Dir | `--cache-dir` | `Path` | `.specprobe/cache` (or `.specprobe/cache/audit` for audit) | CLI flag > `SPECPROBE_CACHE_DIR` / `SPECPROBE_AUDIT_CACHE_DIR` > Default |
| No Cache | `--no-cache` | `bool` | `False` | CLI flag > `SPECPROBE_NO_CACHE` > Default |
