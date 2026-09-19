# Feature Specification: OpenAPI Operation Chunking CLI

**Feature Branch**: `001-chunk-openapi-spec`

**Created**: 2026-09-18

**Status**: Draft

**Input**: User description: "A specprobe chunk CLI command that takes an OpenAPI 3.0 or 3.1 spec (YAML or JSON) and splits it into one chunk per operation. Each chunk contains the operation with referenced schemas resolved and trimmed to what that operation actually uses. Metadata per chunk: path, method, tags, operationId (synthesized when missing), security schemes (operation-level, falling back to global), deprecated flag, and the source spec's title and version. It must handle circular refs, allOf/oneOf/anyOf, and path-level shared parameters. External file refs are reported as unsupported instead of silently dropped, and Swagger 2.0 is rejected with a clear message. Each chunk reports an approximate token count, and a warning is emitted when it exceeds a configurable budget. Output is JSON so I can inspect it. A --stats flag prints operation count, chunk size distribution, and warnings, and --op <operationId> prints a single chunk for spot checking. Nothing is embedded or sent to an LLM in this feature."

## Clarifications

### Session 2026-09-18
- Q: What top-level JSON structure should `specprobe chunk` output by default? → A: Newline-delimited JSON (JSON Lines / JSONL), outputting one complete JSON chunk per line.
- Q: How should circular schema references be represented in each chunk's schema definitions? → A: Retain local $ref pointers (e.g., #/components/schemas/Node) in the schema and define the component once in components.schemas without infinite expansion.
- Q: When the `--stats` flag is supplied, how should `specprobe chunk` present the output? → A: Exclusive mode: Print human-readable summary text/tables to standard output instead of emitting chunks.
- Q: When an unsupported external file reference is encountered, how should the CLI handle execution and exit status? → A: Non-fatal warning (exit code 0): Preserve the raw $ref string, attach a warning to chunk metadata/stderr, and continue processing.
- Q: Which method should `specprobe chunk` use to calculate each chunk's approximate token count? → A: Standard character heuristic (~4 chars/token on serialized JSON), fast and dependency-free.
- Q: How should large interconnected specifications with deep schema graphs be prevented from blowing up chunk token counts? → A: Cap schema traversal depth at `--schema-depth` (default 2) from direct operation schemas. Schemas within the depth limit are fully included in components.schemas; schemas exceeding the limit remain as bare $ref pointers in the parent schema and are omitted from components.schemas, with a warning recorded in chunk metadata naming the truncated schema and its depth.

