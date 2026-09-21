# Quickstart Validation: Negative Input & Resource Test Generation (400 & 404)

**Feature**: `008-negative-input-tests`
**Date**: 2026-09-20
**Status**: Ready for Verification

This guide outlines end-to-end scenarios to validate deterministic 404 Not Found and 400 Bad Request test generation and artifact export across the SpecProbe pipeline.

---

## Prerequisites

Ensure all dependencies are synced and test fixtures are accessible:
```bash
uv sync --all-groups
```

---

## Scenario 1: Generate Default Suite with 404 and 400 Test Cases

### 1.1 Command
Generate test cases for search results containing path parameters and request bodies:
```bash
specprobe generate tests/fixtures/search_full_results.json --cache-dir tests/fixtures/cache > all_test_cases.jsonl
```

### 1.2 Expected Outcome
- Operations with path parameters (e.g., `GET /pets/{petId}`) produce:
  - Happy path (`test_type: "positive"`, status 200)
  - 401 Unauthorized (`test_type: "negative_auth_missing"`, status 401)
  - 403 Forbidden (`test_type: "negative_auth_invalid"`, status 403)
  - 404 Not Found (`test_type: "negative_not_found"`, status 404, path parameter mutated to sentinel)
- Operations with schema-governed request bodies (e.g., `POST /pets`) produce:
  - Happy path (`test_type: "positive"`, status 200/201)
  - 401 & 403 cases (if secured)
  - 400 Bad Request (`test_type: "negative_invalid_input"`, status 400, first required field omitted)
- Operations without path parameters omit 404 test cases.
- Operations without request bodies omit 400 test cases.

---

## Scenario 2: Granular Opt-Out Flags

### 2.1 Disable 404 Not-Found Generation
```bash
specprobe generate tests/fixtures/search_full_results.json --cache-dir tests/fixtures/cache --no-not-found > no_404_cases.jsonl
```
**Verification**:
```bash
python -c "
import json
cases = [json.loads(line) for line in open('no_404_cases.jsonl')]
assert not any(c.get('test_type') == 'negative_not_found' for c in cases)
print('Verified: Zero 404 test cases generated with --no-not-found')
"
```

### 2.2 Disable 400 Invalid-Input Generation
```bash
specprobe generate tests/fixtures/search_full_results.json --cache-dir tests/fixtures/cache --no-invalid-input > no_400_cases.jsonl
```
**Verification**:
```bash
python -c "
import json
cases = [json.loads(line) for line in open('no_400_cases.jsonl')]
assert not any(c.get('test_type') == 'negative_invalid_input' for c in cases)
print('Verified: Zero 400 test cases generated with --no-invalid-input')
"
```

---

## Scenario 3: Export Artifacts & Sibling Serialization

### 3.1 Postman Export
```bash
specprobe export all_test_cases.jsonl --format postman --output exported_postman.json
```
**Verification**:
- Inspect `exported_postman.json`:
  - Contains items prefixed with `[404]` (and `[400]` when operations have request bodies).
  - Item scripts assert `pm.response.to.have.status(404)` and `pm.response.to.have.status(400)`.
  - Headers retain `Bearer {{bearerAuth}}` parameterized syntax.
  - Root collection variables declare `{{bearerAuth}}`.

### 3.2 REST Client (`.http`) Export
```bash
specprobe export all_test_cases.jsonl --format http --output exported_requests.http
```
**Verification**:
- Inspect `exported_requests.http`:
  - Contains `# @name <operation_id>_404` (and `# @name <operation_id>_400`) blocks.
  - Blocks contain `# Expected Status: 404` and `# Expected Status: 400` comments.
  - Headers retain `Authorization: Bearer {{bearerAuth}}` file variable references.
  - Top-level variables declare `@bearerAuth = <token>`.

---

## Scenario 4: Quality Gates Verification

Verify all automated tests, static typing, and formatting:
```bash
uv run ty check src/
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
