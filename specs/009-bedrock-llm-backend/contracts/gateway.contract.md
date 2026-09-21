# Interface Contract: LLMGateway

**Component**: `specprobe.generator.gateway.LLMGateway`
**Feature**: `009-bedrock-llm-backend`
**Date**: 2026-09-21

---

## 1. Class Initialization

```python
class LLMGateway:
    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> None: ...
```

### Preconditions
- If `model` starts with `bedrock/` (case-insensitive):
  - At least one of `AWS_REGION` or `AWS_DEFAULT_REGION` MUST be set in `os.environ`.
  - If neither is set, raises `ValueError` with message:
    `"Cloud model '{model}' requires AWS_REGION or AWS_DEFAULT_REGION environment variable. Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV."`
- If `model` starts with `openai/` or `gpt-`:
  - `OPENAI_API_KEY` or `self.api_key` MUST be set.
- If `model` starts with `anthropic/` or `claude-`:
  - `ANTHROPIC_API_KEY` or `self.api_key` MUST be set.
- If `model` starts with `gemini/`:
  - `GEMINI_API_KEY` or `self.api_key` MUST be set.

### Postconditions
- `self.model`: Resolved string identifier.
- `self.api_base`:
  - If explicitly passed (not `None`): equals the passed string.
  - Else if `SPECPROBE_LLM_API_BASE` in `os.environ`: equals the env var string.
  - Else if `self.model.lower().startswith("bedrock/")`: `None`.
  - Else: `"http://localhost:1234/v1"` (`DEFAULT_LOCAL_API_BASE`).
- `self.temperature`: Float sampling temperature (defaults to `0.0`).
- `self.api_key`: String API key or `None` (defaults to `"lm-studio"` for local endpoints).

---

## 2. Method `complete`

```python
def complete(
    self,
    messages: list[dict[str, str]],
    cache: Any | None = None,
) -> str: ...
```

### Invocation Behavior
1. Check disk cache if `cache` is provided. If cache hit, return cached completion string immediately.
2. If cache miss, invoke `litellm.completion`:
   - `model=self.model`
   - `api_base=self.api_base` (omitted or `None` when `self.api_base is None`)
   - `api_key=self.api_key`
   - `messages=messages`
   - `temperature=self.temperature`
3. If invocation succeeds and cache is provided, persist result to cache with `api_base=self.api_base`.
4. If invocation fails:
   - If `is_local_endpoint(self.api_base)` is True: raise `ConnectionError` with local diagnostic message.
   - Else: raise `RuntimeError(f"LLM completion call failed for model '{self.model}': {exc}")`.
