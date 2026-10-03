# Feature Specification: Structural Diff Between OpenAPI Spec Versions (specprobe diff)

**Feature Branch**: `013-diff-spec-versions`

**Created**: 2026-10-03

**Status**: Draft

**Input**: User description: "A new CLI command, specprobe diff <old_spec> <new_spec>, that deterministically compares two OpenAPI 3.0/3.1 spec files and reports what changed between them at the operation and schema level — zero-LLM, same spirit as chunk/export. Reuses the existing chunker's extraction/pruning logic internally to normalize both specs into comparable per-operation structures rather than re-implementing OpenAPI parsing. Scope for v1: Operation-level changes (operations added/removed, keyed on method + path). Breaking schema changes (request body/parameter gains new required field, response schema loses property, field declared type changes, enum loses valid value). Output as streaming JSONL to stdout plus optional --summary human-readable table to stderr. Exit code reflects whether breaking changes were found. Explicit non-goals for v1: No non-breaking/cosmetic change detection, no semantic versioning, no LLM-assisted judgment calls, no diffing against vector index."

## Clarifications

### Session 2026-10-03

- Q: How should `specprobe diff` match endpoint paths when parameter variable names within the path template differ between versions (for example, `/pets/{petId}` versus `/pets/{id}`)? → A: Structural path template matching — normalize parameter placeholders to positional wildcards (e.g. `/pets/{}`) so `/pets/{petId}` and `/pets/{id}` match as the same endpoint, allowing parameter-level schema changes to be evaluated rather than falsely reporting an operation removal and addition.
- Q: When a candidate specification completely removes an existing response status code from an endpoint, how should `specprobe diff` report this breaking change? → A: B, 2xx removals only — Introduce a dedicated breaking change type `response_status_removed` scoped strictly to 2xx success status codes (e.g. 200, 201, 204). Removing a 2xx success response breaks client branches/deserialization, whereas removing 4xx/5xx error responses breaks nothing and remains unreported per v1 non-breaking exclusion rules. Status swaps (e.g. 200 → 201) are naturally captured as 200 removal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operation-Level Change Detection (Priority: P1) 🎯 MVP

API developers, platform engineers, and API consumers comparing two OpenAPI specification revisions need to identify which endpoints have been introduced or discontinued between releases. When comparing an older baseline specification and a newer candidate specification, the system compares all operations identified by HTTP method and endpoint path. It reports newly added operations (present in the candidate specification but not the baseline) and removed operations (present in the baseline but not the candidate), flagging removed operations as breaking changes and added operations as non-breaking changes.

**Why this priority**: Adding or removing endpoints is the highest-level architectural change in an API lifecycle. Discontinuing an endpoint is immediately breaking for clients targeting that endpoint, while adding an endpoint represents newly available functionality.

**Independent Test**: Run the comparison command on two specifications where specific endpoints were added and removed. Verify that each added and removed endpoint is accurately identified and emitted with operation details (HTTP method, endpoint path) and breaking change classification.

**Acceptance Scenarios**:

1. **Given** an old specification and a new specification with an added endpoint (e.g. `POST /pets`), **When** compared, **Then** the added operation is reported with its method and path, identified as non-breaking (`breaking: false`).
2. **Given** an old specification and a new specification where an existing endpoint was deleted (e.g. `DELETE /pets/{id}`), **When** compared, **Then** the removed operation is reported with its method and path, identified as a breaking change (`breaking: true`).
3. **Given** two specifications where an operation's `operationId` changed but its HTTP method and path remained identical, **When** compared, **Then** the operation is recognized as the same endpoint and is not reported as an added or removed operation.
4. **Given** two specifications where an endpoint path parameter token is renamed (e.g. `GET /pets/{petId}` in the old specification, `GET /pets/{id}` in the new specification), **When** compared, **Then** the operation is recognized as the same endpoint and is not reported as an added or removed operation.
5. **Given** two identical specifications, **When** compared, **Then** zero operation changes are reported.

