# Feature Specification: Negative Input & Resource Test Generation (400 & 404)

**Feature Branch**: `008-negative-input-tests`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "User Story 1 — Not-found (404): For operations with a path parameter identifying a specific resource (GET/PUT/PATCH/DELETE /pets/{petId}), generate a test case that mutates the happy-path request's path parameter to reference a resource that plausibly doesn't exist (out-of-range ID, or a syntactically-valid-but-nonexistent value matching the parameter's schema type/format), keeping everything else unchanged — same headers, same valid credentials, since this tests resource lookup, not auth. Assert status_code == 404. Reuse the test_type discriminator (add negative_not_found) and the 007 exporter scaffolding directly: sibling item, [404] prefix in Postman, # @name <op>_404 / # Expected Status: 404 in REST Client. Skip operations with no path parameters — there's nothing to mutate. User Story 2 — Invalid-input (400): For operations with a request body governed by a schema, generate a test case with a body that violates that schema in a minimal, deterministic way (omit one required field, or violate one field's declared type/format) and assert status_code == 400. This needs a schema-aware mutation step — inspecting required/properties/type on the operation's request schema, not just swapping a parameter value like 404 does. Add test_type = negative_invalid_input. Same exporter treatment: sibling item, [400] prefix / # @name <op>_400. Skip operations with no request body or no schema-constrained body — there's nothing to violate. Both default to enabled, consistent with 007's --negative-auth pattern — pick flag names that fit alongside --negative-auth/--no-negative-auth (e.g. --not-found/--no-not-found, --invalid-input/--no-invalid-input), and raise it as a clarification question if there's ambiguity about whether these should be one combined flag or two independent ones. Stay zero-LLM/deterministic for both — this is schema/parameter mutation, not something requiring judgment."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deterministic 404 Not-Found Test Generation (Priority: P1)

As an API developer or QA engineer testing an API specification,
I want SpecProbe to automatically generate negative test cases asserting HTTP 404 Not Found for any operation that targets a parameterized resource path (e.g., `GET /pets/{petId}` or `DELETE /orders/{orderId}`),
So that I can verify my API server correctly handles requests for nonexistent entities without manually crafting edge-case path identifiers.

**Why this priority**: Resource existence verification (404) is one of the most common REST error cases. Path parameter mutation is completely deterministic, requires no LLM inference, and directly extends the test case model and exporter scaffolding established in Feature 007.

**Independent Test**: Can be tested independently by running test generation on an operation with path parameters (e.g., `GET /pets/{petId}`) and verifying that a sibling test case with `test_type="negative_not_found"` and expected status 404 is emitted with all other parameters (headers, credentials, query parameters) preserved.

**Acceptance Scenarios**:

1. **Given** an operation chunk with path parameter `{petId}` (type `integer`), **When** test generation executes with 404 generation enabled, **Then** a test case is emitted with `test_type="negative_not_found"`, the path parameter mutated to an out-of-range integer value (e.g., `999999`), valid authentication credentials preserved, and expected status `404`.
2. **Given** an operation chunk with path parameter `{id}` (type `string`, format `uuid`), **When** test generation executes, **Then** the path parameter is mutated to a format-compliant but non-existent identifier (e.g., nil UUID `00000000-0000-0000-0000-000000000000`), with expected status `404`.
3. **Given** an operation chunk with NO path parameters (e.g., `GET /pets`), **When** test generation executes, **Then** no 404 test case is generated for this operation.
4. **Given** an operation with multiple path parameters (e.g., `/orgs/{orgId}/users/{userId}`), **When** test generation executes, **Then** the primary leaf resource identifier is mutated to a nonexistent value while maintaining outer path hierarchy.

---

### User Story 2 - Deterministic 400 Invalid-Input Schema Violation Test Generation (Priority: P2)

As an API developer or QA engineer,
I want SpecProbe to automatically generate negative test cases asserting HTTP 400 Bad Request for operations that accept a schema-constrained request body,
So that I can verify my server rejects malformed or incomplete payloads before processing business logic.

**Why this priority**: Input validation (400) is the frontline defense for web APIs. Violating request schemas deterministically tests server-side request parsers and validation middleware without manual fixture authoring.

**Independent Test**: Can be tested independently by generating tests for an operation with a schema-governed request body (e.g., `POST /pets`), confirming that an invalid payload (missing a required property or corrupting a property type) is generated with `test_type="negative_invalid_input"` and expected status 400.

