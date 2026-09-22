# Feature Specification: Minimal Local Mock Server (specprobe mock)

**Feature Branch**: `011-mock-server`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Add specprobe mock — generate a minimal local mock server from an indexed spec so exported Postman/.http artifacts can actually run and pass, not just be eyeballed."

## Clarifications

### Session 2026-09-22

- Q: What is the scope of mock responses in v1? → A: Serve positive cases only (`test_type == "positive"` or 2xx status codes). Any request matching a registered route returns its recorded positive canned response. Negative condition matching is out of scope for v1.
- Q: How should response bodies be produced when test case records specify `schema_shape` without an explicit concrete body? → A: Deterministically synthesize a minimal valid JSON body from `schema_shape` (generating sample values based on schema types: strings, numbers, booleans, objects, arrays) so that Postman's `pm.response.to.have.jsonSchema(...)` assertions pass, while honoring explicit `response.body` if present in fixtures. Empty body for 204 or null schemas.
- Q: How should `specprobe mock` accept input test cases? → A: Accept a positional file path argument (`specprobe mock <test_cases_file>`) and support standard input via `-` (e.g., `specprobe generate ... | specprobe mock -`), buffering all JSONL lines before binding the socket and entering the server event loop.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Serve Positive Canned Responses for Exported Test Artifacts (Priority: P1) 🎯 MVP

A developer or automated test runner executing exported Postman collections or VS Code REST Client `.http` files needs a local HTTP server that responds to requests matching the generated test cases. The developer starts the mock server pointing to a generated test cases file (or piped via stdin). When an HTTP client sends requests matching the HTTP method and resolved path of the recorded fixtures (such as `GET /pets/42`), the mock server matches the incoming request against the positive canned fixtures and immediately returns the recorded HTTP status code, response headers, and a response body satisfying the recorded schema shape, allowing all test assertions (status codes, headers, and schema validations) to pass.

**Why this priority**: Core value of the feature — enables generated and exported test artifacts to execute successfully against a real HTTP endpoint without needing a deployed backend or external dependencies.

**Independent Test**: Start `specprobe mock ./fixtures/test_cases.jsonl --port 8000`. Send an HTTP request (via `curl`, Postman, or REST Client) to `GET http://localhost:8000/pets/42`. Verify the server responds with the recorded status code (e.g. 200), recorded headers (e.g. `Content-Type: application/json`), and a valid JSON response body satisfying the operation's schema.

**Acceptance Scenarios**:

1. **Given** a test cases file containing positive test fixtures, **When** the mock server receives an incoming HTTP request matching a recorded fixture's method and resolved path (e.g., `GET /pets/42` matching `/pets/{petId}` where `petId=42`), **Then** it returns the recorded status code, response headers, and response payload.
2. **Given** an exported Postman collection with `pm.response.to.have.status(...)` and `pm.response.to.have.jsonSchema(...)` assertions, **When** the collection runs against the mock server, **Then** all positive test scenarios pass without assertion failures.
3. **Given** test cases expecting a 204 No Content status code (or null schema), **When** the mock server receives a matching request, **Then** it returns HTTP 204 with an empty response body.
4. **Given** incoming request paths with query parameters (e.g. `/pets?limit=10`), **When** evaluating route matching, **Then** the server matches the path component against registered routes regardless of query parameter ordering or optional parameters.
5. **Given** test cases containing `schema_shape` definitions without pre-rendered response bodies, **When** a request matches, **Then** the server synthesizes and returns a minimal deterministic JSON payload conforming to that schema.

---

### User Story 2 - Configurable Port, Host, and Process Lifecycle (Priority: P2)

A developer needs to run the mock server on custom network interfaces or ports to avoid collisions with local development servers (e.g., using `--port 8080` or `--host 0.0.0.0` for containerized environments). The command runs as a foreground blocking process displaying an active summary of loaded routes upon startup, and cleanly shuts down when interrupted (via Ctrl+C / SIGINT) without leaving hanging sockets or orphan processes.

**Why this priority**: Prevents port conflicts in local workflows and ensures reliable process termination across development and CI environments.

**Independent Test**: Run `specprobe mock ./fixtures/test_cases.jsonl --port 9090 --host 127.0.0.1`. Verify the server starts and binds to the specified port/host, displays the registered mock routes, and terminates cleanly upon receiving an interrupt signal (Ctrl+C).

**Acceptance Scenarios**:

1. **Given** custom `--port` and `--host` options, **When** the mock command executes, **Then** the server listens on the specified host and port.
2. **Given** default invocation without port or host options, **When** the command executes, **Then** the server defaults to listening on `localhost` (127.0.0.1) and port `8000`.
3. **Given** the mock server is running in the foreground, **When** the user sends an interrupt signal (SIGINT / Ctrl+C), **Then** the server gracefully stops accepting new connections, closes open sockets, and exits cleanly with exit code 0.
4. **Given** the specified port is already in use by another process, **When** the mock command attempts to start, **Then** it terminates immediately with an informative error message on `stderr` and a non-zero exit code.

---

### User Story 3 - Diagnostic Handling for Unmatched Routes (Priority: P3)

When an incoming HTTP request does not match any registered method or endpoint path, the developer needs immediate diagnostic feedback explaining why the request failed to match. Instead of a silent hang or generic blank response, the mock server returns HTTP 404 (or 405 Method Not Allowed) with a structured diagnostic payload listing the requested method, requested path, and a list of available mock routes.

**Why this priority**: Drastically reduces debugging time when test clients have path typos, omitted prefix paths, or unsupported HTTP methods.

