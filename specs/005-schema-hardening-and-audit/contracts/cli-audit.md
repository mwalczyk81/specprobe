# CLI Contract: `specprobe audit`

**Command**: `specprobe audit`
**Parent Group**: `specprobe`
**Purpose**: Compare an API specification against existing test artifacts (Postman Collection JSON or REST Client `.http` files) to perform gap analysis and evaluate test quality.

---

## 1. Syntax

```bash
specprobe audit [ARTIFACT_FILE] [OPTIONS]
```

---

## 2. Arguments

| Argument | Type | Required | Description |
|---|---|---|---|
| `ARTIFACT_FILE` | Path (`click.Path(dir_okay=False, allow_dash=True)`) | Optional | Path to Postman Collection v2.1 JSON or REST Client `.http` file. If omitted or passed as `-`, reads from standard input (`stdin`). |

---

## 3. Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--index-dir` | Path (`click.Path(file_okay=False)`) | `.specprobe/index` | Directory of the indexed Qdrant vector database containing operation chunks. Can also be set via `SPECPROBE_INDEX_DIR`. |
| `--spec` | Path (`click.Path(dir_okay=False)`) | `None` | Optional direct path to an OpenAPI 3.0/3.1 YAML or JSON specification file. When provided, operations are extracted directly, bypassing `--index-dir`. |
| `--summary` | Flag | `False` | Render a human-readable summary table of coverage metrics and gap distributions to `stderr` or rich console. |
| `--no-cache` | Flag | `False` | Bypass LLM disk cache when generating semantic assertion critiques. |
| `--cache-dir` | Path (`click.Path(file_okay=False)`) | `.specprobe/cache/audit` | Directory for caching LLM audit critique responses. Can also be set via `SPECPROBE_AUDIT_CACHE_DIR`. |

---

## 4. Exit Codes & Output Streams

| Exit Code | Condition | Output Stream |
|---|---|---|
| `0` | Success: Audit executed and findings streamed. | `stdout` receives streaming JSONL (`OperationCritique` records). `stderr` receives diagnostic logs and `--summary` output. |
| `0` | Empty artifact: Artifact contains zero tests. All specification operations reported as uncovered. | `stdout` receives JSONL with 0% coverage critiques; notice on `stderr`. |
| `1` | Input validation error: Artifact file does not exist, or unparseable format. | Descriptive error message on `stderr`. |
| `1` | Missing specification: Neither `--spec` provided nor index found at `--index-dir`. | Actionable error message instructing user to run `specprobe index` or provide `--spec`. |
| `1` | LLM Gateway failure: LLM invocation failure after retry with no cache hit. | Descriptive error message on `stderr`. |

---

## 5. Output Format

### Standard Output (`stdout`): Streaming JSONL

Every line emitted to `stdout` is a valid JSON object matching the `OperationCritique` schema:

```json
{
  "operation_id": "showPetById",
  "method": "GET",
  "path": "/pets/{petId}",
  "matched_tests_count": 1,
  "documented_status_codes": [200, 400, 404],
  "tested_status_codes": [200],
  "untested_status_codes": [400, 404],
  "gaps": [
    {
      "gap_type": "missing_status_code",
      "severity": "warning",
      "target": "400",
      "description": "Operation documents 400 Bad Request error response, but no test exercises this status code.",
      "recommendation": "Add a negative test scenario passing invalid path or parameter values to assert 400 response."
    },
    {
      "gap_type": "missing_status_code",
      "severity": "warning",
      "target": "404",
      "description": "Operation documents 404 Not Found error response, but no test exercises this status code.",
      "recommendation": "Add a test scenario with a non-existent pet ID to verify 404 behavior."
    },
    {
      "gap_type": "weak_assertion",
      "severity": "suggestion",
      "target": "showPetById",
      "description": "Test asserts status code 200 and property presence, but lacks full JSON Schema validation.",
      "recommendation": "Upgrade test script to use pm.response.to.have.jsonSchema(...) for complete schema verification."
    }
  ],
  "assertion_quality_score": 0.65,
  "critique_summary": "Core happy path is exercised, but error handling branches (400, 404) are completely uncovered. Assertions verify top-level field presence but do not validate field data types or constraints."
}
```

### Standard Error (`stderr`): Optional `--summary` Display

When `--summary` is passed, the CLI renders an aggregated summary table to `stderr`:

```text
============================= SpecProbe Audit Summary =============================
Specification: .specprobe/index (Petstore API)
Artifact:      tests/fixtures/petstore_collection.json

Coverage Metrics:
  Operations:      8 / 10 covered (80.0%)
  Status Codes:    12 / 24 exercised (50.0%)

Coverage Gaps by Severity:
  [CRITICAL]    2  (Untested operations: deletePet, uploadPetImage)
  [WARNING]     8  (Unexercised error status codes: 400, 404, 500)
  [SUGGESTION]  4  (Weak assertions: missing response JSON Schema checks)

Total Gaps:    14
===================================================================================
```