### Key Decisions & Trade-offs
- **Schema Traversal Depth Cap vs. Complete Self-Containment**: A pure transitive schema closure guarantees that every $ref inside a chunk resolves locally within `components.schemas`. However, in enterprise and real-world specifications (such as Stripe's 1,454-schema graph), transitive reachability causes nearly the entire API model (~879 schemas / ~268k tokens) to be duplicated into every chunk. Capping traversal depth (default 2, configurable via `--schema-depth`) reduces chunk sizes by orders of magnitude (to hundreds or low thousands of tokens), making chunks viable for inspection and downstream tooling. **Trade-off:** Chunks are no longer guaranteed to be fully self-contained past the depth limit; schemas deeper than the limit remain as unresolved bare $ref references, with explicit warnings recorded in chunk metadata.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Core Operation Chunking with Schema Trimming (Priority: P1)

As an API engineer or developer working with large API definitions, I want to split an OpenAPI 3.0 or 3.1 specification into discrete, pruned chunks (one per operation) with unused schemas pruned up to a configurable traversal depth, so that I can inspect, index, and analyze individual endpoints without carrying the entire specification's overhead.

**Why this priority**: This is the primary value delivery of the command. Generating clean, trimmed operation chunks is the core engine required for any downstream testing, probing, or inspection tasks.

**Independent Test**: Can be tested independently by supplying an OpenAPI 3.0 or 3.1 specification (YAML or JSON) to `specprobe chunk <file>`, verifying that the output contains exactly one JSON chunk per operation, with path-level parameters merged, metadata attached, and only referenced schemas up to `--schema-depth` included.

**Acceptance Scenarios**:

1. **Given** a valid OpenAPI 3.0 or 3.1 document with multiple paths and operations, **When** the user runs `specprobe chunk <file>`, **Then** the system outputs newline-delimited JSON (JSON Lines / JSONL) with one chunk JSON object per line.
2. **Given** an operation that references a component schema (e.g., `#/components/schemas/User`), which in turn references nested schemas, **When** chunking occurs, **Then** the chunk includes the operation definition and referenced schemas up to the traversal depth limit (`--schema-depth`, default 2), leaving out unreferenced schemas from the root document and truncating schemas beyond the depth limit with bare `$ref` pointers retained and warnings recorded.
3. **Given** an API path with path-level parameters shared across operations, **When** operations under that path are chunked, **Then** path-level parameters are inherited by each operation chunk, with operation-level parameters overriding path-level parameters sharing the same name and `in` location.
4. **Given** an operation without an explicit `operationId`, **When** chunking occurs, **Then** the system synthesizes a deterministic, unique `operationId` derived from the HTTP method and sanitized path (e.g., `get_users_user_id`).
5. **Given** an operation without operation-level security requirements in a spec with global security, **When** chunked, **Then** the chunk's metadata inherits the global security schemes; if the operation explicitly specifies `security: []`, it reports an empty security requirement.
6. **Given** an operation with metadata attributes, **When** chunked, **Then** each chunk includes `path`, `method` (uppercase), `tags`, `operationId`, `security`, `deprecated` (boolean), `source_title`, and `source_version`.

---

### User Story 2 - Token Counting, Budget Alerts, and Statistics Summary (Priority: P2)

As an API practitioner preparing specification chunks for local processing, I want each chunk to report its estimated token size, warn me when a chunk exceeds my token budget, and view high-level distribution statistics using `--stats`, so that I can spot oversized operations and evaluate the API's overall footprint.

**Why this priority**: Real-world operations can contain deeply nested or expansive schemas that overwhelm local models or review buffers. Token estimations and statistical summaries provide vital operational visibility into chunk sizing.

**Independent Test**: Can be tested independently by running `specprobe chunk <file> --stats` or configuring `--max-tokens <budget>`, asserting that token counts are reported, warnings are emitted for oversized chunks, and the summary table or JSON breakdown accurately describes total operation counts and size distributions.

**Acceptance Scenarios**:

1. **Given** any processed operation chunk, **When** the chunk payload is emitted, **Then** an approximate token count field is included in the chunk metadata.
2. **Given** a chunk whose token count exceeds the configured budget (defaulting to 2000 tokens, or overridden via `--max-tokens`), **When** chunking is performed, **Then** an explicit warning is attached to the chunk and reported to standard error / warning summary.
3. **Given** a specification, **When** the user executes `specprobe chunk <file> --stats`, **Then** the system operates in exclusive mode, printing a human-readable summary table to standard output (displaying total operations count, chunk token size distribution across min/max/median/average, and all warnings) instead of streaming chunk JSONL.

---

### User Story 3 - Targeted Spot Checking for Single Operations (Priority: P3)

As a developer debugging or verifying a specific endpoint, I want to isolate and print a single chunk using `--op <operationId>`, so that I can quickly spot check schema resolution, parameter inheritance, and metadata without parsing the entire multi-operation payload.

**Why this priority**: Large OpenAPI documents often contain hundreds of operations. Forcing users to scroll or filter massive JSON payloads hinders rapid verification and developer experience.

**Independent Test**: Can be tested independently by running `specprobe chunk <file> --op <operationId>` on a known specification and verifying that only the single targeted operation chunk is printed to standard output.

**Acceptance Scenarios**:

1. **Given** a specification containing an operation with ID `getUserById`, **When** the user executes `specprobe chunk <file> --op getUserById`, **Then** only the single chunk corresponding to `getUserById` is emitted to standard output.
2. **Given** an operation that had its ID synthesized by the system, **When** the user runs `--op <synthesizedId>`, **Then** the targeted chunk is located and displayed.
3. **Given** a user provides an `--op <invalidId>` that does not match any operation, **When** the command executes, **Then** the system exits with a non-zero status code and prints a descriptive error indicating the operation ID was not found.

---

### User Story 4 - Specification Validation & Unsupported Reference Guardrails (Priority: P4)

As an API engineer submitting various specification files, I want clear rejection of outdated Swagger 2.0 specs and clear warnings for external file references, so that I understand exactly why a file cannot be processed instead of experiencing silent failures or incomplete output.

**Why this priority**: Robust input validation and guardrails prevent corrupt data from propagating into downstream tools, saving developers time when diagnosing compatibility issues.

**Independent Test**: Can be tested independently by passing a Swagger 2.0 document and an OpenAPI 3.x document containing external file `$ref` links, verifying that Swagger 2.0 is cleanly rejected with an informative message and external references generate explicit warnings.

**Acceptance Scenarios**:

1. **Given** a document with `"swagger": "2.0"`, **When** the user runs `specprobe chunk <file>`, **Then** the command rejects the document immediately with a clear, user-facing error message stating that Swagger 2.0 is not supported and OpenAPI 3.0 or 3.1 is required.
2. **Given** an OpenAPI 3.x document containing external file references (e.g., `$ref: "common-models.yaml#/components/schemas/Error"`), **When** chunking occurs, **Then** the system does not silently ignore or drop the reference; instead, it generates a non-fatal descriptive warning detailing the unsupported external reference location, attaches it to chunk metadata/stderr, preserves the raw `$ref` string, and completes with exit code 0.
3. **Given** a malformed YAML or JSON file, **When** the user runs the command, **Then** the system reports a parsing error with file and syntax details and exits cleanly.

---

### Edge Cases

- **Circular Schema References**: A schema references itself directly (e.g., `Node` has a field `children` of type `Array<Node>`) or mutually through cycles (`A` -> `B` -> `A`). The system must detect cycles, terminate recursion at cycle boundaries, retain standard local `$ref` pointers (e.g., `#/components/schemas/Node`), and define the target schema once in `components.schemas` without infinite loop or stack overflow.
- **Complex Schema Compositions**: Schemas utilizing `allOf`, `oneOf`, `anyOf`, and `not` alongside nested `$ref` properties must resolve all branches participating in the active operation while pruning untouched sibling definitions.
- **Deep Schema Chains & Interconnected Graphs**: Specifications with deeply interconnected schemas (e.g., Stripe) can trigger transitive explosion where almost all schemas are pulled into every chunk. Schema traversal is capped at `--schema-depth` (default 2). Schemas beyond this limit retain bare `$ref` pointers in parent schemas, are excluded from `components.schemas`, and have descriptive warnings recorded in chunk metadata.
- **Path-Level vs. Operation-Level Parameter Overrides**: When a parameter with the same `name` and `in` location (e.g., header `X-Request-Id`) is declared at both the path item level and operation level, the operation-level declaration must take precedence.
- **Explicit Security Disabling**: An operation declaring `security: []` explicitly disables security, which must be represented as an empty security requirement rather than falling back to global security.
- **Operation ID Collisions**: If multiple operations omit `operationId` and map to the same method and path (or sanitized equivalent), the synthesis algorithm must ensure unique identifiers (e.g., appending numeric suffixes if necessary).
- **Empty / Minimal Specifications**: Specifications with no paths or empty path items must produce an empty chunk collection (or zero operations reported in `--stats`) without crashing.
- **Very Large Schemas Exceeding Budget**: Extremely large schemas that exceed the token budget must still be completely resolved up to the traversal depth limit and output in full, but accompany an explicit budget overage warning.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept OpenAPI 3.0.x and 3.1.x specification files provided in either YAML or JSON format via file path argument.
- **FR-002**: System MUST validate input specifications and reject Swagger 2.0 documents with an explicit, user-friendly error message indicating that OpenAPI 3.0+ is required.
- **FR-003**: System MUST identify and process all operations defined across all path items and standard HTTP methods (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`, `TRACE`).
- **FR-004**: System MUST merge path-level parameters into each child operation chunk, giving precedence to operation-level parameters whenever a parameter name and `in` location match.
- **FR-005**: System MUST resolve schema references (`$ref`) utilized by each operation (including parameters, request bodies, responses, headers, and callbacks) up to a configurable traversal depth (default 2, configurable via `--schema-depth`). Schemas within the depth limit MUST be included in `components.schemas`. Schemas beyond the depth limit MUST NOT have their definitions included, their bare `$ref` pointers MUST be preserved in parent schemas, and a descriptive warning naming the truncated schema and depth MUST be recorded in chunk metadata.
- **FR-006**: System MUST detect circular schema references and safely resolve them by retaining internal local `$ref` pointers (e.g., `#/components/schemas/<Name>`) and defining each referenced component once in the chunk's `components.schemas` dictionary, terminating recursive traversal at cycle boundaries.
- **FR-007**: System MUST support composite schema structures (`allOf`, `oneOf`, `anyOf`, `not`), resolving and including all component schemas required across all composite branches.
- **FR-008**: System MUST treat external file `$ref` references as non-fatal warnings: preserving the raw `$ref` string within the chunk, attaching a warning notice to the chunk's metadata and printing it to standard error / `--stats`, and completing execution with exit code 0 without silently dropping or omitting the reference.
- **FR-009**: System MUST include standardized metadata in each chunk payload:
  - `path`: The endpoint URI template (e.g., `/api/v1/users/{id}`).
  - `method`: The HTTP method in uppercase.
  - `tags`: List of associated tags (or empty list if absent).
  - `operationId`: The operation's identifier (explicit or synthesized).
  - `security`: Operation-level security requirements, or inherited global security requirements if omitted, or empty if explicitly overridden with `[]`.
  - `deprecated`: Boolean flag indicating if the operation is marked deprecated (default `false`).
  - `source_title`: The API title defined in `info.title` (or "Untitled API" if absent).
  - `source_version`: The API version defined in `info.version` (or "0.0.0" if absent).
  - `estimated_tokens`: The approximate token count of the complete chunk.
- **FR-010**: System MUST synthesize a deterministic, unique `operationId` whenever an operation lacks an explicit identifier, following the convention `{method}_{normalized_path}`.
- **FR-011**: System MUST compute an approximate token count for each chunk using a standard deterministic character heuristic (~4 characters per token calculated over the serialized JSON representation of the chunk), requiring zero external tokenizer dependencies.
- **FR-012**: System MUST emit an explicit warning whenever an operation chunk's estimated token count exceeds the configured token budget (defaulting to 2000 tokens).
- **FR-013**: System MUST allow users to customize the token budget via a `--max-tokens` CLI option.
- **FR-014**: System MUST format its primary output as newline-delimited JSON (JSON Lines / JSONL) written to standard output, emitting one self-contained chunk JSON object per line.
- **FR-015**: System MUST provide an `--op <operationId>` CLI option that outputs only the single chunk corresponding to the requested identifier as formatted JSON, exiting with a non-zero code if not found.
- **FR-016**: System MUST provide a `--stats` CLI option that operates in exclusive mode, outputting a human-readable summary table to standard output (displaying total operation count, token size distribution including minimum, maximum, median, average, and a breakdown of all warnings) instead of emitting chunks.
- **FR-017**: System MUST execute fully offline and deterministically, without invoking any LLM, cloud API, or embedding service.

### Key Entities *(include if feature involves data)*

- **Operation Chunk**: The atomic data structure representing a single API operation. Contains the normalized operation definition (path, method, parameters, request body, responses), the pruned subset of referenced schemas (`components.schemas`), and the metadata block.
- **Chunk Metadata**: Standardized descriptor block capturing operational context (`path`, `method`, `tags`, `operationId`, `security`, `deprecated`, `source_title`, `source_version`, `estimated_tokens`).
- **Chunking Statistics**: Aggregate summary entity capturing total operations, token size percentiles (min, max, median, average), count of oversized operations, and diagnostic warning notices.
- **Warning Notice**: Diagnostic record detailing an advisory condition (e.g., token budget exceeded, unsupported external reference encountered) with file and path pointers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of operations in valid OpenAPI 3.0 and 3.1 specifications are partitioned into discrete, self-contained chunks with no lost operations.
- **SC-002**: 100% of unreferenced components (schemas, parameters, responses) are omitted from each individual operation chunk, reducing chunk payload size compared to the monolithic specification.
- **SC-003**: 100% of circular schema references are resolved without application freeze, stack overflow, or process crash.
- **SC-004**: When executed with `--stats`, user receives complete distribution statistics (min, max, median, average token counts) and warning tallies in under 2 seconds for specifications containing up to 500 operations.
- **SC-005**: 100% of Swagger 2.0 specifications are caught and rejected with a user-facing explanation before any processing occurs.
- **SC-006**: 100% of external file references are surfaced with actionable warning messages identifying the specific unresolved reference location.
- **SC-007**: When executed with `--op <operationId>`, the single requested chunk is located and returned in under 500 milliseconds for specifications containing up to 500 operations.

## Assumptions

- **Target Specifications**: Specifications adhere to OpenAPI 3.0.x or 3.1.x specifications formatted as valid YAML or JSON.
- **Token Estimation Algorithm**: A deterministic character-to-token heuristic (~4 characters per token calculated over the serialized JSON representation of the chunk) provides reliable operational estimation without requiring third-party tokenizer dependencies.
- **Default Token Budget**: A default budget threshold of 2,000 tokens is an effective baseline for local model contexts, while remaining fully configurable via `--max-tokens`.
- **Output Channel Protocol**: Machine-readable JSON output is sent to standard output (`stdout`), while informational statistics (`--stats`), diagnostic messages, and warnings are directed to standard output or standard error (`stderr`) appropriately to support shell piping (`specprobe chunk api.yaml | jq .`).
