# Feature Specification: Negative Authentication Test Case Generation (401/403)

**Feature Branch**: `007-negative-auth-tests`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "specprobe generate currently only produces happy-path (2xx) test cases. Extend it to also generate negative test cases asserting 401 (missing/absent credentials) and 403 (invalid/insufficient-scope credentials) responses for operations that declare a security requirement, reusing the SecurityResolver and scheme metadata already built in Feature 006 (security/security_schemes on GeneratedTestCase, the SecurityResolver in src/specprobe/exporter/security.py) rather than duplicating scheme-resolution logic. Exported artifacts (Postman, .http) need corresponding negative-case request items/blocks with appropriately broken or stripped credentials and an assertion for the expected 401/403 status. Stay zero-LLM/deterministic wherever the existing 006 logic already determines the scheme and placeholder shape — only the "how do I break this credential on purpose" generation step is new; it doesn't need an LLM call either, since the negative fixture is a deterministic transform of the placeholder (omit it, or emit a syntactically-invalid version) rather than something requiring judgment."

## Clarifications

### Session 2026-09-20

- Q: Should negative authentication test case generation in `specprobe generate` be enabled by default or require an explicit opt-in flag? (FR-010) → A: Enabled by default; provide `--no-negative-auth` to disable.
- Q: How should generated 401 and 403 negative test requests be organized within the exported Postman collection? (FR-007) → A: Sibling requests in the same tag folder with [401] and [403] name prefixes.
- Q: For operations defining multiple alternative security schemes (OR logic), should 403 test generation target only the primary resolved scheme or generate a 403 case for each alternative? → A: Target only the primary resolved scheme (matching Feature 006 priority order).
- Q: Should GeneratedTestCase include an explicit discriminator field (e.g., test_type) to distinguish positive vs. negative test cases, or rely on existing fields? → A: Add an explicit test_type: str = "positive" field to GeneratedTestCase.
- Q: How should 403 invalid credentials be represented in exported Postman and REST Client artifacts? → A: Inline invalid literals (e.g., Bearer invalid_token, invalid_api_key) directly on the request.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Missing Credentials Negative Test Case Generation & Export (401 Unauthorized) (Priority: P1)

As an API developer or QA engineer,
I want SpecProbe to automatically generate and export negative test cases for secured operations where credentials are completely omitted,
So that I can verify that unauthenticated requests to protected endpoints are rejected with HTTP 401 Unauthorized without writing manual boilerplate tests.

**Why this priority**: Unauthenticated request rejection is the foundational security baseline for protected APIs. Generating a missing-credential negative case provides immediate value with zero manual test authoring.

**Independent Test**: Can be tested end-to-end by running `generate` on a secured operation (e.g. an endpoint requiring HTTP Bearer or API Key authentication), verifying a 401 test case is produced with all auth headers and query tokens stripped, and confirming `export` renders runnable Postman and REST Client requests asserting HTTP 401.

**Acceptance Scenarios**:

1. **Given** an OpenAPI operation declaring security requirements (e.g., Bearer auth or apiKey header/query),
   **When** `specprobe generate` runs,
   **Then** a negative test case record is generated with `response.status_code = 401`, description reflecting missing credentials, and request headers/query params stripped of credential placeholders.
2. **Given** a generated 401 negative test case,
   **When** `specprobe export --format postman` runs,
   **Then** a Postman request item is created as a sibling in the operation's tag folder named `[401] <Operation Title>` with no auth header/variable, asserting `pm.response.to.have.status(401)`.
3. **Given** a generated 401 negative test case,
   **When** `specprobe export --format http` runs,
   **Then** a REST Client request block is emitted with `# Expected Status: 401`, omitting authorization headers and credential variables.

---

### User Story 2 - Invalid Credentials Negative Test Case Generation & Export (403 Forbidden) (Priority: P2)

