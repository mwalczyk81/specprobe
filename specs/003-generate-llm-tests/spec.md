# Feature Specification: LLM Test Generation & Filter-Only Search

**Feature Branch**: `003-generate-llm-tests`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: "A `specprobe generate` command that reads OperationChunk-bearing search results (the same JSON `specprobe search --full` produces) via stdin or a file argument, and generates Pydantic-validated test cases for each operation using a local-default LLM through the unified LiteLLM gateway: local LM Studio endpoint by default, cloud providers strictly opt-in via explicit API key environment variables, every LLM call disk-cached on a hash of the full prompt payload plus model identifier. To support generating a full test plan across an entire indexed specification rather than only a relevance-ranked subset, `specprobe search`'s query argument becomes optional when metadata filters (--source-title, --source-version, --tag, --method, --deprecated) are supplied without a query string, returning all matching chunks unranked. Each generated test case is a strictly validated Pydantic object naming the operationId it targets, proposed request fixture data, and expected response assertions (status code, JSON schema shape). Single retry on validation failure with schema error feedback in prompt; on second failure, log descriptive error to stderr and continue processing remaining operations without aborting the batch. Emits JSON to stdout (one object per generated test case), ready for downstream Postman/.http exporters."

## Clarifications

### Session 2026-09-19
- Q: When running `specprobe search` without a query string using metadata filters, how should the result limit behave compared to regular search's default limit of 5? → A: In filter-only mode (when query is omitted and filters are present), return all matching chunks by default (unlimited), while respecting an explicit `--limit <N>` if provided by the user.
- Q: What test scenario scope should `specprobe generate` produce for each target operation? → A: Generate a single primary happy-path (2xx success) test case per operation by default.
- Q: In what JSON format should `specprobe generate` emit its generated test cases to standard output? → A: JSON Lines (JSONL, one JSON object per line), streaming each test case to stdout immediately upon validation.
- Q: Should `specprobe generate` accept raw `OperationChunk` streams (such as from `specprobe chunk`) in addition to search results from `specprobe search --full`? → A: Strictly accept `specprobe search --full` output format only, enforcing the single, cohesive index-and-search pipeline contract.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate Validated Test Cases from Operation Chunks (Priority: P1)

As an API tester, developer, or automation engineer, I want to take `OperationChunk`-bearing search results (from `specprobe search --full` via standard input or a file) and run `specprobe generate` to produce structured, schema-validated test cases with realistic request fixtures and expected response assertions, so that I have complete, runnable test scenarios without manual authoring.

**Why this priority**: Test case generation is the core value proposition of the `generate` command. Delivering high-quality, traceable test cases targeting local language models by default allows users to generate test suites immediately while preserving total privacy over their API specifications.

**Independent Test**: Can be tested independently by feeding a JSON file of search results containing `OperationChunk` payloads into `specprobe generate`, verifying that structured test cases are emitted to `stdout` containing the target `operationId`, concrete request fixtures, and expected response assertions, and confirming that the default configuration connects to a local model endpoint.

**Acceptance Scenarios**:

1. **Given** JSON search results containing full operation chunks piped via `stdin`, **When** the user runs `specprobe search "pets" --full | specprobe generate`, **Then** the system parses each operation chunk, invokes the configured language model gateway, validates the generated test cases against the required schema, and streams the test cases as JSON Lines (JSONL) to `stdout` with exit code 0.
2. **Given** a path to a JSON file containing search results on disk, **When** the user runs `specprobe generate <path/to/results.json>`, **Then** the system reads and parses the file, generates test cases for all operations present, and emits them to `stdout`.
3. **Given** default configuration with no cloud provider environment variables or credentials set, **When** `specprobe generate` executes, **Then** the system targets a local model endpoint by default without attempting outbound connections to cloud model APIs.
4. **Given** explicit cloud provider credentials configured via environment variables and an opt-in model flag (e.g. specifying an external provider model), **When** `specprobe generate` executes, **Then** the system routes the request to the configured cloud provider via the unified gateway.
5. **Given** generated test cases, **When** inspected in the output JSON, **Then** every test case explicitly names the `operationId` (or method/path) it targets, contains concrete request fixtures (parameters, headers, body), and defines expected response assertions (status code, response schema shape).

---

### User Story 2 - Resilient Validation, Self-Correction Retry & Graceful Batch Processing (Priority: P2)

As a test automation engineer generating test suites across large specifications, I want the system to automatically prompt the model to self-correct if its output fails schema validation, and to skip unfixable operations gracefully without halting the entire batch, so that one malformed model output does not abort hours of batch processing.

