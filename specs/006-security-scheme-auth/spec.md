# Feature Specification: Security-Scheme-Aware Authentication in Test Generation & Export

**Feature Branch**: `006-security-scheme-auth`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "Add security-scheme-aware auth to generate and export. `specprobe chunk` already extracts each OpenAPI operation's `security` requirements into `OperationChunk` metadata, but nothing downstream reads them. Every exported Postman request and `.http` request block currently has no `Authorization` header, api-key header, or query-param credential — even when the source spec declares the operation requires one (apiKey, http bearer/basic, or oauth2). Running an exported artifact against a real server that enforces auth returns 401/403 on every protected operation, defeating the point of generating runnable tests. Goal: when an operation's chunk has a `security` requirement, the generated test case and the exported artifact should reflect that requirement as a placeholder credential the user fills in, not silently omit it."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Security Credential Placeholders in Generated Test Cases (Priority: P1)

When an API engineer or automation tool generates test cases from API specifications that mandate authentication, each generated test case automatically includes appropriately shaped credential placeholders (such as `Authorization: Bearer <token>`, `Authorization: Basic <credentials>`, or specified API key header/query parameters) in its request fixture instead of omitting them.

**Why this priority**: Without authentication credentials, every test executed against a protected API fails with HTTP 401 Unauthorized or 403 Forbidden. Including standard placeholders enables immediate execution upon substituting test tokens.

**Independent Test**: Can be fully tested by providing an operation with an active security requirement to the test case generation workflow and verifying that the resulting request fixture contains the expected credential header or query parameter placeholder.

**Acceptance Scenarios**:

1. **Given** an API operation requiring HTTP Bearer authentication or OAuth2, **When** test generation is executed, **Then** the request fixture includes an `Authorization: Bearer <token>` header placeholder.
2. **Given** an API operation requiring HTTP Basic authentication, **When** test generation is executed, **Then** the request fixture includes an `Authorization: Basic <credentials>` header placeholder.
3. **Given** an API operation requiring an API key passed in a header (e.g., `X-API-Key`), **When** test generation is executed, **Then** the request fixture includes the specified header with an `<api_key>` placeholder value.
4. **Given** an API operation requiring an API key passed as a query parameter (e.g., `api_key`), **When** test generation is executed, **Then** the request fixture includes that query parameter with an `<api_key>` placeholder value.
5. **Given** an API operation with no security requirement (public endpoint or explicit `security: []`), **When** test generation is executed, **Then** no authentication header or query parameter is added.

---

### User Story 2 - Collection-Level Variable Parameterization in Postman Export (Priority: P1)

When an API tester exports generated test cases to a Postman Collection, any required credentials across requests are parameterized as collection-level variables (e.g., `{{bearerToken}}`, `{{apiKey}}`, `{{basicAuthCredentials}}`) rather than hardcoding static placeholder strings into every individual request. The top-level collection declares these variables with placeholder default values.

**Why this priority**: In real-world API testing, entering credentials once at the collection level allows running all collection requests seamlessly, rather than forcing the tester to edit dozens of individual request headers.

**Independent Test**: Can be tested by exporting test cases containing credential placeholders to a Postman collection and verifying that requests reference `{{...}}` collection variables and the collection's `variable` array contains corresponding definitions.

**Acceptance Scenarios**:

1. **Given** generated test cases containing HTTP Bearer credential placeholders, **When** exported to Postman format, **Then** requests use `Authorization: Bearer {{bearerToken}}` and the collection variable `bearerToken` is declared with default value `<token>`.
2. **Given** generated test cases containing API key header or query placeholders, **When** exported to Postman format, **Then** requests reference `{{apiKey}}` (or `{{<schemeName>}}` if disambiguated) and the variable is declared in collection variables.
3. **Given** multiple requests that share the same security scheme, **When** exported to Postman format, **Then** all requests reference the same collection variable, avoiding redundant variable declarations.

---

### User Story 3 - Top-Level File Variable Parameterization in REST Client (.http) Export (Priority: P1)

