# Feature Specification: Schema Hardening & Artifact Audit

**Feature Branch**: `005-schema-hardening-and-audit`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "Harden GeneratedTestCase.schema_shape to require and validate real JSON Schema, upgrade the exporter to use it, and add an audit command for spec-vs-artifact coverage gap analysis."

## Clarifications

### Session 2026-09-20

- Q: How should `specprobe audit` structure the gap analysis and LLM critique between the specification and the test artifact? → A: Hybrid deterministic diff + per-operation LLM: Algorithmic detection of missing operations/status codes/parameters, combined with per-operation LLM evaluation of assertion quality and depth.
- Q: How should the `specprobe audit` CLI command accept the API specification and test artifact inputs? → A: Positional artifact + `--index-dir` default: `specprobe audit [ARTIFACT_FILE] [--index-dir DIR] [--spec FILE]`, supporting file path or stdin stream (`-`).
- Q: How should the REST Client (`.http`) exporter document the validated response schema in its request metadata comments? → A: Schema signature line: Format as `# Expected Schema: <type> (properties: <prop1>, <prop2>)` (e.g. `# Expected Schema: object (properties: id, name, tag)`), omitting the line when no schema or body is expected.
- Q: Which JSON Schema dialect should `specprobe generate` validate `response.schema_shape` against? → A: JSON Schema Draft 7: Enforce standard Draft 7 meta-schema validation (e.g. `jsonschema.Draft7Validator`), guaranteeing seamless compatibility with Postman's built-in Ajv engine.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Validated JSON Schema in Test Case Generation (Priority: P1)

As an API test engineer, I want the test case generator to require and validate real, structurally sound JSON Schema for every generated response expectation, so that downstream automation tools receive reliable schema contracts instead of arbitrary key dictionaries or unresolvable reference pointers.

**Why this priority**: Trustworthy test case generation is the prerequisite for all downstream consumption. If generated schema shapes contain invalid schema syntax, unresolvable pointers, or malformed data structures, every downstream consumer (exporters, assertion runners, audit tools) must implement brittle defensive workarounds.

**Independent Test**: Can be fully tested by running `specprobe generate` with valid and invalid schema responses from the LLM gateway, verifying that the system validates schemas against the JSON Schema meta-schema, self-corrects via the single retry loop on schema validation failures, and produces strictly valid JSON Schema objects in `response.schema_shape`.

**Acceptance Scenarios**:

1. **Given** an operation chunk with defined response payloads, **When** `specprobe generate` synthesizes test cases, **Then** `response.schema_shape` contains a valid JSON Schema object (e.g. declaring `type`, `properties`, and/or `items`).
2. **Given** an initial LLM response where `response.schema_shape` is an invalid schema, bare unresolvable `$ref` pointer, or non-schema dictionary, **When** schema validation is executed, **Then** the validation error is caught and fed back into the single self-correcting retry loop.
3. **Given** a generation retry that succeeds in emitting a compliant JSON Schema, **When** validated, **Then** the test case is accepted and emitted to the output stream.
4. **Given** a generation retry that fails schema validation a second time, **When** handled, **Then** the failure is recorded as an operation generation error without terminating batch processing of subsequent operations.

---

### User Story 2 - Full-Fidelity Postman & REST Client Schema Assertion Export (Priority: P2)

As an API automation engineer, I want exported Postman collections and REST Client (`.http`) files to assert and document complete response schemas rather than shallow property presence checks, so that runtime test executions rigorously enforce the contract defined in the specification.

**Why this priority**: Shallow property presence checks (`pm.expect(jsonData).to.have.property(key)`) only verify that keys exist; they fail to validate nested types, array items, or structural rules. With validated JSON Schema in place, exporters can emit industry-standard JSON Schema assertions (`pm.response.to.have.jsonSchema(...)`) that validate response structures accurately.

**Independent Test**: Can be tested by running `specprobe export` on test cases bearing validated JSON Schema shapes, verifying that Postman scripts contain `pm.response.to.have.jsonSchema(...)` blocks and `.http` files contain clear schema expectation comments, with 100% deterministic, offline execution and updated golden fixture tests.