---

### User Story 2 - Breaking Schema and Response Change Detection (Priority: P2)

API developers and client SDK authors need automated detection of schema and status code changes that would break existing clients communicating with the API. The system inspects operations shared across both specifications and flags five specific, mechanically verifiable breaking changes:
1. A request body or parameter schema gains a new required field or property.
2. A response schema loses a property that was previously declared.
3. An existing field's declared data type changes (e.g. string to integer).
4. An enum definition loses a previously valid value.
5. An existing 2xx success response status code (e.g. 200, 201, 204) is removed from an operation (`response_status_removed`).

**Why this priority**: Silent breaking schema changes and removed success status codes frequently cause production downtime and runtime deserialization errors for API consumers. Catching these structural regressions guarantees contract integrity without human guesswork or probabilistic models.

**Independent Test**: Run the comparison command against specification pairs that isolate each of the breaking schema and response status scenarios across parameters, request bodies, and responses. Verify that each scenario produces a breaking change record specifying the operation, schema location, change category, and before/after values.

**Acceptance Scenarios**:

1. **Given** an operation where the candidate specification adds a required property to a request body or parameter schema (or changes an optional property to required), **When** compared, **Then** the system emits a breaking change record detailing the newly required field.
2. **Given** an operation where the candidate specification removes a property previously defined in a response schema, **When** compared, **Then** the system emits a breaking change record detailing the removed property.
3. **Given** an operation where an existing field in a parameter, request body, or response schema has its declared data type altered, **When** compared, **Then** the system emits a breaking change record detailing the previous and new data types.
4. **Given** an operation where an enum definition in a parameter, request body, or response schema removes an allowable value, **When** compared, **Then** the system emits a breaking change record detailing the removed enum value.
5. **Given** an operation where the candidate specification removes a 2xx success response status code (e.g. `200` removed, or swapped `200` to `201`), **When** compared, **Then** the system emits a breaking change record with `change_type: "response_status_removed"` and `breaking: true`.
6. **Given** an operation where a non-2xx status code (e.g. `404`, `409`, `500`) is removed, **When** compared, **Then** this is treated as non-breaking and is excluded from diff reporting.
7. **Given** non-breaking schema additions (such as adding an optional request field, adding a new response field, or adding a new enum value), **When** compared, **Then** these are excluded from change reporting in accordance with v1 scope.

---

### User Story 3 - Machine-Readable Streaming Output, Summary Tables, and CI Exit Codes (Priority: P3)

DevOps engineers and automation tooling need machine-readable output to integrate into CI/CD pipelines and PR validation checks, as well as clear human-readable summaries for local developers reviewing changes. The system emits structured JSONL records (one per detected change) to standard output, provides an optional `--summary` flag that displays a formatted summary table of detected changes to standard error, and returns a non-zero exit code when breaking changes are detected (and zero when only non-breaking changes or no changes exist).

**Why this priority**: Enables programmatic consumption by pipeline scripts, PR bots, and downstream tooling, while offering an immediate human-readable summary and reliable exit codes for automated gating.

**Independent Test**: Execute the command against specifications with and without breaking changes, piping standard output to a JSON parser, and inspecting standard error and process exit status.

**Acceptance Scenarios**:

1. **Given** detected changes, **When** the comparison runs, **Then** each change is emitted as an independent JSON line on standard output with fields for change category, breaking status, operation method, path, target path/pointer, description, and old/new values.
2. **Given** the `--summary` option is passed, **When** the comparison completes, **Then** a summary table is written to standard error summarizing totals of added operations, removed operations, and breaking schema changes by category, leaving standard output containing only raw JSONL.
3. **Given** one or more breaking changes (e.g. removed operation, breaking schema change, or removed 2xx status code), **When** execution finishes, **Then** the command exits with exit code 1.
4. **Given** zero breaking changes (even if non-breaking operation additions are present), **When** execution finishes, **Then** the command exits with exit code 0.
5. **Given** invalid or missing specification files, **When** execution starts, **Then** the command outputs a descriptive error message to standard error and exits with exit code 2.

