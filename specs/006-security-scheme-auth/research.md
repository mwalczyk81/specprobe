# Phase 0 Research: Security-Scheme-Aware Authentication

**Feature**: `006-security-scheme-auth`  
**Date**: 2026-09-20  
**Status**: Completed  

---

## Technical Decisions & Rationale

### 1. Security Scheme Definitions Extraction & Chunk Self-Containment

- **Context**: In OpenAPI 3.0/3.1, operations declare requirements via `security: list[dict[str, list[str]]]`, which point to scheme definitions under `components.securitySchemes`. `specprobe chunk` extracts `metadata.security` for each operation, but previously `OperationChunk.components` only contained `schemas`. Without security scheme definitions (specifying `type`, `in`, `name`, `scheme`), downstream commands (`specprobe generate` and `specprobe export`) cannot know the header name or parameter location unless they guess via heuristics.
- **Decision**: Update `OperationExtractor` in `src/specprobe/chunker/extractor.py` to inspect `spec.get("components", {}).get("securitySchemes", {})`. For each extracted operation, prune and include the security scheme definitions matching any scheme referenced in that operation's resolved `security` requirements (or global fallback). Store this dictionary under `OperationChunk.components["securitySchemes"]`.
- **Rationale**: Keeps `OperationChunk` completely self-contained and autonomous. Downstream consumers (`generate`, `export`, `audit`) can inspect the exact scheme type (`http`, `apiKey`, `oauth2`), transport location (`header`, `query`), and parameter name (e.g. `X-API-Key`) without needing access to the original source OpenAPI file.
- **Alternatives Considered**:
  - *Storing scheme definitions in `ChunkMetadata`*: Rejected. Metadata is intended for flat, indexable attributes (operationId, tags, method, path, tokens); `components` is the designated container for OpenAPI schema and component dictionaries.
  - *Re-reading the source OpenAPI specification in `specprobe export`*: Rejected. Violates the decoupled, Unix-pipe CLI design (`chunk | search --full | generate | export`) where downstream commands operate strictly on JSON/JSONL streams from stdin or cache.

---

### 2. Traceable Security Representation in `GeneratedTestCase`

- **Context**: `GeneratedTestCase` is serialized to JSONL by `specprobe generate` and ingested by `specprobe export`. `RequestFixture` contains concrete values (`headers`, `query_params`, `path_params`). If `specprobe export` only receives `RequestFixture.headers = {"Authorization": "Bearer <token>"}`, it cannot deterministically discern the exact OpenAPI security scheme name (e.g., `jwtAuth` vs `bearerAuth`), nor can it identify associated OAuth2 scopes or alternative schemes.
- **Decision**: Add two optional, backward-compatible fields to `GeneratedTestCase` in `src/specprobe/generator/models.py`:
  ```python
  security: list[dict[str, list[str]]] = Field(
      default_factory=list,
      description="Resolved security requirements inherited from the target operation chunk.",
  )
  security_schemes: dict[str, Any] = Field(
      default_factory=dict,
      description="Resolved security scheme definitions inherited from the operation chunk components.",
  )
  ```
  In `GenerationEngine._validate_completion()`, copy `chunk.metadata.security` and `chunk.components.get("securitySchemes", {})` into the generated test case.
- **Rationale**: 
  - Preserves 100% backward compatibility with existing test case JSONL records (defaults to empty list/dict).
  - Gives `specprobe export` direct access to scheme definitions, requirement objects, and scope arrays without relying on fragile reverse-engineering or heuristic guesswork.
  - Keeps `RequestFixture` clean and focused on HTTP request attributes.
- **Alternatives Considered**:
  - *Embedding Postman variable syntax `{{apiKeyAuth}}` directly into `RequestFixture.headers` during generation*: Rejected. Fixtures should be valid, realistic HTTP representations. Injecting export-specific variable syntax into test cases breaks consumers that execute requests directly (e.g., test runners, mock engines) and violates separation of concerns between test generation and test artifact export.
  - *Regex matching on header keys only*: Rejected. Cannot distinguish between different schemes that share header conventions (e.g. multiple custom headers or Bearer vs OAuth2) and cannot recover OAuth2 scopes.

---

### 3. Deterministic Multi-Scheme Selection & Priority Ordering

- **Context**: OpenAPI operations may specify multiple alternative security requirements (e.g., `[{"bearerAuth": []}, {"apiKeyAuth": []}]`), or compound requirements requiring multiple credentials simultaneously (e.g., `[{"apiKey": [], "appId": []}]`).
- **Decision**: Implement a deterministic resolver in `src/specprobe/exporter/security.py` adhering to `FR-005`:
  1. Priority order for alternative requirements:
     1. `http` (scheme: `bearer`) or `oauth2`
     2. `apiKey` (`in: header`)
     3. `apiKey` (`in: query`)
     4. `http` (scheme: `basic`)
  2. For compound requirements (multiple schemes in a single requirement dictionary), resolve and include credentials for *all* schemes in that dictionary (`FR-006`).
  3. If an alternative requirement contains an empty object `{}` alongside a named scheme, the named scheme is selected for happy-path generation, and the exported request is annotated with `(optional)` (`FR-013`).