As an API security tester,
I want SpecProbe to automatically generate and export negative test cases for secured operations where credentials are deliberately corrupted, invalid, or lack required scopes,
So that I can verify that callers with invalid tokens or insufficient permissions are properly rejected with HTTP 403 Forbidden.

**Why this priority**: Testing rejected credentials ensures the API server actually validates credentials and scopes rather than blindly accepting any non-empty header.

**Independent Test**: Can be tested independently by running `generate` on a secured operation, verifying a 403 test case is produced containing intentionally corrupted credentials (e.g., `invalid_<schemeName>_key` or malformed Bearer token), and verifying the exported Postman and `.http` artifacts assert HTTP 403.

**Acceptance Scenarios**:

1. **Given** an OpenAPI operation with a declared security scheme (e.g., Bearer, OAuth2, or apiKey),
   **When** `specprobe generate` runs,
   **Then** a negative test case record is generated with `response.status_code = 403`, description indicating invalid credentials or insufficient scope, and request containing an invalid credential value.
2. **Given** a generated 403 negative test case,
   **When** `specprobe export --format postman` runs,
   **Then** a Postman request item is created as a sibling in the operation's tag folder named `[403] <Operation Title>` containing an inline invalid credential literal directly in the request header or query parameter (e.g., `Bearer invalid_token`), asserting `pm.response.to.have.status(403)`.
3. **Given** a generated 403 negative test case,
   **When** `specprobe export --format http` runs,
   **Then** a REST Client request block is emitted with `# Expected Status: 403` and the inline corrupted credential header or query parameter directly on the request.

---

### User Story 3 - Selective & Unsecured Endpoint Filtering (Priority: P3)

As a tester generating test suites for mixed APIs containing both public and protected endpoints,
I want SpecProbe to only generate negative authentication tests for operations that actually require security,
So that public endpoints are not cluttered with redundant or invalid 401/403 tests.

**Why this priority**: Prevents test suite pollution and false failures on endpoints intentionally designed for unauthenticated access.

**Independent Test**: Can be tested by running `generate` on a specification with both public endpoints (`security: []` or omitted) and secured endpoints, verifying 401/403 tests are emitted only for secured endpoints.

**Acceptance Scenarios**:

1. **Given** an operation with no declared security requirements (or explicit `security: []`),
   **When** `specprobe generate` runs,
   **Then** only the standard happy-path test case is emitted; no 401 or 403 negative cases are produced for that operation.
2. **Given** an operation with optional security (an alternative requirement with `{}`),
   **When** `specprobe generate` runs,
   **Then** negative auth cases are generated only if optional security is explicitly configured to be enforced, otherwise only happy-path is emitted.
3. **Given** CLI flags controlling negative test generation,
   **When** `specprobe generate` runs without negative auth flags,
   **Then** negative authentication generation is enabled by default; when `--no-negative-auth` is specified, negative auth test generation is disabled and only happy-path cases are emitted.

---

### Edge Cases

