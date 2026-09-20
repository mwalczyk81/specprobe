# Feature Specification: Deterministic Export for Runnable Test Artifacts (Postman & REST Client)

**Feature Branch**: `004-export-test-artifacts`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: "Add a deterministic export command that turns generated test cases into runnable artifacts: a Postman Collection v2.1 JSON file and a REST Client .http file. This is the other half of the test-generation pipeline — `specprobe generate` already produces schema-validated GeneratedTestCase JSONL (operation_id, description, request fixture with path/query params, headers, body, and a response assertion with status code, headers, and schema shape), but nothing today turns that into something a developer can actually open and run. Per Constitution Principle II, this step MUST be fully deterministic and MUST NEVER invoke an LLM — same GeneratedTestCase input always produces byte-identical output."

## Clarifications

### Session 2026-09-19
- Q: How should target base URLs be configured and represented in exported Postman collections and REST Client files? (FR-006) → A: Use parameterized variables (`{{baseUrl}}` in Postman collection variables, `@baseUrl` at the top of `.http` files) initialized via an optional `--base-url` CLI option (default: `http://localhost:8000`).
- Q: When a generated test case contains multiple tags, how should it be organized within the Postman collection folder hierarchy? (FR-008) → A: Assign the request to the primary tag's folder (the first tag in the operation's `tags` list), placing each test case in exactly one folder without duplicating requests.
- Q: How should the response `schema_shape` assertion be encoded into Postman test scripts? (FR-010) → A: Generate individual `pm.expect(jsonData).to.have.property(key)` assertions for top-level properties defined in `schema_shape`.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Export Runnable Postman Collection v2.1 (Priority: P1)

As an API developer or QA engineer who has generated test cases, I want to export them into a standard Postman Collection v2.1 JSON file with pre-built test assertion scripts, so that I can immediately import the collection into Postman or Newman to execute automated contract and regression suites.

**Why this priority**: Postman is the industry standard for team API testing, collection sharing, and CI/CD test running via Newman. Delivering a valid Postman collection with embedded verification scripts gives users immediate, executable value from generated test cases.

**Independent Test**: Can be tested independently by feeding a JSON Lines stream of validated test cases into `specprobe export --format postman`, and verifying that the resulting JSON adheres to the official Postman Collection v2.1 schema, contains requests organized by tags, has URL parameters substituted, and contains executable `pm.test` response status and schema validation scripts.

**Acceptance Scenarios**:

1. **Given** a stream of validated test case objects, **When** the user executes `specprobe export --format postman`, **Then** the system produces a valid Postman Collection v2.1 JSON document containing all operations mapped to individual requests, with a top-level `baseUrl` collection variable initialized to `--base-url` (default `http://localhost:8000`).
2. **Given** test cases with tags (e.g. `["pets", "store"]`), **When** the Postman collection is exported, **Then** requests are grouped into folders corresponding to their primary tag (`tags[0]`) so each test case appears in exactly one folder, with untagged requests placed directly in the collection root or a default group.
3. **Given** a test case with concrete path parameters (e.g. `petId = 42` for path `/pets/{petId}`), query parameters, headers, and request body, **When** exported, **Then** the request URL template is constructed as `{{baseUrl}}/pets/42` with path parameters substituted with URL-encoded values, and query parameters, headers, and body payloads are mapped accurately.
4. **Given** a test case with response assertions (expected HTTP status code, optional headers, and optional schema shape), **When** exported, **Then** an attached Postman test script executes `pm.test` assertions verifying HTTP status code and individual `pm.expect(jsonData).to.have.property(key)` checks for properties specified in `schema_shape`.
5. **Given** any exported request, **When** inspected in the Postman collection, **Then** the originating operation identifier is preserved and visible for full traceability.

---

### User Story 2 - Export Runnable REST Client (`.http`) File (Priority: P2)

As a developer who works primarily inside code editors (such as VS Code or JetBrains IDEs), I want to export test cases into a plain-text REST Client (`.http`) file, so that I can inspect, tweak, and execute requests directly against running services with a single click without leaving my development environment.

**Why this priority**: Plain-text `.http` files offer zero-friction local execution, version control friendliness, and human readability directly in the editor, without requiring external desktop GUI applications.

**Independent Test**: Can be tested independently by feeding test case JSONL into `specprobe export --format http`, and verifying that the output contains standard `###`-separated blocks with operation headers, documentation comments, target method/URL, headers, and request bodies compatible with the RFC 7230 / VS Code REST Client format.

**Acceptance Scenarios**:

