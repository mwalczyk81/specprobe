# Technical Research: LLM Test Generation & Filter-Only Search

**Feature**: `003-generate-llm-tests`  
**Date**: 2026-09-19  
**Status**: Completed  

---

## 1. LiteLLM Integration & Local-First Gateway

### Context & Requirements
SpecProbe Constitution Principle IV dictates:
- All LLM invocations MUST route through LiteLLM (`litellm`) as the single unified gateway; vendor SDKs are prohibited.
- Default execution MUST target a local LM Studio endpoint (`http://localhost:1234/v1`) without requiring API keys or external network connectivity.
- Cloud providers (OpenAI, Anthropic, Gemini) are strictly opt-in, activated only when explicit environment variables are set by the user.

### Research Findings
LiteLLM provides native abstraction for OpenAI-compatible local servers (such as LM Studio, Ollama, vLLM, or LocalAI) by prefixing the model with `openai/` and passing `api_base`.

1. **Local LM Studio Target**:
   ```python
   import litellm

   response = litellm.completion(
       model="openai/local-model",
       api_base="http://localhost:1234/v1",
       api_key="lm-studio",  # LM Studio does not require a real key, but OpenAI client needs non-empty string
       messages=[{"role": "user", "content": prompt}],
       temperature=0.0,
   )
   ```
2. **Cloud Opt-In Resolution**:
   If the user specifies an explicit model (e.g. `--model gpt-4o` or `--model claude-3-5-sonnet-20241022` or `--model gemini/gemini-2.5-flash`), LiteLLM automatically inspects the environment for standard vendor keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`). If no credentials exist, LiteLLM raises an `AuthenticationError`.
3. **Configuration Precedence**:
   CLI options (`--model`, `--api-base`) take highest precedence, followed by environment variables (`SPECPROBE_LLM_MODEL`, `SPECPROBE_LLM_API_BASE`), falling back to defaults:
   - Default Model: `openai/local-model`
   - Default API Base: `http://localhost:1234/v1`

### Decision
Implement a lightweight `LLMGateway` class in `src/specprobe/generator/gateway.py` that encapsulates LiteLLM dispatch, endpoint resolution, and credential validation.

---

## 2. Cryptographic Disk Caching Architecture

### Context & Requirements
Constitution Principle IV mandates:
- "All LLM calls MUST be cached to local disk, keyed deterministically on a cryptographic hash of the prompt/message payload and model identifier. Cached hits MUST return immediately without performing inference calls."
- CI pipelines and regression suites MUST run offline without a live LLM runtime by replaying pre-recorded disk cache fixtures.

### Research Findings & Design
1. **Cache Key Determinism**:
   The cache key must uniquely capture the semantic inputs that influence model generation, strictly complying with Constitution Principle IV (hash of the prompt/message payload, model identifier, and sampling temperature):
   - Model identifier (`model`)
   - Complete message history (`messages`: list of dicts with `role` and `content`)
   - Generation parameters (e.g. `temperature`)
   
   **Critical Design Rule**: The endpoint URL (`api_base`) MUST NOT be included in the hashed payload. `api_base` is merely a transport routing detail, not a semantic generation parameter. Omitting `api_base` from the hash ensures that cache fixtures recorded locally (e.g. against `http://localhost:1234/v1`) hit deterministically in CI environments where no live model server is running and offline fixtures are replayed.
   
   To avoid hashing discrepancies caused by dictionary key ordering or whitespace, messages and metadata are serialized to canonical JSON (`sort_keys=True`, `separators=(',', ':')`) and hashed using SHA-256:
   ```python
   import hashlib
   import json

   payload = {
       "messages": messages,
       "model": model,
       "temperature": temperature,
   }
   canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
   cache_key = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
   ```

2. **Storage Layout & Persistence**:
   - Default directory: `.specprobe/cache` relative to working directory, overrideable via `--cache-dir` option or `SPECPROBE_CACHE_DIR` environment variable.
   - Cache file naming: `<cache_dir>/<cache_key>.json`.
   - Cache file payload format (`api_base` is preserved in the file as metadata for inspection/debugging, but is not part of the key):
     ```json
     {
       "cache_key": "a1b2c3d4...",
       "model": "openai/local-model",
       "api_base": "http://localhost:1234/v1",
       "messages": [...],
       "temperature": 0.0,
       "completion_text": "{\n  \"operation_id\": ...\n}",
       "created_at": "2026-09-19T08:30:00Z"
     }
     ```
3. **Atomic Writes**:
   To prevent corrupt or partial cache entries when a user cancels execution (Ctrl+C), write to a temporary file in the same directory (`.<cache_key>.tmp`) and atomically rename (`os.replace`) to the final `<cache_key>.json`.
4. **Bypass Flag (`--no-cache`)**:
   When `--no-cache` is specified, skip reading from cache, invoke live inference, and overwrite/update the cache entry upon completion.

### Decision
Implement `DiskCache` in `src/specprobe/generator/cache.py` providing `get(key) -> str | None` and `set(key, payload, completion_text) -> None`.

---

## 3. Strict Pydantic Schema & Traceability

### Context & Requirements
Constitution Principle V mandates:
- Every generated test case must be parsed and strictly validated through a defined Pydantic model before use.
- Every generated test case must explicitly identify and link to the target operation (`operationId` or method/path). Anonymous test cases are prohibited.
- Clarification Session 2026-09-19 established that each operation generates a single primary happy-path (2xx success) test case.

