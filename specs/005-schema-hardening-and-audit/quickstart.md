# Quickstart: Schema Hardening & Test Artifact Audit

**Feature**: `005-schema-hardening-and-audit`
**Date**: 2026-09-20
**Status**: Ready for Validation

This guide demonstrates how to generate schema-hardened API test cases, export full-fidelity Postman and REST Client assertions, and audit test artifacts against API specifications for coverage gaps.

---

## 1. Prerequisites

1. **Environment**: Python 3.11+ managed by `uv`.
2. **Dependencies**: Installed via `uv sync`.
3. **Local Cache / Gateway**: LLM interactions route through LiteLLM with disk caching enabled by default.

---

## 2. Validation Scenarios

### Scenario 1: Generate Test Cases with Strict JSON Schema Validation

Synthesize test cases from indexed specification operations and verify that `response.schema_shape` produces a strictly valid JSON Schema Draft 7 object:

```bash
# Search for operations and pipe into test generation
uv run specprobe search --source-title "Swagger Petstore" --full \
  | uv run specprobe generate > generated_tests.jsonl

# Validate that generated test cases contain valid schema objects
python -c '
import json, sys
from jsonschema import Draft7Validator

with open("generated_tests.jsonl") as f:
    for line in f:
        tc = json.loads(line)
        schema = tc.get("response", {}).get("schema_shape")
        if schema:
            Draft7Validator.check_schema(schema)
            assert "$ref" not in schema or any(k in schema for k in ("definitions", "$defs", "properties")), "Bare $ref detected!"
print("All generated test cases contain valid, self-contained JSON Schema Draft 7!")
'
```

**Expected verification**:
- Every test case expecting a body contains a valid, self-contained JSON Schema Draft 7 dictionary.
- No unresolvable bare `$ref` pointers exist in the output.

---

### Scenario 2: Export Postman Collection with `to.have.jsonSchema` Assertions

Export generated test cases into a Postman Collection and verify that `pm.response.to.have.jsonSchema` assertions are emitted:

```bash
# Export to Postman collection
uv run specprobe export generated_tests.jsonl --format postman > petstore_collection.json

# Check for jsonSchema assertion
grep -n "pm.response.to.have.jsonSchema" petstore_collection.json
```

**Expected verification**:
- Postman test script events contain:
  ```javascript
  pm.test("Response matches JSON Schema", function () {
      var schema = { ... };
      pm.response.to.have.jsonSchema(schema);
  });
  ```
- Operations expecting no body (e.g. 204 No Content) omit the `jsonSchema` test block while retaining status and header checks.

---

### Scenario 3: Export REST Client (`.http`) with Schema Signature Comments

Export generated test cases into a `.http` file and verify schema signature metadata comments:

```bash
# Export to .http file
uv run specprobe export generated_tests.jsonl --format http > petstore_requests.http

# Inspect top request blocks
head -n 25 petstore_requests.http
```

**Expected verification**:
- Request metadata includes `# Expected Schema: <type> (properties: <p1>, <p2>)` (e.g. `# Expected Schema: object (properties: id, name, tag)`).
- Omitted for responses expecting no body.

---

### Scenario 4: Audit Postman Collection against Specification Index

Audit a Postman Collection against the indexed specification to discover untested operations and missing status code scenarios:

```bash
# Run audit with summary report on stderr and JSONL critiques on stdout
uv run specprobe audit petstore_collection.json --summary > audit_critiques.jsonl

# Inspect first critique record
head -n 1 audit_critiques.jsonl | python -m json.tool
```

**Expected verification**:
- Standard output receives streaming `OperationCritique` JSONL records.
- Standard error displays the aggregated coverage table with operation coverage %, status code coverage %, and gaps categorized by severity.

---

### Scenario 5: Audit REST Client (`.http`) File Directly Against OpenAPI Spec

Perform an audit directly against an OpenAPI YAML/JSON specification file without requiring a pre-built index:

```bash
# Audit an .http file directly against an OpenAPI spec
uv run specprobe audit petstore_requests.http --spec tests/fixtures/petstore_v3.yaml --summary
```

**Expected verification**:
- The `.http` file is parsed into `ArtifactTestItem` instances.
- Spec operations are extracted from `petstore_v3.yaml`.
- Coverage diff and critique are computed seamlessly.

---

### Scenario 6: Full Pipeline Composition

Run the entire pipeline from specification chunking to test generation, artifact export, and coverage auditing:

```bash
uv run specprobe search --source-title "Petstore" --full \
  | uv run specprobe generate \
  | uv run specprobe export --format postman --output /tmp/test_collection.json

uv run specprobe audit /tmp/test_collection.json --summary
```

**Expected verification**:
- 100% end-to-end integration without human intervention or broken intermediate formats.
