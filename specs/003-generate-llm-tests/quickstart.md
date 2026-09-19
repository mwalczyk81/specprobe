# Quickstart: LLM Test Generation & Filter-Only Search

**Feature**: `003-generate-llm-tests`  
**Date**: 2026-09-19  
**Status**: Ready for Validation  

This guide demonstrates end-to-end usage of the `specprobe generate` command and the updated filter-only `specprobe search` command.

---

## 1. Prerequisites

1. **Environment**: Python 3.11+ managed by `uv`.
2. **Local Model Runtime (Optional for Live Execution)**:
   - LM Studio running with a model loaded (e.g. Meta-Llama-3.1-8B-Instruct or similar).
   - Local server listening at `http://localhost:1234/v1`.
3. **Offline / CI Execution**:
   - Automated tests run completely offline by loading pre-recorded cache records from tests/fixtures or disk cache mocks.

---

## 2. Validation Scenarios

### Scenario 1: Unranked Specification Extraction via Filter-Only Search
Verify that `specprobe search` can retrieve an entire specification without requiring a text query or applying relevance rank limits.

```bash
# 1. Index a sample specification
specprobe chunk tests/fixtures/valid_openapi_30.yaml | specprobe index

# 2. Extract all operations from the spec unranked
specprobe search --source-title "Sample Pet Store API" --source-version "1.0.0" --full > search_results.json

# 3. Verify output
# The resulting search_results.json contains an unranked array where each item has score: 0.0 and embeds the complete 'chunk'.
```

### Scenario 2: Generate Test Cases via Pipeline
Pipe unranked search results directly into `specprobe generate` to produce streaming JSONL test cases.

```bash
# Pipe search output directly into generate
specprobe search --source-title "Sample Pet Store API" --full | specprobe generate > generated_tests.jsonl

# Inspect the generated test cases
head -n 2 generated_tests.jsonl
```

Expected output for each line in `generated_tests.jsonl`:
```json
{"operation_id":"getPetById","description":"Retrieve an existing pet by its unique integer identifier","request":{"path_params":{"petId":1},"query_params":{},"headers":{"Accept":"application/json"},"body":null},"response":{"status_code":200,"headers":{"Content-Type":"application/json"},"schema_shape":{"type":"object","properties":["id","name","tag"]}},"tags":["pets"]}
```

### Scenario 3: Verify Zero-Compute Disk Caching
Verify that subsequent runs retrieve completions immediately from the local disk cache without invoking the model server.

```bash
# First run: writes to .specprobe/cache/<hash>.json
specprobe generate search_results.json > out1.jsonl

# Second run: instant response from disk cache (0 LLM inference calls)
time specprobe generate search_results.json > out2.jsonl

# Verify output consistency
diff out1.jsonl out2.jsonl
```

### Scenario 4: Force Cache Refresh via `--no-cache`
Verify that `--no-cache` bypasses existing cache records and requests fresh completions.

```bash
specprobe generate search_results.json --no-cache > out_refreshed.jsonl
```

### Scenario 5: Input Guardrails & Rejection of Compact Search Results
Verify that attempting to generate from search results without `--full` is rejected safely.

```bash
# Compact search (omitting --full)
specprobe search "pets" > compact_results.json

# Attempt generate: should fail with code 1 and error on stderr
specprobe generate compact_results.json
# Error: Incompatible search results: missing full operation chunk schemas. Run 'specprobe search --full' before generating.
```

---

## 3. Running Automated Tests

Run the test suite offline with `pytest`:
```bash
# Run all tests (including offline generator tests with cache fixtures)
uv run pytest

# Check linting and formatting
uv run ruff check .
uv run ruff format --check .
```