### Schema Design
```python
from typing import Any
from pydantic import BaseModel, Field


class RequestFixture(BaseModel):
    """Concrete input fixtures for executing the API request."""

    path_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved path parameters substituting placeholders in the endpoint path.",
    )
    query_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Query string parameters conforming to the endpoint schema.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP request headers (e.g. Content-Type, Accept).",
    )
    body: Any | None = Field(
        default=None,
        description="Concrete request body payload conforming to the endpoint request schema.",
    )


class ResponseAssertion(BaseModel):
    """Verification assertions for evaluating the API response."""

    status_code: int = Field(
        description="Expected HTTP response status code (targeting 2xx success).",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Expected response headers (e.g. Content-Type).",
    )
    schema_shape: dict[str, Any] | None = Field(
        default=None,
        description="Expected JSON schema structure or expected field assertions for the response.",
    )


class GeneratedTestCase(BaseModel):
    """Traceable, executable API test case definition."""

    operation_id: str = Field(
        description="Traceable identifier of the target API operation.",
    )
    description: str = Field(
        description="Plain-language description of the test scenario.",
    )
    request: RequestFixture = Field(
        description="Proposed request fixtures.",
    )
    response: ResponseAssertion = Field(
        description="Expected response assertions.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Operational tags inherited from the OpenAPI specification.",
    )
```

### Decision
Define these models in `src/specprobe/generator/models.py`.

---

## 4. Prompt Engineering & JSON Extraction Strategy

### Context & Requirements
- Language models must receive an informative representation of the operation without distracting raw JSON schema noise.
- Models must produce clean JSON without conversational preamble or formatting chatter.
- JSON must be extracted reliably even if wrapped in markdown code fences (````json ... ````).

### Prompt Design
The prompt incorporates:
1. **System Prompt**: Directs the model to act as an expert API testing engineer. Mandates outputting ONLY valid JSON matching the exact schema definition.
2. **Operation Context**:
   - HTTP Method and Path
   - Operation ID
   - Summary and Description
   - Parameters (name, in, required, schema type/format/enum, description)
   - Request Body schema summary (content types, required fields, properties)
   - Success Responses (200/201 schema shapes and descriptions)
3. **Extraction Helper**:
   Strip leading/trailing markdown fences if present (`re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())`) before passing to `GeneratedTestCase.model_validate_json()`.

### Decision
Implement `PromptBuilder` in `src/specprobe/generator/prompt.py`.

---

## 5. Single-Retry Self-Correction Protocol

### Context & Requirements
Constitution Principle V:
- "If schema validation fails, the system MUST retry the LLM invocation exactly once, providing the schema validation error context to allow self-correction. If the retry fails, the operation MUST immediately fail with a descriptive error."
- Clarification Session 2026-09-19 confirmed: Single operation failures log to `stderr` and skip the failed operation without aborting the entire batch.

### Protocol Implementation
```python
def generate_for_chunk(
    chunk: OperationChunk, gateway: LLMGateway, cache: DiskCache
) -> GeneratedTestCase | None:
    prompt_messages = build_initial_messages(chunk)

    # Attempt 1
    raw_completion = gateway.complete(prompt_messages, cache)
    test_case, error_msg = try_validate(raw_completion, chunk.operation.operation_id)
    if test_case is not None:
        return test_case

    # Retry Attempt (Exactly once)
    retry_messages = list(prompt_messages)
    retry_messages.append({"role": "assistant", "content": raw_completion})
    retry_messages.append(
        {
            "role": "user",
            "content": (
                f"The previous output failed strict Pydantic schema validation with the following error:\n"
                f"{error_msg}\n\n"
                f"Please fix the validation error and return ONLY the corrected, valid JSON object."
            ),
        }
    )

    retry_completion = gateway.complete(retry_messages, cache)
    retry_case, retry_error = try_validate(retry_completion, chunk.operation.operation_id)
    if retry_case is not None:
        return retry_case

    # Second failure: Log to stderr and skip
    sys.stderr.write(
        f"Validation failed for operation '{chunk.operation.operation_id}' after retry: {retry_error}\n"
    )
    return None
```

### Decision
Implement the single-retry loop in `src/specprobe/generator/engine.py`.

---

## 6. Unranked Specification Retrieval via Filter-Only Search

### Context & Requirements
- `specprobe search` query argument becomes optional (`required=False`, default `None`).
- When `query is None`, require at least one metadata filter (`--tag`, `--method`, `--deprecated`, `--source-title`, `--source-version`).
- When query is omitted, return all matching chunks unranked (`score=0.0`) without limit truncation by default (unless `--limit <N>` is explicitly specified).
- Bypasses vector embedding and reranking entirely (0 model inference).

### Technical Mechanism in Qdrant
In Qdrant, retrieving points by filter criteria without vector similarity scoring is performed via `client.scroll()`:
```python
points, next_page_offset = client.scroll(
    collection_name=self.collection_name,
    scroll_filter=q_filter,
    limit=effective_limit or 10_000,
    with_payload=True,
    with_vectors=False,
)
```
If `effective_limit` is None, `scroll()` can iterate through pagination offsets to retrieve 100% of points matching the filter.

### Decision
Add `search_unranked()` to `src/specprobe/search/engine.py` and update `search_command()` in `src/specprobe/cli.py`.