- **Rationale**: Guarantees byte-identical, deterministic output across runs (Constitution Principle II) and prioritizes modern token-based auth while retaining full support for API keys and Basic auth.
- **Alternatives Considered**:
  - *Lexicographical sorting by scheme name*: Rejected. Could arbitrarily prioritize legacy Basic auth over OAuth2 or Bearer auth.
  - *LLM-driven selection*: Rejected. Strictly prohibited by Constitution Principle II (zero-LLM, fully deterministic export).

---

### 4. Postman Collection Parameterization (`{{<sanitizedSchemeName>}}`)

- **Context**: Postman Collection v2.1.0 supports collection-level variables defined in the root `variable` array and referenced in request headers and query parameters as `{{variableName}}`.
- **Decision**:
  - Scheme names are sanitized to valid alphanumeric and underscore characters (e.g. `user-api-key` -> `user_api_key`).
  - The root collection `variable` array declares each unique sanitized scheme name with its standard placeholder value:
    - Bearer / OAuth2: `<token>`
    - Basic: `<credentials>`
    - API Key: `<api_key>`
  - Request headers/query parameters reference `{{<sanitizedSchemeName>}}`:
    - Bearer / OAuth2: `Authorization: Bearer {{<sanitizedSchemeName>}}`
    - Basic: `Authorization: Basic {{<sanitizedSchemeName>}}`
    - API Key in header: `<Header-Name>: {{<sanitizedSchemeName>}}`
    - API Key in query: `<param_name>={{<sanitizedSchemeName>}}` (in both `url.raw` and `url.query`)
  - Request `description` is annotated with security metadata:
    `Security: <schemeName>` (with `(optional)` if optional, `(alternatives: <alts>)` if alternatives exist, and `(scopes: <scopes>)` if OAuth2 scopes exist).
- **Rationale**: Fulfills `FR-007`, `FR-010`, `FR-014`, and User Story 2. Eliminates repetitive manual token editing across dozens of requests while preserving full specification traceability.
- **Alternatives Considered**:
  - *Exporting a separate Postman Environment JSON*: Rejected. Requires managing multiple files and extra import steps in Postman. Collection-level variables are fully self-contained.

---

### 5. VS Code REST Client (`.http`) Parameterization (`@<sanitizedSchemeName> = ...`)

- **Context**: VS Code REST Client supports file variables declared at the top of the file as `@variableName = value` and referenced as `{{variableName}}`.
- **Decision**:
  - Top-level variables are declared immediately after `@baseUrl = ...`, sorted alphabetically by variable name for determinism:
    ```http
    @baseUrl = http://localhost:8000
    @apiKeyAuth = <api_key>
    @bearerAuth = <token>
    ```
  - Request blocks reference `{{<sanitizedSchemeName>}}`.
  - Request metadata comments are added above the request line:
    ```http
    # @name get_pet
    # Operation: get_pet
    # Description: Fetch a pet by ID
    # Expected Status: 200
    # Security: bearerAuth (optional)
    # Alternatives: apiKeyAuth
    # Scopes: read:pets, write:pets
    # Expected Schema: type: object, properties: id, name
    GET {{baseUrl}}/pets/1 HTTP/1.1
    Authorization: Bearer {{bearerAuth}}
    ```
- **Rationale**: Fulfills `FR-008`, `FR-009`, `FR-010`, `FR-013`, `FR-014`, and User Story 3. Developers can paste an active token once at the top of the file and immediately execute all requests in their IDE.
- **Alternatives Considered**:
  - *Using settings.json environment files*: Rejected. Requires external editor workspace configuration; file-level variables work immediately on any machine.

---

### 6. Fallback Heuristics for Missing Scheme Definitions (`FR-011`)

- **Context**: If an operation specifies a security scheme name that is missing from `components.securitySchemes` (or from older indexed chunks), the system must degrade gracefully rather than crash or omit authentication.
- **Decision**: Implement deterministic substring heuristics in the resolver:
  - If `"bearer"` or `"jwt"` in `scheme_id.lower()` -> HTTP Bearer, header `Authorization: Bearer <token>`, placeholder `<token>`
  - If `"basic"` in `scheme_id.lower()` -> HTTP Basic, header `Authorization: Basic <credentials>`, placeholder `<credentials>`
  - If `"key"` or `"token"` or `"auth"` or `"api"` in `scheme_id.lower()` -> API Key in header, header name defaults to scheme identifier, placeholder `<api_key>`
  - Default fallback -> API Key in header with header name equal to scheme identifier.
- **Rationale**: Satisfies `FR-011` deterministically without failing the pipeline.
- **Alternatives Considered**:
  - *Failing with an error*: Rejected. Real-world OpenAPI specs frequently contain minor inconsistencies or missing component definitions; robust tooling should degrade gracefully.

---

## Best Practices & Patterns

1. **Shared Resolver Utility**: Create a single helper module `src/specprobe/exporter/security.py` that encapsulates all security scheme parsing, sanitization, priority resolution, and placeholder formatting. Both `postman.py` and `http_client.py` will import and share this module, eliminating code duplication per Constitution Principle I.
2. **Byte-Identical Golden Fixtures**: Update and add golden file test fixtures in `tests/fixtures/golden/` covering Bearer, Basic, API Key (header), API Key (query), OAuth2 with scopes, optional security, and multiple alternative schemes.
3. **Type Safety & Linting**: All new and modified code will pass `ty check src/` and `pre-commit run --all-files`.