**Why this priority**: Probabilistic models can occasionally emit invalid JSON, omit mandatory fields, or hallucinate non-conforming structures. Strict validation coupled with a single retry and per-operation fault tolerance ensures robust, unattended batch generation across complex API catalogs.

**Independent Test**: Can be tested independently by supplying mock model responses where an operation returns invalid schema on the first attempt and valid on the second (confirming single-retry correction), and where another operation fails twice (confirming descriptive error output on `stderr` while the remaining operations in the batch complete successfully).

**Acceptance Scenarios**:

1. **Given** a model response that fails strict schema validation on the first attempt, **When** validation fails, **Then** the system triggers exactly one retry invocation containing the original prompt augmented with the specific validation error feedback.
2. **Given** a retry invocation that produces a valid schema conforming to all requirements, **When** the retry succeeds, **Then** the system accepts the test case, includes it in the final output, and continues processing subsequent operations.
3. **Given** a retry invocation that fails schema validation a second time, **When** the second failure occurs, **Then** the system logs a descriptive diagnostic message to `stderr` specifying the target operation and validation details, omits the failed test case from `stdout`, and continues processing the remaining operations in the batch without terminating execution.
4. **Given** a batch of operations where a subset fails generation or validation after retry, **When** generation completes, **Then** all successfully generated test cases are streamed to `stdout` as JSON Lines (JSONL), diagnostic warnings are isolated to `stderr`, and the process returns exit code 0 if at least one test case was generated (or exit code 1 if all operations in the batch failed).

---

### User Story 3 - Cryptographic Disk Caching for Repeatable, Zero-Cost Runs (Priority: P3)

As a developer iteratively testing generation workflows or running automated CI suites, I want all model requests and responses cached to local disk based on a cryptographic hash of the prompt and model parameters, so that repeated executions run instantly, cost nothing, and produce reproducible outputs.

**Why this priority**: Disk caching prevents redundant model inference during iterative debugging, eliminates token costs, enables deterministic replay, and allows comprehensive automated test suites to run completely offline without active model runtimes.

**Independent Test**: Can be tested independently by running `specprobe generate` on an input set, verifying that cache entries are created on disk keyed by prompt and model hash, and running the command a second time to verify that results are returned with zero model invocations and near-instant latency.

**Acceptance Scenarios**:

1. **Given** a generation run with no prior cached entries, **When** `specprobe generate` executes, **Then** the system writes each model prompt payload, model identifier, and resulting completion to disk storage, keyed by a deterministic cryptographic hash of the prompt and model configuration.
2. **Given** a subsequent generation run with identical prompt payload and model configuration, **When** `specprobe generate` executes, **Then** the system retrieves the response directly from the disk cache, executing 0 model inference calls and outputting the cached test cases immediately.
3. **Given** automated tests running in an offline or CI environment, **When** tests are supplied with pre-recorded disk cache fixtures, **Then** generation tests execute and pass 100% offline without requiring a live model runtime.
4. **Given** an optional cache bypass flag (e.g. `--no-cache`), **When** `specprobe generate` executes, **Then** the system bypasses existing cache records, queries the model runtime, and refreshes the cache with new responses.

---

### User Story 4 - Unranked Spec-Wide Retrieval via Filter-Only Search (Priority: P4)

As a QA lead wanting to generate a full test plan covering an entire API specification or specific domain module, I want `specprobe search` to accept metadata filters without requiring a query string, returning all matching operations unranked so that I can pipe an entire specification directly into `specprobe generate`.

**Why this priority**: While semantic search finds relevance-ranked subsets of operations, end-to-end test generation often requires comprehensive coverage across an entire API version or tag group. Allowing filter-only search bridges the index and generation stages without artificial relevance ranking.

**Independent Test**: Can be tested independently by executing `specprobe search --source-title <spec> --source-version <version> --full` without a query argument, confirming that all operations belonging to that specification are returned unranked, and piping that output directly into `specprobe generate`.

**Acceptance Scenarios**:

1. **Given** an index with indexed specifications, **When** the user runs `specprobe search --source-title "Petstore" --source-version "1.0.0" --full` without a query argument, **Then** the system returns all indexed operations matching that specification unranked and without default limit truncation (unless an explicit `--limit` is specified), without executing semantic vector similarity scoring.
2. **Given** metadata filters such as `--tag pets` or `--method POST` without a query string, **When** the user executes `specprobe search`, **Then** the system returns all operations matching all specified filters unranked and without default limit truncation.
3. **Given** `specprobe search` is invoked with neither a query string nor any metadata filter, **When** the command executes, **Then** the system prints a clear usage error to `stderr` explaining that either a search query or at least one filter must be provided, and exits with code 1.
4. **Given** an unranked search output piped into generation, **When** the pipeline `specprobe search --source-title "Petstore" --source-version "1.0.0" --full | specprobe generate` executes, **Then** a full test plan covering all operations of the specification is generated and written to `stdout`.

