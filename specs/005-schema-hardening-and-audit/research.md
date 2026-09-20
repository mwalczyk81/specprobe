# Research & Architecture Decisions: Schema Hardening & Artifact Audit

**Feature**: `005-schema-hardening-and-audit`  
**Date**: 2026-09-20  
**Status**: Completed  

---

## 1. JSON Schema Meta-Schema Enforcement

### Decision
Validate `ResponseAssertion.schema_shape` using Python's `jsonschema` library with `jsonschema.Draft7Validator.check_schema()` inside a Pydantic `@field_validator("schema_shape")`, and disallow unresolvable `$ref` keywords in the generated schema structure.

### Rationale
- `jsonschema` 4.26+ is already installed in the environment as a verified dependency.
- `Draft7Validator.check_schema(schema)` inspects the structure of the schema against the official JSON Schema Draft 7 meta-schema and raises `jsonschema.exceptions.SchemaError` if any keyword or property type is invalid.
- Postman's JavaScript runtime executes test scripts with the `ajv` engine, which defaults to JSON Schema Draft 7. Enforcing Draft 7 meta-schema validation upstream in `specprobe generate` guarantees that every generated schema will be accepted and executed by Postman's `pm.response.to.have.jsonSchema(...)` without syntax or dialect failures.
- Rejecting bare or unresolvable `$ref` pointers (e.g. `{"$ref": "#/components/schemas/Pet"}`) guarantees that test cases are self-contained and runnable in isolation, avoiding runtime dereferencing failures.

### Alternatives Considered
- *Permissive dictionary inspection*: Simply checking that `schema_shape` has `"type"` and `"properties"`. Rejected because it allows malformed keywords, invalid types, and broken structures through, leaving downstream exporters vulnerable to runtime errors.
- *Draft 2020-12*: Validating against Draft 2020-12 exclusively. Rejected because older Newman CLI versions and Postman collections default to Draft 7 / Ajv v6/v8 in Draft 7 mode, where keywords like `prefixItems` fail validation.

---

## 2. Generator Prompt & Self-Correcting Retry Integration

### Decision
Update `prompts/generate.md` to explicitly instruct the model to produce a valid, self-contained JSON Schema Draft 7 object for `schema_shape` when a response body is expected (with `"type": "object"`, explicit `"properties"`, or `"type": "array"` with `"items"`), and rely on the existing `GenerationEngine` single-retry loop when Pydantic validation fails.

### Rationale
- `GenerationEngine.generate_chunk()` already intercepts Pydantic `ValidationError` and retries once with the exact validation diagnostics fed back to the model per Constitution Principle V.
- Adding a Pydantic validator to `ResponseAssertion` seamlessly hooks into this existing mechanism without adding speculative retry layers or custom error wrappers (Constitution Principle I).
- Clear prompt instructions with concrete examples of valid self-contained JSON Schema minimize first-pass validation errors.

### Alternatives Considered
- *Separate schema repair pre-pass*: Writing a bespoke algorithm to convert arbitrary dictionaries into JSON Schema before validation. Rejected under Constitution Principle I (avoiding speculative abstractions) and Principle II; the LLM is responsible for generating valid schemas, with automated self-correction feedback on failure.

---

## 3. Postman Exporter Upgrade (`pm.response.to.have.jsonSchema`)

### Decision
Upgrade `src/specprobe/exporter/postman.py` to serialize `pm.response.to.have.jsonSchema(<schema_shape>)` directly into the JavaScript `exec` array of the test item event whenever `schema_shape` is present.

### Rationale
- `pm.response.to.have.jsonSchema(schema)` is Postman's official, first-class assertion for JSON Schema contract testing.
- It validates the entire response body: types, required fields, nested objects, array items, and constraints—vastly superior to checking shallow property presence with `pm.expect(jsonData).to.have.property(...)`.
- The schema is serialized as a native JavaScript object literal in the test script, formatting cleanly and deterministically with sorted keys.
- If `schema_shape` is `None` (e.g. HTTP 204 No Content), the assertion block is omitted, cleanly preserving status code and header assertions.

### Alternatives Considered
- *Dual assertions (property existence + schema)*: Emitting both `pm.expect.to.have.property` and `pm.response.to.have.jsonSchema`. Rejected as redundant; `to.have.jsonSchema` strictly subsumes property checks and produces clearer, standard Ajv error reports in Postman/Newman.

---

## 4. REST Client (`.http`) Schema Representation

### Decision
Format the expected schema in `.http` request metadata comments as a single-line signature: `# Expected Schema: <type> (properties: <p1>, <p2>)` (e.g. `# Expected Schema: object (properties: id, name, tag)` or `# Expected Schema: array of object (properties: id, name)`).