**Acceptance Scenarios**:

1. **Given** a `GeneratedTestCase` with a validated `response.schema_shape`, **When** exported to Postman format, **Then** the generated test script contains `pm.test("Response matches JSON Schema", function () { pm.response.to.have.jsonSchema(<schema>); });` asserting the full schema object.
2. **Given** a `GeneratedTestCase` with no expected response body (e.g. HTTP 204 or `schema_shape: null`), **When** exported to Postman, **Then** no `jsonSchema` test block is emitted, preserving status and header assertions.
3. **Given** a `GeneratedTestCase` with a validated `response.schema_shape`, **When** exported to REST Client (`.http`) format, **Then** the request block metadata comments document the expected response schema signature as `# Expected Schema: <type> (properties: <p1>, <p2>)` (omitted when no body or schema is expected).
4. **Given** golden test fixtures, **When** verified against the new JSON Schema assertion output, **Then** golden regression tests pass byte-for-byte.

---

### User Story 3 - API Specification vs. Artifact Audit & Gap Analysis (Priority: P3)

As a QA lead or API designer, I want a `specprobe audit` command to compare an indexed OpenAPI specification against existing test artifacts (Postman collections or `.http` files), so that I can automatically identify coverage blind spots such as untested operations, unexercised status codes, omitted query/path parameters, and weak assertions.

**Why this priority**: Teams frequently maintain test suites (Postman collections, `.http` files) that drift out of sync with evolving OpenAPI specs. An automated audit provides immediate visibility into specification test coverage gaps without requiring users to manually cross-reference hundreds of endpoints.

**Independent Test**: Can be tested by running `specprobe audit` with an indexed spec and an existing test artifact (e.g., Petstore spec vs. Petstore Postman collection with intentionally missing operations or status codes), confirming that the critique output correctly detects and categorizes the gaps.

**Acceptance Scenarios**:

1. **Given** an indexed OpenAPI specification and an existing Postman collection, **When** `specprobe audit` is executed, **Then** the command identifies operations present in the specification that have no corresponding test in the collection (missing coverage).
2. **Given** an operation in the specification with documented 200, 400, and 404 responses, but the test artifact only exercises 200, **When** audited, **Then** the audit output reports unexercised status codes (400, 404) and missing error-path scenarios.
3. **Given** a test artifact where requests omit optional query or header parameters defined in the specification, **When** audited, **Then** the audit report notes untested parameter combinations.
4. **Given** a test artifact containing weak assertions (e.g. status code only, without response schema validation or property checks), **When** audited, **Then** the audit critique evaluates assertion quality and recommends concrete assertions.
5. **Given** an existing REST Client (`.http`) file, **When** passed to `specprobe audit`, **Then** the audit parses the request blocks and performs the identical gap critique against the specification.

---

### User Story 4 - Audit Output Streaming & CLI Pipeline Composition (Priority: P4)

As a DevOps engineer integrating SpecProbe into a CI/CD pipeline, I want `specprobe audit` to stream structured critique records as JSONL to standard output with optional summary reporting, so that audit findings can be piped into downstream tools, dashboards, or quality gates.

**Why this priority**: Consistency with SpecProbe's existing pipeline architecture (`chunk | index | search | generate | export`) ensures that audit results can be filtered, archived, or evaluated programmatically without custom scrapers.

**Independent Test**: Can be tested by piping `specprobe audit` output to standard tools (`jq`, file redirection) and verifying that every emitted line is a valid JSON object matching the audit Pydantic schema, with summary diagnostics routed to standard error.

**Acceptance Scenarios**:

1. **Given** an audit run across multiple operations, **When** output is emitted, **Then** each finding or operation critique is output as a single JSON object on a distinct line (JSONL) on `stdout`.
2. **Given** the `--summary` flag, **When** audit completes, **Then** a high-level summary table (total operations, covered operations, coverage percentage, total gaps by severity) is rendered to `stderr` or formatted display without corrupting `stdout` JSONL.
3. **Given** an invalid input artifact or missing specification index, **When** `specprobe audit` is invoked, **Then** the command emits a clear error message to `stderr` and exits with code 1.