**Independent Test**: Send a request to `GET http://localhost:8000/unregistered/route` while the mock server is running. Verify the response has HTTP status 404 and includes details identifying the unmatched path alongside available endpoints.

**Acceptance Scenarios**:

1. **Given** a request for a path not defined in the loaded test cases, **When** the request arrives at the mock server, **Then** the server responds with HTTP 404 and a JSON diagnostic body detailing the unmatched request path and listing registered routes.
2. **Given** a request matching a registered path but using an unregistered HTTP method, **When** the request arrives, **Then** the server responds with HTTP 405 (Method Not Allowed) or 404 indicating which methods are supported for that path.

---

### Edge Cases

- **What happens if the test cases file contains negative test cases (401/403/404/400) alongside positive cases?** The mock server loads only positive test cases (`test_type == "positive"` or 2xx status codes) into the route registry, ignoring negative test cases in v1.
- **How is the response body generated when the recorded test case only specifies `schema_shape` without an explicit concrete body?** The server deterministically synthesizes a minimal valid JSON body conforming to `schema_shape` (generating sample values based on schema types: strings, numbers, booleans, objects, arrays) so that schema validations pass. If an explicit `response.body` is present, it is used directly. For 204 status or null schema, an empty body is returned.
- **How should test cases be supplied to the command?** The CLI accepts a positional file path argument (`specprobe mock <test_cases_file>`) or standard input when `-` is specified (e.g., `specprobe generate ... | specprobe mock -`). When reading stdin, all records are buffered into memory before starting the server.
- **What happens if multiple test fixtures exist for the exact same HTTP method and resolved path?** The mock server uses the first matching fixture encountered in the test cases file and logs an informational warning during startup.
- **What happens if the input test cases file is empty or contains malformed JSONL?** The mock server exits immediately with an error message on `stderr` describing the invalid or empty file and a non-zero exit code.
- **What happens if a parameterized path contains URL-encoded characters or multiple segments?** The server normalizes URL paths and matches concrete resolved path parameter values as recorded in the fixture's parameters.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `specprobe mock` CLI command that accepts a test cases file path or standard input (`-`) and starts a local HTTP mock server serving canned responses derived from generated test case records.
- **FR-002**: System MUST match incoming HTTP requests by HTTP method and URL path against recorded test case fixtures with path parameters resolved.
- **FR-003**: System MUST return the recorded HTTP status code, response headers, and response body corresponding to the matched test case. When a test case does not include an explicit response body, the system MUST deterministically synthesize a minimal valid JSON payload satisfying the recorded `schema_shape`.
- **FR-004**: System MUST support configurable server listening options, including `--port` (defaulting to 8000) and `--host` (defaulting to `localhost` / `127.0.0.1`).
- **FR-005**: System MUST run in the foreground as an interactive blocking process and shut down cleanly upon receiving an interrupt signal (SIGINT / Ctrl+C), releasing all network sockets.
- **FR-006**: System MUST display an active startup banner or summary indicating the server URL, listening port, and the list of loaded mock endpoints.
- **FR-007**: System MUST return an HTTP 404 Not Found response with a structured JSON error body when an incoming request does not match any registered endpoint route.
- **FR-008**: System MUST return an HTTP 405 Method Not Allowed response (or 404 with method details) when an incoming request matches a registered path but uses an unsupported HTTP method.
- **FR-009**: System MUST operate completely offline with zero LLM invocations and zero external network calls during server execution (adhering strictly to Constitution Principle II).
- **FR-010**: System MUST handle HTTP 204 No Content responses by returning status code 204 with an empty body and appropriate headers.
- **FR-011**: System MUST fail fast with a descriptive error message on `stderr` and a non-zero exit code if the specified test cases file does not exist, cannot be read, contains malformed JSONL, or if the specified network port is unavailable.
- **FR-012**: System MUST filter test cases during loading to include only positive test cases (`test_type == "positive"` or 2xx status codes), ignoring negative test cases (401/403/404/400) for v1 route matching.

### Key Entities *(include if feature involves data)*

- **MockRoute**: Represents a single mockable endpoint consisting of an HTTP method (GET, POST, PUT, DELETE, etc.), a resolved URL path (e.g. `/pets/42`), and its associated `MockResponse`.
- **MockResponse**: Represents the canned response definition, including HTTP status code, dictionary of response headers, and serialized response body bytes.
- **MockServerConfig**: Encapsulates configuration parameters for the mock server runtime, including host address, port number, input file path or source, and route registry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of positive test cases in an exported Postman collection or `.http` file execute and pass all status, header, and schema assertions when pointed at the mock server.
- **SC-002**: Mock server startup and route registration completes in under 1 second for test case files containing up to 1,000 endpoint fixtures.
- **SC-003**: Incoming mock requests receive a response within 10 milliseconds under local execution.
- **SC-004**: The mock server process terminates within 500 milliseconds of receiving an interrupt signal, leaving zero leaked ports or dangling background tasks.

## Assumptions

- Mock server v1 targets static request-response matching; dynamic state management, persistent databases, and mutating resource simulation are out of scope.
- Incoming HTTP requests from test runners (Postman, Newman, VS Code REST Client) target standard HTTP/1.1 over TCP.
- Path parameters in test cases are resolved using the concrete values recorded in the test case's request fixtures.
- Only positive test cases are served in v1; negative condition simulation (evaluating invalid credentials or mutated path parameters) is deferred to future iterations.
- When reading from standard input (`-`), the server buffers all input lines until EOF before starting the HTTP listener.
- The mock server is designed for local development, verification, and offline CI pipelines.
