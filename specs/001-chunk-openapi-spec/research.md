# Phase 0 Research: OpenAPI Operation Chunking

## Problem Statement & Context
The `specprobe chunk` command needs to take an OpenAPI 3.0 or 3.1 specification (YAML or JSON) and emit one self-contained chunk per operation formatted as newline-delimited JSON (JSONL). Each chunk must isolate the operation, inherit path-level parameters, resolve security schemes, and include a pruned dictionary of `components.schemas` containing only the schemas actually referenced by that operation. The command must handle circular references, schema compositions (`allOf`/`oneOf`/`anyOf`), external file references (as non-fatal warnings), and reject legacy Swagger 2.0 documents.

---

## Key Technical Decisions

### 1. OpenAPI Parser & Spec Loader: `prance` + `openapi-spec-validator`
- **Decision**: Use `prance.BaseParser` with `openapi-spec-validator` backend.
- **Rationale**:
  - `prance` is the standard Python tool for loading, reading, and parsing OpenAPI specs in both YAML and JSON format.
  - `prance.BaseParser` parses the document and performs schema validation without unconditionally inlining all references. This is critical because blind inlining fails on circular references.
  - Combined with `openapi-spec-validator`, `prance` detects and validates OpenAPI 3.0.x and 3.1.x specifications, and detects Swagger 2.0 (`"swagger": "2.0"`) to allow early rejection with clear messaging.
- **Alternatives Considered**:
  - `openapi-core`: Primarily focused on web framework HTTP request/response validation (Flask/Django/FastAPI), less direct for document manipulation and component tree pruning.
  - Hand-rolled YAML/JSON loader: Violates explicit user directive and requires extensive edge-case parsing logic for YAML anchors, tags, and JSON pointers.

### 2. Schema Pruning & Cycle Detection: Visited-Set Pointer Traversal
- **Decision**: Implement a deterministic schema visitor (`SchemaPruner`) that starts at the operation's fields (parameters, request body, responses, callbacks, headers) and transitively collects referenced component schemas into the chunk's `components.schemas` dictionary, using a `visited: set[str]` guard.
- **Rationale**:
  - In OpenAPI, circular references occur when schema `A` references schema `B`, which references `A` (or self-reference `Node` -> `Node`).
  - By retaining the standard internal `$ref` pointer (e.g. `#/components/schemas/Node`) in the schema definition and adding the component name (`Node`) to `visited`, recursion terminates when the pointer is encountered again.
  - The resulting chunk remains valid, parsable OpenAPI, and does not cause `RecursionError`.
  - Transitive exploration naturally traverses `allOf`, `oneOf`, `anyOf`, and `not` composite arrays.
- **Alternatives Considered**:
  - Full inlining: Fails on circular schemas (infinite expansion).
  - Synthetic stub objects: Breaks downstream schema validation and loss of type fidelity.

### 3. Path-Level Parameter Inheritance & Merging
- **Decision**: Path items can define `parameters` that apply to all child operations. When extracting an operation, merge path-level parameters into operation-level parameters. If a parameter exists at both levels with identical `name` and `in` (e.g. `name="X-Request-ID"`, `in="header"`), the operation-level parameter takes precedence.
- **Rationale**: Direct compliance with OpenAPI 3.0/3.1 specifications (Section 4.7.8 Path Item Object). Guarantees the operation chunk is fully autonomous and self-contained.

### 4. Operation ID Synthesis
- **Decision**: When an operation lacks `operationId`, synthesize an ID using `{method}_{normalized_path}` (e.g., `get_api_v1_users_id`). If collisions occur across operations, append a deterministic incrementing suffix (`_1`, `_2`).
- **Rationale**: Guarantees deterministic, predictable, and URI-safe identifiers for downstream spot-checking (`--op <operationId>`) and test case association per Constitution Principle V.

### 5. Security Scheme Inheritance
- **Decision**:
  - If operation defines `security`, use operation-level security.
  - If operation defines `security: []`, treat as explicitly public / disabled.
  - If operation omits `security`, inherit top-level global `security` from spec root.
- **Rationale**: Follows OpenAPI 3.x specification inheritance rules.

### 6. External File Reference Guardrail
- **Decision**: When an external file reference (e.g., `$ref: "models.yaml#/components/schemas/User"` or URL) is found during traversal, record an unsupported warning, retain the raw `$ref` string in the output, write a warning to `stderr`, and exit with code 0.
- **Rationale**: Fulfills clarified decision. Preserves reference traceability without corrupting the chunk or breaking CI pipelines unexpectedly.

### 7. Token Counting & Budget Alerts
- **Decision**: Deterministic character-based heuristic: `max(1, round(len(serialized_json) / 4))`.
- **Rationale**: Rapid, dependency-free, zero-network, and conforms to clarified user specification. If `estimated_tokens > max_tokens`, emit an advisory warning in chunk metadata and stderr.

### 8. CLI & Exclusive Modes
- **Decision**:
  - Standard execution: Stream newline-delimited JSON (JSONL) chunks to `stdout`.
  - `--op <operationId>`: Output single formatted JSON chunk to `stdout`.
  - `--stats`: Exclusive mode; output human-readable distribution table to `stdout` with operations count, token min/max/median/average, and warning list.
  - Non-fatal warnings output to `stderr` (and captured in chunk metadata / stats).

### 9. Test Fixtures Strategy
- **Small Test Fixtures**:
  - `tests/fixtures/valid_openapi_30.yaml`: Baseline 3.0 spec with varied HTTP methods.
  - `tests/fixtures/composition_31.json`: OpenAPI 3.1 spec testing `allOf`, `oneOf`, `anyOf`, and path parameter overriding.
  - `tests/fixtures/circular_spec.yaml`: Self-referencing (`Node` -> `Node`) and mutually circular (`User` -> `Team` -> `User`) schemas.
  - `tests/fixtures/swagger_20.json`: Swagger 2.0 document to assert rejection.
  - `tests/fixtures/external_ref_spec.yaml`: Document with external `$ref` links to assert non-fatal warnings.
- **Scale Test Fixture**:
  - `tests/fixtures/large_public_spec.json`: A large public OpenAPI specification (e.g., Stripe or GitHub REST API) containing hundreds of operations to verify streaming performance (< 2s) and memory efficiency.
