# Quickstart Validation Guide: OpenAPI Operation Chunking

This guide describes the end-to-end validation steps and commands to verify that `specprobe chunk` works correctly against standard specifications, complex schemas, circular references, and large scale documents.

---

## 1. Prerequisites & Setup

Ensure Python 3.11+ and Poetry are installed, and project dependencies are resolved:

```bash
# Verify environment
python --version   # Must be >= 3.11
poetry --version

# Install dependencies and virtual environment
poetry install
```

---

## 2. Validation Scenarios

### Scenario A: Baseline Operation Chunking (JSONL Streaming)
Verify that a standard OpenAPI 3.0 specification is cleanly split into one line per operation chunk.

```bash
poetry run specprobe chunk tests/fixtures/valid_openapi_30.yaml > output.jsonl
```
**Expected Outcome**:
- `output.jsonl` contains exactly one JSON object per operation line.
- Inspect with `jq`:
  ```bash
  head -n 1 output.jsonl | jq .metadata
  ```
- Metadata includes `path`, `method`, `tags`, `operationId`, `security`, `deprecated`, `source_title`, `source_version`, and `estimated_tokens`.
- `components.schemas` in each line contains only schemas referenced by that line's operation.

---

### Scenario B: Spot Checking with `--op`
Verify that `--op` isolates a single operation and prints formatted JSON.

```bash
poetry run specprobe chunk tests/fixtures/valid_openapi_30.yaml --op getUserById
```
**Expected Outcome**:
- Outputs a single pretty-printed JSON chunk to `stdout`.
- Exit code is `0`.
- If an invalid operation ID is passed:
  ```bash
  poetry run specprobe chunk tests/fixtures/valid_openapi_30.yaml --op nonExistentOp
  ```
  Exits with code `1` and outputs `Error: Operation ID 'nonExistentOp' not found in specification.` to `stderr`.

---

### Scenario C: Exclusive Statistics Mode (`--stats`)
Verify that `--stats` displays human-readable summary metrics without streaming chunks.

```bash
poetry run specprobe chunk tests/fixtures/valid_openapi_30.yaml --stats
```
**Expected Outcome**:
- Emits formatted text table showing total operations, min/max/median/average chunk tokens, and warnings list.
- Does NOT print JSONL chunks to `stdout`.
- Exit code is `0`.

---

### Scenario D: Circular Reference Resolution
Verify that self-referencing and mutual circular schema references resolve cleanly without recursion errors.

```bash
poetry run specprobe chunk tests/fixtures/circular_spec.yaml
```
**Expected Outcome**:
- Executes without `RecursionError` or infinite loop.
- The chunk's schema contains `#/components/schemas/Node` pointers and defines `Node` once in `components.schemas`.

---

### Scenario E: Schema Composition (`allOf`, `oneOf`, `anyOf`) & Path Parameter Merging
Verify that polymorphic compositions and path-level parameters are properly extracted.

```bash
poetry run specprobe chunk tests/fixtures/composition_31.json --op createCompositeItem
```
**Expected Outcome**:
- Path-level parameters are present in the operation chunk's parameter list.
- Operation-level parameters override colliding path-level parameters.
- All composite sub-schemas under `allOf`/`oneOf`/`anyOf` are gathered into `components.schemas`.

---

### Scenario F: Swagger 2.0 Rejection
Verify that legacy Swagger 2.0 documents are rejected upfront.

```bash
poetry run specprobe chunk tests/fixtures/swagger_20.json
```
**Expected Outcome**:
- Command exits with status code `1`.
- Outputs clear message to `stderr`: `Error: Swagger 2.0 is not supported. SpecProbe requires OpenAPI 3.0 or 3.1.`

---

### Scenario G: External Reference Non-Fatal Warning
Verify that external file references produce non-fatal warnings with exit code 0.

```bash
poetry run specprobe chunk tests/fixtures/external_ref_spec.yaml
```
**Expected Outcome**:
- Warning printed to `stderr` indicating unsupported external `$ref`.
- The raw `$ref` string is preserved in the emitted chunk.
- Command exits with code `0`.

---

### Scenario H: Large-Scale Public Specification Check (GitHub / Stripe)
Verify performance and memory efficiency against a full-sized real-world API document.

```bash
poetry run specprobe chunk tests/fixtures/large_public_spec.json --stats
```
**Expected Outcome**:
- Processes hundreds of operations in under 2 seconds.
- Memory usage remains bounded and execution completes with exit code `0`.

---

## 3. Automated Test Suite Execution

Run all unit, integration, and fixture tests via `pytest`:

```bash
poetry run pytest -v
```
All tests must pass 100% per Constitution Principle VI.
