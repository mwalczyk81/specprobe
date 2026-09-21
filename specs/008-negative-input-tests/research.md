# Phase 0 Research: Negative Input & Resource Test Generation (400 & 404)

**Feature**: `008-negative-input-tests`
**Date**: 2026-09-20
**Status**: Completed

## Executive Summary

Feature 008 expands SpecProbe's automated test generation to cover 404 Not Found (resource lookup failure) and 400 Bad Request (request body schema violation) negative test cases. Following SpecProbe Constitution Principle II (Deterministic Artifact Generation / Zero-LLM), both mutations are algorithmic transforms operating on validated happy-path `GeneratedTestCase` instances and OpenAPI `OperationChunk` metadata.

---

## 1. 404 Not-Found Mutation Strategy (`PathParameterMutator`)

### Context
When testing REST APIs, verifying that non-existent entity IDs return 404 Not Found is critical for testing database lookup logic, 404 error handlers, and route parameter resolution.

### Research Findings & Technical Decisions
- **Target Selection**:
  - For single path parameter routes (`GET /pets/{petId}`), the single parameter is mutated.
  - For multi-parameter nested routes (`GET /orgs/{orgId}/teams/{teamId}/members/{memberId}`), the leaf (last declared parameter in the route template) is mutated. This asserts child resource absence while keeping ancestor containers valid.
  - Operations without path parameters (e.g. `GET /pets`, `POST /orders`) are skipped silently.
- **Sentinel Generation Rules by Schema Type**:
  - `integer` / `number`: High positive integer sentinel `999999` (safe across standard 32-bit and 64-bit ID spaces without overflow).
  - `string` with `format: uuid`: Nil UUID `"00000000-0000-0000-0000-000000000000"`. Passes UUID regex/format validation at routing middleware while guaranteeing record non-existence.
  - `string` with `enum`: Universal non-existent slug `"specprobe-nonexistent-id"`.
  - `string` (general or unspecified): `"specprobe-nonexistent-id"`.
- **Request State Invariants**:
  - All headers (including `Authorization`), query parameters, and request body fixtures are preserved verbatim from the positive test case.
  - Expected `status_code` is set to `404`.
  - `test_type` is set to `"negative_not_found"`.
  - Description is formatted as `"[404] Resource not found - {operation_id}"`.
  - Tags include `["negative", "404", "not_found"]`.

### Alternatives Considered & Rejected
- *Random string / UUID generation*: Rejected to preserve 100% determinism across test runs (Principle II).
- *Mutating all path parameters simultaneously*: Rejected because mutating parent IDs tests parent collection absence, not leaf entity absence.

---

## 2. 400 Invalid-Input Mutation Strategy (`RequestBodyMutator`)

### Context
Input validation is an API's frontline defense. Verifying that malformed payloads return 400 Bad Request ensures validation middleware blocks bad data before hitting business logic.

### Research Findings & Technical Decisions
- **Media Type Scope**:
  - Targets JSON request bodies (`application/json` and `application/*+json`).
  - Non-JSON bodies (e.g. `multipart/form-data`, `application/x-www-form-urlencoded`, raw binary) and bodiless operations are skipped silently.
- **Single-Violation Rule**:
  - Exactly one 400 test case is generated per eligible operation to keep test suite volume predictable and consistent with the 1-to-1 sibling model.
- **Minimal Mutation Priority Hierarchy**:
  1. *Omit Required Property*: If `schema.get("required")` is present and contains field names present in the positive request body, delete the first declared required field from the body dictionary.
  2. *Type Inversion*: If `required` is empty or all required fields are absent, mutate the first declared property in `schema.get("properties")` with a contradictory type:
     - String value -> Array `["__specprobe_invalid_type__"]`
     - Integer/Number value -> String `"__specprobe_not_a_number__"`
     - Boolean value -> String `"__specprobe_not_a_boolean__"`
     - Array value -> String `"__specprobe_not_an_array__"`
     - Object value -> String `"__specprobe_not_an_object__"`
  3. *Root Array Inversion*: If root schema is `type: array` and body is a list, replace body with an empty object `{}`.
- **Request State Invariants**:
  - Path parameters, query parameters, headers, and security credentials remain valid and identical to the positive test case.
  - Expected `status_code` is set to `400`.
  - `test_type` is set to `"negative_invalid_input"`.
  - Description is formatted as `"[400] Invalid input - {operation_id}"`.
  - Tags include `["negative", "400", "invalid_input"]`.

### Alternatives Considered & Rejected
- *Generating one 400 test case per required field*: Rejected during clarification; leads to cardinality explosion on complex schemas.
- *Completely blanking or replacing body with empty JSON `{}`*: Rejected because removing all properties does not isolate single validation rule failures.

---

## 3. CLI Architecture & Flag Ergonomics

### Context
Following Feature 007's `--negative-auth` flag, CLI users require independent control over each negative test generation category.

### Technical Decisions
- `specprobe generate` CLI options:
  - `--negative-auth / --no-negative-auth` (default: `True`) — 401 & 403 generation
  - `--not-found / --no-not-found` (default: `True`) — 404 generation
  - `--invalid-input / --no-invalid-input` (default: `True`) — 400 generation
- `GenerationEngine.generate_batch(...)` interface:
  ```python
  def generate_batch(
      self,
      chunks: list[OperationChunk],
      stream_stdout: bool = True,
      out_stream: Any = None,
      err_stream: Any = None,
      negative_auth: bool = True,
      not_found: bool = True,
      invalid_input: bool = True,
  ) -> BatchResult:
  ```
- Batch generator ordering per chunk:
  1. Emit positive test case (`200`/`201`/etc.)
  2. If `negative_auth` enabled: emit 401 & 403 cases (if secured)
  3. If `not_found` enabled: emit 404 case (if path parameters exist)
  4. If `invalid_input` enabled: emit 400 case (if schema-constrained JSON body exists)

---

## 4. Exporter Serialization & Security Parameterization

### Technical Decisions
- **Discriminator Check**:
  - Exporters check `test_type` exclusively:
    - `"negative_auth_missing"` -> 401
    - `"negative_auth_invalid"` -> 403
    - `"negative_not_found"` -> 404
    - `"negative_invalid_input"` -> 400
- **Postman Exporter**:
  - Item naming: prepend `[404]` and `[400]` respectively.
  - Assertions: `pm.response.to.have.status(404)` and `pm.response.to.have.status(400)`.
  - Security variables: 404 and 400 are NOT negative auth cases, so headers/query params retain collection variable parameterization (`Bearer {{bearerAuth}}`) and collection variables are registered in `collection["variable"]`.
- **REST Client (`.http`) Exporter**:
  - Block names: `# @name <operation_id>_404` and `# @name <operation_id>_400`.
  - Comments: `# Expected Status: 404` and `# Expected Status: 400`.
  - Headers retain file variable parameterization (`Authorization: Bearer {{bearerAuth}}`).