---

### Edge Cases

- **Empty Input Stream or Empty Search Results**: When `stdin` or a provided file contains an empty JSON list (`[]`) or zero search results, `specprobe generate` emits nothing to `stdout` (closing the stream cleanly with 0 lines), logs an informational message to `stderr`, and exits with code 0.
- **Malformed Input JSON**: When input from `stdin` or a file is not valid JSON, the system reports a parsing error identifying the issue to `stderr` and exits immediately with code 1 without invoking any model.
- **Input Search Results Missing Full Chunk Bodies or Incompatible Chunk Streams**: If input JSON contains compact search results (missing the `--full` payload / `chunk` object) or raw chunk JSON without search metadata wrappers, the system detects the incompatible structure, emits an error message explaining that `specprobe search --full` output is required, and exits with code 1.
- **Unavailable Local Model Runtime**: When the default local model endpoint (e.g. LM Studio) is not running or unreachable, the system emits a clear diagnostic message indicating connection failure, actionable instructions on starting the local runtime or specifying an alternative endpoint, and exits with code 1.
- **Partial Batch Failures**: When a batch contains 10 operations and 2 fail validation after retry, the system streams the 8 valid test cases to `stdout` as JSON Lines, logs details of the 2 failures to `stderr`, and exits with code 0.
- **Complete Batch Failure**: When all operations in a batch fail generation or validation after retry, the system logs all failure details to `stderr`, emits no lines to `stdout`, and exits with code 1.
- **Missing or Generated `operationId`**: If an OpenAPI operation in the chunk lacks an explicit `operationId`, the system assigns a deterministic fallback identifier derived from the HTTP method and path (e.g. `GET_/pets/{petId}`) to maintain strict traceability.
- **Cache Directory Creation**: If the target disk cache directory does not exist, the system creates it automatically with appropriate directory permissions on the first write.
- **Corrupted Disk Cache File**: If an existing cache file on disk contains corrupted or invalid JSON, the system discards the corrupted entry, logs a warning to `stderr`, falls back to executing model inference, and updates the cache record.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `specprobe generate` CLI command that accepts input from standard input (`stdin`) or from an optional file path argument.
- **FR-002**: System MUST strictly accept input formatted as search results containing full `OperationChunk` payloads (the JSON array structure produced by `specprobe search --full`), rejecting unformatted chunk streams or non-conforming structures with a descriptive error message on standard error (`stderr`).
- **FR-003**: System MUST route all model generation calls through a unified model gateway supporting local and cloud model providers without vendor-specific SDK coupling.
- **FR-004**: System MUST default model execution to a local endpoint without requiring external network connectivity or cloud provider API credentials.
- **FR-005**: System MUST treat cloud model providers as strictly opt-in, only activating external endpoints when explicit API key environment variables or provider configurations are supplied by the user.
- **FR-006**: System MUST persist all model prompts, configurations, and completed responses in a local disk cache, keyed deterministically by a cryptographic hash of the prompt payload and model identifier.
- **FR-007**: System MUST query the disk cache prior to executing any model call, returning the cached completion immediately upon a cache hit without performing model inference or network requests.
- **FR-008**: System MUST generate a single primary happy-path (2xx success) test case per operation by default, and validate each generated test case against a strict schema that requires:
  - An explicit, traceable target operation identifier (`operationId` or method/path).
  - Concrete request fixtures, including path parameters, query parameters, headers, and request body conforming to the operation's schema.
  - Concrete expected response assertions, including expected HTTP status code (targeting 2xx), expected headers or content type, and expected response schema structure.