**Acceptance Scenarios**:

1. **Given** an operation with a request body schema specifying required fields (e.g., `["name", "category"]`), **When** test generation executes with 400 generation enabled, **Then** a test case is emitted with `test_type="negative_invalid_input"`, where one required field is deterministically omitted from the body, and expected status `400`.
2. **Given** an operation with a request body schema that has properties but NO required fields, **When** test generation executes, **Then** a test case is emitted with one field's type mutated (e.g., string replaced with an array or boolean), producing an invalid schema payload with expected status `400`.
3. **Given** an operation with NO request body (e.g., `GET /pets`) or an untyped/empty body schema, **When** test generation executes, **Then** no 400 test case is generated.
4. **Given** an operation that requires authentication and has a request body, **When** the 400 test case is emitted, **Then** valid authentication headers/tokens are preserved intact because this tests payload validation, not security.

---

### User Story 3 - Independent CLI Control & Sibling Export Serialization (Priority: P3)

As a test engineer exporting runnable test artifacts,
I want to control 404 and 400 test case generation independently via CLI flags, and have them exported seamlessly into Postman and REST Client files as sibling requests,
So that I can selectively enable negative test coverage in CI/CD and inspect all positive and negative variants grouped together.

**Why this priority**: Consistency with Feature 007's default-enabled `--negative-auth` pattern ensures pipeline predictability while giving users fine-grained control over which negative scenarios to include.

**Independent Test**: Can be tested independently by invoking `specprobe generate` with CLI flag permutations and exporting the result with `specprobe export`, asserting proper labeling (`[404]`, `[400]`, `# @name <op>_404`, `# @name <op>_400`) and status assertion generation.

**Acceptance Scenarios**:

1. **Given** an operation with both path parameters and a request body, **When** `specprobe generate` runs with default settings, **Then** positive, negative auth (401, 403), 404 not-found, and 400 invalid-input test cases are all generated.
2. **Given** a user passing `--no-not-found` (or equivalent opt-out flag), **When** test generation executes, **Then** 404 test cases are omitted while 400 and auth test cases remain.
3. **Given** a generated test suite containing 404 and 400 test cases, **When** exported to Postman format, **Then** items are named with `[404]` and `[400]` prefixes and contain `pm.response.to.have.status(404)` and `pm.response.to.have.status(400)` assertions respectively.
4. **Given** a generated test suite containing 404 and 400 test cases, **When** exported to REST Client `.http` format, **Then** blocks are annotated with `# @name <op>_404` and `# @name <op>_400`, accompanied by `# Expected Status: 404` and `# Expected Status: 400` comments.

---

### Edge Cases

- **Operations with multiple path parameters**: How does the mutator decide which path parameter to alter (e.g., `/teams/{teamId}/members/{memberId}`)? Altering the leaf (`memberId`) tests item not-found; altering the parent (`teamId`) tests parent not-found.
- **Path parameters with strict pattern regex or enum constraints**: If a path parameter defines `enum: ["active", "archived"]` or a regex pattern, how is an out-of-range/nonexistent value constructed that fails resource lookup without triggering a router-level 400 or 404?
- **Schemas with `$ref` or composition (`allOf`/`oneOf`/`anyOf`)**: How does the 400 mutation step resolve required fields inside nested schemas or composed definitions?
- **Operations with request bodies that permit arbitrary additional properties**: If a schema has `additionalProperties: true` and no required properties, type corruption on an existing property is required rather than injecting unrecognized keys.
- **Combined flag vs. granular flags**: How should CLI flags be structured to avoid flag proliferation while maintaining granular control?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST extend `GeneratedTestCase.test_type` to include `negative_not_found` and `negative_invalid_input` alongside existing `positive`, `negative_auth_missing`, and `negative_auth_invalid` types.
- **FR-002**: System MUST deterministically generate a 404 Not Found test case (`negative_not_found`) for any operation defining at least one path parameter, mutating the path parameter value to a nonexistent representation while keeping all headers, credentials, and body fixtures identical to the positive test case.
- **FR-003**: System MUST mutate path parameters based on parameter schema type:
  - Integer / Number: Out-of-range positive sentinel value (e.g., `999999` or `2147483647`).
  - String with UUID format: Formatted nil UUID (`"00000000-0000-0000-0000-000000000000"`).
  - String with general format or unformatted: Syntactically valid non-existent slug (e.g., `"specprobe-nonexistent-id"`).