### Rationale
- RFC 7230 `.http` files are plain text documents primarily used with VS Code REST Client. Unlike Postman, they lack an embedded JavaScript test runner and rely on comments for developer guidance.
- A concise schema signature comment provides immediate readability at a glance without cluttering the document with dozens of lines of raw JSON Schema before every request line.
- When `schema_shape` is `None`, the comment is cleanly omitted.

### Alternatives Considered
- *Multi-line raw JSON comment block*: Printing `# Expected Schema:` followed by indented raw JSON. Rejected because multi-line comments in `.http` files add significant visual noise and make browsing endpoints cumbersome.
- *Retaining `# Expected Properties:`*: Rejected per User clarification Q3 in favor of `# Expected Schema:`, which explicitly conveys the schema type and structure.

---

## 5. Test Artifact Parsing (Postman & REST Client)

### Decision
Implement a lightweight, deterministic parser in `src/specprobe/audit/parser.py` capable of reading:
1. Postman Collection v2.1 JSON files (extracting requests recursively from folders, resolving HTTP method, path, headers, query parameters, expected status code, and assertion script types).
2. VS Code REST Client (`.http`) files (extracting request blocks delimited by `###`, parsing request lines, headers, metadata comments `# @name`, `# Expected Status:`, and `# Expected Schema:`).

### Rationale
- SpecProbe already exports both Postman and `.http` formats. Supporting the exact same two formats for audit ensures round-trip symmetry: users can audit their exported collections or existing hand-crafted collections against the original specification.
- Both parsers normalize extracted test requests into a uniform internal representation (`ArtifactTestItem`), isolating downstream matching and analysis from format-specific nuances.

### Alternatives Considered
- *Using third-party Postman parser libraries*: Rejected; Postman v2.1 JSON schema is straightforward, and existing custom dependencies add bloat and potential security vulnerabilities. Standard Python `json` and regex/parsing suffice.

---

## 6. Specification-vs-Artifact Matching & Deterministic Gap Analysis

### Decision
Adopt a hybrid audit pipeline:
1. *Deterministic Matching & Structural Diff*: Algorithmically match `ArtifactTestItem` instances against OpenAPI `OperationChunk` records using HTTP method and normalized path parameter matching (`/pets/{petId}` $\leftrightarrow$ `/pets/:petId` $\leftrightarrow$ `/pets/123`).
2. *Deterministic Gap Detection*: Compute missing operations, unexercised documented status codes (e.g., spec documents 200, 400, 404, but artifact only tests 200), and missing documented parameters without LLM calls.
3. *Per-Operation Semantic Critique*: For operations with matched tests, pass the operation chunk and test items to the LLM gateway to critique assertion depth (e.g. status code only vs. schema validation), edge-case parameter combinations, and response validation quality.

### Rationale
- Complies with Constitution Principle II: zero-LLM for algorithmic operations that can be computed deterministically.
- Complies with Constitution Principle III & IV: runs locally, uses local LM Studio model by default, and caches LLM critiques by operation chunk and test item hash.
- Per-operation LLM analysis respects local model context windows (4k–8k tokens) and prevents token exhaustion on large specifications.

### Alternatives Considered
- *All-LLM audit*: Sending the entire spec and entire artifact in one prompt. Rejected because large specifications exceed context limits, cost is high, and deterministic diffs are faster and 100% accurate.

---

## 7. Audit Prompt & Structured Output

### Decision
Create a versioned prompt template at `prompts/audit.md` and define strict Pydantic schemas in `src/specprobe/audit/models.py` (`CoverageGap`, `OperationCritique`, `AuditReport`). Validate model responses using Pydantic, streaming `OperationCritique` objects as JSONL lines to `stdout`.

### Rationale
- Follows the proven architecture of `specprobe generate` (`prompts/generate.md` + Pydantic schema + LiteLLM gateway).
- Streaming JSONL preserves UNIX pipe composability (`specprobe audit ... | jq .`).
- Optional `--summary` outputs a formatted table to `stderr` or rich console without corrupting piped JSONL.

---

## 8. CLI Command Contract

### Decision
Add `specprobe audit [ARTIFACT_FILE]` with options:
- `--index-dir`: Path to Qdrant index (default: `.specprobe/index` or `$SPECPROBE_INDEX_DIR`).
- `--spec`: Optional direct path to OpenAPI spec file (bypasses pre-indexed store).
- `--summary`: Render an aggregated coverage summary table to stderr/console.
- `--no-cache`: Bypass LLM disk cache.
- `--cache-dir`: Directory for caching audit critiques (default: `.specprobe/cache/audit`).

### Rationale
- Matches the established UX conventions of `specprobe search`, `generate`, and `export`.
- Supports reading artifacts from files or stdin (`-`), allowing pipelines like `cat collection.json | specprobe audit -`.