- **FR-009**: System MUST enforce a single-retry protocol on schema validation failure: if initial model output fails schema validation, the system MUST re-prompt the model exactly once, providing the specific schema validation error details to enable self-correction.
- **FR-010**: System MUST handle persistent validation failures gracefully: if an operation fails schema validation on its retry attempt, the system MUST log a descriptive error detailing the failure and operation identifier to standard error (`stderr`), skip that operation, and continue processing remaining operations in the batch without terminating execution.
- **FR-011**: System MUST emit all successfully generated and validated test cases as JSON Lines (JSONL, one JSON object per line) to standard output (`stdout`), streaming each test case immediately upon successful validation, ready for downstream consumption by test artifact exporters.
- **FR-012**: System MUST modify `specprobe search` to make the search query argument optional when one or more metadata filter options (`--source-title`, `--source-version`, `--tag`, `--method`, `--deprecated`) are provided.
- **FR-013**: System MUST retrieve and return all matching operation chunks unranked and without default limit truncation when `specprobe search` is executed with metadata filters and no query string, while respecting `--limit <N>` if explicitly specified by the user.
- **FR-014**: System MUST reject `specprobe search` invocations that specify neither a search query string nor any metadata filter, reporting an informative error message to `stderr` and exiting with code 1.
- **FR-015**: System MUST direct all non-data diagnostic output, progress updates, validation warnings, and cache hit/miss notifications to standard error (`stderr`), ensuring that standard output (`stdout`) contains only clean, machine-readable JSON.

### Key Entities *(include if feature involves data)*

- **Generated Test Case**: The primary output entity representing an executable test definition. Contains:
  - `operation_id`: Traceable identifier of the target API operation.
  - `description`: Plain-language explanation of the scenario tested.
  - `request`: Request fixture data containing `path_params`, `query_params`, `headers`, and optional `body`.
  - `response`: Expected response assertion data containing `status_code`, optional `headers`, and expected `schema_shape` or attribute assertions.
  - `tags`: Optional list of operational or thematic tags inherited from the operation chunk.
- **Request Fixture**: The data structure capturing concrete values for an HTTP request. Encapsulates key-value parameter mappings and structured payload data conforming to the endpoint's parameter and request body schemas.
- **Response Assertion**: The data structure defining expected verification criteria for the response, including expected HTTP status code (e.g. 200, 201, 400) and expected response properties or structural patterns.
- **Model Cache Record**: The persistent storage record representing a cached model invocation. Contains the deterministic cache key (cryptographic hash), model identifier, prompt payload, completion text, and creation timestamp.
- **Generation Batch Context**: The runtime execution entity managing the processing of multiple operation chunks, tracking total operations, successful test cases, retry attempts, cache hit statistics, and failed operations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of generated test cases emitted to standard output conform strictly to the target schema and include an explicit, traceable operation identifier linking back to the source specification.
- **SC-002**: Cached batch generation executions require zero external network requests and zero model inference calls, completing previously cached batches of up to 50 operations in under 1 second.
- **SC-003**: 100% of model completions failing initial schema validation trigger exactly one automated retry containing the specific validation error feedback before failing the individual test case.
- **SC-004**: Single-operation validation failures do not abort batch processing; 100% of remaining valid operations in a multi-operation batch are processed to completion.
- **SC-005**: In filter-only search mode (no search query string), 100% of operations in the index matching the specified filter criteria are retrieved unranked without relevance score distortion or default limit truncation (unless an explicit `--limit` is specified).
- **SC-006**: Default execution of the test generation command operates 100% offline or against local endpoints with zero outbound network transmissions to external cloud services unless explicitly enabled.
- **SC-007**: Piped execution of unranked search into test generation (e.g. `specprobe search --source-title <spec> --full | specprobe generate`) processes and produces test cases for an entire specification without manual intermediate steps.

## Assumptions

- **Local Model Runtime**: Users utilizing the default local execution have a compatible local model server (such as LM Studio or an equivalent local OpenAI-compatible endpoint) running and accessible at the default local endpoint.
- **Default Local Endpoint**: The default local endpoint targets `http://localhost:1234/v1` (LM Studio standard), configurable via CLI options (e.g. `--api-base`, `--model`) or environment variables (`SPECPROBE_LLM_API_BASE`, `SPECPROBE_LLM_MODEL`).
- **Disk Cache Storage**: Cache records are stored locally in `.specprobe/cache` within the project root by default, overrideable via `--cache-dir` CLI option or `SPECPROBE_CACHE_DIR` environment variable.
- **Input Format Compatibility**: Input to `specprobe generate` strictly conforms to the JSON output emitted by `specprobe search --full`, where the payload is a JSON array of search result objects, each including a `chunk` field serializing an `OperationChunk`.
- **Single Test Case Per Operation**: By default, one primary success/happy-path test case is generated per operation chunk, with future extensibility for multi-scenario test generation.
- **Downstream Format Readiness**: Emitted test case JSONL adheres to clean, standardized fields so that subsequent deterministic generators (Postman collection builder, REST Client `.http` exporter) can consume them directly without requiring secondary LLM transformation.