---

### Edge Cases

- **Empty / Minimal Test Artifact**: If the input Postman collection or `.http` file contains zero test requests, the audit command reports 0% coverage and flags all specification operations as untested, rather than crashing.
- **Artifact Operations Not in Specification**: If a test artifact contains requests to paths or methods that do not exist in the OpenAPI spec, the audit flags them as "phantom" or "orphaned" tests.
- **Complex / Polymorphic Schemas (`anyOf`, `oneOf`, `allOf`)**: Schema validation during test generation and Postman export must accept valid JSON Schema constructs involving composition keywords without rejecting them as invalid.
- **Schema Validation Metaschema Dialect**: Schemas emitted by the generator must adhere to standard JSON Schema (Draft 7 / Draft 2020-12 compatible core), avoiding proprietary keywords that fail validation in standard validators and Postman's Ajv engine.
- **Circular or Deeply Nested Schema References**: Generation prompts and schemas must require self-contained schema objects with resolved subschemas rather than unresolved external or document-relative `$ref` pointers.
- **Offline Execution & Replay**: In environments without live LLMs or external networks, `specprobe audit` and `specprobe generate` must operate using disk cache replay fixtures without failing.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Part A: Schema Hardening (Generate + Export)

- **FR-001**: The test generation prompt (`prompts/generate.md`) and generation schema MUST require the LLM to output a structurally complete, self-contained JSON Schema for `response.schema_shape` (when a response body is expected).
- **FR-002**: The system MUST validate `response.schema_shape` against the JSON Schema Draft 7 meta-schema during Pydantic model validation of `GeneratedTestCase`.
- **FR-003**: If `schema_shape` fails JSON Schema meta-schema validation or contains an unresolved `$ref` pointer, the system MUST treat it as a Pydantic validation error and trigger the existing single self-correcting retry loop with the validation diagnostics fed back to the LLM.
- **FR-004**: If the retry attempt also produces an invalid schema, the system MUST log the failure and handle it according to the existing partial-failure resilience contract (skipping or failing that operation gracefully without halting the batch).
- **FR-005**: The Postman exporter (`src/specprobe/exporter/postman.py`) MUST emit `pm.response.to.have.jsonSchema(schema)` assertions embedding the validated `schema_shape` object for responses expecting bodies.
- **FR-006**: The Postman exporter MUST omit the `jsonSchema` assertion block for test cases where no body is expected (e.g. HTTP 204 or `schema_shape: null`), preserving status and header assertions.
- **FR-007**: The REST Client exporter (`src/specprobe/exporter/http_client.py`) MUST format expected response schemas as `# Expected Schema: <type> (properties: <p1>, <p2>)` (e.g. `# Expected Schema: object (properties: id, name, tag)`), omitting the line when no schema or body is expected.
- **FR-008**: Golden test fixtures (`tests/fixtures/golden/`) and unit test assertions MUST be updated to reflect the `pm.response.to.have.jsonSchema` structure, ensuring byte-identical determinism and regression test compliance.

#### Part B: Audit Command (Coverage & Quality Gap Analysis)

- **FR-009**: The system MUST provide a CLI command `specprobe audit [ARTIFACT_FILE]` that accepts an existing test artifact (Postman collection JSON or `.http` file) via file path or standard input (`-`), resolving the specification from `--index-dir` (defaulting to `.specprobe/index` or `$SPECPROBE_INDEX_DIR`) or an explicit `--spec <file>` path.
- **FR-010**: The audit command MUST parse the test artifact to extract tested operations (methods, paths), request parameters, expected status codes, and existing assertion types.
- **FR-011**: The audit command MUST match artifact test requests against specification operations using normalized paths, path parameter patterns, and HTTP methods.
- **FR-012**: The audit command MUST evaluate coverage gaps across at least four distinct dimensions using a hybrid pipeline:
  1. *Structural Gaps (Deterministic)*: Untested operations, unexercised status codes, and omitted parameters MUST be computed algorithmically without LLM calls.
  2. *Semantic Quality Gaps (LLM-Critiqued)*: Assertion strength (e.g. status code only vs. schema validation), payload coverage, and edge-case depth MUST be critiqued per-operation via the LLM.