When a developer exports generated test cases to a VS Code REST Client (`.http`) document, required credentials are parameterized as top-level file variables (e.g., `@bearerToken = <token>`, `@apiKey = <api_key>`) at the start of the file, and individual request blocks reference these variables (e.g., `Authorization: Bearer {{bearerToken}}`).

**Why this priority**: Developers using `.http` files execute requests directly in their IDE. Declaring file variables at the top of the file lets them paste an active JWT or API key once at line 3 and test all endpoints interactively.

**Independent Test**: Can be tested by exporting protected test cases to `.http` format and verifying that the header contains top-level `@variable = ...` declarations and request blocks reference `{{variable}}`.

**Acceptance Scenarios**:

1. **Given** test cases requiring HTTP Bearer authentication, **When** exported to `.http` format, **Then** the file header declares `@bearerToken = <token>` directly following `@baseUrl`, and requests include `Authorization: Bearer {{bearerToken}}`.
2. **Given** test cases requiring API key authentication, **When** exported to `.http` format, **Then** the file header declares the corresponding API key variable (e.g., `@apiKey = <api_key>`) and requests reference `{{apiKey}}`.
3. **Given** test cases with zero authentication requirements, **When** exported to `.http` format, **Then** no authentication variables are declared at the top of the document.

---

### User Story 4 - Deterministic Selection and Traceability for Multiple Security Schemes (Priority: P2)

When an API operation specifies multiple alternative security schemes (e.g., an endpoint accepts either OAuth2 Bearer token OR an API key), the system selects a scheme according to a deterministic priority order, documents the selected scheme and available alternatives in the exported request metadata, and formats the request accordingly.

**Why this priority**: OpenAPI allows alternative security requirements via a list of security objects. Deterministic selection prevents output drift between runs, and metadata documentation tells the tester which authentication mechanism was configured and what alternatives exist.

**Independent Test**: Can be tested by processing an operation specifying `[{"oauth2": []}, {"apiKeyAuth": []}]` and asserting that the primary scheme is selected and an explanatory comment (e.g., `# Security: oauth2 (alternatives: apiKeyAuth)`) appears in the exported output.

**Acceptance Scenarios**:

1. **Given** an operation with alternative schemes, **When** evaluated, **Then** the scheme is selected following the deterministic priority: (1) HTTP Bearer / OAuth2, (2) API Key (header), (3) API Key (query), (4) HTTP Basic.
2. **Given** an operation with multiple alternative schemes, **When** exported to `.http` format, **Then** a comment `# Security: <selectedScheme> (alternatives: <otherScheme1>, ...)` is added to the request metadata block.
3. **Given** an operation with compound security requirements (multiple schemes in a single requirement object, representing a logical AND), **When** exported, **Then** all required credentials for that compound requirement are included in the request.

---

### Edge Cases

