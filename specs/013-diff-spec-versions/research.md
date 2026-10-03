# Research & Technical Decisions: `specprobe diff`

**Feature Branch**: `013-diff-spec-versions`
**Date**: 2026-10-03
**Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/specs/013-diff-spec-versions/spec.md)

---

## 1. OpenAPI Normalization & Chunker Reuse

### Decision
Reuse `load_openapi_spec` from `src/specprobe/chunker/loader.py` and `OperationExtractor` from `src/specprobe/chunker/extractor.py` to ingest and normalize both specifications into per-operation dictionaries and `OperationChunk` instances. Set `schema_depth=None` during chunk extraction for diffing to prevent premature schema truncation, ensuring that deep nested schemas are preserved for comparison.

### Rationale
- Reusing `load_openapi_spec` immediately provides robust file reading, YAML/JSON parsing, stdin handling, Swagger 2.0 rejection, and OpenAPI 3.0/3.1 validation without duplicate logic.
- `OperationExtractor` already resolves path-level parameters into operation-level parameters, prunes unreferenced component schemas, and synthesizes metadata.
- Setting `schema_depth=None` allows full recursive traversal of nested schemas during diff analysis while retaining cycle guards.

### Alternatives Considered
- *Writing a custom OpenAPI diff parser from scratch*: Rejected. Violates Constitution Principle I (avoiding speculative reimplementation and duplicate parsing logic).
- *Third-party libraries (e.g. `openapi-diff` or `deepdiff`)*: Rejected. Adding heavy external dependencies or CLI tools introduces binary bloat and packaging complexity. `specprobe` already contains the necessary parsing primitives.

---

## 2. Operation Keying and Matching Strategy

### Decision
Key operations by the compound key `(method.upper(), normalized_path)`.
- `method`: Normalized to uppercase (e.g., `GET`, `POST`).
- `normalized_path`: Structural path template matching. Parameter placeholders within path segments are normalized to positional wildcards (e.g. converting `{petId}`, `{id}`, and `{item_id}` to `{}`).
- When matching, `operationId` is completely ignored. If an operation has the same HTTP method and structural path template in both specifications, it is considered the same endpoint regardless of `operationId` changes, tag updates, or path parameter token renames.

### Rationale
- Endpoint URIs and HTTP methods define the HTTP transport contract for API consumers. Changing an `operationId` is an internal code-generation artifact that does not break network-level HTTP clients.
- Normalizing path parameter tokens (e.g. `/pets/{petId}` -> `/pets/{}` and `/pets/{id}` -> `/pets/{}`) prevents false positive operation removals and additions when an author renames a parameter variable, allowing parameter schemas to be compared directly.

### Alternatives Considered
- *Exact literal path template string matching*: Rejected during clarification session (2026-10-03). Exact matching would treat `/pets/{petId}` and `/pets/{id}` as two separate endpoints, falsely reporting an operation removal and an operation addition rather than checking parameter schema evolution.
- *Keying by `operationId`*: Rejected. `operationId` is optional in OpenAPI and can be refactored without altering the network contract.

---

## 3. Scope of Breaking Schema & Response Change Detection (v1)

### Decision
Strictly limit v1 detection to five mechanical, rule-based breaking changes across shared operations:

1. **`required_request_property_added`**:
   - A request body schema gains a new property listed in its `required` array.
   - An existing request body property changes from optional to required.
   - An operation parameter gains `required: true` (or a new parameter with `required: true` is introduced).
   - A parameter's object schema gains a new required property.
2. **`response_property_removed`**:
   - A response schema for an existing status code and media type (e.g. `200` `application/json`) loses a property previously declared in its `properties` map.
3. **`response_status_removed`**:
   - An existing 2xx success response status code (e.g. `200`, `201`, `204`) is removed from an operation.
   - Non-2xx status code removals (4xx, 5xx) are excluded and remain unreported per v1 non-breaking scope.
   - Status code swaps (e.g. 200 -> 201) are naturally detected as the removal of 200.
4. **`type_changed`**:
   - An existing property in a request body, parameter, or response schema has its declared `type` changed (e.g., `string` -> `integer`, `integer` -> `number`, `boolean` -> `string`, `object` -> `array`).
   - Narrowing of multi-type declarations in OpenAPI 3.1 (e.g., `["string", "null"]` -> `["string"]`) is also classified as a breaking type change.
5. **`enum_value_removed`**:
   - An existing `enum` list in a parameter, request body, or response schema has one or more previously allowed values removed.

### Rationale
- These five categories represent mathematically objective, mechanical breaking changes.
- Eliminates subjective heuristics or probabilistic LLM inference (adhering strictly to Constitution Principle II).
- Removing a 2xx success response breaks client branches and deserialization, whereas removing 4xx/5xx error responses breaks nothing because clients that handle them will simply not encounter them.
- Non-breaking changes (adding optional request fields, adding new response fields, adding enum values, updating descriptions, removing 4xx/5xx responses) are explicitly ignored in v1.

### Alternatives Considered
- *Reporting non-2xx status code removals as breaking*: Rejected during clarification session (2026-10-03). Clients handling documented 4xx/5xx errors do not break if the server stops emitting them.
- *Mislabling status code removal as `response_property_removed`*: Rejected. A status code is not an object property; distinct categorization (`response_status_removed`) provides clean filtering.

---

## 4. `$ref` Dereferencing & Schema Traversal

### Decision
Implement a lightweight, non-mutating schema resolver helper that resolves `$ref` pointers (e.g. `#/components/schemas/Pet`) using the specification's components map. Recursively traverse object `properties` and array `items` with a recursion set to prevent infinite loops in cyclic schemas.

### Rationale
- OpenAPI schemas frequently use `$ref` to reference reusable models in `components.schemas`.
- Resolving `$ref` targets before comparison ensures that changes inside referenced models are detected just as accurately as changes in inline schemas.
- Cycle detection prevents recursion crashes on self-referential models (e.g. linked lists or tree hierarchies).

---

## 5. Output Streams, Formatting, and Exit Codes

### Decision
- **Standard Output (`stdout`)**: Exclusively line-delimited JSON (`JSONL`). Each line is a self-contained JSON object conforming to `DiffChangeRecord`.
- **Standard Error (`stderr`)**: Reserved for diagnostics and the human-readable summary table rendered via `rich.table.Table` when `--summary` is passed.
- **Exit Codes**:
  - `0`: Success, no breaking changes detected (even if non-breaking operation additions are present).
  - `1`: Success, but one or more breaking changes (`breaking: true`) were detected.
  - `2`: Error during execution (file not found, invalid syntax, unsupported specification version).

### Rationale
- Keeping `stdout` clean for JSONL ensures pipeline composability (`specprobe diff old.yaml new.yaml | jq .`).
- Rendering `--summary` to `stderr` matches `specprobe audit --summary` and `specprobe chunk --stats`.
- Exit codes `0`, `1`, `2` follow standard POSIX diff and linter conventions (like `diff`, `grep`, `git diff --check`).