---

### Edge Cases

- **Invalid or missing specification files**: If either the old or new specification file path does not exist, cannot be opened, or contains invalid JSON or YAML syntax, the command outputs a descriptive error message to standard error and terminates with exit code 2.
- **Unsupported specification versions**: If either input file is a Swagger 2.0 specification or unsupported schema version, the command terminates with an error message on standard error and exit code 2.
- **Identical specifications**: When identical specification files are compared, the command emits zero change lines on standard output, reports 0 changes in `--summary`, and exits with exit code 0.
- **Method case-insensitivity**: HTTP methods declared in lowercase (e.g., `get`, `post`) or uppercase (`GET`, `POST`) are normalized to uppercase so that casing differences do not produce false operation additions or removals.
- **Path template matching**: Operations are keyed by HTTP method and structurally normalized URL path templates (normalizing parameter variable names like `{petId}` and `{id}` to a positional placeholder `{}`), ensuring parameter token renames match as the same endpoint and are diffed at the parameter level rather than triggering false operation removals/additions.
- **Nested schema structures**: Breaking changes (such as added required fields, removed response fields, type changes, or removed enum values) located within nested object hierarchies (properties within properties) or array item schemas are detected and reported with their full hierarchical property path.
- **Response status code changes**: Removing a 2xx success status code (e.g. 200, 201, 204) from an operation is reported as a breaking change (`change_type: "response_status_removed"`). Removing non-2xx status codes (4xx, 5xx) is considered non-breaking and is excluded from reporting in v1. Status code swaps (e.g. 200 replaced by 201) are naturally detected as the removal of 200.
- **Reordered elements**: Reordering of properties in schemas or parameters in operations without structural modification is ignored and produces no diff records.
- **Cosmetic and documentation updates**: Changes to description text, summaries, titles, contact information, license information, or example values are ignored in v1.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `specprobe diff <old_spec> <new_spec>` CLI command that accepts paths to two OpenAPI 3.0 or 3.1 specification files (JSON or YAML) and performs a deterministic structural diff between them.
- **FR-002**: System MUST operate completely offline with zero LLM invocations and zero external network calls during diff execution (adhering strictly to Constitution Principle II).
- **FR-003**: System MUST identify and match operations between specifications using a compound key of normalized uppercase HTTP method and structurally normalized endpoint path template (converting parameter tokens like `{petId}` and `{id}` to positional wildcards `{}`), disregarding `operationId` modifications and path parameter token naming differences.
- **FR-004**: System MUST detect operations present in the candidate specification but absent from the baseline specification, reporting them as added operations with `breaking: false`.
- **FR-005**: System MUST detect operations present in the baseline specification but absent from the candidate specification, reporting them as removed operations with `breaking: true`.
- **FR-006**: System MUST detect when an existing operation's request body or parameter schema gains a new required field or property (or an existing optional property becomes required), reporting it as a breaking change with `breaking: true`.
- **FR-007**: System MUST detect when an existing operation's response schema loses a property that was declared in the baseline specification, reporting it as a breaking change with `breaking: true`.
- **FR-008**: System MUST detect when an existing field or property in a parameter, request body, or response schema changes its declared data type, reporting it as a breaking change with `breaking: true`.
- **FR-009**: System MUST detect when an existing enum definition in a parameter, request body, or response schema removes one or more allowable values, reporting it as a breaking change with `breaking: true`.
- **FR-010**: System MUST stream detected change records as JSONL (one JSON object per line) to standard output (`stdout`), where each record includes change type, breaking flag, HTTP method, path, schema location pointer, human-readable description, old value, and new value.
- **FR-011**: System MUST support an optional `--summary` CLI flag that renders a formatted table to standard error (`stderr`) summarizing the count of added operations, removed operations, and breaking schema/status changes by category.
- **FR-012**: System MUST exit with return code 1 when one or more breaking changes (`breaking: true`) are detected.
- **FR-013**: System MUST exit with return code 0 when no breaking changes are detected (including cases with zero changes or only non-breaking operation additions).
- **FR-014**: System MUST exit with return code 2 and write an informative error message to standard error (`stderr`) when either input file does not exist, cannot be read, contains malformed syntax, or represents an unsupported specification version.
- **FR-015**: System MUST exclude cosmetic and non-breaking modifications (description text, examples, summaries, parameter reordering, and schema property reordering) from change reporting in v1.
- **FR-016**: System MUST detect when an existing operation removes a 2xx success response status code (e.g. 200, 201, 204) previously declared in the baseline specification, reporting it as a breaking change with `change_type: "response_status_removed"` and `breaking: true`. Removals of non-2xx status codes (4xx, 5xx) MUST NOT be reported.