- **FR-004**: System MUST skip 404 test case generation for operations that declare no path parameters.
- **FR-005**: System MUST deterministically generate a 400 Bad Request test case (`negative_invalid_input`) for any operation defining a schema-constrained request body, mutating the payload to violate the schema while keeping path parameters, query parameters, headers, and credentials identical to the positive test case.
- **FR-006**: System MUST mutate request bodies using a minimal violation strategy:
  - If the schema defines `required` properties: omit exactly one required property (the first required field found).
  - If the schema defines `properties` but no `required` fields: replace one property value with a contradictory type (e.g., replace string with boolean or array).
  - If the schema is an array type: supply an object or primitive instead of an array.
- **FR-007**: System MUST skip 400 test case generation for operations that have no request body or whose request body has no defined schema properties/constraints.
- **FR-008**: System MUST support independent boolean CLI flag pairs on `specprobe generate`:
  - `--not-found` / `--no-not-found`: Controls 404 not-found test case generation (default: enabled).
  - `--invalid-input` / `--no-invalid-input`: Controls 400 invalid-input test case generation (default: enabled).
  - These operate alongside existing `--negative-auth` / `--no-negative-auth`, allowing users to independently toggle any combination of negative test generators.
- **FR-009**: Exporter for Postman MUST serialize `negative_not_found` items with `[404]` name prefix and a `pm.response.to.have.status(404)` assertion in the test script.
- **FR-010**: Exporter for Postman MUST serialize `negative_invalid_input` items with `[400]` name prefix and a `pm.response.to.have.status(400)` assertion in the test script.
- **FR-011**: Exporter for REST Client (`.http`) MUST serialize `negative_not_found` items with `# @name <operation_id>_404` and `# Expected Status: 404`.
- **FR-012**: Exporter for REST Client (`.http`) MUST serialize `negative_invalid_input` items with `# @name <operation_id>_400` and `# Expected Status: 400`.
- **FR-013**: System MUST preserve valid collection/file variable parameterization for security credentials in both 404 and 400 test cases (unlike 401 which strips credentials and 403 which inlines invalid credentials).
- **FR-014**: System MUST execute 100% deterministically with ZERO LLM calls for both 404 and 400 generation steps (in compliance with Constitution Principle II).

---

### Key Entities

- **GeneratedTestCase**: The core model representing a runnable test case. Extended with new `test_type` values (`negative_not_found`, `negative_invalid_input`).
- **PathParameterMutator**: Deterministic utility responsible for inspecting parameter schemas and generating nonexistent sentinel values.
- **RequestBodyMutator**: Deterministic utility responsible for analyzing JSON Schema constraints (`required`, `properties`, `type`) and applying minimal schema-violating mutations.
- **NegativeGenerationConfig**: Configuration entity capturing user choices for `--negative-auth`, `--not-found`, and `--invalid-input` generation modes.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of operations with path parameters produce a corresponding 404 test case when 404 generation is enabled.
- **SC-002**: 100% of operations with schema-constrained request bodies produce a corresponding 400 test case when 400 generation is enabled.
- **SC-003**: 0% regression on happy-path and negative-auth test generation; existing positive (2xx) and auth (401/403) test cases remain byte-for-byte identical.
- **SC-004**: Zero LLM calls are invoked during 404 parameter mutation and 400 body mutation (zero token cost and sub-millisecond execution time per operation).
- **SC-005**: Both Postman and REST Client exporters serialize 404 and 400 items as siblings within the same operation group with appropriate status assertions.
- **SC-006**: CLI allows full control to disable either or both negative test generators independently.

---

## Assumptions

- **Target Operation Scope**: Operations without path parameters cannot support meaningful 404 generation and must be skipped silently for the 404 pass.
- **Target Body Scope**: Operations without request bodies (e.g. `GET`, `DELETE` without payload) cannot support meaningful 400 generation and must be skipped silently for the 400 pass.
- **Leaf-Parameter Priority**: When an operation contains multiple path parameters (e.g., `/tenants/{tenantId}/items/{itemId}`), mutating the leaf/last path parameter represents the standard resource-level 404 scenario.
- **Minimal Mutation Rationale**: Violating one required property or one field type is more diagnostically valuable than obliterating the entire payload, as it isolates single validation rule failures.
- **Security Independence**: 404 and 400 test cases test routing and input validation respectively; hence, authentication credentials must be kept valid so requests reach the routing/validation logic.