- **FR-013**: The audit command MUST use a versioned prompt template (`prompts/audit.md`) and route per-operation LLM critiques through the local-first LiteLLM gateway, defaulting to local model execution with cryptographic disk caching.
- **FR-014**: Audit critique outputs MUST be strictly validated through a defined Pydantic model (`AuditReport` / `OperationCritique`) before emission.
- **FR-015**: Audit findings MUST be streamed to `stdout` as JSONL records, one record per audited operation or finding.
- **FR-016**: The audit command MUST provide an optional `--summary` flag that displays aggregated metrics (operation coverage percentage, status code coverage count, gap distribution by severity) directed to `stderr` or rich console display.

---

### Key Entities *(include if feature involves data)*

- **ValidatedSchemaShape**: A self-contained, valid JSON Schema dictionary adhering to standard meta-schema syntax (e.g., defining `type`, `properties`, `required`, `items`), containing zero unresolved `$ref` references.
- **GeneratedTestCase**: The core test case model representing a synthesized test, updated so that `response.schema_shape` is guaranteed to be a valid `ValidatedSchemaShape` or `None`.
- **ArtifactTestItem**: An extracted test request from a Postman collection or `.http` file, capturing HTTP method, path template, query parameters, header keys, request body presence, expected status code, and assertion types present in scripts/comments.
- **CoverageGap**: A single identified deficiency between the API specification and the test artifact, categorized by type (`missing_operation`, `missing_status_code`, `missing_parameter`, `weak_assertion`), severity (`critical`, `warning`, `suggestion`), description, and actionable remediation recommendation.
- **OperationCritique**: A structured audit finding for a specific API operation, associating the specification operation ID with matched test items, covered status codes, uncovered status codes, identified coverage gaps, and an overall quality assessment.
- **AuditReport**: An aggregated summary of an audit execution containing total specification operations, total tested operations, coverage percentages, and a list of all identified `CoverageGap` records.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of test cases generated by `specprobe generate` with response bodies contain a valid JSON Schema validated against the JSON Schema meta-schema, with zero malformed schemas or bare `$ref` pointers emitted.
- **SC-002**: Exporters emit complete, runnable schema validations: 100% of Postman test cases expecting response bodies use `pm.response.to.have.jsonSchema(...)`, passing Postman collection schema checks.
- **SC-003**: The `specprobe audit` command correctly identifies 100% of intentionally omitted operations and status codes in test verification fixtures.
- **SC-004**: Running `specprobe audit` against an indexed specification and test artifact completes evaluation with cached/local models in under 30 seconds for specs with up to 50 operations.
- **SC-005**: All exported artifacts and test suite executions continue to run 100% offline with zero live network calls in standard CI test suites.
- **SC-006**: Existing golden fixtures and pipeline integration tests pass with zero regression failures after updating assertion fixtures.

---

## Assumptions

- **JSON Schema Dialect**: Schemas emitted by the generator and expected by the validator conform strictly to JSON Schema Draft 7, supported out of the box by Postman's built-in Ajv validator.
- **Self-Contained Schemas**: Generated schemas are fully resolved and self-contained; component definitions are embedded inline rather than referencing external files or unresolvable document pointers.
- **Artifact Parsing Scope**: The audit command supports standard Postman Collection v2.1 JSON files and RFC 7230 `.http` files (the formats produced by `specprobe export`). Proprietary third-party runner formats are out of scope for initial release.
- **Gateway & Caching Alignment**: The audit command adheres strictly to Constitution Principle IV, using LiteLLM with local LM Studio default, opt-in cloud access, and SHA-256 disk caching for offline determinism.
- **Sequencing**: Part A (schema hardening in generate + export) must be completed and verified before Part B (audit command), ensuring the audit command can evaluate schema assertions against trustworthy generated models.