### Key Entities *(include if feature involves data)*

- **DiffChangeRecord**: Represents an individual detected change between two specification versions.
  - `change_type`: The category of change (`operation_added`, `operation_removed`, `required_request_property_added`, `response_property_removed`, `response_status_removed`, `type_changed`, `enum_value_removed`).
  - `breaking`: Boolean indicator where `true` designates a contract-breaking change for API consumers.
  - `method`: HTTP method of the affected operation (e.g. `GET`, `POST`, or `null` for global/spec-level scope).
  - `path`: URL path template of the affected operation (e.g. `/pets/{id}`).
  - `location`: Structured location identifier or JSON pointer indicating where the change occurred (e.g. `responses['200']` or `requestBody.content['application/json'].schema.properties.name`).
  - `description`: Plain-language explanation of the change.
  - `old_value`: The value or declaration present in the baseline specification (`null` for additions).
  - `new_value`: The value or declaration present in the candidate specification (`null` for removals).
- **DiffSummary**: Aggregate summary metrics computed over all detected differences.
  - `total_changes`: Total number of detected change records.
  - `breaking_changes`: Total count of changes with `breaking: true`.
  - `operations_added`: Count of new operations introduced.
  - `operations_removed`: Count of existing operations discontinued.
  - `schema_breaking_changes`: Count of breaking schema and response status modifications across shared operations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of added and removed operations between two specifications are detected and categorized correctly, with 0 false additions/removals caused by `operationId` renames or parameter placeholder token differences (e.g. `{petId}` vs `{id}`).
- **SC-002**: 100% of defined breaking schema and response changes (new required request properties, removed response properties, type changes, removed enum values, and removed 2xx response status codes) across test fixtures are detected and marked as breaking.
- **SC-003**: 0 non-breaking or cosmetic modifications (description edits, example alterations, property reordering, non-2xx status code removals) are reported in output records.
- **SC-004**: Comparison of two 1,000-operation OpenAPI specifications completes in under 2 seconds on standard developer workstations.
- **SC-005**: Exit code 1 is returned in 100% of runs containing breaking changes, and exit code 0 is returned in 100% of runs containing only non-breaking changes or identical specifications.
- **SC-006**: Standard output emits strictly valid, line-delimited JSON (JSONL) records that can be parsed by standard stream processors without stderr pollution when `--summary` is active.

## Assumptions

- Specifications are provided as local files adhering to OpenAPI 3.0 or 3.1 syntax in JSON or YAML format.
- Operations are uniquely identified within each specification by HTTP method and URL path template.
- Cosmetic modifications (descriptions, titles, examples, formatting) do not affect consumer integration contracts and are deliberately excluded from v1.
- Non-2xx response status code removals do not break client contracts and are excluded from v1 diff reporting.
- No dependency on local vector index or embedding stores; diff operates strictly and deterministically on file inputs.
- The command executes locally in an air-gapped or developer workstation environment with zero external network connectivity.