1. **Given** a stream of validated test case objects, **When** the user runs `specprobe export --format http`, **Then** the system outputs a text file beginning with a top-level `@baseUrl` variable initialized to `--base-url` (default `http://localhost:8000`), followed by `###`-delimited blocks for each test case.
2. **Given** a test case with operation identifier, description, and expected response criteria, **When** exported to `.http`, **Then** each block begins with a comment section detailing the operation identifier, description, and human-readable expected status and schema requirements.
3. **Given** a test case with HTTP method, substituted endpoint path, headers, and body, **When** exported to `.http`, **Then** the block renders the HTTP request line targeting `{{baseUrl}}/path` followed by header lines, a blank separator line, and the formatted request body payload.

---

### User Story 3 - Dual-Format Export & Output Destination Management (Priority: P3)

As a DevOps or QA lead automating test pipelines, I want to export both Postman and REST Client artifacts in a single command run or direct output to specified files and directories, so that I can generate comprehensive test assets for both CI test runners and local developers in one build step.

**Why this priority**: Build pipelines and local developer scripts need flexible destination control, avoiding multiple tool passes or manual file-splitting logic.

**Independent Test**: Can be tested by running `specprobe export --format both --output ./artifacts/`, confirming that both `collection.json` and `requests.http` are created in the target directory with byte-identical determinism across multiple runs.

**Acceptance Scenarios**:

1. **Given** `--format both` and an output directory path via `--output <dir>`, **When** the command executes, **Then** both the Postman collection and the `.http` file are written to the target directory.
2. **Given** `--format both` invoked without `--output`, **When** the command executes, **Then** the system reports a descriptive error to standard error (`stderr`) explaining that `--output` is required when producing both formats, and exits with code 1.
3. **Given** a single format (`--format postman` or `--format http`) and no `--output` flag, **When** the command executes, **Then** the generated artifact is streamed directly to standard output (`stdout`), allowing shell redirection.
4. **Given** a single format with `--output <path>`, **When** the command executes, **Then** the artifact is written to the specified file path.
5. **Given** `--collection-name <name>`, **When** exporting Postman collections, **Then** the collection's title is set to the provided name; if omitted, the name is deterministically derived from specification metadata in the test cases or falls back to a standardized default name.

---

### User Story 4 - End-to-End Pipeline Composition (Priority: P4)

As an engineer using SpecProbe CLI in scripts or CI, I want `specprobe export` to consume standard input directly from `specprobe generate`, so that the full sequence `search | generate | export` runs as a seamless, unified shell pipeline.

**Why this priority**: Seamless Unix pipeline composition is a core architectural pillar of SpecProbe, eliminating unnecessary intermediate files on disk.

**Independent Test**: Can be tested by executing `specprobe search --full | specprobe generate | specprobe export --format postman` in a single command pipeline and verifying valid collection output.

**Acceptance Scenarios**:

1. **Given** piped test case JSONL from standard input (`stdin`), **When** `specprobe export` executes without a file argument, **Then** it reads and processes the entire stream to completion.
2. **Given** a path to an existing JSONL file as a command argument, **When** `specprobe export <file>` executes, **Then** it reads test cases from the specified file.

---

### Edge Cases

- **Empty Input Stream (0 Test Cases)**: When `stdin` or the input file contains zero test cases or empty content:
  - Postman exporter produces a valid empty Postman Collection v2.1 object (with empty item array) rather than invalid JSON or failing.
  - REST Client exporter produces an empty file with zero request blocks.
  - The command exits cleanly with code 0 and logs an informational notice to `stderr`.