- **Compound Security Requirements (AND logic)**: When an operation requires multiple schemes simultaneously (e.g., `apiKeyAuth` AND `oauth2`), a 401 missing-credentials test must omit all schemes, and 403 tests should verify partial/invalid combinations.
- **Multiple Alternative Schemes (OR logic)**: When an operation accepts alternative schemes (e.g., Bearer OR apiKey), a 401 test omits all credentials across all alternatives, while the 403 test targets exclusively the primary resolved scheme (following Feature 006 priority: Bearer/OAuth2 > apiKey header > apiKey query > Basic) with corrupted credentials, maintaining a consistent 1:1:1 test case pattern per operation.
- **Query-based vs Header-based API Keys**: For query-based API keys (`in: query`), the 401 case must strip the query parameter completely from `request.query_params`, while the 403 case replaces its value with `invalid_<name>`.
- **Cookie-based Authentication**: When security is `in: cookie`, 401 strips the `Cookie` header while 403 provides an invalid cookie token.
- **Operations with Existing 401/403 Documentation**: If the OpenAPI spec defines custom schemas for 401 or 403 responses, the negative test case incorporates the documented response schema if available, otherwise sets `schema_shape = null`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect whether an operation declares security requirements by inspecting its chunk metadata and resolved schemes (reusing Feature 006 `SecurityResolver`).
- **FR-002**: For any secured operation, the system MUST generate a 401 Unauthorized negative test case where all authentication credentials, headers, and query parameters are omitted.
- **FR-003**: For any secured operation, the system MUST generate a 403 Forbidden negative test case where authentication credentials for the primary resolved security scheme (reusing Feature 006 resolution priority) are replaced with deterministic invalid placeholders.
- **FR-004**: The generation of 401 and 403 negative test cases MUST be 100% deterministic (zero-LLM), derived algorithmically from the synthesized happy-path test case and Feature 006 scheme metadata.
- **FR-005**: Every generated negative test case MUST preserve the exact `operation_id` of the target operation to maintain strict operation traceability per Constitution Principle V.
- **FR-006**: Generated test cases MUST include an explicit `test_type: str = "positive"` discriminator field (with values `"positive"`, `"negative_auth_missing"`, or `"negative_auth_invalid"`), accompanied by descriptive `tags` (including `"negative"`, `"auth"`) and expected `response.status_code`.
- **FR-007**: `specprobe export` MUST recognize 401 and 403 test cases and serialize them into Postman collections as sibling requests within the operation's tag folder, with appropriate request naming (e.g. `[401] <Name>` and `[403] <Name>`), inline invalid literals for 403 requests (without modifying collection-level variables), and `pm.response.to.have.status(401/403)` test assertions.
- **FR-008**: `specprobe export` MUST recognize 401 and 403 test cases and serialize them into REST Client (`.http`) files with appropriate `# @name` suffixes, `# Expected Status: 401` / `# Expected Status: 403` headers, and inline invalid literals for 403 requests.
- **FR-009**: Operations with no security requirements or explicit empty security (`security: []`) MUST NOT produce negative authentication test cases.
- **FR-010**: `specprobe generate` CLI MUST enable negative authentication test case generation by default, and MUST provide a `--no-negative-auth` option to disable it.

### Key Entities *(include if feature involves data)*

- **NegativeTestCaseDescriptor**: Represents the configuration for a negative auth variant (status code 401 or 403, mutation strategy: OMIT vs INVALIDATE, credential manipulation target).
- **GeneratedTestCase (extended)**: Existing Pydantic model extended with `test_type: str = "positive"` (values: `"positive"`, `"negative_auth_missing"`, `"negative_auth_invalid"`), `security` and `security_schemes` populated, `response.status_code` set to 401 or 403, and request fixtures adjusted according to the negative mutation strategy.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of secured operations processed by `specprobe generate` with negative auth enabled produce valid 401 and 403 test cases without increasing LLM token consumption or API calls (0 additional LLM tokens used).
- **SC-002**: Exported Postman collections and REST Client files generated from secured specs execute against standard mock servers with 100% passing status assertions when valid credentials reject invalid/missing calls.
- **SC-003**: 0% regression in existing happy-path test generation or export behavior; all 242 existing unit and integration tests remain passing.
- **SC-004**: Negative test generation completes in under 5 milliseconds per operation (deterministic in-memory transformation).

## Assumptions

- Happy-path test generation remains the source of truth for realistic path, query, and body fixtures; negative auth tests derive directly from the happy-path request structure.
- HTTP 401 represents unauthenticated (missing or unparseable credentials) access across all supported security schemes (HTTP Basic, Bearer, API Key, OAuth2).
- HTTP 403 represents authenticated but unauthorized or invalid-token access.
- If an OpenAPI spec does not document 401 or 403 response schemas, `schema_shape` for negative cases defaults to `null`, asserting only HTTP status code.
- Existing Feature 006 golden file regression fixtures remain intact; new dedicated negative-auth golden fixtures will be added for verification.