- **Operation with explicit empty security (`security: []`)**: Overrides global API security. The system must treat this as public and omit all authentication headers/variables for this operation, even if the rest of the API requires authentication.
- **API key in query string with existing query parameters**: The API key placeholder query parameter must merge cleanly with existing query parameters without duplication or syntax errors.
- **Missing security scheme definitions in component schemas**: If an operation specifies a security scheme name that lacks a corresponding component definition (e.g., partial specification chunk), the system must fall back to standard naming heuristics (e.g., matching "bearer", "token", "basic", or "api_key" substrings) rather than failing or omitting authentication.
- **Multiple operations requiring different API keys**: If an API defines multiple distinct API key schemes (e.g., `headerKey` and `queryKey`), the exporter must generate distinct variable names (e.g., `@headerKey` and `@queryKey`) to prevent collisions.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The test generation workflow MUST inspect operation security requirements and include the appropriate authentication placeholder in generated request fixtures.
- **FR-002**: Supported security scheme types MUST include HTTP Bearer (`Authorization: Bearer <token>`), HTTP Basic (`Authorization: Basic <credentials>`), API Key in header (`<Header-Name>: <api_key>`), API Key in query parameter (`<param_name>=<api_key>`), and OAuth2 (mapped to `Authorization: Bearer <token>`).
- **FR-003**: In test generation prompts, the system MUST instruct the model on the operation's active security requirement so generated fixtures preserve credential headers and parameters.
- **FR-004**: If an operation does not require authentication (or explicitly declares `security: []`), the system MUST NOT add authentication headers or query parameters.
- **FR-005**: When multiple alternative security schemes are specified for an operation, the system MUST choose deterministically using the priority order: HTTP Bearer / OAuth2 > API Key (header) > API Key (query) > HTTP Basic.
- **FR-006**: When an operation declares compound security requirements (multiple schemes within a single requirement dictionary), the system MUST generate placeholders for all schemes in that requirement.
- **FR-007**: Postman exporter MUST parameterize credential placeholders into collection-level variables (e.g., `{{bearerToken}}`, `{{apiKey}}`) and declare them in the top-level collection `variable` array with default placeholder values.
- **FR-008**: REST Client (`.http`) exporter MUST parameterize credential placeholders into top-level file variables (e.g., `@bearerToken = <token>`) declared at the beginning of the file and referenced in request blocks via `{{variableName}}`.
- **FR-009**: The REST Client exporter MUST annotate requests having security requirements with a comment indicating the applied security scheme (e.g., `# Security: bearerAuth`). If alternatives existed, the comment MUST list the alternatives.
- **FR-010**: Exporters MUST avoid creating duplicate collection or file variable declarations when multiple requests utilize the same security scheme.
- **FR-011**: If security scheme component definitions are missing or unresolvable from specification chunks, the system MUST apply deterministic heuristics based on the scheme identifier name to derive the appropriate scheme type and location.
- **FR-012**: Artifact generation and export MUST remain 100% deterministic and execute zero LLM calls, adhering to SpecProbe Constitution Principle II.

---

### Key Entities

- **SecurityRequirement**: Represents an operation's security mandate as defined in OpenAPI (`list[dict[str, list[str]]]`), indicating one or more alternative security schemes and optional scopes.
- **SecuritySchemeDefinition**: Represents the schema and transport location of an authentication scheme (type: `http`, `apiKey`, `oauth2`; in: `header`, `query`, `cookie`; name: parameter or header name; scheme: `bearer`, `basic`).
- **AuthCredentialPlaceholder**: Standardized representation of a resolved credential placeholder for a test case (transport: `header` or `query`; key: header/parameter name; variable_name: identifier for exporter parameterization; default_value: placeholder string such as `<token>` or `<api_key>`).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of generated test cases for operations declaring security requirements contain the appropriate authentication header or query parameter placeholder.
- **SC-002**: 100% of exported Postman collections parameterize security credentials into collection-level variables, requiring zero manual edits across individual request headers to configure an active token.
- **SC-003**: 100% of exported REST Client (`.http`) files declare required security variables at the top of the file, allowing full credential configuration in a single location.
- **SC-004**: Zero operations with explicit empty security (`security: []`) receive authentication headers or query parameters in generated tests or exported artifacts.
- **SC-005**: All exported artifacts produce byte-identical output across repeated exporter runs given identical input test cases, preserving strict determinism.

---

## Assumptions

- **Placeholder Value Uniformity**: Standard placeholder tokens (`<token>`, `<api_key>`, `<credentials>`) are sufficient for test generation fixtures; automated retrieval of live tokens or OAuth2 token exchange flows is out of scope.
- **Cookie-Based Security Schemes**: API keys in cookies are rare in REST API test automation and can be treated as custom headers (`Cookie: <name>=<value>`) or deferred if not encountered in common specs.
- **Single Active Profile**: Each exported collection or `.http` document assumes a single active credential set per security scheme, representing standard development/testing environment behavior.
- **Negative Auth Scenarios Deferred**: Generating test cases specifically asserting 401/403 responses upon invalid or absent credentials is out of scope for this feature and planned for Feature 007.