- **Untagged Operations**: When a test case has an empty or missing `tags` list, it is placed into a clean root folder or default group rather than crashing or being omitted.
- **Path Parameter URL Encoding**: Path parameter values containing reserved or unsafe characters (spaces, slashes, punctuation, Unicode characters) must be properly URL-encoded during template substitution so URLs remain valid.
- **Empty Request Body or Headers**: When a test case defines null or empty request bodies or headers, the generated requests omit body payloads and header lines cleanly without dangling whitespace, null literals, or invalid syntax.
- **Malformed Input JSONL**: If any line in the input file or stream is not valid JSON or does not conform to the expected test case schema, the command stops immediately, emits an error message identifying the line number and parsing error to `stderr`, and exits with code 1 without writing corrupted artifacts.
- **Missing Output Directory**: If `--output` points to a non-existent directory or file in a non-existent path, the system automatically creates the parent directories with standard permissions.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `specprobe export` CLI command that accepts test case inputs from standard input (`stdin`) or from an optional file path argument.
- **FR-002**: System MUST enforce that test artifact export is 100% deterministic and zero-LLM: identical input test cases and options MUST yield byte-identical output artifacts across repeated invocations without executing probabilistic model calls or outbound network traffic.
- **FR-003**: System MUST support three output format modes selectable via `--format`: `postman` (Postman Collection v2.1 JSON), `http` (VS Code REST Client `.http`), and `both` (both artifacts simultaneously). The default format mode MUST be `both`.
- **FR-004**: System MUST allow routing single-format output to standard output (`stdout`) by default when `--output` is omitted, enabling direct redirection and pipeline composition.
- **FR-005**: System MUST require an explicit `--output <directory>` argument when `--format both` is selected, writing `collection.json` and `requests.http` to the specified directory, and failing with an informative error on `stderr` with exit code 1 if omitted.
- **FR-006**: System MUST support a `--collection-name <name>` option to customize the exported Postman collection name, defaulting to a name derived from the test cases' specification metadata or a standardized default when omitted.
- **FR-007**: Postman exporter MUST generate valid JSON conforming strictly to the Postman Collection v2.1.0 schema specification.
- **FR-008**: Postman exporter MUST organize requests into collection folders based on the primary operational tag (the first tag in the operation's `tags` list), placing untagged requests in the collection root or a default group without duplicating requests across multiple folders.
- **FR-009**: Postman exporter MUST map request details from each test case: HTTP method, path with parameter substitutions, query parameters, request headers, and formatted body payloads.
- **FR-010**: Postman exporter MUST attach automated test verification scripts (`pm.test`) to each request, asserting expected HTTP status codes, response headers (if specified), and individual property assertions (`pm.expect(jsonData).to.have.property(key)`) for top-level properties defined in `schema_shape` (if specified).
- **FR-011**: Postman exporter MUST preserve traceability by embedding the originating `operation_id` explicitly within each request's metadata or name.
- **FR-012**: REST Client exporter MUST generate syntax fully compliant with the VS Code REST Client (`.http`) extension, separating distinct requests with `###` delimiters.
- **FR-013**: REST Client exporter MUST include a comment block preceding each request documenting the operation identifier, description, expected status code, and expected schema attributes for human inspection.
- **FR-014**: REST Client exporter MUST render the HTTP request line, header lines, and formatted body payload separated by standard HTTP delimiter blank lines.
- **FR-015**: System MUST direct all progress messages, error details, and summary diagnostics exclusively to standard error (`stderr`), keeping standard output (`stdout`) free of non-artifact content.
- **FR-016**: System MUST support an optional `--base-url <url>` CLI option (default: `http://localhost:8000`) and embed this target as a configurable variable (`{{baseUrl}}` in Postman collection variables and `@baseUrl = <url>` at the top of `.http` files) so exported requests are immediately runnable and environment-switchable.

---

### Key Entities

- **Exported Test Batch**: The collection of input `GeneratedTestCase` records to be rendered into target artifact formats.
- **Postman Collection Artifact**: A structured JSON entity conforming to the Postman v2.1 schema containing folders, item requests, URL structures, header arrays, body specifications, and embedded test scripts.
- **REST Client Artifact**: A plain-text document conforming to the RFC 7230 / VS Code REST Client format composed of `###` delimiters, comment annotations, HTTP request lines, headers, and request bodies.
- **Export Configuration**: The runtime parameters specifying format selection (`postman`, `http`, `both`), target output path or stdout stream, and collection naming.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of exported Postman collections pass strict schema validation against the official Postman Collection v2.1 schema specification.
- **SC-002**: 100% of exported REST Client `.http` files parse cleanly without syntax errors in standard editor tooling (such as VS Code REST Client).
- **SC-003**: 100% of export executions are byte-identical across runs given identical test case inputs and CLI parameters (0% drift).
- **SC-004**: 100% of export operations complete locally with zero network calls and zero model inference calls.
- **SC-005**: Exporting a batch of 50 generated test cases completes in under 200 milliseconds.
- **SC-006**: 100% of exported requests retain explicit, traceable links back to their originating `operation_id`.

---

## Assumptions

- **Input Conformance**: Input data strictly conforms to the JSON Lines format emitted by `specprobe generate`, where each line is a valid serialized `GeneratedTestCase` object.
- **Default Filenames**: When exporting `--format both` to an output directory, the generated artifacts are named `collection.json` and `requests.http`.
- **URL Encoding**: Standard RFC 3986 URL encoding is applied to path parameter values when replacing template parameters (e.g. `{id}`).
- **Local Host URL Default**: Since test cases represent relative API paths (e.g. `/pets`), exported URLs default to a configurable or standard base URL variable (e.g. `{{baseUrl}}` in Postman and `@baseUrl` variable in `.http` file, defaulting to `http://localhost:8000` or extracted spec host) so requests are runnable immediately upon setting the target host.
